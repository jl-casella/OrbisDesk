/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Included by hw_overlay.c; callers hold the overlay lock. No file browser or guest keys. */
static int profile_running(const char *name)
{
    if(!name[0]) return 0;
    for(int i=0;i<program_count;i++) if(!strcasecmp(name,programs[i])) return 1;
    return 0;
}
static int profile_select(const char *name)
{
    if(!pw_profile_allowed(name)) return 0;
    /* Never discard an in-flight SET, nor allow a late GET to answer a new request. */
    if(render_request && (render_taken || render_request==RENDER_SET)) {
        set_toast(str(S_PROFILE_WAIT));return 0;
    }
    snprintf(edit_program,sizeof(edit_program),"%s",name);
    snprintf(render_program,sizeof(render_program),"%s",name);
    profile_default_pad=pad_default();
    render_saved=-1;render_choice=0;render_taken=render_error=0;render_request=RENDER_GET;
    render_deadline_us=sceKernelGetProcessTime()+RENDER_ANSWER_US;
    reset_choices();
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY profile selected exe=%s running=%d live=%d\n",name,profile_running(name),profile_live());
    return 1;
}
static void profile_editor_begin(void)
{
    const char *name=program_count && !desktop_front && pw_profile_allowed(cursor_program)?cursor_program:
        profile_history.count?profile_history.rows[0].name:"";
    if(!name[0]) {
        for(int i=0;i<cursor_saved_count;i++) if(pw_profile_allowed(cursor_saved[i].name)) {name=cursor_saved[i].name;break;}
    }
    if(!name[0]) {
        edit_program[0]=render_program[0]=0;profile_default_pad=pad_default();return;
    }
    profile_select(name);
}
static void profile_row_add(const char *name,int bits)
{
    if(!pw_profile_allowed(name)) return;
    for(int i=0;i<profile_rows_count;i++) if(!strcasecmp(name,profile_rows[i].name)) return;
    if(profile_rows_count==PROFILE_ROWS) return;
    struct pw_profile *row=&profile_rows[profile_rows_count++];
    snprintf(row->name,sizeof(row->name),"%s",name);row->bits=bits;
}
static void profile_picker_open(void)
{
    profile_rows_count=0;profile_row=0;profile_scroll=0;
    /* Snapshot order while the list is open; a guest exiting does not move the cursor. */
    for(int i=0;i<profile_history.count;i++) profile_row_add(profile_history.rows[i].name,profile_history.rows[i].bits);
    for(int i=0;i<cursor_saved_count;i++) profile_row_add(cursor_saved[i].name,0);
    for(int i=0;i<program_count;i++) profile_row_add(programs[i],0);
    for(int i=0;i<profile_rows_count;i++) if(!strcasecmp(edit_program,profile_rows[i].name)) profile_row=i;
    profile_scroll=profile_row>=8?profile_row-7:0;
    view=VIEW_PROFILES;
}
static void profile_picker_input(uint32_t pressed,uint32_t nav)
{
    if(nav&NAV_UP) profile_row=(profile_row+profile_rows_count)%(profile_rows_count+1);
    if(nav&NAV_DOWN) profile_row=(profile_row+1)%(profile_rows_count+1);
    if(profile_row<profile_scroll) profile_scroll=profile_row;
    if(profile_row>=profile_scroll+8) profile_scroll=profile_row-7;
    if(pressed&ORBIS_PAD_BUTTON_CIRCLE) {view=VIEW_PANEL;focus=FOCUS_PROFILE;return;}
    if(!(pressed&ORBIS_PAD_BUTTON_CROSS)) return;
    if(profile_row==profile_rows_count) {
        profile_name[0]=0;profile_caret=0;kb_row=1;kb_col=0;kb_page=kb_shift=0;view=VIEW_PROFILE_NAME;
    } else if(profile_select(profile_rows[profile_row].name)) {view=VIEW_PANEL;focus=FOCUS_PROFILE;}
}
static void profile_name_key(uint32_t vk,const char *label)
{
    size_t length=strlen(profile_name);
    if(vk==VK_ESCAPE) {view=VIEW_PROFILES;return;}
    if(vk==VK_LEFT) {if(profile_caret) profile_caret--;return;}
    if(vk==VK_RIGHT) {if(profile_caret<(int)length) profile_caret++;return;}
    if(vk==VK_HOME) {profile_caret=0;return;}
    if(vk==VK_END) {profile_caret=(int)length;return;}
    if(vk==VK_BACK || vk==VK_DELETE) {
        if(vk==VK_BACK) {if(!profile_caret) return;profile_caret--;}
        if(profile_caret<(int)length) memmove(profile_name+profile_caret,profile_name+profile_caret+1,length-(size_t)profile_caret);
        return;
    }
    if(vk==VK_RETURN) {
        if(!pw_profile_allowed(profile_name)) {set_toast(str(S_PROFILE_INVALID));return;}
        if(render_request && (render_taken || render_request==RENDER_SET)) {set_toast(str(S_PROFILE_WAIT));return;}
        struct pw_profiles previous=profile_history;
        pw_profiles_note(&profile_history,profile_name,0,0);
        if(!write_config(lang)) {profile_history=previous;set_toast(str(S_T_CONFIG_NOT_SAVED));return;}
        if(profile_select(profile_name)) {view=VIEW_PANEL;focus=FOCUS_PROFILE;}
        return;
    }
    /* Only printable characters produced by this keyboard enter the local buffer. */
    if(!label[0] || label[1] || (unsigned char)label[0]<32 || strchr("/\\:*?\"<>|=",label[0])) return;
    if(length>=sizeof(profile_name)-1) return;
    memmove(profile_name+profile_caret+1,profile_name+profile_caret,length-(size_t)profile_caret+1);
    profile_name[profile_caret++]=label[0];
}
