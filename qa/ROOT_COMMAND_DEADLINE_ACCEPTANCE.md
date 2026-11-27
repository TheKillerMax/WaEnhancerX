# Root command deadline: isolated public regression

Reconciles the root runner subset of PR #94, independently of HMA repair,
on nightly c089458569564c241e6e2cddbd5a4de301299f28.
Production bytes match the PR's bounded startup and output capture implementation.
The current restart fixture retains its profile, signature and diagnostic checks.
The deadline fixture starts only a synthetic unprivileged Java child, never su.

On the local JDK 21, both the current nightly and candidate compiled with
the same deadline fixture: 13 executions, ten assertion failures on nightly
and zero on the candidate. The missing complete-output API counts as a
behavioral assertion rather than a compilation failure. The runner rejects
incomplete streams and preserves interrupt state. No Android, root permission,
HMA configuration, privileged command, or physical acceptance is claimed.
A timeout cannot undo effects of a command already executed; platform startup
or termination can remain uninterruptible.

Run: python qa/test_root_command_deadline.py --out NEW_EVIDENCE_DIR
