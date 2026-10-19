package com.waenhancer.xposed.views;

/** Pixel bounds shared by file/blob decoding and the final row-sized bitmap. */
final class StatusThumbnailPolicy {
    private StatusThumbnailPolicy() { }

    static int targetSize(int requestedPixels) {
        return Math.max(1, Math.min(512, requestedPixels));
    }

    static int sampleSize(int width, int height, int requestedPixels) {
        int longest = Math.max(width, height);
        int bound = targetSize(requestedPixels) * 4;
        int sample = 1;
        while ((longest + (long) sample - 1) / sample > bound) sample <<= 1;
        return sample;
    }
}
