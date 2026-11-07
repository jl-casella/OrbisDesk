$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot/..").Path
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class LifecycleDebug {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {
  public int cb; public string reserved,desktop,title; public int x,y,cx,cy,cols,rows,fill,flags;
  public short show,reserved2; public IntPtr reservedPtr,input,output,error;
 }
 [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr process,thread;public uint pid,tid; }
 [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcessW(string app,StringBuilder args,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref Startup startup,out ProcessInfo process);
 [DllImport("kernel32",SetLastError=true)] static extern bool WaitForDebugEvent(IntPtr data,uint ms);
 [DllImport("kernel32")] static extern bool ContinueDebugEvent(uint pid,uint tid,uint status);
 [DllImport("kernel32")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32",CharSet=CharSet.Unicode)] static extern uint GetFinalPathNameByHandleW(IntPtr h,StringBuilder path,uint length,uint flags);
 [DllImport("kernel32")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32")] static extern IntPtr OpenThread(uint access,bool inherit,uint tid);
 [DllImport("kernel32")] static extern bool Wow64GetThreadContext(IntPtr thread,IntPtr context);
 [DllImport("kernel32")] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] data,int size,out IntPtr read);
 public static string[] Run(string exe,string cwd) {
  var startup=new Startup{cb=Marshal.SizeOf(typeof(Startup))}; ProcessInfo pi;
  if(!CreateProcessW(exe,new StringBuilder("\""+exe+"\""),IntPtr.Zero,IntPtr.Zero,false,0x08000002,IntPtr.Zero,cwd,ref startup,out pi)) throw new Exception("CreateProcess "+Marshal.GetLastWin32Error());
  var buffer=Marshal.AllocHGlobal(176);var lines=new List<string>();var modules=new Dictionary<ulong,string>();
  var end=DateTime.UtcNow.AddSeconds(20);bool exited=false;
  try {
   while(DateTime.UtcNow<end) {
    if(!WaitForDebugEvent(buffer,1000)) continue;
    var b=new byte[176];Marshal.Copy(buffer,b,0,b.Length);
    uint type=BitConverter.ToUInt32(b,0),pid=BitConverter.ToUInt32(b,4),tid=BitConverter.ToUInt32(b,8);uint status=0x10002;
    if(type==3 || type==6) {
     ulong address=BitConverter.ToUInt64(b,type==3?40:24);var h=new IntPtr(BitConverter.ToInt64(b,16));var path=new StringBuilder(1024);
     GetFinalPathNameByHandleW(h,path,1024,0);modules[address]=path.ToString();lines.Add("load 0x"+address.ToString("x")+" "+path);if(h!=IntPtr.Zero)CloseHandle(h);
    }
    if(type==1) {
     uint code=BitConverter.ToUInt32(b,16);ulong address=BitConverter.ToUInt64(b,32),memory=BitConverter.ToUInt64(b,56);uint first=BitConverter.ToUInt32(b,168);
     string module="unknown";ulong best=0;foreach(var p in modules)if(p.Key<=address&&p.Key>=best){best=p.Key;module=p.Value;}
     lines.Add("exception 0x"+code.ToString("x")+" first="+first+" pc=0x"+address.ToString("x")+" memory=0x"+memory.ToString("x")+" module="+module+" offset=0x"+(address-best).ToString("x"));
     if(code==0xc0000005) {
      var thread=OpenThread(8,false,tid);var context=Marshal.AllocHGlobal(716);Marshal.WriteInt32(context,0x10007);
      if(Wow64GetThreadContext(thread,context))lines.Add("eax=0x"+Marshal.ReadInt32(context,176).ToString("x")+" ecx=0x"+Marshal.ReadInt32(context,172).ToString("x")+" reason=0x"+Marshal.ReadInt32(context,168).ToString("x")+" fs=0x"+Marshal.ReadInt32(context,144).ToString("x"));
      Marshal.FreeHGlobal(context);CloseHandle(thread);
      var data=new byte[24];IntPtr read;if(ReadProcessMemory(pi.process,new IntPtr((long)best+0x2000),data,24,out read))lines.Add("TLS="+BitConverter.ToString(data));
      data=new byte[8];if(ReadProcessMemory(pi.process,new IntPtr((long)best+0x3000),data,8,out read))lines.Add("index="+BitConverter.ToString(data));
      data=new byte[48];if(ReadProcessMemory(pi.process,new IntPtr((long)best+0x3020),data,48,out read))lines.Add("diagnostics="+BitConverter.ToString(data));
     }
     if(code!=0x80000003)status=0x80010001;
    }
    if(type==5){lines.Add("exit="+BitConverter.ToUInt32(b,16));exited=true;}
    ContinueDebugEvent(pid,tid,status);if(exited)break;
   }
   if(!exited){TerminateProcess(pi.process,254);lines.Add("timeout");}
  }finally{Marshal.FreeHGlobal(buffer);CloseHandle(pi.thread);CloseHandle(pi.process);}
  return lines.ToArray();
 }
}
'@
[LifecycleDebug]::Run((Join-Path $root 'out/lifecycle-host.exe'),(Join-Path $root 'out')) | Tee-Object -FilePath "$root/build/host/windows-lifecycle-debug.log"
