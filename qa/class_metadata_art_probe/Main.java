package org.lab.waex.qa.classmetadata;
import android.os.Build;
import android.os.Process;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.ref.WeakReference;
import java.util.Map;
import java.util.WeakHashMap;

/** Narrow neutral ART class-linkage probe: never installs a hook or touches a host account. */
public final class Main {
    private static final String JID = "com.waenhancer.xposed.core.wa.WaJid";
    private static final String RECEIPTS = "com.waenhancer.xposed.features.privacy.HideReceiptsHook";
    private static int checks;
    public static final class SyntheticJid {
        public String getRawString() { return "123.4:5@s.whatsapp.net"; }
    }
    public static final class NoGetter {}
    private static void check(boolean b, String label) {
        if (!b) throw new AssertionError(label);
        checks++;
    }
    private static boolean isClassValueLinkage(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            String m = t.getMessage();
            if ((t instanceof NoClassDefFoundError || t instanceof ClassNotFoundException)
                    && m != null && (m.contains("java/lang/ClassValue") || m.contains("java.lang.ClassValue"))) {
                return true;
            }
            if (t.getCause() == t) break;
        }
        return false;
    }
    private static Class<?> load(String name, boolean shouldFail) throws Exception {
        Class<?> type;
        try {
            type = Class.forName(name, true, Main.class.getClassLoader());
        } catch (LinkageError error) {
            if (!shouldFail || !isClassValueLinkage(error)) throw error;
            checks++;
            System.out.println("CLASS|" + name + "|EXPECTED_CLASSVALUE_LINKAGE_ERROR");
            return null;
        }
        check(!shouldFail && type.getClassLoader() == Main.class.getClassLoader(),
                "exact class loader or expected failure: " + name);
        System.out.println("CLASS|" + name + "|INITIALIZED");
        return type;
    }
    private static Object field(Class<?> type, String name) throws Exception {
        Field f = type.getDeclaredField(name); f.setAccessible(true); return f.get(null);
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !args[0].matches("[a-f0-9]{32}")
                || !(args[1].equals("baseline") || args[1].equals("candidate")))
            throw new IllegalArgumentException("nonce, variant, API required");
        String nonce = args[0], variant = args[1];
        int api = Integer.parseInt(args[2]);
        check(api == Build.VERSION.SDK_INT && api >= 24 && api <= 37,
                "expected real SDK");
        check(Process.myUid() == 2000 && ("ranchu".equals(Build.HARDWARE)
                || "goldfish".equals(Build.HARDWARE)), "isolated emulator shell only");
        check(Class.forName("java.lang.String", true, null) == String.class, "boot class control");
        boolean classValuePresent;
        try { Class.forName("java.lang.ClassValue", false, null); classValuePresent = true; }
        catch (ClassNotFoundException absent) { classValuePresent = false; }
        check(classValuePresent == (api >= 34), "real ClassValue API boundary");
        System.out.println("API|" + api + "|CLASSVALUE|" + classValuePresent);
        boolean failBaseline = variant.equals("baseline") && api < 34;
        Class<?> jid = load(JID, failBaseline), receipts = load(RECEIPTS, failBaseline);
        if (!failBaseline) {
            Method raw = jid.getDeclaredMethod("raw", Object.class);
            check("123@s.whatsapp.net".equals(raw.invoke(null, new SyntheticJid())), "typed raw");
            check("456@lid".equals(raw.invoke(null, "456:9@lid")), "string raw");
            check(raw.invoke(null, "missing-domain") == null, "invalid raw");
            check(raw.invoke(null, new NoGetter()) == null, "negative lookup");
            Object rawCache = field(jid, "RAW_STRING");
            Object keyCache = field(receipts, "MESSAGE_KEY_FIELDS");
            if (variant.equals("candidate")) {
                check(rawCache instanceof WeakHashMap && keyCache instanceof WeakHashMap, "weak class keys");
                Object cached = ((Map<?,?>)rawCache).get(SyntheticJid.class);
                check(cached instanceof WeakReference, "weak method metadata");
                check(field(jid, "NO_RAW_STRING") instanceof WeakReference, "negative marker");
            } else {
                Class<?> cv = Class.forName("java.lang.ClassValue", false, null);
                check(cv.isInstance(rawCache), "baseline raw ClassValue");
                check(cv.isInstance(keyCache), "baseline fields ClassValue");
            }
        }
        int expected = failBaseline ? 6 : variant.equals("candidate") ? 13 : 12;
        check(checks == expected, "exact checks before finish");
        System.out.println("WAEX_CLASS_METADATA_ART|" + nonce + "|" + variant + "|" + api + "|" + checks + "|PASS");
    }
}
