package com.waenhancer.utils;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Context-free snapshot of the declared xposed_scope, excluding the manager.
 * Keep in sync with arrays.xml; qa/test_declared_targets.py requires exact equality.
 * This is a targeting rule, not certificate authentication or compatibility proof.
 */
public final class DeclaredWhatsAppTargets {
    private DeclaredWhatsAppTargets() {}

    private static final Set<String> PACKAGES = Collections.unmodifiableSet(new LinkedHashSet<>(
            Arrays.asList(
                    "com.whatsapp",
                    "com.whatsapp.w4b",
                    "com.gbwhatsapp",
                    "com.fmwhatsapp",
                    "com.yowhatsapp",
                    "com.aerowtsapp",
                    "com.aero",
                    "com.delta",
                    "com.ultra",
                    "com.delight",
                    "com.universe.messenger",
                    "com.directchat.app",
                    "com.sathwbg.easymessager",
                    "com.whatsapplitex",
                    "com.whatsapplitex2",
                    "com.whatsapp.litex",
                    "com.wa.litex",
                    "online.whatsticker",
                    "com.gbwhatsapp.sofid",
                    "com.yowa",
                    "com.ymwhatsapp",
                    "com.nowha",
                    "com.nowha2",
                    "com.whatsapp2",
                    "com.wa",
                    "com.wago",
                    "com.whatsapp.plus",
                    "com.ogwhatsapp",
                    "com.soula2",
                    "com.co.whatsapp",
                    "com.bwhatsapp",
                    "com.fouadwhatsapp",
                    "com.samwhatsapp",
                    "com.hewhatsapp",
                    "com.mbwhatsapp",
                    "com.rcwhatsapp",
                    "com.na4whatsapp",
                    "com.na7whatsapp",
                    "com.anwhatsapp",
                    "com.obwhatsapp",
                    "com.ob2whatsapp",
                    "com.ob3whatsapp",
                    "com.ob4whatsapp",
                    "com.ob5whatsapp",
                    "com.ob6whatsapp",
                    "com.whatsapp.dual",
                    "com.whatsapp.clone"
            )));

    public static boolean contains(String packageName) {
        // Exact, case-sensitive membership: do not normalize a different package into a target.
        return packageName != null && PACKAGES.contains(packageName);
    }

    public static Set<String> packages() {
        return PACKAGES;
    }
}
