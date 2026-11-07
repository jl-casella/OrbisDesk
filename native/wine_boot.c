/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_platform.h"
#include "pw_wine_fs.h"
#include <orbis/libkernel.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
extern void __wine_main(int,char **);
extern int pw_wine_boot_services(void);
extern int pw_wine_boot_ipc_services(void);
extern int pw_wine_boot_gs_services(void);
extern int pw_wine_boot_signal_services(void);
extern int pw_wine_boot_pipe_services(void);
extern int pw_wine_boot_fs_services(void);
extern int pw_wine_boot_metadata_services(void);
extern int pw_wine_prefix_preflight(void);
int main(int argc,char **argv)
{
    if(argc>1 && !strcmp(argv[1],"--services")) return pw_wine_boot_services();
    if(argc>1 && !strcmp(argv[1],"--ipc-services")) return pw_wine_boot_ipc_services();
    if(argc>1 && !strcmp(argv[1],"--gs-services")) return pw_wine_boot_gs_services();
    if(argc>1 && !strcmp(argv[1],"--signal-services")) return pw_wine_boot_signal_services();
    if(argc>1 && !strcmp(argv[1],"--pipe-services")) return pw_wine_boot_pipe_services();
    if(argc>1 && !strcmp(argv[1],"--fs-services")) return pw_wine_boot_fs_services();
    if(argc>1 && !strcmp(argv[1],"--metadata-services")) return pw_wine_boot_metadata_services();
    int prepared=argc>1 && (!strcmp(argv[1],"--prepared-prefix") || !strcmp(argv[1],"--prefix-preflight"));
    int preflight_only=prepared && !strcmp(argv[1],"--prefix-preflight");
    const char *prefix=prepared?"/data/wine-prefix":argc>2?argv[2]:"/data/wine-prefix";
    const char *exe=prepared?"C:\\orbis\\console32.exe":argc>1?argv[1]:"/data/console32.exe";
    unsetenv("WINE_PS4_EXTERNAL_PREFIX");
    if(pw_wine_init_paths(prefix,"/data/wine-home","orbis")) {sceKernelDebugOutText(0,"PWBOOT paths_failed\n");return 90;}
    /* PS4 applications have no symbolic links: the sealed prefix's DOS drives (c: ../drive_c,
     * z: ../..) are a fixed mount table. A fresh prefix keeps Wine's own links (z: is /). */
    if(prepared && pw_wine_fs_drive_mounts(prefix)) {sceKernelDebugOutText(0,"PWBOOT drive_mounts_failed\n");return 90;}
    if(prepared) {
        int rc=pw_wine_prefix_preflight();if(rc || preflight_only) return rc;
        if(setenv("WINE_PS4_EXTERNAL_PREFIX","1",1) || setenv("WINEARCH","wow64",1)) return 91;
    }
    if(pw_wine_chdir(0,"/data") || pw_wine_chdir(1,prefix)) return 90;
    if(prepared && pw_wine_chdir(0,"/data/wine-prefix/drive_c/orbis")) return 90;
    if(setenv("WINE_PS4_NTDLL_DIR","/data/wine/lib/wine/x86_64-unix",1) ||
       setenv("WINE_PS4_NLS_DIR","/data/wine/share/wine/nls",1) ||
       setenv("WINE_PS4_DATA_DIR","/data/wine/share/wine",1) ||
       setenv("WINEDLLPATH","/data/wine/lib/wine",1) ||
       setenv("WINELOADERNOEXEC","1",1)) return 91;
    enum {MAX_WINE_ARGS=16};  /* W265 (W263: PoP, Worms 3D): up to 16 program arguments, as wine_hardware.c */
    char *wine_argv[MAX_WINE_ARGS+3]={"/data/wine/bin/wine",(char *)exe};
    int wine_argc=2;
    for(int i=2;prepared && i<argc;++i) {
        if(!strncmp(argv[i],"--winedebug=",12)) {if(setenv("WINEDEBUG",argv[i]+12,1)) return 91;}
        else if(!strncmp(argv[i],"--wow64-cpu=",12)) {if(setenv("WINE_PS4_WOW64_CPU",argv[i]+12,1)) return 91;}
        else if(!strncmp(argv[i],"--env=",6) && strchr(argv[i]+6,'=')) {if(putenv(argv[i]+6)) return 91;}
        else if(!strncmp(argv[i],"--wine-exe=",11) && argv[i][11]) wine_argv[1]=argv[i]+11;
        else if(!strncmp(argv[i],"--wine-arg=",11) && wine_argc<MAX_WINE_ARGS+2) wine_argv[wine_argc++]=argv[i]+11;
        else return 91;
    }
    wine_argv[wine_argc]=NULL;
    sceKernelDebugOutText(0,"PWBOOT entered___wine_main\n");
    __wine_main(wine_argc,wine_argv);
    sceKernelDebugOutText(0,"PWBOOT unexpected_return\n");return 94;
}
