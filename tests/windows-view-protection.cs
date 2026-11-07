using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class WindowsViewProtectionProbe {
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr CreateFileMappingW(IntPtr file, IntPtr attributes, uint protection,
                                           uint high, uint low, string name);
    [DllImport("kernelbase.dll", SetLastError=true)]
    static extern IntPtr MapViewOfFile3(IntPtr mapping, IntPtr process, IntPtr address,
                                       ulong offset, UIntPtr bytes, uint allocation,
                                       uint protection, IntPtr parameters, uint count);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool VirtualProtect(IntPtr address, UIntPtr bytes, uint protection, out uint old);
    [DllImport("kernel32.dll")] static extern bool UnmapViewOfFile(IntPtr address);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();

    public static string Run(bool executableView) {
        const uint rw=4, rwx=0x40, rx=0x20;
        IntPtr section=CreateFileMappingW(new IntPtr(-1), IntPtr.Zero, rwx, 0, 0x10000, null);
        if(section==IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        IntPtr view=IntPtr.Zero;
        try {
            view=MapViewOfFile3(section,GetCurrentProcess(),IntPtr.Zero,0,new UIntPtr(0x10000),0,
                                executableView ? rwx : rw,IntPtr.Zero,0);
            if(view==IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            uint old;
            if(executableView && !VirtualProtect(view,new UIntPtr(0x4000),rw,out old))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            Marshal.WriteInt32(view,42);
            bool success=VirtualProtect(view,new UIntPtr(0x4000),rx,out old);
            int error=success ? 0 : Marshal.GetLastWin32Error();
            return String.Format("initial_view={0}; RW_to_RX={1}; win32_error={2}; value={3}",
                                 executableView ? "RWX_then_RW" : "RW",success,error,Marshal.ReadInt32(view));
        } finally {
            if(view!=IntPtr.Zero) UnmapViewOfFile(view);
            CloseHandle(section);
        }
    }
}
