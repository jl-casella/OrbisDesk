#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.27 (docs/SHADER_CACHE.md): Mesa's disk shader cache on the PS4 (RADV, Crema's tree, VARIANT=wine only).

Every disk cache type maps an "index" file shared (MAP_SHARED) and sizes it with posix_fallocate first; until either
has been seen to work on the console's /data, a failure there turns the whole cache off. Here, on __PS4__ only:
- a posix_fallocate error of any kind falls back to ftruncate, as upstream already does for EOPNOTSUPP;
- a failed shared map of the index falls back to an anonymous one, said once in the log. The title is the only
  process using the cache, so nothing needs to see the index from outside; the database cache OrbisDesk selects
  (MESA_DISK_CACHE_DATABASE, native/wine_hardware.c) keeps its own size and eviction in its files, not in the index.
patch-mesa-disk-cache-ps4.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk 04.27 disk cache'
path='src/util/disk_cache_os.c'
target=mesa/path;text=normalize_marker(target.read_text())
if MARK in text:
    print(path,'already patched');raise SystemExit(0)
edits=[
('''         if (ret == EOPNOTSUPP) {''','''#ifdef __PS4__ /* '''+MARK+''': whatever the error, the size ftruncate gives is enough */
         if (1) {
#else
         if (ret == EOPNOTSUPP) {
#endif'''),
('''   cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE,
                            MAP_SHARED, fd, 0);
   if (cache->index_mmap == MAP_FAILED)
      goto path_fail;''','''   cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE,
                            MAP_SHARED, fd, 0);
#ifdef __PS4__ /* '''+MARK+''': only the title uses the cache; an anonymous index is enough */
   if (cache->index_mmap == MAP_FAILED) {
      fprintf(stderr, "PWCACHE index %s: shared map failed (errno %d), kept in memory\\n", path, errno);
      cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
   }
#endif
   if (cache->index_mmap == MAP_FAILED)
      goto path_fail;'''),
]
for old,new in edits:
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:70])
    text=text.replace(old,new,1)
target.write_text(text);print(path,'patched')
