/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <orbis/libkernel.h>

int main(void)
{
    OrbisKernelModule handles[128]; size_t count = 0;
    const char *symbols[] = {"fork", "rfork", "posix_spawn", "sceKernelSpawn", "execve"};
    FILE *log = fopen("/data/process-capabilities.jsonl", "w");
    if (!log) return 70;
    int rc = sceKernelGetModuleList(handles, 128, &count);
    fprintf(log, "{\"event\":\"module_list\",\"pid\":%ld,\"rc\":%d,\"count\":%zu}\n", (long)getpid(), rc, count);
    if (!rc && count <= 128) {
        for (unsigned s = 0; s < sizeof(symbols) / sizeof(symbols[0]); ++s) {
            unsigned found = 0;
            for (size_t i = 0; i < count; ++i) {
                void *address = NULL;
                int result = sceKernelDlsym(handles[i], symbols[s], &address);
                if (!result && address) ++found;
            }
            fprintf(log, "{\"event\":\"symbol_scan\",\"symbol\":\"%s\",\"loaded_module_matches\":%u}\n", symbols[s], found);
        }
    }
    fputs("{\"event\":\"complete\",\"discovery_only\":true,\"native_child_started\":false,\"multiprocess_status\":\"not_demonstrated\"}\n", log);
    fclose(log);
    return rc || count > 128 ? 71 : 0;
}
