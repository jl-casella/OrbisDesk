/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Actual native overlay rendering; shared by host preview and console. */
static void draw_profiles(const struct surface *s)
{
    enum {W=760,H=488,ROW=44,VISIBLE=8};
    int x=(s->width-W)/2,y=(s->height-H)/2;
    char line[96];
    box(s,x,y,W,H,C_PANEL,C_EDGE);
    text(s,x+20,y+18,str(S_PROFILE_TITLE),C_TEXT,3);
    snprintf(line,sizeof(line),"%d / %d",profile_row+1,profile_rows_count+1);
    text(s,x+W-20-text_width(line,2),y+24,line,C_DIM,2);
    for(int row=profile_scroll;row<profile_rows_count+1 && row<profile_scroll+VISIBLE;row++) {
        int at=y+64+(row-profile_scroll)*ROW;
        if(row==profile_row) fill(s,x+12,at,W-24,ROW-4,C_SELECTED);
        if(row==profile_rows_count) text(s,x+24,at+12,str(S_PROFILE_ADD),C_EDGE,2);
        else {
            const struct pw_profile *p=&profile_rows[row];
            const char *status=str(profile_running(p->name)?S_PROFILE_RUNNING:S_PROFILE_CLOSED);
            /* 63 bytes at scale 1 always fit; long names keep their full identity. */
            text(s,x+24,at+7,p->name,C_TEXT,strlen(p->name)>42?1:2);
            snprintf(line,sizeof(line),"%s%s",status,p->bits==64?"  64-bit":p->bits==32?"  32-bit":"");
            text(s,x+24,at+27,line,C_DIM,1);
        }
    }
    text(s,x+20,y+H-52,str(S_PROFILE_PICK_FOOT),C_TEXT,1);
    text(s,x+20,y+H-30,str(S_PROFILE_NAME_HELP),C_DIM,1);
}
