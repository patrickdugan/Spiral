"""Loopback RPC adapter for CLN in WSL and Bitcoin Core on Windows.

Uses WSL executable interop, never a shell or a public Core listener. The trusted
private config selects bitcoin-cli and its datadir; clients cannot select wallets
or supply CLI options. Broadcast is disabled until explicitly enabled locally.
This is transport instrumentation, not an accounting or policy enforcement layer.
"""
import argparse
import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess

READS = {'getblockchaininfo', 'getnetworkinfo', 'getblockcount', 'getblockhash',
         'getblock', 'getblockheader', 'getrawtransaction', 'gettxout',
         'estimatesmartfee', 'getmempoolinfo', 'getrawmempool', 'getmempoolentry',
         'getchaintips', 'getdeploymentinfo', 'echo', 'echojson'}


def dispatch(config, request, run=subprocess.run):
    """Return a JSON response string, preserving Core's decimal result tokens."""
    request_id = request.get('id') if isinstance(request, dict) else None
    def error(code, message):
        return json.dumps({'result': None, 'error': {'code': code, 'message': message}, 'id': request_id})
    if not isinstance(request, dict) or not isinstance(request_id, (str, int, type(None))):
        return error(-32600, 'invalid request')
    method, params = request.get('method'), request.get('params', [])
    allowed = READS | ({'sendrawtransaction'} if config.get('allow_broadcast') is True else set())
    if not isinstance(method, str) or method not in allowed:
        return error(-32601, 'method disabled by local bridge')
    if not isinstance(params, list) or len(params) > 8:
        return error(-32602, 'positional parameters required')
    # bitcoin-cli options are parsed separately from RPC parameters. Refuse option
    # injection as well as control characters (no allowlisted method needs these).
    if any(isinstance(p, str) and (p.startswith('-') or any(ord(c) < 32 for c in p)) for p in params):
        return error(-32602, 'unsafe CLI parameter')
    argv = [config['cli'], '-datadir=' + config['datadir'], '-testnet4', method]
    argv += [p if isinstance(p, str) else json.dumps(p, separators=(',', ':'), allow_nan=False) for p in params]
    try:
        result = run(argv, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        # A timed-out broadcast is uncertain: never resubmit automatically here.
        return error(-32000, 'local CLI unavailable or timed out; broadcast outcome may be uncertain')
    if result.returncode:
        code = re.search(r'error code:\s*(-?\d+)', result.stderr)
        return error(int(code.group(1)) if code else -32000, 'Core RPC failed (private details withheld)')
    raw = result.stdout.strip()
    if method in {'getblockhash', 'getblock', 'getblockheader', 'getrawtransaction', 'sendrawtransaction'} and re.fullmatch(r'[0-9a-f]+', raw):
        raw = json.dumps(raw)
    try:
        json.loads(raw)
    except ValueError:
        raw = json.dumps(raw)  # CLI prints scalar hashes and hex without quotes.
    return '{"result":' + raw + ',"error":null,"id":' + json.dumps(request_id) + '}'


def handler(config):
    auth = 'Basic ' + base64.b64encode((config['user'] + ':' + config['password']).encode()).decode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not log authentication, raw transactions or private paths.

        def do_POST(self):
            if self.path != '/' or not hmac.compare_digest(self.headers.get('Authorization', ''), auth):
                self.send_error(401); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1_000_000:
                    self.send_error(413); return
                request = json.loads(self.rfile.read(length))
                response = dispatch(config, request).encode()
            except (ValueError, TypeError):
                self.send_error(400); return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if len(config['password']) < 32:
        raise ValueError('private bridge authentication must contain at least 32 characters')
    server = ThreadingHTTPServer(('127.0.0.1', config['port']), handler(config))
    server.serve_forever()


if __name__ == '__main__':
    main()
