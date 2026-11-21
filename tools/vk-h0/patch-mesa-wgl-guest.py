#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""alpha-1 (run-0178, 2026-11-17: Alan Wake's American Nightmare, 32-bit, wined3d on OpenGL through this Zink, closed
from the overlay; free memory at the next start fell 4.77 -> 3.50 GB and "PWGUEST vulkan ... shared=1": its memory was
Zink's). Mesa's WGL frontend keeps one screen (one Zink VkDevice) for the whole process. A guest program whose threads
are terminated never deletes its GL contexts, so their textures and buffers, and Zink's caches, stay in that device's
memory; its threads, Zink's queue threads among them (created from the guest's threads), are gone. Two changes:

- each stw_context records the guest of the thread that created it (TEB.UserReserved[0], as Wine's kernelbase keeps
  it: 0 for the desktop's own threads);
- pw_wgl_release_screen(), exported, called by Wine's kernelbase when a guest has ended and no other guest runs in
  this world (tools/build-guest-hw.py): unless a desktop thread's context is left, the device forgets its screen,
  contexts and framebuffers without touching them (their threads may have been terminated holding their locks), and
  the next context makes a new screen. win32u then frees the old Zink device's memory (tools/build-win32u-ps4.py).
  Returns -1 not initialized/no memory, 0 no screen, 1 released, 2 kept (desktop contexts).

patch-mesa-wgl-guest.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys

src = pathlib.Path(sys.argv[1])

edits = [
    ('src/gallium/frontends/wgl/stw_context.h',
     """   struct hud_context *hud;
};
""",
     """   struct hud_context *hud;

   ULONG_PTR pw_owner;  /* OrbisDesk alpha-1 (run-0178): the guest of the creating thread, 0 for the desktop's */
};

/* OrbisDesk alpha-1 (run-0178): Wine's kernelbase keeps a thread's guest program in TEB.UserReserved[0] */
static inline ULONG_PTR
pw_wgl_owner(void)
{
   return *(ULONG_PTR *)((char *)NtCurrentTeb() + (sizeof(void *) == 8 ? 0xe8 : 0xac));
}
"""),
    ('src/gallium/frontends/wgl/stw_context.c',
     """   ctx->shared = shareCtx != NULL;
""",
     """   ctx->shared = shareCtx != NULL;
   ctx->pw_owner = pw_wgl_owner();  /* OrbisDesk alpha-1 (run-0178) */
"""),
    ('src/gallium/frontends/wgl/stw_device.h',
     """struct stw_device *
stw_get_device(void);
""",
     """struct stw_device *
stw_get_device(void);

/* OrbisDesk alpha-1 (run-0178), exported */
int
pw_wgl_release_screen(unsigned *contexts, unsigned *desktop);
"""),
    ('src/gallium/frontends/wgl/stw_device.c',
     """#include "stw_st.h"
""",
     """#include "stw_st.h"
#include "stw_context.h"  /* OrbisDesk alpha-1 (run-0178) */
"""),
    ('src/gallium/frontends/wgl/stw_device.c',
     """struct stw_device *
stw_get_device(void)
{
   return stw_dev;
}
""",
     """struct stw_device *
stw_get_device(void)
{
   return stw_dev;
}

/* OrbisDesk alpha-1 (run-0178): after a guest program ended, with no other guest running in this world, the screen
 * is forgotten unless a desktop thread's context is left: its contexts and framebuffers are not touched (their
 * threads, Zink's queue threads among them, may have been terminated holding their locks), and the next context
 * makes a new screen. Wine's win32u then frees the old Zink device's memory. */
int
pw_wgl_release_screen(unsigned *contexts, unsigned *desktop)
{
   struct pipe_frontend_screen *fscreen;
   struct handle_table *table;
   unsigned handle;

   *contexts = *desktop = 0;
   if (!stw_dev || !stw_dev->initialized)
      return -1;
   if (!stw_dev->screen)
      return 0;
   for (handle = handle_table_get_first_handle(stw_dev->ctx_table); handle;
        handle = handle_table_get_next_handle(stw_dev->ctx_table, handle)) {
      struct stw_context *ctx = handle_table_get(stw_dev->ctx_table, handle);

      (*contexts)++;
      if (ctx && !ctx->pw_owner)
         (*desktop)++;
   }
   if (*desktop)
      return 2;

   fscreen = CALLOC_STRUCT(pipe_frontend_screen);
   table = handle_table_create();
   if (!fscreen || !table) {
      FREE(fscreen);
      if (table)
         handle_table_destroy(table);
      return -1;
   }
   fscreen->get_param = stw_get_param;

   /* a lock left by a terminated thread is not waited for */
   InitializeCriticalSection(&stw_dev->screen_mutex);
   InitializeCriticalSection(&stw_dev->ctx_mutex);
   InitializeCriticalSection(&stw_dev->fb_mutex);

   free(stw_dev->st_options.force_explicit_uniform_loc_zero);
   free(stw_dev->st_options.force_gl_vendor);
   free(stw_dev->st_options.force_gl_renderer);
   free(stw_dev->st_options.mesa_extension_override);
   memset(&stw_dev->st_options, 0, sizeof(stw_dev->st_options));
   driDestroyOptionCache(&stw_dev->option_cache);
   driDestroyOptionInfo(&stw_dev->option_info);
   util_dynarray_fini(&stw_dev->pixelformats);
   stw_dev->pixelformat_count = 0;

   stw_dev->ctx_table = table;
   stw_dev->fb_head = NULL;
   stw_dev->fscreen = fscreen;
   stw_dev->screen = NULL;
   stw_dev->zink = false;
   stw_dev->screen_initialized = false;
   return 1;
}
"""),
    ('src/gallium/targets/wgl/gallium_wgl.def.in',
     """stw_get_device
""",
     """stw_get_device
pw_wgl_release_screen
"""),
]

for name, old, new in edits:
    p = src / name
    t = normalize_marker(p.read_text())
    if new in t:
        print(f'{name}: already patched')
    elif t.count(old) == 1:
        p.write_text(t.replace(old, new))
        print(f'{name}: patched')
    else:
        raise SystemExit(f'unexpected {name}')
