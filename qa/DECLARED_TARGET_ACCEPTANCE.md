# Exact declared target selection

Use the same immutable, case-sensitive 47-name xposed_scope snapshot before and
after Application/Context initialization. Names, labels and historical telemetry
do not add undeclared targets. The regression requires exact equality with the
resource declaration; update both when deliberately changing scope.

This removes scanner/recovery false positives and restores consistency for nine
declared names missed by the old context-free pattern. It does not prove that any
configured clone is authentic, signed by a trusted publisher or functionally
compatible. Provider caller authorization, version checks, licensing and restart
permission boundaries remain separate and unchanged.

223 production Java/extracted-Kotlin checks cover every declared name in both
paths, case/suffix/confusable inputs, immutable membership and historical reports.
No installed application or LSPosed instance is exercised by these JVM tests.
