#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/host
cc -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer \
    -Iplatform/ps4 -Iupstream/prospero-win/include \
    tests/vm_backend.c platform/ps4/pw_vm_ps4.c upstream/prospero-win/src/pw_vm.c \
    -pthread -o build/host/vm_backend
ASAN_OPTIONS=detect_leaks=1 build/host/vm_backend 2>&1 | tee build/host/vm-tests.log
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
paths = ['tests/vm_backend.c', 'platform/ps4/pw_vm_ps4.c',
         'platform/ps4/pw_vm_ps4.h', 'platform/ps4/pw_vm_ps4_kernel.h']
report = {'status': 'passed', 'environment': 'WSL host fault injection, not PS4',
          'sanitizers': ['address', 'undefined', 'leak detection'],
          'concurrent_cycles': 400,
          'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
          'sources': {p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}}
pathlib.Path('build/host/vm-tests.json').write_text(json.dumps(report, indent=2) + '\n')
PY
