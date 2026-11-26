# Current process evidence in Android profiles

The event-driven `TargetAppManager`/`RootProbe` architecture and PID/boot evidence
are preserved. PackageManager establishes each target UID in the initiating
manager's user. UID-bearing process records are checked against those owners;
the initiating manager PID must appear before missing targets can count as absent.
Unknown package UIDs remain unknown. Invalid context identity never runs root.

The primary command requests `UID,PID,NAME`. Its legacy fallback recognizes
bionic's `u<user>_a<app>` user names, with bounded arithmetic. Failed ps attempts
discard their partial output before the exact-name filter; a successful grep
cannot turn a failed producer into complete evidence.

`qa/test_profile_process_probe.py` exercises complete public owner/parser code
and the extracted complete `RootProbe`, with actual Robolectric Android APIs.
22 scenarios pass on API24/28/34 (66 executions). Four compiled mutations fail
15,3,3,3 assertions. Five shell cases execute the production command against
a controlled ps executable. No root, real process enumeration or LSPosed DB runs.
The current runtime diagnostics entry point also passes173 checks and8 shell
cases; its recovered event-driven coverage is retained.

Run with JDK17+, Kotlin2.0.20 in `KOTLIN_HOME`, and the verified Robolectric4.17
cache: `python3 qa/test_profile_process_probe.py --out /tmp/waex-profiles --deps /path/deps --sdk-jars /path/sdk-jars --mutations`.

The bionic naming basis is immutable Android7 source:
https://github.com/aosp-mirror/platform_bionic/blob/android-7.0.0_r1/libc/bionic/stubs.cpp
and UID ranges follow the existing production `AndroidUserScope` contract.
Vendor ps formats that cannot establish identity stay unavailable. Device
profile/scope visibility and injection remain independent acceptance requirements.
