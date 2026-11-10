package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import java.io.File;

/** Resolves an existing database only in the injected application's current Context. */
final class CallPrivacyDatabaseLocator {
    private CallPrivacyDatabaseLocator() {}

    static File findExisting(Context context, String name) {
        if (context == null) throw new NullPointerException("context");
        if (name == null || name.isEmpty() || ".".equals(name) || "..".equals(name)
                || name.indexOf('/') >= 0 || name.indexOf('\\') >= 0) {
            throw new IllegalArgumentException("A database name, not a path, is required");
        }
        // The framework owns the package, user/profile and storage-volume mapping.
        // A missing/locked database must never fall back to another user's or app's data.
        File database = context.getDatabasePath(name);
        return database != null && database.isFile() && database.canRead() ? database : null;
    }
}
