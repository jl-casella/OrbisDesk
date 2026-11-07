/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <orbis/libkernel.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
int main(void)
{
    int fd=open("/data/image.bin",O_RDONLY);if(fd<0) return 96;
    void *output=(void *)(uintptr_t)0x12345678;
    puts("PWMMAP requesting private file map length=0x1000 offset=0xc00");fflush(stdout);
    int32_t rc=sceKernelMmap(NULL,0x1000,3,2,fd,0xc00,&output);
    int ok=rc==(int32_t)0x80020016 && output==(void *)(uintptr_t)0x12345678;
    printf("PWMMAP returned rc=%08x output=%p expected_einval=%d\n",(unsigned)rc,output,ok);fflush(stdout);
    if(!rc) sceKernelMunmap(output,0x1000);
    close(fd);return ok?0:97;
}
