# View-once exception diagnostics

Four error handlers in `DownloadViewOnceHook` concatenated raw exception messages
into the shared Xposed log. A file/storage/reflection failure can include paths,
URIs or other input details in that message. These diagnostics now retain the
operation and exception class without copying the exception message.

The existing required exception-privacy suite now scans every `XposedBridge.log`
call in this class, including the export error that already used a class-only
diagnostic. The expanded guard fails on the current main source and passes on
the revised source. This is a static callsite check, not a runtime log capture or
a claim that every diagnostic in the application has been audited.

For device acceptance, use authorized test media and simulate viewer/storage
failures. Check that operation labels and exception class names remain useful,
and that Xposed logs do not contain the exception's path or URI payload. Confirm
that the same export control, success flow and error feedback remain available.

This change does not establish which message or file the view-once resolver
selects. See `VIEW_ONCE_EXPORT_ACCEPTANCE.md` for export identity and storage
acceptance; those checks still require the intended host and Android environment.
