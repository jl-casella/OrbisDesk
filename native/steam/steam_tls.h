/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>

int mbedtls_hardware_poll(void *data,unsigned char *output,size_t len,size_t *olen);
int steam_entropy_check(int *error,int *zero,int *same);
