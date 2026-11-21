/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Included in the external GPL loader adaptation; no fake success on missing PIDs. */
static int orbisdesk_adopt_child(pid_t pid,char *const argv[])
{
  char *end=0;long value=strtol(argv[1]+16,&end,10);
  if(!end || *end || value<=0 || value>0x7fffffff || value==pid)return 0;
  pid_t owner=(pid_t)value;unsigned char caps[16]={0};
  intptr_t root=kernel_get_proc_rootdir(owner),jail=kernel_get_proc_jaildir(owner),prison=kernel_get_ucred_prison(owner);
  pw_loader_stage("self_owner_pid",owner);pw_loader_stage("self_child_pid",pid);
  if(!root || !jail || !prison || !kernel_get_proc_rootdir(pid) || !kernel_get_ucred_prison(pid)){
    pw_loader_stage("self_context_missing",1);return 0;
  }
  int rc=kernel_set_proc_rootdir(pid,root);pw_loader_stage("self_root_set",rc);if(rc)return 0;
  rc=kernel_set_proc_jaildir(pid,jail);pw_loader_stage("self_jail_set",rc);if(rc)return 0;
  rc=kernel_set_ucred_prison(pid,prison);pw_loader_stage("self_prison_set",rc);if(rc)return 0;
  rc=kernel_set_ucred_uid(pid,0);pw_loader_stage("self_uid_set",rc);if(rc)return 0;
  if(kernel_get_ucred_caps(pid,caps))return 0;
  caps[5]=0x1c;caps[7]=0x40;caps[15]|=0x40;
  if(kernel_set_ucred_caps(pid,caps) || kernel_set_ucred_authid(pid,0x3801000000000013l))return 0;
  int match=kernel_get_proc_rootdir(pid)==root && kernel_get_proc_jaildir(pid)==jail && kernel_get_ucred_prison(pid)==prison;
  pw_loader_stage("self_context_readback",match);return match;
}
static int orbisdesk_self_files(const char *image)
{
  const char *fios="/app0/sce_module/libSceFios2.prx";
  int fd=open(fios,O_RDONLY);int error=fd<0?errno:0;
  pw_loader_stage("self_fios_open_errno",error);
  klog_printf("P011 child %d FiOS open=%d errno=%d\n",getpid(),fd,error);
  if(fd<0)return 0;
  close(fd);
  fd=open(image,O_RDONLY);error=fd<0?errno:0;
  pw_loader_stage("self_image_open_errno",error);
  klog_printf("P011 child %d image open=%d errno=%d\n",getpid(),fd,error);
  if(fd<0)return 0;
  close(fd);return 1;
}
