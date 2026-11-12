/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Host harness for the MangoHud Settings file logic (fixtures/win32/mangohudcfg.c, MHC_CONF_ONLY).
 * stdin: a MangoHud.conf. "read" prints what the form would show; "merge [key=value...]" prints the
 * file a save would write after those edits (row keys 0/1, position by name, numbers). */
#define MHC_CONF_ONLY
#include "../fixtures/win32/mangohudcfg.c"

int main(int argc,char **argv)
{
    static char text[1<<20];size_t len=fread(text,1,sizeof(text),stdin);
    struct mhc_conf c;
    mhc_read(text,len,&c);
    if(argc<2) return 2;
    if(!strcmp(argv[1],"read")) {
        for(int i=0;i<MHC_ROWS;i++) printf("%s=%d\n",mhc_row_keys[i],c.row[i]);
        printf("position=%s\noffset_x=%d\noffset_y=%d\nfont_size=%d\nalpha_pct=%d\n",mhc_positions[c.position],
               c.offset_x,c.offset_y,c.font_size,c.alpha_pct);
        return 0;
    }
    if(strcmp(argv[1],"merge")) return 2;
    for(int a=2;a<argc;a++) {
        char *value=strchr(argv[a],'=');
        if(!value) return 2;
        *value++=0;
        for(int i=0;i<MHC_ROWS;i++) if(!strcmp(argv[a],mhc_row_keys[i])) c.row[i]=atoi(value);
        for(int i=0;i<MHC_POSITIONS;i++) if(!strcmp(argv[a],"position") && !strcmp(value,mhc_positions[i])) c.position=i;
        if(!strcmp(argv[a],"offset_x")) c.offset_x=atoi(value);
        if(!strcmp(argv[a],"offset_y")) c.offset_y=atoi(value);
        if(!strcmp(argv[a],"font_size")) c.font_size=atoi(value);
        if(!strcmp(argv[a],"alpha_pct")) c.alpha_pct=atoi(value);
    }
    size_t out_len;char *out=mhc_merge(text,len,&c,&out_len);
    if(!out) return 1;
    fwrite(out,1,out_len,stdout);
    free(out);
    return 0;
}
