"""Keep complete subprocess logs and surface failures through nested build drivers."""
from pathlib import Path
import os
import signal
import subprocess


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


def run_logged(command, log, *, cwd=None, env=None, timeout=None, process_group=False):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open('w') as stream:
            arguments = list(map(str, command))
            if not process_group:
                return subprocess.run(arguments, cwd=cwd, env=env, timeout=timeout,
                                      stdout=stream, stderr=subprocess.STDOUT, check=True)
            if os.name != 'posix':
                raise ValueError('Process-group cleanup requires POSIX')
            process = subprocess.Popen(arguments, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print('Command failed', flush=True)
        # Keep the full file as evidence. The bounded tail makes nested drivers useful
        # in Actions without dumping potentially enormous compiler logs to the console.
        print_log_tail(log)
        raise
