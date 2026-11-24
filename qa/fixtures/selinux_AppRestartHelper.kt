package com.waenhancer.xposed.utils
/** No shell, su, device, network or other process is invoked by this double. */
object AppRestartHelper {
    var response: String? = "Enforcing"
    var fail = false
    val commands = mutableListOf<String>()
    val threads = mutableListOf<String>()
    @JvmStatic fun runRootCommand(command: String): String? {
        commands.add(command)
        threads.add(Thread.currentThread().name)
        check(command == "getenforce") { "Unexpected command: $command" }
        check(Thread.currentThread().name == "selinux-qa-io") { "Root call from UI surrogate" }
        if (fail) throw IllegalStateException("fixture root runner failure")
        return response
    }
}
