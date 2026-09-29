"""Start the real entrypoint against a temporary snapshot DB; check over HTTP."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nabari.db import init_db, import_snapshot


def main():
    snapshot = json.loads((ROOT / 'data/collected_snapshot.json').read_text())
    day = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    expected = [a for a in snapshot['articles'] if not a['source_date'] or a['source_date'] <= day]
    with tempfile.TemporaryDirectory() as directory:
        database = str(Path(directory) / 'http.sqlite3')
        init_db(database)
        import_snapshot(database, ROOT / 'data/collected_snapshot.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        process = subprocess.Popen([sys.executable, 'run.py', '--no-collect', '--port', str(port)],
            cwd=ROOT, env=os.environ | {'NABARI_DATABASE': database}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(40):
                try:
                    if requests.get(base + '/healthz', timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Waitress did not start')
            checks = []
            for path in ['/', '/?source=tourism', '/?q=ごみ', '/status', '/about', '/research/', '/healthz']:
                r = requests.get(base + path, timeout=10)
                assert r.status_code == 200, (path, r.status_code)
                checks.append({'path': path, 'status': r.status_code, 'bytes': len(r.content)})
            all_data = requests.get(base + '/api/articles', timeout=10).json()
            tourism = requests.get(base + '/api/articles?source=tourism', timeout=10).json()
            assert all_data['total'] == len(expected)
            assert tourism['total'] == sum(a['source_key'] == 'tourism' for a in expected)
            r = requests.get(base + '/articles/' + tourism['items'][0]['id'], timeout=10)
            assert r.status_code == 200 and '名張市観光協会の公式ページへ' in r.text
            home = requests.get(base + '/', timeout=10).text
            assert len(BeautifulSoup(home, 'html.parser').select('.card')) == min(12, len(expected))
            output = {'server': 'run.py / Flask / Waitress on loopback', 'asOfJST': day, 'routes': checks,
                'allVisible': all_data['total'], 'tourismVisible': tourism['total'], 'detailStatus': 200, 'result': 'passed'}
            (ROOT / 'results/http_smoke.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
            (ROOT / 'results/live_home.html').write_text(home)
            print(json.dumps(output, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
