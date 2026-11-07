"""One-click HomieTV/YSFlix/RMCMM/AdsFly extractor. Standard-library-only backend."""
import concurrent.futures
import hashlib
import html
from html.parser import HTMLParser
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
JOBS = Path(os.environ.get('LINK_JOBS_DIR', str(ROOT / 'link-jobs')))
JOBS.mkdir(exist_ok=True)
ALLOWED = {'homietv.com', 'www.homietv.com', 'ysflix.com', 'www.ysflix.com', 'adsfly.org', 'www.adsfly.org', 'rmcmm.org', 'www.rmcmm.org'}

def validate(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in ALLOWED or p.username or p.password or p.port not in (None, 443):
        raise ValueError('HTTPS HomieTV / YSFlix / RMCMM / AdsFly link ပဲ ထည့်ပေးပါ။')
    return p

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def opener():
    return urllib.request.build_opener(SafeRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def fetch(client, url, extra=None, payload=None):
    validate(url)
    headers = {'User-Agent': 'Mozilla/5.0', **(extra or {})}
    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
    with client.open(req, timeout=22) as response:
        data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError('Response too large')
        return data.decode('utf-8', errors='replace')

def resolve_once(row):
    result = dict(row)
    try:
        url = row['source']
        p = urllib.parse.urlsplit(url)
        if p.hostname not in {'adsfly.org', 'www.adsfly.org'}:
            result.update(url=url, status='direct')
            return result
        validate(url)
        raw = next(v for k, _, v in (q.partition('=') for q in p.query.split('&')) if k == 'e')
        value = urllib.parse.unquote(raw).replace(' ', '+')
        url = urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode({'e': value})))
        client = opener()
        page = fetch(client, url)
        match = re.search(r'data-page=[\"\x27](.*?)[\"\x27](?:\s|>)', page, re.S)
        if not match:
            raise ValueError('AdsFly စာမျက်နှာပုံစံ ပြောင်းထားသည် သို့မဟုတ် access ပိတ်ထားသည်။')
        props = json.loads(html.unescape(match.group(1)))['props']
        csrf = re.search(r'name="csrf-token" content="([^"]+)"', page)
        if not csrf:
            raise ValueError('AdsFly session token မရပါ။')
        answer = json.loads(fetch(client, urllib.parse.urljoin(url, '/get-real-url'),
            {'Referer': url, 'Origin': f'{p.scheme}://{p.netloc}', 'Content-Type': 'application/json',
             'Accept': 'application/json', 'X-CSRF-TOKEN': csrf.group(1), 'X-Requested-With': 'XMLHttpRequest'},
            {'e': props['e'], 'access_token': props['access_token']}))
        dest = answer.get('url')
        if not isinstance(dest, str) or urllib.parse.urlsplit(dest).scheme not in ('https', 'http'):
            raise ValueError('မူရင်း URL မရပါ။ Link ပျက်နေနိုင်သည်။')
        result.update(url=dest, status='resolved')
        if not result.get('resolution'):
            m = re.search(r'(\d{3,4}p)', dest, re.I)
            result['resolution'] = m.group(1) if m else ''
    except Exception as err:
        result.update(status='failed', error=str(err)[:240], url='')
    return result

def resolve(row):
    result = resolve_once(row)
    if result.get('status') == 'failed' and any(s in result.get('error', '').lower() for s in ('temporary', 'timed out', 'timeout', 'http error 502', 'http error 503', 'http error 429')):
        time.sleep(1)
        return resolve_once(row)
    return result

