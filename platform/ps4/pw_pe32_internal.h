/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PE32_INTERNAL_H
#define PW_PE32_INTERNAL_H
#include "pw_pe32.h"
const uint8_t *pw_pe32_file_rva(const uint8_t *, const PwPe32Info *, uint32_t, uint32_t);
int pw_pe32_parse_tables(const uint8_t *, PwPe32Info *);
#endif
