import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import extractor

PUBLIC = Path(__file__).parent / 'public'
jobs = {}
lock = threading.Lock()
slots = threading.BoundedSemaphore(2)
rate = {}

def run(job, url):
    try:
        extractor.work(job, url)
    finally:
        slots.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log submitted URLs or job access tokens.

    def send(self, code, data, kind='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.send(200, {'ok': True})
        if path.startswith('/api/jobs/'):
            job = path.rsplit('/', 1)[-1]
            with lock:
                valid = job in jobs and time.time() - jobs[job] < 7200
            if not valid:
                return self.send(404, {'error': 'Job expired. Link ပြန်ထည့်ပေးပါ။'})
            try:
                return self.send(200, json.loads(extractor.job_path(job).read_text()))
            except FileNotFoundError:
                return self.send(404, {'error': 'Job မတွေ့ပါ။'})
        files = {'/theme.js': ('theme.js', 'text/javascript; charset=utf-8'), '/themes.css': ('themes.css', 'text/css; charset=utf-8'), '/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/comic.css': ('comic.css', 'text/css; charset=utf-8')}
        files.update({
            '/readability.css': ('readability.css', 'text/css; charset=utf-8'),
            '/artwork.css': ('artwork.css', 'text/css; charset=utf-8'),
            '/assets/link-lab-art.webp': ('assets/link-lab-art.webp', 'image/webp'),
        })
        if path not in files:
            return self.send(404, {'error': 'Not found'})
        filename, kind = files[path]
        return self.send(200, (PUBLIC / filename).read_bytes(), kind)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send(403, {'error': 'Cross-origin request blocked'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 12000:
                return self.send(400, {'error': 'Invalid request size'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                return self.send(400, {'error': 'JSON object required'})
            path = urlsplit(self.path).path
            if path == '/api/start':
                url = str(data.get('url', '')).strip()
                extractor.validate(url)
                ip = self.client_address[0]
                with lock:
                    now = time.time()
                    for old, stamp in list(jobs.items()):
                        if now - stamp > 7200:
                            jobs.pop(old, None)
                            for suffix in ('.json', '.cancel'):
                                (extractor.JOBS / (old + suffix)).unlink(missing_ok=True)
                    if now - rate.get(ip, 0) < 5:
                        return self.send(429, {'error': 'ခဏစောင့်ပြီး ပြန်စမ်းပါ။'})
                    if not slots.acquire(blocking=False):
                        return self.send(429, {'error': 'Server အလုပ်များနေပါတယ်။ ခဏနေရင် ပြန်စမ်းပါ။'})
                    job = uuid.uuid4().hex
                    jobs[job] = now
                    rate[ip] = now
                try:
                    extractor.save(job, {'job': job, 'source': url, 'status': 'queued', 'title': '', 'total': 0, 'done': 0, 'rows': []})
                    threading.Thread(target=run, args=(job, url), daemon=True).start()
                except Exception:
                    with lock:
                        jobs.pop(job, None)
                    slots.release()
                    return self.send(500, {'error': 'အလုပ်စတင်မရပါ။ ခဏနေရင် ပြန်စမ်းပါ။'})
                return self.send(200, {'job': job})
            if path == '/api/cancel':
                job = str(data.get('job', ''))
                with lock:
                    valid = job in jobs
                if not valid:
                    return self.send(404, {'error': 'Job မတွေ့ပါ။'})
                extractor.job_path(job).with_suffix('.cancel').write_text('cancel')
                return self.send(200, {'cancelled': True})
            return self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, KeyError) as err:
            err_msg = str(err).strip() if str(err).strip() else 'Support လုပ်ထားသော website မှ HTTPS link အပြည့်အစုံ ထည့်ပေးပါ။'
            return self.send(400, {'error': err_msg})

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
