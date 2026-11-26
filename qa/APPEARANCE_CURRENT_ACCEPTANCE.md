# Current appearance contracts

The three hooks retain current settings, styles and diagnostics. FAB readiness
uses a removable layout listener; repeated selection preserves drawing state;
transition backgrounds do not nest indefinitely. Recommendation hiding honors
the live switch and host visibility rebinding through the public dispatcher.
View selectors reject ambiguous/foreign classes. Meta AI removal honors its
master switch. Existing incomplete online-dot/text-only behavior is unchanged.

`test_appearance_current.py --out <new-directory> --deps <robolectric-jars>
--sdk-jars <instrumented-sdk-jars> --dexkit-jar <dexkit-2.2.0.jar>
--core-api-jar <core-1.18.0.jar> --mutations` requires JDK17+, Kotlin2.0.20 and
Robolectric4.17. The receipt records every source, fixture and dependency hash.
Thirty scenarios execute on API24/28/34:90 executions pass. Five independently
compiled mutations fail6/3/3/9/6 assertions. Setup/compilation failures never count
as rejected mutants. Actual public BaseFeature cleanup removes dispatcher owners.

Xposed, host discovery and the private ScreenScopedFeature declaration are explicit
boundaries. No private engine lifecycle, WhatsApp DEX selection, device injection,
GPU appearance, hook-mode compatibility or exact-commit public CI is established.
Maintainer review and the full licensed build remain separate requirements.
