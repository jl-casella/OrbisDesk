"""Small standard-library helpers shared by CI entry points."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'reports/ci'
sys.path.append(str(ROOT / 'tools'))
from logged_process import run_logged


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def revision():
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()


@contextmanager
def phase(name):
    RESULTS.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    record = {'phase': name, 'source_sha': revision(), 'status': 'failed',
              'started_at': datetime.now(timezone.utc).isoformat()}
    try:
        yield record
        record['status'] = 'failed' if record.pop('failed', False) else 'passed'
    finally:
        record['duration_seconds'] = round(time.monotonic() - start, 3)
        record['completed_at'] = datetime.now(timezone.utc).isoformat()
        record['runner'] = os.environ.get('RUNNER_NAME', 'local')
        with (RESULTS / 'timings.jsonl').open('a') as stream:
            stream.write(json.dumps(record) + '\n')
        print(json.dumps(record), flush=True)


def run(command, log, timeout=2700, env=None, minimum_free_bytes=0):
    return run_logged(command, log, cwd=ROOT, timeout=timeout, env=env,
                      process_group=os.name == 'posix', minimum_free_bytes=minimum_free_bytes)
