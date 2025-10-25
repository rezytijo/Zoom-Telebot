"""Small helper to obtain a Zoom OAuth authorization code and exchange it for tokens.

Usage:
  python oauth_helper.py --port 8765 --save

What it does:
  - Reads Zoom client_id and client_secret from `config.settings` (ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET).
  - Starts a temporary local HTTP server and prints (and opens) the OAuth authorize URL.
  - Waits for the redirect with the authorization code, exchanges it for access_token + refresh_token,
    prints the tokens and (optionally) saves the refresh_token to a .env file.

Notes:
  - Make sure your Zoom OAuth app has the redirect URI http://localhost:<port>/callback registered.
  - This script is for development convenience only. Treat the printed tokens as secrets.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import threading
import time
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

import asyncio
import aiohttp

from config import settings

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "ZoomOAuthHelper/0.1"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get('code', [None])[0]
        state = qs.get('state', [None])[0]
        # store on server object for outer thread to read
        setattr(self.server, 'oauth_code', code)
        setattr(self.server, 'oauth_state', state)

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        if code:
            self.wfile.write(b"<html><body><h2>Authorization received</h2><p>You can close this window and return to the terminal.</p></body></html>")
        else:
            self.wfile.write(b"<html><body><h2>No code received</h2><p>Check the URL parameters and try again.</p></body></html>")

    def log_message(self, format, *args):
        # reduce noise
        logger.debug(format % args)


def start_server(port: int) -> HTTPServer:
    server = HTTPServer(('127.0.0.1', port), OAuthCallbackHandler)
    setattr(server, 'oauth_code', None)
    setattr(server, 'oauth_state', None)

    def serve():
        logger.info('Starting temporary HTTP server on http://127.0.0.1:%s', port)
        try:
            server.serve_forever()
        except Exception:
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return server


async def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    token_url = 'https://zoom.us/oauth/token'
    basic_raw = f"{client_id}:{client_secret}".encode('utf-8')
    basic_b64 = base64.b64encode(basic_raw).decode('ascii')
    headers = {
        'Authorization': f'Basic {basic_b64}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri}
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f'Token exchange failed {resp.status}: {text}')
            return await resp.json()


def save_refresh_token_to_env(refresh_token: str, path: str = '.env') -> None:
    # append or update ZOOM_REFRESH_TOKEN in .env
    lines = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith('ZOOM_REFRESH_TOKEN='):
            lines[i] = f'ZOOM_REFRESH_TOKEN={refresh_token}'
            found = True
            break
    if not found:
        lines.append(f'ZOOM_REFRESH_TOKEN={refresh_token}')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765, help='Local port for the redirect URI')
    parser.add_argument('--save', action='store_true', help='Save refresh token to .env')
    args = parser.parse_args()

    client_id = settings.zoom_client_id
    client_secret = settings.zoom_client_secret
    if not client_id or not client_secret:
        print('ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET must be set in config/settings or environment.')
        return

    redirect_uri = f'http://127.0.0.1:{args.port}/callback'
    # Zoom authorize URL
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
    }
    authorize_url = 'https://zoom.us/oauth/authorize?' + urllib.parse.urlencode(params)

    server = start_server(args.port)

    print('\nOpen the following URL in your browser to authorize the app:')
    print(authorize_url)
    try:
        webbrowser.open(authorize_url)
    except Exception:
        pass

    print('\nWaiting for authorization redirect...')
    # wait until server gets code or timeout
    start = time.time()
    code = None
    try:
        while time.time() - start < 300:
            code_val = getattr(server, 'oauth_code', None)
            if code_val:
                code = code_val
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\nCancelled by user')
        return

    # shutdown server
    try:
        server.shutdown()
    except Exception:
        pass

    if not code:
        print('No authorization code received. Ensure the redirect URI matches and try again.')
        return

    print('Received code, exchanging for tokens...')

    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        token_resp = loop.run_until_complete(exchange_code_for_tokens(client_id, client_secret, code, redirect_uri))
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass

    print('\nToken response:')
    print(json.dumps(token_resp, indent=2))

    refresh = token_resp.get('refresh_token')
    if refresh:
        print('\nRefresh token obtained. Keep it secret.')
        if args.save:
            save_refresh_token_to_env(refresh)
            print('Saved refresh token to .env as ZOOM_REFRESH_TOKEN')
        else:
            print('To persist this value, add the following to your .env file:')
            print(f'ZOOM_REFRESH_TOKEN={refresh}')
    else:
        print('\nNo refresh token returned. You may need to request the correct scopes or use a different Zoom app type.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
