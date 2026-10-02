"""Render the README screenshots from a live local server.

Usage: .venv/bin/python scripts/screenshots.py [output_dir] [--full] [--mobile]
  --full    capture whole pages (for reviewing layout) instead of the fold
  --mobile  use an iPhone-sized viewport
Needs Playwright (pip install playwright) and Google Chrome; it drives the
installed Chrome, so no browser download is required. Starts the app on a
spare port with the supermarket demo loaded and no API key.
"""
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
FULL = '--full' in sys.argv
MOBILE = '--mobile' in sys.argv
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(ROOT, 'docs', 'screenshots'))
PORT = 5098
BASE = f'http://127.0.0.1:{PORT}'

SHOTS = [
    ('executive', '/dashboard/executive'),
    ('forecast', '/dashboard/executive#forecast'),
    ('financial', '/dashboard/financial'),
    ('growth', '/dashboard/growth'),
    ('inventory', '/dashboard/inventory'),
    ('trends', '/dashboard/trends'),
    ('chat', '/dashboard/chat'),
]


def wait_for_server():
    for _ in range(60):
        try:
            urllib.request.urlopen(f'{BASE}/login', timeout=1)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit('server did not start')


def main():
    os.makedirs(OUT, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ('GEMINI_API_KEY', 'FLASK_DEBUG')}
    env['PORT'] = str(PORT)
    server = subprocess.Popen([sys.executable, 'main.py'], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome')
            viewport = {'width': 390, 'height': 844} if MOBILE else {'width': 1440, 'height': 900}
            page = browser.new_page(viewport=viewport, device_scale_factor=2)
            page.goto(f'{BASE}/login')
            page.screenshot(path=os.path.join(OUT, 'login.png'))
            page.fill('input[name=username]', 'demo')
            page.fill('input[name=password]', 'demo')
            page.click('button[type=submit], input[type=submit]')
            page.wait_for_load_state('networkidle')
            page.screenshot(path=os.path.join(OUT, 'upload.png'))
            page.request.post(f'{BASE}/load-demo-data',
                              form={'demo_type': 'supermarket_data', 'date_filter': 'all'})
            for name, path in SHOTS:
                page.goto(BASE + path.split('#')[0])
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1200)  # let Chart.js finish animating
                if name == 'forecast':
                    page.locator('.forecast-card').screenshot(path=os.path.join(OUT, f'{name}.png'))
                else:
                    page.screenshot(path=os.path.join(OUT, f'{name}.png'), full_page=FULL)
                print('saved', name)
            browser.close()
    finally:
        server.terminate()


if __name__ == '__main__':
    main()
