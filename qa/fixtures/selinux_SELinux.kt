package android.os
/** Models the documented boolean boundary; does not simulate Android SELinux policy. */
object SELinux {
    var enforced = false
    var fail = false
    var calls = 0
    @JvmStatic fun isSELinuxEnforced(): Boolean {
        calls++
        if (fail) throw IllegalAccessException("fixture hidden/native API unavailable")
        return enforced
    }
}
