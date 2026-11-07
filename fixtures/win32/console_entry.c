/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
extern int console_main(void);
void entry(void) {ExitProcess(console_main());}
