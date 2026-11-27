package com.waenhancer.xposed.features.privacy;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;

/** Runs production fingerprint code over APK bytes; no target class is loaded. */
public final class CallTypeProfileFileCheck {
    private static int checks;
    private static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
        checks++;
    }
    private static void profile(File file, String packageName, String api, String adapter,
                                String first, String second, int arity) {
        long start = System.nanoTime();
        CallTypeHostProfile result = CallTypeHostProfile.findFile(packageName, file);
        long firstNanos = System.nanoTime() - start;
        check(result != null && result.apiName.equals(api) && result.adapterName.equals(adapter)
                && result.firstOperation.equals(first) && result.secondOperation.equals(second)
                && result.argumentCount == arity, "exact APK profile " + packageName);
        start = System.nanoTime();
        for (int index = 0; index < 100; index++) {
            if (CallTypeHostProfile.findFile(packageName, file) != result) throw new AssertionError("unstable memo");
        }
        long memoNanos = System.nanoTime() - start;
        checks++;
        System.out.println("{\"package\":\"" + packageName + "\",\"sha256\":\"" + result.sha256
                + "\",\"bytes\":" + file.length() + ",\"argument_count\":" + arity
                + ",\"first_process_lookup_ns\":" + firstNanos + ",\"memo_100_lookups_ns\":" + memoNanos + "}");
    }
    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 3) throw new IllegalArgumentException("personal.apk business.apk NEW_WORK_DIR");
        File personal = new File(arguments[0]), business = new File(arguments[1]);
        Path work = Path.of(arguments[2]);
        Files.createDirectory(work);
        profile(personal, "com.whatsapp", "X.0p1", "X.60R", "C70", "C73", 3);
        profile(business, "com.whatsapp.w4b", "X.0oi", "X.8Zt", "CMV", "CMY", 4);
        check(CallTypeHostProfile.findFile("com.whatsapp.w4b", personal) == null, "cross-package personal");
        check(CallTypeHostProfile.findFile("com.whatsapp", business) == null, "cross-package business");
        check(CallTypeHostProfile.findFile("unknown.package", personal) == null, "unknown package");
        check(CallTypeHostProfile.findFile("com.whatsapp", null) == null, "missing path");
        check(CallTypeHostProfile.findFile("com.whatsapp", work.toFile()) == null, "directory");
        check(CallTypeHostProfile.findFile("com.whatsapp", work.resolve("absent.apk").toFile()) == null, "missing file");
        Path small = work.resolve("small.apk"); Files.write(small, new byte[]{0x50, 0x4b, 3, 4});
        check(CallTypeHostProfile.findFile("com.whatsapp", small.toFile()) == null, "wrong length");
        check(CallTypeHostProfile.find(null) == null, "missing context");
        Path changed = work.resolve("same-size.apk");
        Files.copy(personal.toPath(), changed, StandardCopyOption.COPY_ATTRIBUTES);
        check(CallTypeHostProfile.findFile("com.whatsapp", changed.toFile()) != null, "identical copied bytes");
        long timestamp = changed.toFile().lastModified();
        int original;
        try (RandomAccessFile file = new RandomAccessFile(changed.toFile(), "rw")) {
            original = file.readUnsignedByte(); file.seek(0); file.write(original ^ 1);
        }
        Files.setLastModifiedTime(changed, FileTime.fromMillis(timestamp + 2000));
        check(CallTypeHostProfile.findFile("com.whatsapp", changed.toFile()) == null, "same-size changed content");
        try (RandomAccessFile file = new RandomAccessFile(changed.toFile(), "rw")) { file.write(original); }
        Files.setLastModifiedTime(changed, FileTime.fromMillis(timestamp + 4000));
        check(CallTypeHostProfile.findFile("com.whatsapp", changed.toFile()) != null, "changed metadata invalidates rejection");
        Files.delete(changed); Files.delete(small);
        System.out.println("{\"status\":\"PASS\",\"checks\":" + checks
                + ",\"target_classes_loaded\":false,\"target_code_executed\":false,\"device_actions\":0}");
    }
}
