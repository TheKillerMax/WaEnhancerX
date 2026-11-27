package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** Exact APK identities whose classic/popup Runnable branches were inspected. */
final class CallTypeHostProfile {
    private static final CallTypeHostProfile[] PROFILES = {
            new CallTypeHostProfile("com.whatsapp", 90265021L,
                    "bde176036af43fc9540d0cc76ad6162d2fcd4c9845f91d9c1603e84bb605bb83",
                    "X.0p1", "X.60R", "C70", "C73", 3),
            new CallTypeHostProfile("com.whatsapp.w4b", 105226514L,
                    "bab1f720551c2e84dedabbb01d2f1a0a8947b12ab764f64c50db03af0992dc20",
                    "X.0oi", "X.8Zt", "CMV", "CMY", 4)
    };
    final String packageName, sha256, apiName, adapterName, firstOperation, secondOperation;
    final long bytes;
    final int argumentCount;
    private static String memoPath;
    private static long memoLength, memoModified;
    private static CallTypeHostProfile memoExpected, memoResult;

    private CallTypeHostProfile(String packageName, long bytes, String sha256, String apiName,
                               String adapterName, String first, String second, int argumentCount) {
        this.packageName = packageName; this.bytes = bytes; this.sha256 = sha256;
        this.apiName = apiName; this.adapterName = adapterName;
        this.firstOperation = first; this.secondOperation = second;
        this.argumentCount = argumentCount;
    }

    static CallTypeHostProfile find(Context context) {
        if (context == null) return null;
        try {
            return findFile(context.getPackageName(), new File(context.getApplicationInfo().sourceDir));
        } catch (RuntimeException unavailable) {
            return null;
        }
    }

    /** Same bounded, process-local fingerprint strategy as MediaHostFingerprint. */
    static synchronized CallTypeHostProfile findFile(String packageName, File apk) {
        try {
            if (apk == null || !apk.isFile()) return null;
            long length = apk.length(), modified = apk.lastModified();
            CallTypeHostProfile expected = null;
            for (CallTypeHostProfile profile : PROFILES) {
                if (profile.packageName.equals(packageName) && profile.bytes == length) {
                    if (expected != null) return null;
                    expected = profile;
                }
            }
            if (expected == null) return null;
            String path = apk.getCanonicalPath();
            if (expected == memoExpected && path.equals(memoPath)
                    && length == memoLength && modified == memoModified) return memoResult;
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            long consumed = 0;
            try (FileInputStream input = new FileInputStream(apk)) {
                int count;
                while ((count = input.read(buffer)) != -1) {
                    consumed += count;
                    if (consumed > expected.bytes) return null;
                    digest.update(buffer, 0, count);
                }
            }
            StringBuilder actual = new StringBuilder(64);
            for (byte value : digest.digest()) {
                actual.append(Character.forDigit((value >>> 4) & 15, 16));
                actual.append(Character.forDigit(value & 15, 16));
            }
            boolean unchanged = consumed == length && apk.length() == length && apk.lastModified() == modified;
            CallTypeHostProfile result = unchanged && expected.sha256.contentEquals(actual) ? expected : null;
            if (unchanged) {
                memoPath = path; memoLength = length; memoModified = modified;
                memoExpected = expected; memoResult = result;
            }
            return result;
        } catch (IOException | NoSuchAlgorithmException | SecurityException unavailable) {
            return null;
        }
    }
}
