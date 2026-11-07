/* SPDX-License-Identifier: LGPL-2.1-or-later */
volatile unsigned seed = 7;
volatile unsigned * volatile seed_pointer = &seed;
volatile unsigned result;

unsigned entry(void)
{
    if (result) return 0xbad;
    unsigned value = *seed_pointer;
    result = value * 5 + 7;
    return result;
}
