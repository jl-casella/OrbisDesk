/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "loader.c"
int pw_wine_test_paths(void)
{
    int rc;
    set_home_dir();
    set_config_dir();
    rc=strcmp(home_dir,getenv("HOME")) || strcmp(user_name,getenv("USER")) ||
           strcmp(config_dir,getenv("WINEPREFIX"));
    free((void *)home_dir);free((void *)user_name);free((void *)config_dir);
    home_dir=user_name=config_dir=NULL;
    return rc;
}
