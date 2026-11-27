#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Retired compiler rows must not consume slots or alter remaining overlay settings."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'native/hw_overlay.c').read_text()
def fn(name):
    start=source.rfind('\n',0,source.index(name+'('))+1
    brace=source.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]+'\n'
assert '[SEC_GRAPHICS]={IT_RENDER,IT_STRETCH,-1,-1,-1,-1,-1}' in source
assert 'IT_COMPILER' not in source and 'pw_compiler' not in source
code=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include "pw_compiler_policy.h"
#include "pw_overlay_profiles.h"
static struct pw_profiles profile_history;
#define CONFIG_FILE "overlay.ini"
enum {LANG_ES,LANG_EN,LANGS,STRINGS=1,CURSOR_GAME=0,CURSOR_ALWAYS=1,CURSOR_HIDDEN=2,CURSOR_MODES=3,CURSOR_SAVED=64,FPS_DEFAULT=30,FPS_CHOICES=4,TYPES=2};
enum {S_T_COMPILER_NO_PROGRAM=1,S_T_COMPILER_FAILED,S_T_COMPILER_SAVED};
static const char *lang_words[]={"es","en"},*cursor_words[]={"game","always","hidden"},*fps_words[]={"off","30","60","auto"},*type_words[]={"generic","x360"};
static const int fps_values[]={0,30,60,-1};
static const char *strings[2][1]={{"es"},{"en"}};
static struct {char name[64];int mode,stretch,fps,fg,pad,swapsticks,swapbuttons;} cursor_saved[64];
static int cursor_saved_count,compiler_choice,compiler_saved,lang,lang_choice,toast;
static char cursor_program[64];
static const char *str(int id){return id==S_T_COMPILER_SAVED?"saved":id==S_T_COMPILER_FAILED?"failed":"no program";}
static void set_toast(const char *s){toast=!strcmp(s,"saved")?3:!strcmp(s,"failed")?2:1;}
static int fail_rename;
static int replace_file(const char *a,const char *b){if(fail_rename){errno=EACCES;return -1;}return rename(a,b);}
#define rename replace_file
'''+''.join(fn(n) for n in ('fps_index','cursor_slot','read_config','write_config','save_config'))+r'''
static void load(void){cursor_saved_count=0;memset(cursor_saved,0,sizeof(cursor_saved));read_config();}
int main(void){
 FILE *f=fopen(CONFIG_FILE,"w");assert(f);
 for(int i=0;i<130;i++)fprintf(f,"compiler.old%d.exe=2\n",i);
 fputs("lang=es\ncursor.game.exe=hidden\nfpslimit.game.exe=60\nframegen.game.exe=on\npad.game.exe=x360\nstretch.game.exe=on\ncompiler.game.exe=2\n",f);fclose(f);
 load();int a=cursor_slot("GAME.exe",0);assert(a>=0&&cursor_saved_count==1);
 assert(cursor_saved[a].mode==CURSOR_HIDDEN&&cursor_saved[a].fps==60&&cursor_saved[a].fg&&cursor_saved[a].pad==1&&cursor_saved[a].stretch);
 fail_rename=1;assert(!save_config(LANG_EN));load();assert(lang==LANG_ES);
 fail_rename=0;assert(save_config(LANG_EN));load();assert(lang==LANG_EN);a=cursor_slot("game.exe",0);
 f=fopen(CONFIG_FILE,"r");char text[4096];size_t n=fread(text,1,sizeof(text)-1,f);text[n]=0;fclose(f);
 assert(!strstr(text,"compiler."));
 assert(cursor_saved[a].mode==CURSOR_HIDDEN&&cursor_saved[a].fg&&cursor_saved[a].fps==60);
 puts("PASS: retired compiler rows ignored without slot exhaustion, removed on save; language, FPS, FG, input and cursor preserved; failed atomic save preserves disk");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie','-I'+str(root/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
    subprocess.run([str(p/'check')],cwd=p,check=True,timeout=10)
