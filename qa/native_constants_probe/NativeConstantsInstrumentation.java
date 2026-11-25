package org.lab.waex.qa.nativeconstants;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.system.Os;
import android.system.OsConstants;
import com.waenhancer.utils.NativeDiagPaths;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Isolated loader/constant-return test. Never opens or executes a returned path or command. */
public final class NativeConstantsInstrumentation extends Instrumentation {
    private static final String PACKAGE = "org.lab.waex.qa.nativeconstants";
    private Bundle arguments;
    private JSONObject methods;
    private final JSONObject values = new JSONObject();
    private int calls;
    private int strings;
    private String phase = "arguments";
    private boolean loaded;

    @Override public void onCreate(Bundle input) {
        super.onCreate(input);
        arguments = input == null ? new Bundle() : new Bundle(input);
        start();
    }

    private static void require(boolean valid, String message) {
        if (!valid) throw new IllegalStateException(message);
    }

    private static byte[] readBounded(InputStream input, int limit) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        for (int count; (count = input.read(buffer)) != -1;) {
            require(output.size() + count <= limit, "input exceeds limit");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private static String sha(byte[] data) throws Exception {
        StringBuilder value = new StringBuilder();
        for (byte item : MessageDigest.getInstance("SHA-256").digest(data)) {
            value.append(String.format(Locale.ROOT, "%02x", item & 255));
        }
        return value.toString();
    }

    private void scalar(String name, String actual) throws Exception {
        calls++;
        JSONObject expected = methods.getJSONObject(name);
        require("String".equals(expected.getString("return_type")), "scalar contract type: " + name);
        require(actual != null && actual.equals(expected.getString("value")), "scalar mismatch: " + name);
        strings++;
        values.put(name, actual);
    }

    private void array(String name, String[] actual) throws Exception {
        calls++;
        JSONObject expected = methods.getJSONObject(name);
        require("String[]".equals(expected.getString("return_type")), "array contract type: " + name);
        JSONArray wanted = expected.getJSONArray("value");
        require(actual != null && actual.length == wanted.length(), "array length: " + name);
        JSONArray captured = new JSONArray();
        for (int index = 0; index < actual.length; index++) {
            require(actual[index] != null && actual[index].equals(wanted.getString(index)),
                    "array mismatch: " + name + "[" + index + "]");
            strings++;
            captured.put(actual[index]);
        }
        values.put(name, captured);
    }

    @Override public void onStart() {
        long began = SystemClock.elapsedRealtime();
        String nonce = arguments.getString("run_nonce", "");
        Bundle result = new Bundle();
        int finishCode = Activity.RESULT_CANCELED;
        try {
            require(nonce.matches("[0-9a-f]{32}"), "invalid nonce");
            int api = Integer.parseInt(arguments.getString("expected_api", ""));
            int page = Integer.parseInt(arguments.getString("expected_page_size", ""));
            require(api >= 24 && api <= 37 && Build.VERSION.SDK_INT == api, "API mismatch");
            require(page == 4096 || page == 16384, "invalid expected application page size");
            phase = "identity";
            Context context = getTargetContext();
            ApplicationInfo info = context.getApplicationInfo();
            require(PACKAGE.equals(context.getPackageName()) && PACKAGE.equals(info.packageName), "package mismatch");
            require(Process.myUid() >= 10000 && Process.myUid() == info.uid, "UID mismatch");
            require((info.flags & ApplicationInfo.FLAG_TEST_ONLY) != 0, "not test-only");
            require((info.flags & ApplicationInfo.FLAG_DEBUGGABLE) == 0, "unexpected debuggable flag");
            require("ranchu".equals(Build.HARDWARE) || "goldfish".equals(Build.HARDWARE), "not an expected emulator");
            require(Process.is64Bit() && Arrays.asList(Build.SUPPORTED_64_BIT_ABIS).contains("x86_64"), "not x86_64/64bit");
            long applicationPage = Os.sysconf(OsConstants._SC_PAGESIZE);
            require(applicationPage == page, "application page size mismatch");
            File apk = new File(info.sourceDir);
            byte[] apkBytes;
            try (InputStream input = new FileInputStream(apk)) { apkBytes = readBounded(input, 8 * 1024 * 1024); }
            String apkSha = sha(apkBytes);
            String elfSha;
            try (ZipFile zip = new ZipFile(apk)) {
                ZipEntry entry = zip.getEntry("lib/x86_64/libwaexdiag.so");
                require(entry != null && entry.getMethod() == ZipEntry.STORED, "native entry missing/compressed");
                try (InputStream input = zip.getInputStream(entry)) { elfSha = sha(readBounded(input, 1024 * 1024)); }
            }
            require(elfSha.equals(BuildIdentity.ELF_SHA256), "bundled ELF identity mismatch");
            byte[] contractBytes;
            try (InputStream input = context.getAssets().open("expected_constants.json")) {
                contractBytes = readBounded(input, 32768);
            }
            require(sha(contractBytes).equals(BuildIdentity.CONTRACT_SHA256), "contract asset mismatch");
            JSONObject contract = new JSONObject(new String(contractBytes, "UTF-8"));
            require("WAEXDIAG_CONSTANT_CONTRACT_V1".equals(contract.getString("schema")), "contract schema");
            require(BuildIdentity.SOURCE_REVISION.equals(contract.getString("source_revision"))
                    && BuildIdentity.SOURCE_SHA256.equals(contract.getString("source_sha256")), "source contract mismatch");
            methods = contract.getJSONObject("methods");
            require(methods.length() == 14, "contract count");
            phase = "load";
            System.loadLibrary("waexdiag");
            loaded = true;
            phase = "jni_constants";
            scalar("lspConfigDb", NativeDiagPaths.lspConfigDb());
            scalar("hmaZygiskPath", NativeDiagPaths.hmaZygiskPath());
            array("knownHmaPackages", NativeDiagPaths.knownHmaPackages());
            array("knownHmaConfigPaths", NativeDiagPaths.knownHmaConfigPaths());
            scalar("hmaActiveCheckCommand", NativeDiagPaths.hmaActiveCheckCommand());
            scalar("lspHmaCheckCommand", NativeDiagPaths.lspHmaCheckCommand());
            scalar("hmaShallowSearchCommand", NativeDiagPaths.hmaShallowSearchCommand());
            scalar("hmaConfigGlobCommand", NativeDiagPaths.hmaConfigGlobCommand());
            scalar("lspLogGlob", NativeDiagPaths.lspLogGlob());
            scalar("magiskVersionCommand", NativeDiagPaths.magiskVersionCommand());
            scalar("magiskDenylistStatusCommand", NativeDiagPaths.magiskDenylistStatusCommand());
            scalar("magiskDenylistListCommand", NativeDiagPaths.magiskDenylistListCommand());
            scalar("magiskDenylistRemovePrefix", NativeDiagPaths.magiskDenylistRemovePrefix());
            scalar("magiskDenylistRemoveSuffix", NativeDiagPaths.magiskDenylistRemoveSuffix());
            require(calls == 14 && strings == 38 && values.length() == 14, "JNI observation count");
            JSONObject receipt = new JSONObject();
            receipt.put("schema", "WAEXDIAG_JNI_CONSTANTS_V2");
            receipt.put("scope", "WAEXDIAG_CONSTANTS_ONLY_NO_COMMANDS_ROOT_OR_OTHER_LIBRARIES");
            receipt.put("package", PACKAGE);
            receipt.put("run_nonce", nonce);
            receipt.put("sdk", Build.VERSION.SDK_INT);
            receipt.put("release", Build.VERSION.RELEASE);
            receipt.put("hardware", Build.HARDWARE);
            receipt.put("supported_abis", new JSONArray(Arrays.asList(Build.SUPPORTED_ABIS)));
            receipt.put("process_is_64bit", Process.is64Bit());
            receipt.put("uid", Process.myUid());
            receipt.put("pid", Process.myPid());
            receipt.put("application_page_size_bytes", applicationPage);
            receipt.put("own_apk_sha256", apkSha);
            receipt.put("bundled_elf_sha256", elfSha);
            receipt.put("source_revision", BuildIdentity.SOURCE_REVISION);
            receipt.put("source_sha256", BuildIdentity.SOURCE_SHA256);
            receipt.put("cmake_sha256", BuildIdentity.CMAKE_SHA256);
            receipt.put("contract_sha256", BuildIdentity.CONTRACT_SHA256);
            receipt.put("load_library_returned", loaded);
            receipt.put("jni_calls", calls);
            receipt.put("strings_checked", strings);
            receipt.put("return_values", values);
            receipt.put("duration_ms", SystemClock.elapsedRealtime() - began);
            result.putString("waex_native_receipt", receipt.toString());
            finishCode = Activity.RESULT_OK;
        } catch (Throwable error) {
            result.putString("waex_native_error", error.getClass().getName() + ": " + error.getMessage());
            result.putString("phase", phase);
            result.putString("run_nonce", nonce);
            result.putBoolean("load_library_returned", loaded);
            result.putInt("jni_calls", calls);
        }
        finish(finishCode, result);
    }
}
