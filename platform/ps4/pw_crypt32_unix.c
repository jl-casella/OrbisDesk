/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W180 (phase 9): crypt32's Unix side for the console (tools/build-unixlibs-ps4.py).
 *
 * W179: crypt32.dll failed to initialise in both views ("failed to load .../crypt32.so: Dynamic
 * loading not supported"; in 32-bit programs a Unix call without a table faulted first). xul.dll of
 * Wine Gecko and of Pale Moon imports crypt32 through wintrust, so neither loaded ("Failed to init
 * Gecko", Pale Moon's "Could not load XPCOM").
 *
 * dlls/crypt32/unixlib.c is compiled unpatched with its own recipe. The console's config.h has no
 * SONAME_LIBGNUTLS, so its PFX and key-store calls are Wine's no-GnuTLS ones and return
 * STATUS_DLL_NOT_FOUND. Its root certificates come from CA bundles at fixed paths (/etc/ssl/certs/...),
 * which the console does not have: the enumeration returns STATUS_NO_MORE_ENTRIES at once, and
 * crypt32's root store keeps only the Microsoft roots built into rootstore.c.
 * Pale Moon checks certificates with its own NSS store (nssckbi.dll); MSHTML has no TLS on the
 * console (schannel has no Unix side), so neither needs more.
 *
 * Wine's tables are renamed pw_crypt32_wine_* at compile time (DEFINES in the builder). These are
 * the tables pw_wine_unixlibs.c registers: the same entries, with a PWCRYPT line the first time the
 * root enumeration ends empty and each time a GnuTLS call answers STATUS_DLL_NOT_FOUND. */
#if 0
#pragma makedep unix
#endif

#include "config.h"

#include <stdarg.h>
#include <stdio.h>

#include "ntstatus.h"
#include "windef.h"
#include "winbase.h"
#include "winternl.h"
#include "wincrypt.h"
#include "bcrypt.h"
#include "crypt32_private.h"

static const char *const names[unix_funcs_count] =
{
    "process_attach", "process_detach", "open_cert_store", "import_store_key",
    "import_store_cert", "close_cert_store", "enum_root_certs", "export_cert_store",
};

static NTSTATUS traced( const unixlib_entry_t *table, unsigned int index, const char *view, void *args )
{
    static int roots_reported[2];
    NTSTATUS status = table[index]( args );
    int wow = view[0] == 'w';

    if (index == unix_enum_root_certs)
    {
        if (!roots_reported[wow])
        {
            roots_reported[wow] = 1;
            if (status == STATUS_NO_MORE_ENTRIES)
                fprintf( stderr, "PWCRYPT %s root_certs=none: no CA bundle in Wine's known paths "
                         "(/etc/ssl/certs/...); the root store keeps crypt32's built-in Microsoft roots\n", view );
            else
                fprintf( stderr, "PWCRYPT %s root_certs found status=0x%08x\n", view, (unsigned int)status );
        }
    }
    else if (status == STATUS_DLL_NOT_FOUND)
        fprintf( stderr, "PWCRYPT %s %s unsupported: no GnuTLS on the console (status=0x%08x)\n",
                 view, names[index], (unsigned int)status );
    return status;
}

#define ENTRY(table, index, view) \
    static NTSTATUS table##_##index( void *args ) { return traced( table, index, view, args ); }

ENTRY(__wine_unix_call_funcs, 0, "x64")
ENTRY(__wine_unix_call_funcs, 1, "x64")
ENTRY(__wine_unix_call_funcs, 2, "x64")
ENTRY(__wine_unix_call_funcs, 3, "x64")
ENTRY(__wine_unix_call_funcs, 4, "x64")
ENTRY(__wine_unix_call_funcs, 5, "x64")
ENTRY(__wine_unix_call_funcs, 6, "x64")
ENTRY(__wine_unix_call_funcs, 7, "x64")
ENTRY(__wine_unix_call_wow64_funcs, 0, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 1, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 2, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 3, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 4, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 5, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 6, "wow64")
ENTRY(__wine_unix_call_wow64_funcs, 7, "wow64")

/* the indices above, in crypt32_private.h's order */
C_ASSERT( unix_process_attach == 0 && unix_process_detach == 1 && unix_open_cert_store == 2 && unix_import_store_key == 3 && unix_import_store_cert == 4 &&
          unix_close_cert_store == 5 && unix_enum_root_certs == 6 && unix_export_cert_store == 7 &&
          unix_funcs_count == 8 );

DECLSPEC_EXPORT const unixlib_entry_t pw_crypt32_unix_call_funcs[] =
{
    __wine_unix_call_funcs_0, __wine_unix_call_funcs_1, __wine_unix_call_funcs_2, __wine_unix_call_funcs_3, __wine_unix_call_funcs_4,
    __wine_unix_call_funcs_5, __wine_unix_call_funcs_6, __wine_unix_call_funcs_7,
};
DECLSPEC_EXPORT const unixlib_entry_t pw_crypt32_unix_call_wow64_funcs[] =
{
    __wine_unix_call_wow64_funcs_0, __wine_unix_call_wow64_funcs_1, __wine_unix_call_wow64_funcs_2, __wine_unix_call_wow64_funcs_3, __wine_unix_call_wow64_funcs_4,
    __wine_unix_call_wow64_funcs_5, __wine_unix_call_wow64_funcs_6, __wine_unix_call_wow64_funcs_7,
};
