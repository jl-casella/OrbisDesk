/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_SHELL_OPEN_H
#define PW_SHELL_OPEN_H
#include <windows.h>
#define PW_SHELL_OPEN_TAG 0x50574f50u
#define PW_SHELL_OPEN_MESSAGE (WM_APP + 0x4b5)
struct pw_shell_open_request { WCHAR path[MAX_PATH]; WCHAR directory[MAX_PATH]; };
/* PoP D.4: a program a separate Windows process starts, to run here as a guest (docs/POP_SEPARATE_PROCESS.md).
 * The separate process writes PW_TITLE_LAUNCH_FILE (UTF-8: image, command line, directory and a token, one per
 * line); explorer's watcher posts it to the desktop window, which starts it with CreateProcessW and answers in
 * PW_TITLE_LAUNCH_REPLY_FILE: "<token> started <pid>" or "<token> failed <error>", then "<token> ended" when the
 * guest has ended. The separate process stays until then, as a launcher stays while its game runs: Prince of
 * Persia's POP.exe ends with status 300 unless the launcher's named shared memory (PrinceSM) is alive. */
#define PW_SHELL_LAUNCH_MESSAGE (WM_APP + 0x4b6)
#define PW_TITLE_LAUNCH_FILE L"Z:\\orbisdesk\\process-p014\\title-launch"
#define PW_TITLE_LAUNCH_REPLY_FILE L"Z:\\orbisdesk\\process-p014\\title-launch-reply"
struct pw_shell_launch_request { WCHAR image[MAX_PATH]; WCHAR command[1024]; WCHAR directory[MAX_PATH]; DWORD token; };
#endif
