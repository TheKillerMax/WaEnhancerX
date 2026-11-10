# Parallel download stream: bounded HTTP Range acceptance

## Scope and baseline

This QA covers the compiled `ParallelDownloadingInputStream` used by the
WaEnhancerX 2.0.6 parallel media downloader. It does not load the Xposed hook,
authenticate against WhatsApp CDN endpoints, or assert real media throughput.

On upstream `4750124e36223dd21d8535c14f2fb658025d8480`, a synthetic
`206 Partial Content` response claiming an extra ending byte was accepted as
valid because the code checked only the range's starting prefix. The fixture
received the wrong final byte instead of falling back to the original stream.
The same source did not validate content encoding or declared response size,
and it treated premature EOF from the original first chunk as a normal EOF.

## Required contract

- A `206` response must identify the exact requested starting and ending bytes.
- Its complete resource length must be syntactically valid and greater than
  the inclusive ending offset; an explicitly unknown total (`*`) is allowed.
- A stated HTTP body length must equal the requested byte count. An unknown
  length is allowed; a transformed encoding other than `identity` is not.
- If the first extra range request is unusable, the original connection must
  remain available for sequential fallback.
- An incomplete first chunk must fail with `IOException`, not a successful
  short download. Invalid `read(byte[], off, len)` bounds must be rejected.
- Diagnostic errors must not include a signed download URL.

## Automated acceptance

With a complete JDK providing `javac --release 17`:

```bash
python3 qa/test_parallel_download_stream.py
```

The runner compiles the **production stream class** against a minimal Xposed
logging double and exercises deterministic URL connections. It verifies:

1. A valid range supplies the expected final byte.
2. A valid unknown complete length (`*`) is accepted.
3. A mismatched range end falls back to the original connection.
4. An invalid complete length falls back.
5. An incorrect declared body length falls back.
6. A transformed content encoding falls back.
7. A server without Range support (`200`) falls back.
8. A truncated original first chunk fails closed.
9. An invalid zero-byte read offset throws instead of silently succeeding.
10. A rejected non-HTTP signed URL falls back without exposing its query token
    in Xposed diagnostic messages.

For source/target language checking, the class can also be compiled with
`-source 17 -target 17` on a reduced JDK without `ct.sym`, but that does **not**
replace the workflow's `--release 17` API compatibility check.

## Device acceptance still required

Use a legitimately signed module build, authorized WhatsApp test account, and
known media fixtures across supported Android and WhatsApp versions. Inspect
the actual response type and hook registration. Compare SHA-256 hashes of
complete media downloads with parallel downloading enabled and disabled.
Exercise partial transfers, resumes, cancellations, connection failures,
servers that ignore Range, and repeated downloads. Measure latency, memory,
thread count, CPU, and network traffic on identical fixtures. Recheck Debug
and Release separately.

The implementation still cannot transparently resume from the original stream
after it has closed that stream and later parallel chunks fail. A future change
to that behavior needs a separate recovery design and device validation.
