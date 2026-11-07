/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef PW_PS4_TRANSLATOR_RUNTIME_PROBES_H
#define PW_PS4_TRANSLATOR_RUNTIME_PROBES_H
#include <stddef.h>
int probe_translator_teb(int threaded, char *detail, size_t capacity);
int probe_hostexec(int cache, char *detail, size_t capacity);
int probe_dispatcher(int kind, char *detail, size_t capacity);
int probe_pe32(int kind, char *detail, size_t capacity, int *exit_status);
int probe_console(char *detail, size_t capacity, int *exit_status);
int probe_lifecycle_host(char *detail, size_t capacity, int *exit_status);
int probe_console32(char *detail, size_t capacity, int *exit_status);
int probe_dll(int kind, char *detail, size_t capacity, int *exit_status);
int probe_lifecycle(int kind, char *detail, size_t capacity);
#endif
