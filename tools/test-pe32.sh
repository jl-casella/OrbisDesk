#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/host
cc -std=c11 -g -O1 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -Iplatform/ps4 -Iupstream/prospero-win/src \
    -Iupstream/prospero-win/include tests/pe32_parser.c platform/ps4/pw_pe32.c platform/ps4/pw_pe32_tables.c \
    upstream/prospero-win/src/pw_vm.c -o build/host/pe32-parser
for fixture in minimal32.exe minimal4k32.exe imports32.exe testmath.dll nested.dll lifecycle.dll lifecycle-peer.dll lifecycle-fail.dll; do
    ASAN_OPTIONS=detect_leaks=1 ./build/host/pe32-parser "out/$fixture" | tee "build/host/pe32-parser-$fixture.json"
done
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
path = pathlib.Path('build/host/pe32-parser.json')
names = ('minimal32.exe', 'minimal4k32.exe', 'imports32.exe', 'testmath.dll', 'nested.dll',
         'lifecycle.dll', 'lifecycle-peer.dll', 'lifecycle-fail.dll')
result = {'status': 'passed', 'environment': 'WSL host parser, not PS4',
          'fixtures': {name: json.loads(pathlib.Path(f'build/host/pe32-parser-{name}.json').read_text()) for name in names}}
result['sanitizers'] = ['address', 'undefined', 'leak detection']
result['compiler'] = subprocess.check_output(['cc', '--version'], text=True).splitlines()[0]
result['sources'] = {name: hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() for name in (
    'platform/ps4/pw_pe32.c', 'platform/ps4/pw_pe32.h', 'platform/ps4/pw_pe32_tables.c',
    'platform/ps4/pw_pe32_internal.h', 'tests/pe32_parser.c', 'tools/test-pe32.sh',
    *('out/' + name for name in names))}
path.write_text(json.dumps(result, indent=2) + '\n')
PY
