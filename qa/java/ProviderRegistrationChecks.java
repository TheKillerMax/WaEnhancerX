package com.waenhancer.xposed.bridge;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** JDK-only doubles: executes the extracted production registration branch.
 * Not a Binder, Android filesystem, or SharedPreferences durability test.
 */
public final class ProviderRegistrationChecks {
    private static final String AUTHORITY = "test.provider";
    private static int checks;
    static void check(boolean ok, String why) {
        checks++;
        if (!ok) throw new AssertionError(why);
    }

    static final class Bundle {
        final Map<String, Object> values = new HashMap<>();
        String getString(String key) { return (String) values.get(key); }
        int getInt(String key, int fallback) { return (int) values.getOrDefault(key, fallback); }
        void putBoolean(String key, boolean value) { values.put(key, value); }
    }
    static final class Uri {
        static String parse(String value) { return value; }
    }
    static final class Prefs {
        final Map<String, Object> saved = new HashMap<>();
        final boolean commitResult;
        int editors, commits, notifications;
        boolean committed;
        Prefs(boolean result) { commitResult = result; }
        Set<String> getStringSet(String key, Set<String> fallback) { return fallback; }
        Editor edit() { editors++; return new Editor(this); }
    }
    static final class Editor {
        final Prefs prefs;
        final Map<String, Object> changes = new HashMap<>();
        Editor(Prefs p) { prefs = p; }
        void putStringSet(String key, Set<String> value) { changes.put(key, new HashSet<>(value)); }
        void putLong(String key, long value) { changes.put(key, value); }
        void putInt(String key, int value) { changes.put(key, value); }
        void putString(String key, String value) { changes.put(key, value); }
        boolean commit() {
            prefs.commits++;
            prefs.committed = prefs.commitResult;
            if (prefs.committed) prefs.saved.putAll(changes);
            return prefs.commitResult;
        }
    }
    static final class Context {
        final Prefs prefs;
        final String[] packages;
        Context(Prefs prefs, String... packages) {
            this.prefs = prefs;
            this.packages = packages;
        }
        Context getContentResolver() { return this; }
        void notifyChange(String uri, Object observer) {
            check(prefs.committed, "notification before acknowledged commit");
            check(uri.equals("content://" + AUTHORITY + "/runtime_health"), "changed notification route");
            prefs.notifications++;
        }
    }
    static boolean callerOwnsPackage(Context context, int callerUid, String pkg) {
        return CallerScopePolicy.ownsPackage(callerUid, 20000, context.packages, pkg);
    }

    static Bundle register(String method, String arg, Bundle extras, Context context,
                           Prefs prefs, int callerUid, int callerPid) {
        // PRODUCTION_REGISTRATION_BRANCH
        return null;
    }

    public static void main(String[] args) {
        final String pkg = "com.whatsapp";
        for (boolean persisted : new boolean[]{false, true}) {
            for (boolean fromExtras : new boolean[]{false, true}) {
                Prefs prefs = new Prefs(persisted);
                Context context = new Context(prefs, pkg);
                Bundle extras = new Bundle();
                extras.values.put("package", pkg);
                extras.values.put("boot_count", 12);
                Bundle result = register("register_hooked_package", fromExtras ? null : pkg,
                        extras, context, prefs, 21000, 4242);
                check(result != null, "missing registration acknowledgement");
                check(result.values.get("success").equals(persisted), "false persistence acknowledgement");
                check(prefs.editors == 1 && prefs.commits == 1, "expected one registration transaction");
                check(prefs.notifications == (persisted ? 1 : 0), "incorrect notification count");
                if (persisted) {
                    check(prefs.saved.get("runtime_pid_" + pkg).equals(4242), "caller PID not retained");
                    check(prefs.saved.get("runtime_boot_" + pkg).equals(12), "boot counter not retained");
                    check(prefs.saved.get("runtime_status_" + pkg).equals("INJECTED"), "status changed");
                    check(prefs.saved.get("hooked_whatsapp_packages").equals(Set.of(pkg)), "package set changed");
                }
            }
        }
        Prefs rejected = new Prefs(true);
        Context other = new Context(rejected, "com.whatsapp.w4b");
        check(register("register_hooked_package", pkg, null, other, rejected, 21001, 99) == null,
                "other package accepted");
        check(register("register_hooked_package", null, null, other, rejected, 21001, 99) == null,
                "absent package accepted");
        check(rejected.editors == 0 && rejected.commits == 0 && rejected.notifications == 0,
                "rejected caller caused effects");
        System.out.println("PASS: " + checks + " registration persistence/ownership/notification assertions");
    }
}
