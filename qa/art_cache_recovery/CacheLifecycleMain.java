package org.lab.waex.qa.artcache;

import android.os.Build;
import android.os.Process;
import android.system.Os;
import android.system.OsConstants;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONObject;

/** A new cache lifecycle fixture. It never links or invokes a canonical workload. */
public final class CacheLifecycleMain {
    private static final String PRODUCER_HEAD = "__PRODUCER_HEAD__";
    private static final String PRODUCER_RUN = "__PRODUCER_RUN__";
    private static final String PRODUCER_ATTEMPT = "__PRODUCER_ATTEMPT__";

    private static void require(boolean ok, String message) {
        if (!ok) throw new IllegalStateException(message);
    }

    private static byte[] bounded(String path, int limit) throws Exception {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        try (FileInputStream stream = new FileInputStream(path)) {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                require(result.size() + count <= limit, "Input exceeded its byte bound");
                result.write(buffer, 0, count);
            }
        }
        return result.toByteArray();
    }

    private static String hex(byte[] raw) {
        char[] alphabet = "0123456789abcdef".toCharArray();
        StringBuilder result = new StringBuilder(raw.length * 2);
        for (byte value : raw) {
            result.append(alphabet[(value & 255) >>> 4]);
            result.append(alphabet[value & 15]);
        }
        return result.toString();
    }

    private static String digest(byte[] raw) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(raw));
    }

    private static String boot() throws Exception {
        String value = new String(bounded("/proc/sys/kernel/random/boot_id", 128),
                                  StandardCharsets.US_ASCII).trim();
        require(value.matches("[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"), "Malformed kernel boot");
        return value;
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 10, "Ten explicit identity arguments required");
        String target = args[0], nonce = args[1];
        require(target.equals("api27") || target.equals("api28"), "Only cache profiles27/28 admitted");
        int sdk = Integer.parseInt(target.substring(3));
        require(nonce.matches("[0-9a-f]{32}"), "Malformed nonce");
        require(PRODUCER_HEAD.matches("[0-9a-f]{40}") && PRODUCER_HEAD.equals(args[9])
                && PRODUCER_RUN.matches("[1-9][0-9]*") && PRODUCER_RUN.equals(args[7])
                && PRODUCER_ATTEMPT.equals("1") && PRODUCER_ATTEMPT.equals(args[8]), "Producer differs");
        String before = boot();
        require(before.equals(args[2]), "Boot differs before probe");
        require(Build.VERSION.SDK_INT == sdk && Build.FINGERPRINT.equals(args[3])
                && Build.HARDWARE.equals("ranchu"), "Image identity differs");
        require(Process.myUid() == 2000 && Process.myPid() > 0 && Process.is64Bit(), "Process identity differs");
        long pageSize = Os.sysconf(OsConstants._SC_PAGESIZE);
        require(pageSize == 4096L, "Application page size differs");
        String executable = Os.readlink("/proc/self/exe");
        require(executable.equals("/system/bin/app_process64"), "Unexpected executable");
        byte[] elf = new byte[64];
        try (FileInputStream stream = new FileInputStream("/proc/self/exe")) {
            int offset = 0;
            while (offset < elf.length) {
                int count = stream.read(elf, offset, elf.length - offset);
                require(count > 0, "Truncated ELF identity");
                offset += count;
            }
        }
        require(elf[0] == 127 && elf[1] == 'E' && elf[2] == 'L' && elf[3] == 'F'
                && elf[4] == 2 && elf[5] == 1 && elf[6] == 1 && elf[18] == 62 && elf[19] == 0
                && (elf[16] == 2 || elf[16] == 3) && elf[17] == 0
                && elf[20] == 1 && elf[21] == 0 && elf[22] == 0 && elf[23] == 0
                && elf[52] == 64 && elf[53] == 0, "Not an ELF64 little-endian x86_64 process");
        String expectedPath = "/data/local/tmp/waex-art-cache-probe-" + nonce + "/probe.jar";
        require(args[4].equals(expectedPath) && System.getProperty("java.class.path").equals(expectedPath),
                "Classpath must contain only the new probe JAR");
        File file = new File(expectedPath);
        require(file.isFile() && file.getCanonicalPath().equals(expectedPath), "Probe JAR is redirected");
        int expectedBytes = Integer.parseInt(args[6]);
        require(expectedBytes > 0 && expectedBytes <= 65536 && file.length() == expectedBytes,
                "Probe JAR byte count differs");
        byte[] jar = bounded(expectedPath, 65536);
        String jarDigest = digest(jar);
        require(jar.length == expectedBytes && args[5].matches("[0-9a-f]{64}")
                && jarDigest.equals(args[5]), "Probe JAR SHA differs");
        String after = boot();
        require(after.equals(before), "Boot changed during probe");
        JSONObject producer = new JSONObject().put("workflow_commit", PRODUCER_HEAD)
                .put("run_id", PRODUCER_RUN).put("attempt", PRODUCER_ATTEMPT);
        JSONObject report = new JSONObject().put("schema", "WAEX_ART_CACHE_PROCESS_IDENTITY_V1")
                .put("status", "PASS").put("target", target).put("nonce", nonce)
                .put("sdk_int", Build.VERSION.SDK_INT).put("is_64_bit", Process.is64Bit())
                .put("uid", Process.myUid()).put("pid", Process.myPid()).put("hardware", Build.HARDWARE)
                .put("fingerprint", Build.FINGERPRINT).put("executable", executable)
                .put("elf_header_hex", hex(elf)).put("elf_header_sha256", digest(elf))
                .put("application_page_size_bytes", pageSize)
                .put("page_size_method", "android.system.Os.sysconf(_SC_PAGESIZE)")
                .put("boot_id_before", before).put("boot_id_after", after)
                .put("jar_path", expectedPath).put("jar_bytes", jar.length).put("jar_sha256", jarDigest)
                .put("producer", producer).put("canonical_workload_invoked", false);
        System.out.println("WAEX_ART_CACHE_IDENTITY|" + report.toString());
    }
}
