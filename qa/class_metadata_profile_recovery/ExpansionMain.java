package org.lab.waex.qa.classmetadata.expansion;

import android.os.Build;
import android.os.Process;
import android.system.Os;
import android.system.OsConstants;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONObject;

/** Identity wrapper only. The two canonical workload DEX JARs remain byte-for-byte unchanged. */
public final class ExpansionMain {
    private static int identityChecks;
    private static final String ORIGINAL_MANIFEST = "76c2a3397d81bab85e341fc4c7adba5618e5b27afd70b8b391bd886b64702191";
    private static final String BASELINE = "3e6378e13dee4ac9af960dcda75ed92f5d314fa6736aee4c996888d9151a9fa8";
    private static final String CANDIDATE = "44526934c737ed2e53376560e4474013896f0f2dee19d111e13fbbd766d1c47e";
    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }
    private static void check(boolean condition, String label) {
        require(condition, label);
        identityChecks++;
    }
    private static String hex(byte[] data) {
        StringBuilder text = new StringBuilder(data.length * 2);
        for (byte value : data) text.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return text.toString();
    }
    private static byte[] boundedRead(String name, int bound) throws Exception {
        try (FileInputStream stream = new FileInputStream(name);
             ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[Math.min(8192, bound + 1)];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                require(bytes.size() + count <= bound, "bounded read: " + name);
                bytes.write(buffer, 0, count);
            }
            return bytes.toByteArray();
        }
    }
    private static String boot() throws Exception {
        String value = new String(boundedRead("/proc/sys/kernel/random/boot_id", 64), StandardCharsets.US_ASCII).trim();
        require(value.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "boot ID shape");
        return value;
    }
    private static byte[] elfHeader() throws Exception {
        byte[] header = new byte[64];
        int offset = 0;
        try (FileInputStream stream = new FileInputStream("/proc/self/exe")) {
            while (offset < header.length) {
                int count = stream.read(header, offset, header.length - offset);
                require(count > 0, "complete own ELF header");
                offset += count;
            }
        }
        return header;
    }
    private static int u16(byte[] header, int offset) {
        return (header[offset] & 255) | ((header[offset + 1] & 255) << 8);
    }
    private static String hashJar(String path) throws Exception {
        File file = new File(path);
        require(file.isFile() && file.length() > 0 && file.length() <= 8 * 1024 * 1024, "bounded own JAR");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream stream = new FileInputStream(file)) {
            byte[] buffer = new byte[8192];
            long total = 0;
            int count;
            while ((count = stream.read(buffer)) != -1) {
                total += count;
                require(total <= 8 * 1024 * 1024, "JAR changed beyond bound");
                digest.update(buffer, 0, count);
            }
            require(total == file.length(), "stable JAR length");
        }
        return hex(digest.digest());
    }
    private static void target(String name, int api, int minor, int pages) {
        require(name.matches("api(?:26|29|35|36|35-16k|36-16k|36\\.1-16k|37-16k)"),
                "only eight pending ART recovery profiles");
        String label = name.substring(3).replace("-16k", "");
        String[] parts = label.split("\\.");
        require(api == Integer.parseInt(parts[0]) && minor == (parts.length == 2 ? Integer.parseInt(parts[1]) : 0)
                && pages == (name.endsWith("-16k") ? 16384 : 4096), "target tuple");
    }
    public static void main(String[] args) throws Exception {
        require(args.length == 18, "eighteen identity arguments required");
        String nonce = args[0], variant = args[1], target = args[2];
        int api = Integer.parseInt(args[3]), expectedMinor = Integer.parseInt(args[4]), expectedPages = Integer.parseInt(args[5]);
        String expectedBoot = args[6], run = args[7], attempt = args[8], head = args[9];
        String producer = args[10], original = args[11], driverPath = args[12], driverSha = args[13];
        String canonicalPath = args[14], canonicalSha = args[15], phaseNonce = args[17];
        require(nonce.matches("[0-9a-f]{32}") && phaseNonce.matches("[0-9a-f]{32}")
                && !nonce.equals(phaseNonce) && (variant.equals("baseline") || variant.equals("candidate")), "nonce/variant");
        require(run.matches("[1-9][0-9]*") && attempt.equals("1") && head.matches("[0-9a-f]{40}")
                && producer.matches("[0-9a-f]{64}") && original.equals(ORIGINAL_MANIFEST)
                && driverSha.matches("[0-9a-f]{64}") && canonicalSha.matches("[0-9a-f]{64}"), "producer identities");
        target(target, api, expectedMinor, expectedPages);
        require(!target.equals("api35-16k") || variant.equals("candidate"), "previous API35-16k baseline must not repeat");
        String expectedFingerprint = new String(Base64.decode(args[16], Base64.NO_WRAP), StandardCharsets.UTF_8);
        require(expectedFingerprint.length() > 0 && expectedFingerprint.length() <= 1024, "fingerprint bound");
        check(Build.VERSION.SDK_INT == api, "own major SDK");
        check(Process.myUid() == 2000 && ("ranchu".equals(Build.HARDWARE) || "goldfish".equals(Build.HARDWARE)), "owned emulator shell");
        boolean is64Bit = Process.is64Bit();
        check(is64Bit, "own process is 64 bit");
        byte[] header = elfHeader();
        String executable = Os.readlink("/proc/self/exe");
        check(header[0] == 127 && header[1] == 'E' && header[2] == 'L' && header[3] == 'F'
                && header[4] == 2 && header[5] == 1 && header[6] == 1
                && (u16(header, 16) == 2 || u16(header, 16) == 3) && u16(header, 18) == 62
                && header[20] == 1 && header[21] == 0 && header[22] == 0 && header[23] == 0
                && u16(header, 52) == 64 && executable.matches("/(?:system/bin|apex/com\\.android\\.(?:runtime|art)/bin)/app_process64"),
                "own ELF64 little endian EM_X86_64 executable");
        long pages = Os.sysconf(OsConstants._SC_PAGESIZE);
        check(pages == expectedPages, "own application-facing page size");
        Integer full = null, fullMajor = null, fullMinor = null;
        if (api >= 36) {
            full = Build.VERSION.class.getField("SDK_INT_FULL").getInt(null);
            fullMajor = (Integer) Build.class.getMethod("getMajorSdkVersion", int.class).invoke(null, full);
            fullMinor = (Integer) Build.class.getMethod("getMinorSdkVersion", int.class).invoke(null, full);
            check(full > 0 && fullMajor == api && fullMinor == expectedMinor, "own SDK_INT_FULL helpers");
        } else {
            check(expectedMinor == 0, "legacy profile has no minor SDK field requirement");
        }
        String before = boot();
        check(before.equals(expectedBoot), "own boot before workload");
        check(Build.FINGERPRINT.equals(expectedFingerprint), "own fingerprint");
        String directory = "/data/local/tmp/waex-art-recovery-" + phaseNonce;
        check(driverPath.equals(directory + "/driver.jar") && canonicalPath.equals(directory + "/" + variant + ".jar")
                && (driverPath + ":" + canonicalPath).equals(System.getenv("CLASSPATH")), "exact own classpath");
        String observedDriverSha = hashJar(driverPath);
        check(observedDriverSha.equals(driverSha), "executed driver JAR identity");
        String observedCanonicalSha = hashJar(canonicalPath);
        check(observedCanonicalSha.equals(canonicalSha) && canonicalSha.equals(variant.equals("baseline") ? BASELINE : CANDIDATE),
                "executed canonical JAR identity");
        Class<?> main = Class.forName("org.lab.waex.qa.classmetadata.Main", true, ExpansionMain.class.getClassLoader());
        check(main.getClassLoader() == ExpansionMain.class.getClassLoader(), "canonical Main uses exact shared classloader");
        Method method = main.getMethod("main", String[].class);
        try {
            method.invoke(null, (Object) new String[] {nonce, variant, Integer.toString(api)});
        } catch (InvocationTargetException error) {
            Throwable cause = error.getCause();
            if (cause instanceof Error) throw (Error) cause;
            if (cause instanceof Exception) throw (Exception) cause;
            throw error;
        }
        String after = boot();
        check(after.equals(before), "own boot stable after workload");
        require(identityChecks == 13, "identity check count");
        JSONObject expected = new JSONObject();
        expected.put("run_id", run).put("attempt", attempt).put("workflow_commit", head)
                .put("producer_manifest_sha256", producer).put("canonical_manifest_sha256", original)
                .put("boot_id", expectedBoot).put("fingerprint", expectedFingerprint);
        JSONObject row = new JSONObject();
        row.put("schema", "WAEX_ART_PROFILE_IDENTITY_V1").put("status", "PASS").put("nonce", nonce)
                .put("phase_nonce", phaseNonce).put("variant", variant).put("target", target)
                .put("sdk_int", Build.VERSION.SDK_INT).put("sdk_int_full_field_read", api >= 36)
                .put("sdk_int_full", full == null ? JSONObject.NULL : full)
                .put("sdk_full_major", fullMajor == null ? JSONObject.NULL : fullMajor)
                .put("sdk_full_minor", fullMinor == null ? JSONObject.NULL : fullMinor)
                .put("sdk_full_helpers_called", api >= 36).put("expected_minor", expectedMinor)
                .put("legacy_minor_zero_from_profile_only", api < 36)
                .put("is_64_bit", is64Bit).put("elf_class", 64).put("elf_machine", 62).put("elf_endian", "little")
                .put("elf_header_hex", hex(header)).put("elf_header_sha256", hex(MessageDigest.getInstance("SHA-256").digest(header)))
                .put("executable", executable).put("application_page_size_bytes", pages)
                .put("page_size_method", "android.system.Os.sysconf(_SC_PAGESIZE)")
                .put("uid", Process.myUid()).put("pid", Process.myPid()).put("hardware", Build.HARDWARE)
                .put("fingerprint", Build.FINGERPRINT).put("boot_id_before", before).put("boot_id_after", after)
                .put("driver_path", driverPath).put("driver_sha256", observedDriverSha).put("driver_bytes", new File(driverPath).length())
                .put("canonical_path", canonicalPath).put("canonical_sha256", observedCanonicalSha)
                .put("canonical_bytes", new File(canonicalPath).length())
                .put("canonical_invocation_returned", true).put("canonical_workload_modified", false)
                .put("identity_checks", identityChecks).put("host_expected", expected);
        System.out.println("WAEX_ART_PROFILE_IDENTITY_V1|" + row.toString());
    }
}
