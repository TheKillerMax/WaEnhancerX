package com.waenhancer.xposed.features.automation;

import android.content.Context;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.content.res.Resources;
import com.waenhancer.app.R;

/** Receipt text is loaded on the lookup executor, never while delivering a toast. */
final class ReceiptToastText {
    private final Context host;
    private Context module;
    private Context localized;
    private Configuration configuration;

    ReceiptToastText(Context host) { this.host = host; }

    synchronized String format(ReceiptObservationPolicy.Kind kind, String name) {
        String contact = name == null || name.isEmpty() ? "A contact" : name;
        try {
            if (module == null) module = host.createPackageContext("com.waenhancer", 0);
            Configuration desired = host.getResources().getConfiguration();
            if (localized == null || !desired.equals(configuration)) {
                Configuration next = new Configuration(desired);
                Context nextContext = module.createConfigurationContext(next);
                configuration = next;
                localized = nextContext;
            }
            int resource = kind == ReceiptObservationPolicy.Kind.STATUS
                    ? R.string.receipt_observed_status : R.string.receipt_observed_message;
            String expected = "com.waenhancer:string/" + (kind == ReceiptObservationPolicy.Kind.STATUS
                    ? "receipt_observed_status" : "receipt_observed_message");
            boolean moduleContext = "com.waenhancer".equals(localized.getPackageName());
            String actual = localized.getResources().getResourceName(resource);
            if (moduleContext && expected.equals(actual)) return localized.getString(resource, contact);
        } catch (PackageManager.NameNotFoundException | Resources.NotFoundException | SecurityException unavailable) {
            // Missing resources and foreign numeric resource IDs share the same fallback.
        }
        return "Read receipt from " + contact + (kind == ReceiptObservationPolicy.Kind.STATUS
                ? " for your status" : " for your message");
    }
}
