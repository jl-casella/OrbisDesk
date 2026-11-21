/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase B / P014 desktop probe. Seeded to the "separate" execution mode (tools/build-wine-hardware.py writes
 * AppDefaults\separate_probe64.exe\OrbisExecutionMode="separate"). When launched from the OrbisDesk desktop,
 * kernelbase's PW_EXEC_SEPARATE path (tools/build-guest-hw.py) intercepts it: it does NOT run this image in
 * process but instead spawns a separate native process that joins the title's wineserver and creates a named
 * object the title then opens, logging PWSEP markers. So this body normally does not execute; it exists only
 * as a valid launchable image. If the separate path is ever disabled, it just shows a message. */
#include <windows.h>

int main(void)
{
    MessageBoxW(NULL,
        L"OrbisDesk separate-process probe (P014). This should be intercepted by the "
        L"\"separate\" execution mode and never reach here.",
        L"OrbisDesk P014",MB_OK|MB_ICONINFORMATION);
    return 0;
}
