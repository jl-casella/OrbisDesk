/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* dwrite's Unix side (dlls/dwrite/freetype.c) for Orbis, unpatched: tools/build-unixlibs-ps4.py
 * compiles it with HAVE_FT2BUILD_H, a SONAME_LIBFREETYPE and dlopen/dlsym/dlclose renamed to the
 * functions below, which answer from the FreeType that win32u already links into the boot ELF
 * (build/freetype-ps4). The title has no dynamic loader, so Wine's dlopen of libfreetype failed.
 *
 * MangoJuice (docs/MANGOJUICE.md): MSYS2's libharfbuzz imports DWrite.dll, so without it neither
 * harfbuzz, freetype, cairo nor GTK loaded (run-0060). A name that FreeType does not define is
 * answered NULL, so dwrite's own "cannot find certain functions" failure stays real. */
#include <string.h>
#include <ft2build.h>
#include FT_GLYPH_H
#include FT_FREETYPE_H
#include FT_OUTLINE_H
#include FT_TRUETYPE_TABLES_H
#include FT_SIZES_H

static const char handle_name[]="static-orbis-freetype";

void *pw_dwrite_dlopen(const char *name,int flags)
{
    (void)flags;
    return name && !strcmp(name,handle_name)?(void *)handle_name:NULL;
}

void *pw_dwrite_dlsym(void *handle,const char *name)
{
#define F(f) {#f,(void *)f}
    static const struct {const char *name;void *function;} table[]={
        F(FT_Activate_Size),F(FT_Done_Face),F(FT_Done_FreeType),F(FT_Done_Glyph),F(FT_Done_Size),
        F(FT_Get_First_Char),F(FT_Get_Glyph),F(FT_Get_Kerning),F(FT_Get_Sfnt_Table),F(FT_Glyph_Copy),
        F(FT_Glyph_Get_CBox),F(FT_Glyph_Transform),F(FT_Init_FreeType),F(FT_Library_Version),
        F(FT_Load_Glyph),F(FT_Matrix_Multiply),F(FT_MulDiv),F(FT_New_Memory_Face),F(FT_New_Size),
        F(FT_Outline_Copy),F(FT_Outline_Decompose),F(FT_Outline_Done),F(FT_Outline_EmboldenXY),
        F(FT_Outline_Get_Bitmap),F(FT_Outline_New),F(FT_Outline_Transform),F(FT_Outline_Translate),
        F(FT_Set_Pixel_Sizes)};
#undef F
    if(handle!=(void *)handle_name || !name) return NULL;
    for(unsigned n=0;n<sizeof(table)/sizeof(table[0]);++n)
        if(!strcmp(name,table[n].name)) return table[n].function;
    return NULL;
}

int pw_dwrite_dlclose(void *handle)
{
    return handle==(void *)handle_name?0:-1;
}
