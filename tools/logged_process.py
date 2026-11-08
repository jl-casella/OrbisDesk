"""Keep complete subprocess logs and surface failures through nested build drivers."""
from pathlib import Path
import subprocess


def run_logged(command, log, *, cwd=None, env=None, timeout=None):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open('w') as stream:
            return subprocess.run(list(map(str, command)), cwd=cwd, env=env, timeout=timeout,
                                  stdout=stream, stderr=subprocess.STDOUT, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print('Command failed; complete output: ' + str(log), flush=True)
        # Keep the full file as evidence. The bounded tail makes nested drivers useful
        # in Actions without dumping potentially enormous compiler logs to the console.
        size = log.stat().st_size
        with log.open('rb') as stream:
            stream.seek(max(0, size - 64 * 1024))
            data = stream.read()
        if size > 64 * 1024:
            print('[Earlier output retained in the complete log]', flush=True)
        print(data.decode(errors='replace'), flush=True)
        raise
