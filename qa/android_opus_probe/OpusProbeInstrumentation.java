/* Neutral serial QA probe for the pinned io.element.android Opus1.2.0 AAR.
 * Synthetic PCM only. No recording, playback, network or production hooks.
 */
package org.lab.waex.qa.opus;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import io.element.android.opusencoder.OggOpusEncoder;
import io.element.android.opusencoder.configuration.SampleRate;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class OpusProbeInstrumentation extends Instrumentation {
    private static final String PACKAGE = "org.lab.waex.qa.opus";
    private static final String NATIVE_SHA = "4f2b782362aeda7da6f9f4a0bdfdb30a310a824a91da1f2e770b4f65780864dc";
    private static final String PCM48_SHA = "00cde5d613eaadc51c6b3e8b66f827a57f681aebbd1c9228bc365d082a6d92ba";
    private static final String PCM16_SHA = "4e57713a4022f94e833ea3f8567f1eec0204f9db2b32ae63f6bbcb1ab9ce59e5";
    private static final int MAX_OGG = 1024 * 1024;
    private static final int CHUNK_BYTES = 12288;
    private static final long MAX_NS = 120000000000L;
    private long started;
    private String nonce = "";
    private int checks;
    private final JSONArray cases = new JSONArray();

    private void req(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
        checks++;
    }

    private void budget() {
        if (SystemClock.elapsedRealtimeNanos() - started > MAX_NS) {
            throw new IllegalStateException("TIME_BUDGET");
        }
    }

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        nonce = arguments == null ? "" : arguments.getString("run_nonce", "");
        start();
    }

    @Override public void onStart() {
        started = SystemClock.elapsedRealtimeNanos();
        File directory = null;
        boolean owned = false;
        Throwable failure = null;
        String cleanupFailure = "";
        JSONObject receipt = null;
        try {
            req(nonce.matches("[a-f0-9]{32}"), "RUN_NONCE");
            req(PACKAGE.equals(getTargetContext().getPackageName()), "PACKAGE_ID");
            ApplicationInfo info = getTargetContext().getApplicationInfo();
            req(android.os.Process.myUid() == info.uid && info.uid >= 10000, "OWN_UNPRIVILEGED_UID");
            req((info.flags & ApplicationInfo.FLAG_TEST_ONLY) != 0, "TEST_ONLY_APK");
            req((info.flags & ApplicationInfo.FLAG_DEBUGGABLE) == 0, "NON_DEBUGGABLE_APK");
            PackageInfo packageInfo = getTargetContext().getPackageManager().getPackageInfo(PACKAGE, PackageManager.GET_PERMISSIONS);
            req(packageInfo.requestedPermissions == null || packageInfo.requestedPermissions.length == 0, "NO_REQUESTED_PERMISSIONS");
            req(Build.VERSION.SDK_INT == 35, "SDK_35_ONLY");
            req("ranchu".equals(Build.HARDWARE) || "goldfish".equals(Build.HARDWARE), "EMULATOR_HARDWARE");
            req(Arrays.asList(Build.SUPPORTED_ABIS).contains("x86_64") && android.os.Process.is64Bit(), "X86_64_PROCESS");
            long pages = android.system.Os.sysconf(android.system.OsConstants._SC_PAGESIZE);
            req(pages == 4096 || pages == 16384, "APPLICATION_PAGE_SIZE");
            verifyNativeEntry(info.sourceDir);
            File cache = getTargetContext().getCacheDir().getCanonicalFile();
            directory = new File(cache, "waex-opus-" + nonce);
            req(!directory.exists() && directory.getCanonicalFile().equals(directory.getAbsoluteFile()), "NEW_OWN_DIRECTORY");
            req(directory.mkdir(), "CREATE_OWN_DIRECTORY");
            owned = true;
            receipt = new JSONObject();
            receipt.put("schema", "WAEX_ANDROID_OPUS_PROBE_V1");
            receipt.put("run_nonce", nonce);
            receipt.put("package", PACKAGE);
            receipt.put("sdk", Build.VERSION.SDK_INT);
            receipt.put("release", Build.VERSION.RELEASE);
            receipt.put("hardware", Build.HARDWARE);
            receipt.put("uid", info.uid);
            receipt.put("pid", android.os.Process.myPid());
            receipt.put("application_page_size_bytes", pages);
            receipt.put("process_is_64bit", true);
            receipt.put("test_only", true);
            receipt.put("debuggable", false);
            receipt.put("requested_permissions", new JSONArray());
            JSONArray abis = new JSONArray();
            for (String abi : Build.SUPPORTED_ABIS) abis.put(abi);
            receipt.put("supported_abis", abis);
            receipt.put("native_sha256", NATIVE_SHA);
            receipt.put("wrapper", "io.element.android.opusencoder.OggOpusEncoder");
            receipt.put("cases", cases);
            encodeCase(directory, "pcm48k", "pcm48k_mono_s16le.pcm", 48000, 96000, 960, PCM48_SHA);
            encodeCase(directory, "pcm16k", "pcm16k_mono_s16le.pcm", 16000, 16000, 320, PCM16_SHA);
            budget();
        } catch (Throwable error) {
            failure = error;
        } finally {
            if (owned) {
                try {
                    cleanupOwned(directory);
                } catch (Throwable error) {
                    cleanupFailure = describe(error);
                    if (failure == null) failure = error;
                }
            }
        }
        Bundle output = new Bundle();
        int result = Activity.RESULT_CANCELED;
        if (failure == null) {
            try {
                req(owned && directory != null && !directory.exists(), "OWN_DIRECTORY_ABSENT");
                receipt.put("status", "PASS_ENCODE_ONLY");
                receipt.put("own_directory_absent", true);
                receipt.put("checks", checks);
                receipt.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1000000L);
                output.putString("waex_opus_receipt", receipt.toString());
                result = Activity.RESULT_OK;
            } catch (Throwable error) {
                failure = error;
            }
        }
        if (failure != null) {
            output.putString("waex_opus_error", describe(failure));
            output.putString("waex_opus_run_nonce", nonce);
            output.putString("waex_opus_cleanup_error", cleanupFailure);
            output.putString("waex_opus_own_directory_absent", Boolean.toString(owned && directory != null && !directory.exists()));
            output.putString("waex_opus_partial_cases", cases.toString());
        }
        finish(result, output);
    }

    private void verifyNativeEntry(String apkPath) throws Exception {
        try (ZipFile apk = new ZipFile(apkPath)) {
            int nativeCount = 0;
            for (Enumeration<? extends ZipEntry> entries = apk.entries(); entries.hasMoreElements();) {
                ZipEntry entry = entries.nextElement();
                if (!entry.isDirectory() && entry.getName().startsWith("lib/")) {
                    req("lib/x86_64/libopuscodec.so".equals(entry.getName()), "ONLY_PINNED_NATIVE_ABI");
                    nativeCount++;
                }
            }
            req(nativeCount == 1, "ONE_NATIVE_ENTRY");
            ZipEntry entry = apk.getEntry("lib/x86_64/libopuscodec.so");
            req(entry != null && entry.getMethod() == ZipEntry.STORED, "UNCOMPRESSED_NATIVE");
            try (InputStream stream = apk.getInputStream(entry)) {
                req(NATIVE_SHA.equals(sha(readBounded(stream, 8 * 1024 * 1024))), "NATIVE_BINARY_IDENTITY");
            }
        }
    }

    private void encodeCase(File directory, String name, String asset, int rate, int sampleCount,
                            int frameSamples, String pcmPin) throws Throwable {
        budget();
        byte[] raw;
        try (InputStream stream = getTargetContext().getAssets().open(asset)) {
            raw = readBounded(stream, 192000);
        }
        req(raw.length == sampleCount * 2 && pcmPin.equals(sha(raw)), "PCM_INPUT_IDENTITY_" + name);
        File file = new File(directory, name + "-" + nonce + ".ogg");
        req(!file.exists() && file.getCanonicalFile().equals(file.getAbsoluteFile())
                && file.getParentFile().equals(directory), "NEW_OUTPUT_PATH");
        JSONObject row = new JSONObject();
        cases.put(row);
        row.put("name", name);
        row.put("asset", asset);
        row.put("input_rate", rate);
        row.put("input_samples", sampleCount);
        row.put("frame_samples", frameSamples);
        row.put("pcm_sha256", pcmPin);
        row.put("output_name", file.getName());
        JSONArray bitrateEvents = new JSONArray();
        JSONArray encodeCodes = new JSONArray();
        row.put("bitrate_events", bitrateEvents);
        row.put("encode_rc", encodeCodes);
        int releaseAttempts = 0;
        int releaseCompleted = 0;
        boolean active = false;
        Throwable failure = null;
        OggOpusEncoder encoder = null;
        try {
            encoder = OggOpusEncoder.Companion.create();
            SampleRate sampleRate = rate == 48000 ? SampleRate.Rate48kHz.INSTANCE : SampleRate.Rate16kHz.INSTANCE;
            int initialized = encoder.init(file.getAbsolutePath(), sampleRate);
            row.put("init_rc", initialized);
            req(initialized == 0, "JNI_INIT_" + name);
            active = true;
            bitrate(encoder, bitrateEvents, 0, 32000);
            short[] frame = new short[frameSamples];
            for (int start = 0; start < sampleCount; start += frameSamples) {
                budget();
                if (rate == 48000 && start == 48000) bitrate(encoder, bitrateEvents, start, 64000);
                for (int sample = 0; sample < frameSamples; sample++) {
                    int offset = (start + sample) * 2;
                    frame[sample] = (short) ((raw[offset] & 255) | ((raw[offset + 1] & 255) << 8));
                }
                int rc = encoder.encode(frame, frameSamples);
                encodeCodes.put(rc);
                req(rc == 0, "JNI_ENCODE_" + name + "_" + start);
            }
        } catch (Throwable error) {
            failure = error;
        } finally {
            if (active) {
                active = false;
                releaseAttempts++;
                try {
                    encoder.release();
                    releaseCompleted++;
                } catch (Throwable error) {
                    row.put("release_failure", describe(error));
                    if (failure == null) failure = error;
                }
            }
            row.put("release_attempts", releaseAttempts);
            row.put("release_completed", releaseCompleted);
        }
        if (failure != null) throw failure;
        req(releaseAttempts == 1 && releaseCompleted == 1, "SINGLE_RELEASE_" + name);
        budget();
        req(file.isFile() && file.length() > 0 && file.length() <= MAX_OGG, "OGG_FILE_BOUND_" + name);
        byte[] ogg;
        try (InputStream stream = new FileInputStream(file)) {
            ogg = readBounded(stream, MAX_OGG);
        }
        req(ogg.length == file.length() && ogg.length >= 27, "OGG_READ_COMPLETE_" + name);
        row.put("ogg_bytes", ogg.length);
        row.put("ogg_sha256", sha(ogg));
        int total = (ogg.length + CHUNK_BYTES - 1) / CHUNK_BYTES;
        row.put("chunk_count", total);
        for (int index = 0; index < total; index++) {
            budget();
            int from = index * CHUNK_BYTES;
            byte[] body = Arrays.copyOfRange(ogg, from, Math.min(from + CHUNK_BYTES, ogg.length));
            JSONObject chunk = new JSONObject();
            chunk.put("schema", "WAEX_OPUS_CHUNK_V1");
            chunk.put("run_nonce", nonce);
            chunk.put("name", name);
            chunk.put("index", index);
            chunk.put("total", total);
            chunk.put("bytes", body.length);
            chunk.put("sha256", sha(body));
            chunk.put("data", Base64.encodeToString(body, Base64.NO_WRAP));
            Bundle status = new Bundle();
            status.putString("waex_opus_chunk", chunk.toString());
            sendStatus(0, status);
        }
    }

    private void bitrate(OggOpusEncoder encoder, JSONArray events, int sample, int bits) throws Exception {
        int rc = encoder.setBitrate(bits);
        JSONObject event = new JSONObject();
        event.put("at_sample", sample);
        event.put("bps", bits);
        event.put("rc", rc);
        events.put(event);
        req(rc == 0, "JNI_BITRATE_" + sample);
    }

    private void cleanupOwned(File directory) throws Exception {
        req(directory != null && directory.isDirectory() && directory.getCanonicalFile().equals(directory), "CLEANUP_OWN_DIRECTORY");
        File[] entries = directory.listFiles();
        req(entries != null && entries.length <= 2, "CLEANUP_ENTRY_COUNT");
        for (File entry : entries) {
            String name = entry.getName();
            req((name.equals("pcm48k-" + nonce + ".ogg") || name.equals("pcm16k-" + nonce + ".ogg"))
                    && entry.isFile() && entry.getCanonicalFile().equals(entry.getAbsoluteFile())
                    && entry.getParentFile().equals(directory), "CLEANUP_ENTRY_SCOPE");
        }
        for (File entry : entries) req(entry.delete() && !entry.exists(), "CLEANUP_FILE");
        req(directory.delete() && !directory.exists(), "CLEANUP_DIRECTORY");
    }

    private static byte[] readBounded(InputStream stream, int bound) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] block = new byte[8192];
        int count;
        while ((count = stream.read(block)) != -1) {
            if (output.size() + count > bound) throw new IllegalStateException("READ_BOUND");
            output.write(block, 0, count);
        }
        return output.toByteArray();
    }

    private static String sha(byte[] value) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(value);
        StringBuilder text = new StringBuilder(64);
        for (byte part : hash) {
            text.append(Character.forDigit((part >>> 4) & 15, 16));
            text.append(Character.forDigit(part & 15, 16));
        }
        return text.toString();
    }

    private static String describe(Throwable error) {
        String text = error.getClass().getName() + ":" + String.valueOf(error.getMessage());
        return text.length() <= 1000 ? text : text.substring(0, 1000);
    }
}
