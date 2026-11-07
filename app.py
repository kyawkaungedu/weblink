"""Vercel-only, stateless adapter; server.py remains the Docker entrypoint."""
import concurrent.futures
import os
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault('LINK_JOBS_DIR', '/tmp/link-lab-jobs')
from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
import extractor

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 65536

@app.after_request
def secure(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.path.startswith('/api/') or request.path in ('/ui', '/client.js'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.before_request
def origin_check():
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error='Cross-origin request blocked'), 403

@app.errorhandler(Exception)
def error(err):
    if isinstance(err, HTTPException):
        return jsonify(error=err.description), err.code
    if isinstance(err, (ValueError, TypeError, KeyError)):
        return jsonify(error=str(err)[:300]), 400
    # Do not print request bodies or destination URL tokens into logs.
    return jsonify(error='Upstream request မအောင်မြင်ပါ။ ခဏစောင့်ပြီး ပြန်စမ်းပါ။'), 502

@app.get('/health')
def health():
    return jsonify(ok=True, runtime='vercel-stateless', batchSize=4)

@app.get('/')
@app.get('/ui')
def index():
    page = (PUBLIC / 'index.html').read_text(encoding='utf-8')
    # Works for either relative or absolute references to app.js.
    page = page.replace('src="/app.js"', 'src="/client.js"').replace('src="app.js"', 'src="/client.js"')
    return Response(page, mimetype='text/html')

@app.get('/client.js')
def client():
    original = (PUBLIC / 'app.js').read_text(encoding='utf-8')
    bridge = (ROOT / 'vercel-bridge.js').read_text(encoding='utf-8')
    return Response(original + '\n;\n' + bridge, mimetype='text/javascript')

@app.post('/api/collect')
def collect():
    data = request.get_json()
    if not isinstance(data, dict) or not isinstance(data.get('url'), str) or len(data['url']) > 12000:
        raise ValueError('Invalid URL')
    url = data['url'].strip()
    extractor.validate(url)
    title, rows = extractor.collect(url)
    return jsonify(title=title, source=url, rows=rows, total=len(rows))

@app.post('/api/resolve')
def resolve():
    data = request.get_json()
    rows = data.get('rows') if isinstance(data, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4:
        raise ValueError('A batch must contain 1–4 links')
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid row')
        item = {}
        for key in ('source', 'episode', 'server', 'size', 'resolution'):
            value = row.get(key, '')
            if not isinstance(value, str) or len(value) > (12000 if key == 'source' else 500):
                raise ValueError('Invalid row field')
            item[key] = value
        parsed = urlsplit(item['source'])
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid source URL')
        if parsed.hostname in ('adsfly.org', 'www.adsfly.org'):
            extractor.validate(item['source'])
        cleaned.append(item)
    # All workers finish before this request returns: no background jobs or
    # persistent filesystem/in-memory state is required across invocations.
    # Use resolve_once to avoid a second 44s attempt within a 60s invocation.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(extractor.resolve_once, cleaned))
    return jsonify(rows=result)

@app.get('/<path:name>')
def static_file(name):
    return send_from_directory(PUBLIC, name)