class DownloadTableParser(HTMLParser):
    """Read only explicit download tables, never navigation or ad links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.anchor = None
        self.heading = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1' and not self.title.strip():
            self.heading = True
        if tag == 'table':
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = {'text': '', 'links': []}
        elif tag == 'a' and self.cell is not None:
            self.anchor = {'href': attrs.get('href', ''), 'text': ''}

    def handle_data(self, text):
        if self.heading:
            self.title += text
        if self.cell is not None:
            self.cell['text'] += text
        if self.anchor is not None:
            self.anchor['text'] += text

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.heading = False
        elif tag == 'a' and self.anchor is not None:
            if self.cell is not None:
                self.cell['links'].append(self.anchor)
            self.anchor = None
        elif tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.table is not None:
                self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None

def collect_rmc(url):
    if not re.fullmatch(r'/(tvshows|movies)/[A-Za-z0-9_-]+/?', validate(url).path):
        raise ValueError('RMCMM ရဲ့ /tvshows/... သို့မဟုတ် /movies/... ပို့စ် link ထည့်ပေးပါ။')
    parser = DownloadTableParser()
    parser.feed(fetch(opener(), url))
    rows = []
    seen = set()
    for table in parser.tables:
        if not table:
            continue
        headers = [c['text'].strip().lower() for c in table[0]]
        if 'quality' not in headers:
            continue
        # Series use Download; movie tables use Options with a Download anchor.
        link_header = next((h for h in ('download', 'options') if h in headers), None)
        if link_header is None:
            continue
        quality_idx, download_idx = headers.index('quality'), headers.index(link_header)
        server_idx = headers.index('server') if 'server' in headers else None
        size_idx = headers.index('size') if 'size' in headers else None
        episode_idx = headers.index('episode') if 'episode' in headers else None
        for cells in table[1:]:
            if len(cells) <= max(quality_idx, download_idx, episode_idx or 0):
                continue
            label = 'Episode ' + cells[episode_idx]['text'].strip() if episode_idx is not None else 'Movie'
            match = re.search(r'(\d{3,4})\s*p', cells[quality_idx]['text'], re.I)
            quality = match.group(1) + 'p' if match else ''
            for link in cells[download_idx]['links']:
                dest = urllib.parse.urljoin(url, link['href'].strip())
                parsed = urllib.parse.urlsplit(dest)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    continue
                key = (label, quality, dest)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({'episode': label, 'server': (cells[server_idx]['text'].strip() if server_idx is not None and server_idx < len(cells) else '') or link['text'].strip() or parsed.hostname,
                             'size': cells[size_idx]['text'].strip() if size_idx is not None and size_idx < len(cells) else '', 'resolution': quality, 'source': dest})
    if not rows:
        raise ValueError('RMCMM download table မတွေ့ပါ။ Website ပုံစံပြောင်းနေနိုင်သည်။')
    if len(rows) > 400:
        raise ValueError('ပို့စ်တစ်ခုလျှင် link ၄၀၀ အထိသာ ထုတ်နိုင်သည်။')
    return parser.title.strip() or 'RMCMM', rows

def collect(url):
    p = validate(url)
    if p.hostname in {'rmcmm.org', 'www.rmcmm.org'}:
        return collect_rmc(url)
    if p.hostname.endswith('adsfly.org'):
        return 'AdsFly link', [{'episode': 'Single link', 'server': 'Destination', 'size': '', 'resolution': '', 'source': url}]
    m = re.fullmatch(r'/(tv-show|movie)/([A-Za-z0-9_-]+)/?', p.path)
    if not m:
        raise ValueError('HomieTV / YSFlix ရဲ့ /tv-show/... သို့မဟုတ် /movie/... ပို့စ် link အပြည့်အစုံ ထည့်ပေးပါ။')
    kind, slug = m.groups()
    route = '/api/tv-shows/' if kind == 'tv-show' else '/api/movies/'
    # Keep each site's slug on its own API; the sites share a data format,
    # but availability and titles are not assumed to be interchangeable.
    origin = 'https://www.ysflix.com' if p.hostname in {'ysflix.com', 'www.ysflix.com'} else 'https://www.homietv.com'
    answer = json.loads(fetch(opener(), origin + route + slug))
    data = answer.get('data', answer)
    if not isinstance(data, dict) or not data.get('title'):
        raise ValueError('ပို့စ်အချက်အလက် မတွေ့ပါ။')
    rows = []
    def add(items, episode):
        for item in items or []:
            u = item.get('url', '')
            if isinstance(u, str) and urllib.parse.urlsplit(u).scheme in ('http', 'https'):
                rows.append({'episode': episode, 'server': str(item.get('server_name') or 'Link').strip(),
                    'size': str(item.get('size') or ''), 'resolution': str(item.get('resolution') or ''), 'source': u})
    for season in data.get('seasons') or []:
        for ep in season.get('episodes') or []:
            label = f"S{ep.get('season_number') or season.get('season_number') or 1} · Episode {ep.get('episode_number') or ep.get('name') or '?'}"
            add(ep.get('tvshow_download_links') or ep.get('download_links'), label)
    for key in ('movie_download_links', 'tv_show_download_links', 'download_links', 'downloads', 'zip_download_links'):
        add(data.get(key), 'Movie' if kind == 'movie' else 'Full season / Other')
    unique = {}
    for row in rows:
        unique.setdefault((row['episode'], row['source']), row)
    rows = list(unique.values())
    if not rows:
        raise ValueError('ဒီပို့စ်မှာ download link မတွေ့ပါ။')
    if len(rows) > 400:
        raise ValueError('Link ၄၀၀ ထက်များနေပါတယ်။ ဒီပို့စ်ကို thread ထဲ ပို့ပေးပါ။')
    return data['title'], rows

def job_path(job):
    if not re.fullmatch(r'[a-f0-9]{32}', job):
        raise ValueError('Invalid job ID')
    return JOBS / (job + '.json')

def save(job, state):
    path = job_path(job)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    os.replace(tmp, path)

def work(job, url):
    state = {'job': job, 'status': 'running', 'source': url, 'title': '', 'total': 0, 'done': 0, 'rows': [], 'started': time.time()}
    save(job, state)
    try:
        title, rows = collect(url)
        state.update(title=title, total=len(rows))
        save(job, state)
        results = [None] * len(rows)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(resolve, row): i for i, row in enumerate(rows)}
            for f in concurrent.futures.as_completed(futures):
                if (JOBS / (job + '.cancel')).exists():
                    state['status'] = 'cancelled'
                    for future in futures:
                        future.cancel()
                    break
                results[futures[f]] = f.result()
                state.update(done=state['done'] + 1, rows=[r for r in results if r is not None])
                save(job, state)
        if state['status'] != 'cancelled':
            state['status'] = 'complete'
        state['resolved'] = sum(bool(r.get('url')) for r in state['rows'])
    except Exception as err:
        state.update(status='error', error=str(err)[:400])
    state['finished'] = time.time()
    save(job, state)

def main():
    command = sys.argv[1]
    if command == 'start':
        url = sys.argv[2].strip()
        validate(url)
        job = uuid.uuid4().hex
        save(job, {'job': job, 'status': 'queued', 'title': '', 'total': 0, 'done': 0, 'rows': []})
        (JOBS / 'latest.txt').write_text(job)
        with (JOBS / (job + '.log')).open('w') as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'work', job, url],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        print(json.dumps({'job': job}))
    elif command == 'work':
        work(sys.argv[2], sys.argv[3])
    elif command == 'status':
        print(job_path(sys.argv[2]).read_text())
    elif command == 'latest':
        path = JOBS / 'latest.txt'
        print(job_path(path.read_text().strip()).read_text() if path.exists() else '{}')
    elif command == 'cancel':
        job_path(sys.argv[2])
        (JOBS / (sys.argv[2] + '.cancel')).write_text('cancel')
        print(json.dumps({'cancelled': True}))
    else:
        raise ValueError('Unknown command')

if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print(json.dumps({'error': str(err)}, ensure_ascii=False))
        sys.exit(1)
