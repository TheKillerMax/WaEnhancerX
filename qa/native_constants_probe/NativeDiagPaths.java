package com.waenhancer.utils;

/** JNI declarations only. Returned strings are data; this probe never executes them. */
public final class NativeDiagPaths {
    private NativeDiagPaths() {}
    public static native String lspConfigDb();
    public static native String hmaZygiskPath();
    public static native String[] knownHmaPackages();
    public static native String[] knownHmaConfigPaths();
    public static native String hmaActiveCheckCommand();
    public static native String lspHmaCheckCommand();
    public static native String hmaShallowSearchCommand();
    public static native String hmaConfigGlobCommand();
    public static native String lspLogGlob();
    public static native String magiskVersionCommand();
    public static native String magiskDenylistStatusCommand();
    public static native String magiskDenylistListCommand();
    public static native String magiskDenylistRemovePrefix();
    public static native String magiskDenylistRemoveSuffix();
}
