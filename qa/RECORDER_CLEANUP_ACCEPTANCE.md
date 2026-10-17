# Recorder failure cleanup

Always release the local MediaRecorder instance after attempted stop, even when
stop throws after the recorder field has been cleared. Descriptor closing and
invalid destination deletion remain in an outer finally even if release fails.
No recording preference, consent, audio source, provider authorization or format
selection changes are included.

Run test_recorder_cleanup.py. It compiles the exact production cleanup method
bodies with explicit recorder, descriptor and provider doubles. Normal/failed stop,
failed release, duplicate/inactive stop and 2,000 repeated cycles are checked.
This proves explicit release control flow, not microphone capture or native audio
server resource reclamation. Test immediate stop and real media failures on an
authorized device; do not close the historical RAM issue on this evidence alone.
