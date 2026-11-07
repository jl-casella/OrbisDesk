/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <freetype/config/ftoption.h>
/* Orbis has ordinary files, not classic Mac resource forks or named forks.
 * Invalid sfnt files must return a format error instead of probing these paths. */
#undef FT_CONFIG_OPTION_MAC_FONTS
