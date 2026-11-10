"""Keep complete subprocess logs and surface failures through nested build drivers."""
from pathlib import Path
import os
import signal
import shutil
import subprocess
import time


def print_log_tail(log):
    log = Path(log)
    if not log.is_file():
        return
    print('Complete output: ' + str(log), flush=True)
    size = log.stat().st_size
    with log.open('rb') as stream:
        stream.seek(max(0, size - 64 * 1024))
        data = stream.read()
    if size > 64 * 1024:
        print('[Earlier output retained in the complete log]', flush=True)
    print(data.decode(errors='replace'), flush=True)


def run_logged(command, log, *, cwd=None, env=None, timeout=None, process_group=False,
               minimum_free_bytes=0):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open('w') as stream:
            arguments = list(map(str, command))
            if minimum_free_bytes and not process_group:
                raise ValueError('Disk monitoring requires process-group cleanup')
            if not process_group:
                return subprocess.run(arguments, cwd=cwd, env=env, timeout=timeout,
                                      stdout=stream, stderr=subprocess.STDOUT, check=True)
            if os.name != 'posix':
                raise ValueError('Process-group cleanup requires POSIX')
            process = subprocess.Popen(arguments, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                if not minimum_free_bytes:
                    code = process.wait(timeout=timeout)
                else:
                    deadline = time.monotonic() + timeout if timeout is not None else None
                    while True:
                        free = shutil.disk_usage(cwd or Path.cwd()).free
                        if free < minimum_free_bytes:
                            raise OSError(f'Runner disk reserve exhausted: {free} bytes free; '
                                          f'reserve {minimum_free_bytes}; stopping build process group')
                        remaining = deadline - time.monotonic() if deadline is not None else 10
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(arguments, timeout)
                        try:
                            code = process.wait(timeout=min(10, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            continue
            except BaseException:
                # The driver, Ninja, ccache and compilers share this new group.
                # Stop all of them before statistics/cache saving can begin.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise
            result = subprocess.CompletedProcess(arguments, code)
            result.check_returncode()
            return result
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        print('Command failed', flush=True)
        # Keep the full file as evidence. The bounded tail makes nested drivers useful
        # in Actions without dumping potentially enormous compiler logs to the console.
        print_log_tail(log)
        raise
