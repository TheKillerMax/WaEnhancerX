package com.waenhancer.xposed.features.media;

import de.robv.android.xposed.XposedBridge;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.util.Arrays;

/** Exercise the production stream with deterministic HTTP Range responses. */
public final class ParallelDownloadingStreamTest {
    private static final int SIZE = ParallelDownloadingInputStream.CHUNK_SIZE + 1;
    private static final byte ORIGINAL_TAIL = 11;
    private static final byte RANGE_TAIL = 22;
    private static int checks;

    private enum Response {
        VALID, UNKNOWN_TOTAL, WRONG_END, INVALID_TOTAL, WRONG_LENGTH, COMPRESSED, NO_RANGE
    }

    private static void check(boolean condition, String description) {
        checks++;
        if (!condition) throw new AssertionError(description);
    }

    private static byte[] originalBytes() {
        byte[] bytes = new byte[SIZE];
        Arrays.fill(bytes, (byte) 7);
        bytes[SIZE - 1] = ORIGINAL_TAIL;
        return bytes;
    }

    private static URL fixtureUrl(Response response) throws Exception {
        return new URL(null, "https://fixture.test/media", new URLStreamHandler() {
            @Override
            protected URLConnection openConnection(URL url) {
                return new HttpURLConnection(url) {
                    @Override public void connect() {}
                    @Override public void disconnect() {}
                    @Override public boolean usingProxy() { return false; }
                    @Override public int getResponseCode() {
                        return response == Response.NO_RANGE ? 200 : 206;
                    }
                    @Override public String getHeaderField(String key) {
                        if (!"Content-Range".equalsIgnoreCase(key)) return null;
                        long start = ParallelDownloadingInputStream.CHUNK_SIZE;
                        long end = start + (response == Response.WRONG_END ? 1 : 0);
                        String total = response == Response.UNKNOWN_TOTAL ? "*"
                                : Long.toString(response == Response.INVALID_TOTAL ? end : end + 1);
                        return "bytes " + start + "-" + end + "/" + total;
                    }
                    @Override public long getContentLengthLong() {
                        return response == Response.WRONG_LENGTH ? 2 : 1;
                    }
                    @Override public String getContentEncoding() {
                        return response == Response.COMPRESSED ? "gzip" : null;
                    }
                    @Override public InputStream getInputStream() {
                        return new ByteArrayInputStream(new byte[] { RANGE_TAIL });
                    }
                };
            }
        });
    }

    private static void checkDelivery(Response response, byte expectedTail) throws Exception {
        try (InputStream stream = new ParallelDownloadingInputStream(
                new ByteArrayInputStream(originalBytes()), SIZE, 2, fixtureUrl(response), 0)) {
            byte[] result = stream.readAllBytes();
            check(result.length == SIZE, response + " changed the output length");
            check(result[0] == 7, response + " changed the original first chunk");
            check(result[SIZE - 1] == expectedTail,
                    response + " accepted malformed range data or failed to use valid range data");
        }
    }

    private static void checkPrematureOriginalEof() throws Exception {
        byte[] truncated = Arrays.copyOf(originalBytes(), ParallelDownloadingInputStream.CHUNK_SIZE - 1);
        try (InputStream stream = new ParallelDownloadingInputStream(
                new ByteArrayInputStream(truncated), SIZE, 2, fixtureUrl(Response.VALID), 0)) {
            try {
                stream.readAllBytes();
                throw new AssertionError("Premature end of the original stream was silently accepted");
            } catch (IOException expected) {
                check(true, "Truncated original stream is rejected");
            }
        }
    }

    private static void checkBounds() throws Exception {
        try (InputStream stream = new ParallelDownloadingInputStream(
                new ByteArrayInputStream(originalBytes()), SIZE, 2, fixtureUrl(Response.VALID), 0)) {
            try {
                stream.read(new byte[1], 2, 0);
                throw new AssertionError("Out-of-bounds empty read was accepted");
            } catch (IndexOutOfBoundsException expected) {
                check(true, "Invalid empty read bounds are rejected");
            }
        }
    }

    private static void checkSignedUrlRedaction() throws Exception {
        String secret = "signed-url-secret-fixture";
        URL url = new URL(null, "test://fixture.test/media?token=" + secret, new URLStreamHandler() {
            @Override protected URLConnection openConnection(URL target) {
                return new URLConnection(target) {
                    @Override public void connect() {}
                };
            }
        });
        XposedBridge.messages.clear();
        try (InputStream stream = new ParallelDownloadingInputStream(
                new ByteArrayInputStream(originalBytes()), SIZE, 2, url, 0)) {
            check(stream.readAllBytes()[SIZE - 1] == ORIGINAL_TAIL,
                    "A non-HTTP URL must fall back to the original stream");
        }
        check(!XposedBridge.messages.isEmpty(), "Non-HTTP fallback was not diagnosed");
        for (String message : XposedBridge.messages) {
            check(!message.contains(secret), "Signed media URL leaked into diagnostics");
        }
    }

    public static void main(String[] args) throws Exception {
        checkDelivery(Response.VALID, RANGE_TAIL);
        checkDelivery(Response.UNKNOWN_TOTAL, RANGE_TAIL);
        checkDelivery(Response.WRONG_END, ORIGINAL_TAIL);
        checkDelivery(Response.INVALID_TOTAL, ORIGINAL_TAIL);
        checkDelivery(Response.WRONG_LENGTH, ORIGINAL_TAIL);
        checkDelivery(Response.COMPRESSED, ORIGINAL_TAIL);
        checkDelivery(Response.NO_RANGE, ORIGINAL_TAIL);
        checkPrematureOriginalEof();
        checkBounds();
        checkSignedUrlRedaction();
        System.out.println("PASS: " + checks + " compiled stream and HTTP Range contract checks");
    }
}
