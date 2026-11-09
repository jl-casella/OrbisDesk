#!/usr/bin/env python3
"""OrbisDesk alpha-1: Crema's RADV winsys log (ac_ps4_drm.c, OrbisDesk's copy in the Mesa tree) in a release run.

W299: 968 radv lines in one release run log, 430 of them twice.
- ps4_log wrote each line to stderr and to sceKernelDebugOutText, and OrbisDesk's launcher puts both in the
  run log: here only stderr (plus the winsys's own /data/orbisdesk/gpu/radv-ps4.log, unchanged).
- Without OrbisDesk's trace switch (platform/ps4/pw_trace.h; the weak pw_trace_level counts as on where it is
  not linked, as in the probes), the per-device startup lines, the first 40 and every 1000th submission, the
  verbose mapping lines and RADV's startup trace points are not written. A failed check, a refused submission,
  a startup step that fails, GPU hangs and faults still are.
"""
import argparse, pathlib
parser = argparse.ArgumentParser(); parser.add_argument('source', type=pathlib.Path)
path = parser.parse_args().source
text = path.read_text()
marker = '/* OrbisDesk alpha-1: the trace switch'
if marker not in text:
    def replace(old, new):
        global text
        if text.count(old) != 1: raise SystemExit('Crema traces context changed: ' + old[:100])
        text = text.replace(old, new, 1)
    replace('''static void
ps4_log(const char *fmt, ...)
{''', '''/* OrbisDesk alpha-1: the trace switch (platform/ps4/pw_trace.h); weak, so on where it is not linked */
extern int pw_trace_level __attribute__((weak));
static inline bool
ps4_traced(void)
{
   return &pw_trace_level ? pw_trace_level > 0 : true;
}

static void
ps4_log(const char *fmt, ...)
{''')
    replace('''   fputs(line, stderr);
   sceKernelDebugOutText(0, line);
''', '''   fputs(line, stderr); /* OrbisDesk: its launcher logs stderr and the debug output, so once */
''')
    replace('''#define PS4_VERBOSE(...) do { if (ps4_verbose_left) {''',
            '''#define PS4_VERBOSE(...) do { if (ps4_verbose_left && ps4_traced()) {''')
    replace('''   ps4_log("radv/ps4: GPU address windows''', '''   if (ps4_traced())
   ps4_log("radv/ps4: GPU address windows''')
    replace('''      ps4_log("radv/ps4: virtual query check %s''', '''      if (!ps4_vq_ok || ps4_traced())
      ps4_log("radv/ps4: virtual query check %s''')
    replace('''      ps4_log("radv/ps4: EOP event queue %#x, sceGnmAddEqEvent %#x\\n", r, a);''',
            '''      if (r || a || ps4_traced())
         ps4_log("radv/ps4: EOP event queue %#x, sceGnmAddEqEvent %#x\\n", r, a);''')
    replace('''   ps4_log("radv/ps4: device initialized\\n");''', '''   if (ps4_traced())
      ps4_log("radv/ps4: device initialized\\n");''')
    replace('''   if (seq <= 40 || seq % 1000 == 0)
      ps4_log("radv/ps4: submit %llu:''', '''   if ((seq <= 40 || seq % 1000 == 0) && ps4_traced())
      ps4_log("radv/ps4: submit %llu:''')
    replace('''ac_ps4_trace(const char *fmt, ...)
{
   char line[256];
   va_list args;
   va_start(args, fmt);
   vsnprintf(line, sizeof(line), fmt, args);
   va_end(args);
''', '''ac_ps4_trace(const char *fmt, ...)
{
   char line[256];
   va_list args;
   va_start(args, fmt);
   vsnprintf(line, sizeof(line), fmt, args);
   va_end(args);
   if (!ps4_traced()) {
      /* OrbisDesk alpha-1: without traces, only a step that failed ("-> fail_...", "= <nonzero>") */
      const char *result = strstr(line, " = ");
      if (!strstr(line, "fail") && !(result && strtol(result + 3, NULL, 0) != 0))
         return;
   }
''')
    path.write_text(text)
print('crema traces', path)
