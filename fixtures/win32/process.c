/* SPDX-License-Identifier: LGPL-2.1-or-later */
typedef unsigned int U;
static U r(U p,U offset) {return *(volatile U *)(p+offset);}
static int wide(U descriptor,const char *expected)
{
    const volatile unsigned short *p=(void *)r(descriptor,4);
    U i=0;for(;expected[i];++i) if(p[i]!=(unsigned char)expected[i]) return 0;
    return !p[i] && *(volatile unsigned short *)descriptor==i*2;
}
int entry(void)
{
    U peb,teb;__asm__("movl %%fs:0x30,%0":"=r"(peb));
    __asm__("movl %%fs:0x18,%0":"=r"(teb));
    if(!peb || r(teb,0x30)!=peb || r(teb,4)<=r(teb,8)) return 10;
    U params=r(peb,0x10),ldr=r(peb,0xc);
    if(r(params,8)!=1 || !wide(params+0x38,"C:\\process32.exe") ||
       !wide(params+0x40,"process32.exe --verify") || !wide(params+0x24,"C:\\")) return 11;
    U env=r(params,0x48);if(r(env,0)) return 12;
    U head=ldr+0xc,node=r(head,0);
    if(node==head || r(node,0)!=head || r(node,4)!=head || r(head,4)!=node) return 13;
    if(r(node,0x18)!=r(peb,8) || !wide(node+0x2c,"process32.exe")) return 14;
    head=ldr+0x1c;if(r(head,0)!=head || r(head,4)!=head) return 15;
    return 42;
}
