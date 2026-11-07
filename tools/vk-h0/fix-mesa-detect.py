# H0: Mesa's function checks with an empty prefix only test that the symbol links. The OpenOrbis
# libc defines qsort_s (and others) without declaring them, so Mesa then calls undeclared
# functions. Require a declaration from the usual headers.
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / 'meson.build'
t = p.read_text()
old = "  'qsort_s': '',"
if old in t:
    hdr = "'#include <stdlib.h>\n#include <string.h>\n#include <stdio.h>\n#include <fcntl.h>'"
    for f in ('strtof', 'mkostemp', 'random_r', 'flock', 'strtok_r', 'qsort_s', 'posix_fallocate', 'secure_getenv'):
        t = t.replace("  '%s': ''," % f, "  '%s': %s," % (f, hdr))
    p.write_text(t)
    print('detect fixed')
