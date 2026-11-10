from pathlib import Path
p=W/'app/src/main/java/com/waenhancer/xposed/features/media/MediaPreviewHook.kt';s=p.read_text(encoding='utf-8')
s=s.replace('        var lastProgressPostAt = 0L','        var lastProgressPostAt = 0L\n        var progressTask: Runnable? = null\n        var latestProgress = 0\n        var latestSizeInfo = ""\n        var pendingBitmap: Bitmap? = null')
s=s.replace('''        if (!isCurrent(session)) return
        mainHandler.postAtTime({ if (isCurrent(session)) action() }, session, SystemClock.uptimeMillis())''','''        synchronized(session) {
            if (!isCurrent(session)) return
            // Cancellation cannot remove callbacks between this check and registration.
            mainHandler.postAtTime({ if (isCurrent(session)) action() }, session, SystemClock.uptimeMillis())
        }''')
a=s.index('        val now = SystemClock.uptimeMillis()',s.index('    private fun postDownloadProgress('));b=s.index('\n    private fun displayImage(',a)
s=s[:a]+'''        synchronized(session) {
            if (!isCurrent(session)) return
            session.latestProgress = progress.coerceIn(0, 100)
            session.latestSizeInfo = sizeInfo
            if (session.progressTask != null) return
            val now = SystemClock.uptimeMillis()
            if (progress < 100 && now - session.lastProgressPostAt < 100L) return
            session.lastProgressPostAt = now
            val update = Runnable {
                val value: Int
                val size: String
                synchronized(session) {
                    session.progressTask = null
                    if (!isCurrent(session)) return@Runnable
                    value = session.latestProgress
                    size = session.latestSizeInfo
                }
                progressBar.progress = value
                progressText.text = UiText.get(R.string.waex_ui_downloading_1_s_2_s, "Downloading… %1\\$s%%\\n%2\\$s", value, size)
            }
            session.progressTask = update
            mainHandler.postAtTime(update, session, now)
        }
    }

    /** Only bitmaps decoded by this preview enter this pending ownership slot. */
    private fun postDecodedImage(session: PreviewSession, bitmap: Bitmap?, context: Context,
                                 container: FrameLayout, loading: LinearLayout) {
        synchronized(session) {
            if (!isCurrent(session)) {
                bitmap?.recycle()
                return
            }
            session.pendingBitmap = bitmap
            postPreview(session) {
                synchronized(session) { session.pendingBitmap = null }
                loading.visibility = View.GONE
                if (bitmap != null) displayImage(context, container, bitmap)
                else Toast.makeText(context, UiText.get(R.string.waex_ui_the_full_quality_image_could_not_be_de,
                        "The full-quality image could not be decoded"), Toast.LENGTH_LONG).show()
            }
        }
    }
''' + s[b:]
a=s.index('                postPreview(session) {',s.index('    private fun downloadAndDisplayMedia('));b=s.index('\n            }\n        } catch',a)
s=s[:a]+'''                if (mimeType.startsWith("image")) {
                    postDecodedImage(session, bitmap, context, contentContainer, loadingContainer)
                } else postPreview(session) {
                    loadingContainer.visibility = View.GONE
                    displayVideo(session, context, contentContainer, file)
                }'''+s[b:]
a=s.index('            postPreview(session) {',s.index('    private fun displayLocalMedia('));b=s.index('\n        } catch',a)
s=s[:a]+'''            if (mimeType.startsWith("image")) {
                postDecodedImage(session, bitmap, context, contentContainer, loadingContainer)
            } else postPreview(session) {
                loadingContainer.visibility = View.GONE
                displayVideo(session, context, contentContainer, file)
            }'''+s[b:]
s=s.replace('        val file: File?\n        synchronized(session)', '        val file: File?\n        val pendingBitmap: Bitmap?\n        synchronized(session)')
s=s.replace('            session.temporaryFile = null\n        }','            session.temporaryFile = null\n            pendingBitmap = session.pendingBitmap\n            session.pendingBitmap = null\n            session.progressTask = null\n        }')
s=s.replace('        mainHandler.removeCallbacksAndMessages(session)\n', '        mainHandler.removeCallbacksAndMessages(session)\n        pendingBitmap?.recycle()\n')
p.write_text(s,encoding='utf-8')
