/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_SHELL_OPEN_H
#define PW_SHELL_OPEN_H
#include <windows.h>
#define PW_SHELL_OPEN_TAG 0x50574f50u
#define PW_SHELL_OPEN_MESSAGE (WM_APP + 0x4b5)
struct pw_shell_open_request { WCHAR path[MAX_PATH]; WCHAR directory[MAX_PATH]; };
#endif
