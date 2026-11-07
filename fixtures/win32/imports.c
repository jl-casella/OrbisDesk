/* SPDX-License-Identifier: LGPL-2.1-or-later */
__declspec(dllimport) unsigned Scale(unsigned value);
__declspec(dllimport) unsigned OrdinalScale(unsigned value);
unsigned entry(void)
{
    unsigned value = Scale(1);
    return OrdinalScale(value);
}
