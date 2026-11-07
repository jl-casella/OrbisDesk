/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standalone entry for the existing native probes; does not initialize Wine. */
#include <stdio.h>
#include <string.h>
extern int pw_wine_boot_ipc_services(void);
extern int pw_wine_boot_pipe_services(void);
extern int pw_wine_boot_fs_services(void);
extern int pw_wine_boot_metadata_services(void);
int main(int argc, char **argv)
{
    const char *name = argc > 1 ? argv[1] : "";
    int result = 93;
    if (!strcmp(name, "ipc")) result = pw_wine_boot_ipc_services();
    else if (!strcmp(name, "pipes")) result = pw_wine_boot_pipe_services();
    else if (!strcmp(name, "filesystem")) result = pw_wine_boot_fs_services();
    else if (!strcmp(name, "metadata")) result = pw_wine_boot_metadata_services();
    printf("PWCI {\"case\":\"%s\",\"exit_code\":%d}\n", name, result);
    fflush(stdout);
    return result;
}
