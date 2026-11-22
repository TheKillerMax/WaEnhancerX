#!/usr/bin/env python3
"""Verify production call-type feature registration, resources and fail-closed source contracts.

This is a source/resource wiring regression gate, not a replacement for the
separate 87-case compiled Robolectric call-type integration suite. No real
WhatsApp, DexKit JNI, phone dialer, or Android lifecycle is exercised here.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app/src/main/java/com/waenhancer"
HOOK = SRC / "xposed/features/privacy/CallTypeControllerHook.java"
CONTRACT = SRC / "xposed/features/privacy/CallTypeHostContract.java"
REGISTRY = SRC / "xposed/core/FeatureRegistry.java"
XML_DIR = ROOT / "app/src/main/res"
LOCALES = ("values", "values-es", "values-b+es+419", "values-sl")
KEYS = ("call_type_dialog_title", "call_type_dialog_message", "call_type_phone",
        "call_type_dialer_unavailable", "call_type_whatsapp_failed")

def require(condition, description):
    if not condition:
        raise RuntimeError("Call-type integration regression: " + description)

def verify(hook, contract, registry, localized):
    checks = 0
    def check(condition, description):
        nonlocal checks
        require(condition, description)
        checks += 1
    check('ENABLED = "call_type_controller"' in hook, "canonical preference drift")
    check("CallTypeHostContract.discover(context, loader)" in hook, "host discovery not bound")
    check("contract.sites.size() != 4" in hook, "all four call paths must be verified")
    check("ArrayBlockingQueue<>(1)" in hook, "bounded lookup queue absent")
    check("LOOKUP_TIMEOUT_MS = 1500L" in hook, "lookup timeout contract changed")
    check("request.future.cancel(true)" in hook, "cancellation of in-flight lookup absent")
    check("ContactIdentityPolicy.isLid(snapshot.peer)" in hook, "LID mapping guard absent")
    check("if (arguments == null || arguments.length != 3) return false;" in hook,
          "original call must remain available on unknown host signatures")
    check("param.setResult(null)" in hook and "if (intercept(" in hook,
          "original continuation must be cancelled only on successful ownership")
    check("Intent.ACTION_DIAL" in hook and '"tel"' in hook,
          "phone path must use Android dialer and verified digits")
    check("if (!ready.get() || !enabled()" in hook,
          "disabled preference must not intercept calls")
    check("onActivityDestroyed(Activity activity)" in hook,
          "activity-destroy cancellation missing")
    check("calls.size() != 2" in contract and "candidates.size() != 1" in contract,
          "ambiguous DexKit signatures must fail closed")
    check("LIFECYCLE_STATES" in contract and '"RESUMED"' in contract,
          "host lifecycle ownership check missing")
    check("ContactIdentityPolicy.phoneUser(canonical)" in contract,
          "validated PN identity missing")
    check(registry.count("import com.waenhancer.xposed.features.privacy.CallTypeControllerHook;") == 1,
          "missing or duplicate registry import")
    check(registry.count("registerFeature(CallTypeControllerHook.class") == 1,
          "missing or duplicate feature registration")
    check('prefs.getBoolean("call_type_controller", false)' in registry,
          "disabled-by-default predicate missing")
    for key in KEYS:
        check("R.string." + key in hook, "resource not referenced by actual production hook: " + key)
    for name, entries in localized.items():
        for key in KEYS:
            check(key in entries and bool(entries[key].strip()),
                  "missing or empty resource: " + name + "/" + key)
        check(entries["call_type_dialog_message"].count("%1$s") == 1,
              "recipient placeholder invalid: " + name)
    return checks

def main():
    hook, contract, registry = (p.read_text(encoding="utf-8") for p in
                                (HOOK, CONTRACT, REGISTRY))
    tables = {}
    for locale in LOCALES:
        path = XML_DIR / locale / "strings.xml"
        root = ET.parse(path).getroot()
        names = [(e.get("name"), "".join(e.itertext())) for e in root.findall("string")]
        require(len(names) == len({key for key, _ in names}), "duplicate values: " + locale)
        tables[locale] = dict(names)
    checks = verify(hook, contract, registry, tables)
    mutants = (
        ("missing-validation", hook.replace("contract.sites.size() != 4", "contract.sites.size() != 1"), contract, registry, tables),
        ("unbounded-worker", hook.replace("ArrayBlockingQueue<>(1)", "ArrayBlockingQueue<>(1024)"), contract, registry, tables),
        ("unregistered-feature", hook, contract, registry.replace("registerFeature(CallTypeControllerHook.class",
                                                                                  "registerFeature(UnknownFeature.class"), tables),
        ("translation-placeholder", hook, contract, registry,
         {**tables, "values": {**tables["values"], "call_type_dialog_message": "Call using:"}}),
    )
    for name, h, c, reg, loc in mutants:
        try:
            verify(h, c, reg, loc)
        except RuntimeError:
            print("KILLED " + name, flush=True)
        else:
            raise RuntimeError("Source contract mutant escaped: " + name)
    print(f"PASS call-type source wiring: {checks} assertions across four locales, 4 negative controls", flush=True)
    print("LIMIT: static source assertions, not compiled host/Android behavior", flush=True)

if __name__ == "__main__":
    main()
