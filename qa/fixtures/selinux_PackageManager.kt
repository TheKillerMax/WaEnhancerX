package android.content.pm
class ApplicationInfo
class PackageInfo {
    val versionName: String? = "fixture"
    val versionCode = 1
    val longVersionCode = 1L
    val applicationInfo: ApplicationInfo? = ApplicationInfo()
}
class PackageManager {
    fun getPackageInfo(name: String, flags: Int): PackageInfo {
        check(flags == 0)
        if (name != "com.waenhancer.fixture") throw IllegalArgumentException("No fixture package: $name")
        return PackageInfo()
    }
    fun getApplicationLabel(info: ApplicationInfo): CharSequence = "fixture"
}
