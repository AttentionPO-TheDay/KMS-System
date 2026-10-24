"""Internal, authenticated fixed-model evaluator. No DB or business keys."""
import hmac
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evaluate import CASES

LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        token = os.environ.get('INTERNAL_TOKEN', '')
        if not token or not hmac.compare_digest(self.headers.get('X-Internal-Token', ''), token):
            return self.reply(403, {'error': 'Forbidden'})
        if self.path != '/evaluate':
            return self.reply(404, {'error': 'Unknown path'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 256 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {'caseId'} or payload['caseId'] not in CASES:
                raise ValueError()
        except (TypeError, ValueError):
            return self.reply(400, {'error': 'Only fixed caseId is accepted'})
        if not LOCK.acquire(blocking=False):
            return self.reply(429, {'error': 'Evaluation running'})
        try:
            output = subprocess.check_output(
                [sys.executable, os.path.join(os.path.dirname(__file__), 'evaluate.py'), '--case-id', payload['caseId']],
                timeout=100, stderr=subprocess.DEVNULL)
            self.reply(200, json.loads(output))
        except Exception:
            self.reply(503, {'error': 'Evaluation failed; no complete evidence'})
        finally:
            LOCK.release()

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    if len(os.environ.get('INTERNAL_TOKEN', '')) < 16:
        raise SystemExit('INTERNAL_TOKEN must have at least 16 characters')
    ThreadingHTTPServer(('0.0.0.0', 8800), Handler).serve_forever()
