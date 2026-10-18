package com.waenhancer.xposed.views;

import com.waenhancer.app.R;
import com.waenhancer.utils.UiText;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.text.TextPaint;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;

import com.waenhancer.utils.ContactNameResolver;
import com.waenhancer.utils.ContactIdentityPolicy;
import com.waenhancer.xposed.core.components.WaexBottomSheet;
import com.waenhancer.xposed.features.customization.IGStatusHook;
import com.waenhancer.xposed.features.homescreen.MenuIconLoader;
import com.waenhancer.xposed.utils.ActivityTracker;

import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

public class IGStatusAdapter extends ArrayAdapter<Object> {

    private static final String TAG = "[WAEX][IGStatusAdapter]";
    private static final StatusRowWorkQueue ROW_WORK = new StatusRowWorkQueue(2, 32);
    private static final StatusRowWorkQueue.Dispatcher MAIN = new StatusRowWorkQueue.Dispatcher() {
        private final Handler handler = new Handler(Looper.getMainLooper());
        @Override public boolean post(Runnable delivery) { return handler.post(delivery); }
        @Override public void remove(Runnable delivery) { handler.removeCallbacks(delivery); }
    };

    private Object[] statusItems = IGStatusHook.snapshotItems();
    private Bitmap defaultAvatarBitmap;
    private boolean defaultAvatarDark;

    @Override public void notifyDataSetChanged() {
        statusItems = IGStatusHook.snapshotItems();
        super.notifyDataSetChanged();
    }

    private final Class<?> statusInfoClazz;
    private final Class<?> contactStatusThumbnailClazz;
    private final Method setCountStatusMethod;

    public IGStatusAdapter(@NonNull Context context,
                           @NonNull Class<?> statusInfoClazz,
                           @Nullable Class<?> contactStatusThumbnailClazz) {
        super(context, 0);
        this.statusInfoClazz = statusInfoClazz;
        this.contactStatusThumbnailClazz = contactStatusThumbnailClazz;

        Method countMethod = null;
        if (contactStatusThumbnailClazz != null) {
            for (Method m : contactStatusThumbnailClazz.getDeclaredMethods()) {
                if (m.getParameterCount() == 3) {
                    Class<?>[] pTypes = m.getParameterTypes();
                    if (pTypes[0] == int.class && pTypes[1] == int.class && pTypes[2] == int.class) {
                        m.setAccessible(true);
                        countMethod = m;
                        break;
                    }
                }
            }
        }
        this.setCountStatusMethod = countMethod;
    }

    @Override
    public int getCount() {
        return statusItems.length;
    }

    @NonNull
    @Override
    public View getView(int position, @Nullable View convertView, @NonNull ViewGroup parent) {
        Object[] snapshot = statusItems;
        if (position < 0 || position >= snapshot.length) {
            if (convertView != null && convertView.getTag() instanceof ViewHolder) {
                ((ViewHolder) convertView.getTag()).cancelLoad();
                convertView.setOnClickListener(null);
            }
            return new View(getContext());
        }

        Object item = snapshot[position];
        ViewHolder holder;
        if (convertView == null || !(convertView.getTag() instanceof ViewHolder)
                || !((ViewHolder) convertView.getTag()).belongsTo(this)) {
            if (convertView != null && convertView.getTag() instanceof ViewHolder) {
                ((ViewHolder) convertView.getTag()).cancelLoad();
            }
            holder = new ViewHolder();
            convertView = createItemView(holder);
            convertView.setTag(holder);
        } else {
            holder = (ViewHolder) convertView.getTag();
        }

        // Apply left-side whitespace on My Status (position == 0) while keeping the scroller full-width
        int leftPad = (position == 0) ? dipToPx(12) : 0;
        convertView.setPadding(leftPad, 0, 0, 0);

        ViewGroup.LayoutParams lp = convertView.getLayoutParams();
        int baseWidth = dipToPx(82);
        int targetWidth = (position == 0) ? (baseWidth + leftPad) : baseWidth;
        if (lp != null && lp.width != targetWidth) {
            lp.width = targetWidth;
            convertView.setLayoutParams(lp);
        }

        if (item == null) {
            holder.bindMyStatus();
        } else {
            holder.bindItem(item);
        }

        convertView.setOnClickListener(v -> onItemClicked(holder));
        return convertView;
    }

    private void onItemClicked(ViewHolder holder) {
        Activity activity = ActivityTracker.getCurrentActivity();
        if (activity == null && getContext() instanceof Activity) {
            activity = (Activity) getContext();
        }
        if (activity == null) return;

        if (holder.isMyStatus) {
            if (hasOwnActiveStatus(getContext())) {
                // If I have status added, open my statuses screen (MyStatusesActivity)
                try {
                    Class<?> myStatusAct = XposedHelpers.findClassIfExists(
                            "com.whatsapp.status.playback.MyStatusesActivity", activity.getClassLoader());
                    if (myStatusAct != null) {
                        Intent intent = new Intent(activity, myStatusAct);
                        activity.startActivity(intent);
                        return;
                    }
                } catch (Throwable ignored) {}

                try {
                    Class<?> statusPlayback = XposedHelpers.findClassIfExists(
                            "com.whatsapp.status.playback.StatusPlaybackActivity", activity.getClassLoader());
                    if (statusPlayback != null) {
                        Intent intent = new Intent(activity, statusPlayback);
                        intent.putExtra("jid", "status@broadcast");
                        activity.startActivity(intent);
                        return;
                    }
                } catch (Throwable t) {
                    Toast.makeText(activity, UiText.get(R.string.waex_ui_error_8eecdde0, "Error: ") + t.getMessage(), Toast.LENGTH_SHORT).show();
                }
            } else {
                // Otherwise directly open write text status composer screen
                try {
                    Class<?> composerAct = XposedHelpers.findClassIfExists(
                            "com.whatsapp.status.composer.ConsolidatedStatusComposerActivity", activity.getClassLoader());
                    if (composerAct == null) {
                        composerAct = XposedHelpers.findClassIfExists(
                                "com.whatsapp.textstatuscomposer.TextStatusComposerActivity", activity.getClassLoader());
                    }
                    if (composerAct != null) {
                        Intent intent = new Intent(activity, composerAct);
                        intent.putExtra("status_composer_mode", 2);
                        activity.startActivity(intent);
                    }
                } catch (Throwable t) {
                    Toast.makeText(activity, UiText.get(R.string.waex_ui_error_8eecdde0, "Error: ") + t.getMessage(), Toast.LENGTH_SHORT).show();
                }
            }
            return;
        }

        if (holder.targetJid != null && !holder.targetJid.isEmpty()) {
            launchStatusPlayback(activity, holder.targetJid);
        }
    }

    public static boolean hasOwnActiveStatus(Context context) {
        if (context != null) {
            try {
                File statusDb = context.getDatabasePath("status.db");
                if (statusDb != null && statusDb.exists()) {
                    android.database.sqlite.SQLiteDatabase db = android.database.sqlite.SQLiteDatabase.openDatabase(
                            statusDb.getAbsolutePath(), null, android.database.sqlite.SQLiteDatabase.OPEN_READONLY);
                    try (android.database.Cursor cursor = db.rawQuery(
                            "SELECT total_count, last_status_timestamp FROM status_info WHERE chat_jid = 'status_me' LIMIT 1", null)) {
                        if (cursor.moveToFirst()) {
                            int totalCount = cursor.getInt(0);
                            long lastTimestamp = cursor.getLong(1);
                            long now = System.currentTimeMillis();
                            if (totalCount > 0 && (lastTimestamp <= 0 || (now - lastTimestamp < 24 * 60 * 60 * 1000L))) {
                                return true;
                            }
                        }
                    } finally {
                        db.close();
                    }
                }
            } catch (Throwable ignored) {}
        }

        for (Object item : IGStatusHook.snapshotItems()) {
            if (item == null) continue;
            try {
                Object jidObj = findJidObject(item, 4);
                if (jidObj != null) {
                    String str = String.valueOf(jidObj);
                    if (str.contains("status@broadcast") || str.startsWith("status@")) {
                        return true;
                    }
                }
            } catch (Throwable ignored) {}
        }
        return false;
    }

    public static boolean hasOwnActiveStatus() {
        return hasOwnActiveStatus(ActivityTracker.getCurrentActivity());
    }

    private void launchStatusPlayback(Activity activity, String rawJid) {
        try {
            Class<?> statusPlayback = XposedHelpers.findClassIfExists(
                    "com.whatsapp.status.playback.StatusPlaybackActivity", activity.getClassLoader());
            if (statusPlayback != null) {
                Intent intent = new Intent(activity, statusPlayback);
                intent.putExtra("jid", rawJid);
                activity.startActivity(intent);
            }
        } catch (Throwable t) {
            Toast.makeText(activity, UiText.get(R.string.waex_ui_error_opening_status_768e80f2, "Error opening status: ") + t.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private View createItemView(ViewHolder holder) {
        Context ctx = getContext();

        RelativeLayout root = new RelativeLayout(ctx);
        root.setLayoutParams(new RelativeLayout.LayoutParams(dipToPx(82), ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout frame = new FrameLayout(ctx);
        frame.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout column = new LinearLayout(ctx);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setGravity(Gravity.CENTER_HORIZONTAL);
        column.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        RelativeLayout avatarBox = new RelativeLayout(ctx);
        avatarBox.setLayoutParams(new RelativeLayout.LayoutParams(dipToPx(62), dipToPx(62)));

        ImageView photoView = new ImageView(ctx);
        RelativeLayout.LayoutParams photoParams = new RelativeLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        photoView.setLayoutParams(photoParams);
        photoView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        holder.photoView = photoView;

        RelativeLayout addBadge = new RelativeLayout(ctx);
        RelativeLayout.LayoutParams badgeParams = new RelativeLayout.LayoutParams(dipToPx(20), dipToPx(20));
        badgeParams.addRule(RelativeLayout.ALIGN_PARENT_BOTTOM);
        badgeParams.addRule(RelativeLayout.ALIGN_PARENT_END);
        addBadge.setLayoutParams(badgeParams);

        GradientDrawable badgeBg = new GradientDrawable();
        badgeBg.setShape(GradientDrawable.OVAL);
        badgeBg.setColor(0xFF25D366);
        addBadge.setBackground(badgeBg);

        ImageView addIcon = new ImageView(ctx);
        int iconSize = dipToPx(12);
        RelativeLayout.LayoutParams iconParams = new RelativeLayout.LayoutParams(iconSize, iconSize);
        iconParams.addRule(RelativeLayout.CENTER_IN_PARENT);
        addIcon.setLayoutParams(iconParams);
        Drawable editIcon = MenuIconLoader.load(ctx, "ic_waex_edit");
        if (editIcon != null) {
            addIcon.setImageDrawable(editIcon);
        } else {
            addIcon.setImageDrawable(createPlusDrawable(ctx));
        }
        addBadge.addView(addIcon);
        holder.addBadge = addBadge;

        avatarBox.addView(photoView);
        avatarBox.addView(addBadge);

        TextView nameView = new TextView(ctx);
        nameView.setEllipsize(TextUtils.TruncateAt.END);
        nameView.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams nameParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        nameParams.topMargin = dipToPx(4);
        nameView.setLayoutParams(nameParams);
        nameView.setTextAlignment(View.TEXT_ALIGNMENT_CENTER);
        nameView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f);
        nameView.setTypeface(Typeface.DEFAULT_BOLD);
        nameView.setMaxLines(1);
        nameView.setTextColor(isDarkTheme() ? 0xFFE9EDEF : 0xFF111B21);
        holder.nameView = nameView;

        column.addView(avatarBox);
        column.addView(nameView);
        frame.addView(column);
        root.addView(frame);
        root.addOnAttachStateChangeListener(holder);

        return root;
    }

    private static Object findJidObject(Object obj, int depth) {
        if (obj == null || depth < 0) return null;
        Class<?> clazz = obj.getClass();
        String name = clazz.getName();

        if (name.endsWith(".Jid") || name.endsWith(".UserJid") || name.endsWith(".PhoneUserJid") || name.endsWith(".DeviceJid")) {
            return obj;
        }

        if (name.startsWith("java.") || name.startsWith("android.") || name.startsWith("androidx.") || name.startsWith("kotlin.")) {
            return null;
        }

        if (obj instanceof String) {
            String str = (String) obj;
            if (str.contains("@s.whatsapp.net") || str.contains("@broadcast") || str.contains("@lid") || str.contains("@g.us")) {
                return str;
            }
        }

        for (Field f : clazz.getDeclaredFields()) {
            try {
                f.setAccessible(true);
                Object val = f.get(obj);
                if (val == null) continue;
                Object found = findJidObject(val, depth - 1);
                if (found != null) return found;
            } catch (Throwable ignored) {}
        }
        return null;
    }

    private class ViewHolder implements StatusRowWorkQueue.Target<LoadedRow>, View.OnAttachStateChangeListener {
        ImageView photoView;
        RelativeLayout addBadge;
        TextView nameView;
        boolean isMyStatus = false;
        String targetJid = null;
        boolean detached;
        boolean loaded;
        StatusRowWorkQueue.Ticket<LoadedRow> pending;

        boolean belongsTo(IGStatusAdapter adapter) { return IGStatusAdapter.this == adapter; }

        void cancelLoad() {
            if (pending != null) pending.cancel();
            pending = null;
        }

        void resetBinding() {
            cancelLoad();
            loaded = false;
            if (photoView != null) photoView.setImageDrawable(createDefaultAvatarDrawable());
        }

        void bindMyStatus() {
            resetBinding();
            this.isMyStatus = true;
            this.targetJid = "status@broadcast";
            if (addBadge != null) addBadge.setVisibility(View.VISIBLE);
            if (nameView != null) nameView.setText(UiText.get(R.string.waex_ui_my_status_43503c17, "My Status"));
            requestLoad();
        }

        void bindItem(Object item) {
            resetBinding();
            this.isMyStatus = false;
            if (addBadge != null) addBadge.setVisibility(View.GONE);
            String jid = null;
            Object jidObj = findJidObject(item, 4);
            if (jidObj != null) {
                try {
                    Method m = jidObj.getClass().getMethod("getRawString");
                    jid = (String) m.invoke(jidObj);
                } catch (Throwable ignored) {
                    jid = String.valueOf(jidObj);
                }
            }
            if (jid != null && jid.contains("@")) jid = jid.trim();
            this.targetJid = jid;
            if (nameView != null) nameView.setText("Contact");
            requestLoad();
        }

        void requestLoad() {
            if (detached || pending != null) return;
            Context app = getContext().getApplicationContext();
            // A queued load must not retain an Activity through this adapter.
            if (app == null || app instanceof Activity) return;
            final boolean own = isMyStatus;
            final String jid = targetJid;
            final int size = StatusThumbnailPolicy.targetSize(dipToPx(62));
            pending = ROW_WORK.submit(() -> loadRow(app, own, jid, size), this, MAIN);
            if (pending.isCancelled()) pending = null;
        }

        @Override public void onLoaded(StatusRowWorkQueue.Ticket<LoadedRow> ticket, LoadedRow row) {
            if (pending != ticket || ticket.isCancelled() || detached) return;
            pending = null;
            loaded = true;
            if (row == null) return;
            if (isMyStatus && addBadge != null) {
                addBadge.setVisibility(row.ownActive ? View.GONE : View.VISIBLE);
            }
            if (!isMyStatus && row.name != null && nameView != null) nameView.setText(row.name);
            if (row.photo != null && photoView != null) photoView.setImageDrawable(row.photo);
        }

        @Override public void onViewAttachedToWindow(View view) {
            detached = false;
            if (!loaded) requestLoad();
        }

        @Override public void onViewDetachedFromWindow(View view) {
            detached = true;
            if (pending != null) loaded = false;
            cancelLoad();
        }
    }

    private static final class LoadedRow {
        final boolean ownActive;
        final String name;
        final Drawable photo;
        LoadedRow(boolean ownActive, String name, Drawable photo) {
            this.ownActive = ownActive;
            this.name = name;
            this.photo = photo;
        }
    }

    private static LoadedRow loadRow(Context context, boolean own, String jid, int size) {
        if (own) {
            boolean active = hasOwnActiveStatus(context);
            Drawable photo = active ? loadMyLatestStatusPreview(context, size) : null;
            if (photo == null) photo = loadMyPhoto(context, size);
            return new LoadedRow(active, null, toCircleDrawable(context, photo, size));
        }
        String name = jid != null ? ContactNameResolver.INSTANCE.resolveName(context, jid, null, null) : null;
        Drawable photo = jid != null ? loadContactPhoto(context, jid, size) : null;
        return new LoadedRow(false, name, toCircleDrawable(context, photo, size));
    }

    private static Drawable loadMyLatestStatusPreview(Context context, int size) {
        try {
            File statusDb = context.getDatabasePath("status.db");
            if (statusDb == null || !statusDb.exists()) return null;

            android.database.sqlite.SQLiteDatabase db = android.database.sqlite.SQLiteDatabase.openDatabase(
                    statusDb.getAbsolutePath(), null, android.database.sqlite.SQLiteDatabase.OPEN_READONLY);
            try {
                // Query latest status row for status_me
                long statusRowId = -1;
                int type = -1;
                String textData = null;
                try (android.database.Cursor cursor = db.rawQuery(
                        "SELECT row_id, type, text_data FROM status WHERE sender_user_jid = 'status_me' ORDER BY timestamp DESC LIMIT 1", null)) {
                    if (cursor.moveToFirst()) {
                        statusRowId = cursor.getLong(0);
                        type = cursor.getInt(1);
                        textData = cursor.getString(2);
                    }
                }

                if (statusRowId <= 0) return null;

                // Check if image/video thumbnail exists in status_thumbnail
                try (android.database.Cursor thumbCursor = db.rawQuery(
                        "SELECT thumbnail, thumbnail_path FROM status_thumbnail WHERE status_row_id = ? LIMIT 1",
                        new String[]{String.valueOf(statusRowId)})) {
                    if (thumbCursor.moveToFirst()) {
                        byte[] blob = thumbCursor.getBlob(0);
                        if (blob != null && blob.length > 0) {
                            Bitmap bmp = decodeThumbnail(blob, size);
                            if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
                        }
                        String path = thumbCursor.getString(1);
                        if (path != null && !path.isEmpty()) {
                            File f = new File(path);
                            if (f.exists()) {
                                Bitmap bmp = decodeThumbnail(f.getAbsolutePath(), size);
                                if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
                            }
                        }
                    }
                }

                // If text status, check status_text for background color and render text preview
                int bgColor = 0xFF00A884;
                try (android.database.Cursor textCursor = db.rawQuery(
                        "SELECT background_color, thumbnail FROM status_text WHERE status_row_id = ? LIMIT 1",
                        new String[]{String.valueOf(statusRowId)})) {
                    if (textCursor.moveToFirst()) {
                        int col = textCursor.getInt(0);
                        if (col != 0) {
                            bgColor = col;
                        }
                        byte[] blob = textCursor.getBlob(1);
                        if (blob != null && blob.length > 0) {
                            Bitmap bmp = decodeThumbnail(blob, size);
                            if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
                        }
                    }
                }

                // Render circular preview bitmap with background color and text snippet
                Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
                Canvas canvas = new Canvas(bitmap);

                Paint bgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
                bgPaint.setColor(bgColor);
                canvas.drawCircle(size / 2f, size / 2f, size / 2f, bgPaint);

                if (textData != null && !textData.trim().isEmpty()) {
                    TextPaint textPaint = new TextPaint(Paint.ANTI_ALIAS_FLAG);
                    textPaint.setColor(Color.WHITE);
                    textPaint.setTextSize(size * 13f / 62f);
                    textPaint.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD));
                    textPaint.setTextAlign(Paint.Align.CENTER);

                    // Clean text (remove formatting symbols for small preview snippet)
                    String previewSnippet = textData.trim();
                    if (previewSnippet.length() > 6) {
                        previewSnippet = previewSnippet.substring(0, 5) + "…";
                    }

                    Paint.FontMetrics fm = textPaint.getFontMetrics();
                    float textY = (size / 2f) - ((fm.descent + fm.ascent) / 2f);
                    canvas.drawText(previewSnippet, size / 2f, textY, textPaint);
                }

                return new BitmapDrawable(context.getResources(), bitmap);
            } finally {
                db.close();
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static Drawable loadMyPhoto(Context context, int size) {
        try {
            File filesDir = context.getFilesDir();
            File avatarDir = new File(filesDir, "Avatars");
            File meJ = new File(avatarDir, "me.j");
            if (meJ.exists()) {
                Bitmap bmp = decodeThumbnail(meJ.getAbsolutePath(), size);
                if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
            }
            File me = new File(filesDir, "me.jpg");
            if (me.exists()) {
                Bitmap bmp = decodeThumbnail(me.getAbsolutePath(), size);
                if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static Drawable loadContactPhoto(Context context, String jid, int size) {
        if (ContactIdentityPolicy.canonicalJid(jid) == null) return null;
        try {
            File filesDir = context.getFilesDir();
            File avatarDir = new File(filesDir, "Avatars");
            // Check direct avatar file: e.g. <jid>.j or <user>@s.whatsapp.net.j
            File jFile = new File(avatarDir, jid + ".j");
            if (jFile.exists()) {
                Bitmap bmp = decodeThumbnail(jFile.getAbsolutePath(), size);
                if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
            }

            // A LID/group number is not a phone alias. Only the exact JID above
            // is valid without a verified mapping; phone-only caches require PN.
            String user = ContactIdentityPolicy.phoneUser(jid);
            if (user == null) return null;

            // Check Profile Pictures cache
            File cacheDir = context.getCacheDir();
            File picDir = new File(cacheDir, "Profile Pictures");
            if (picDir.exists()) {
                File pic = new File(picDir, user + ".jpg");
                if (pic.exists()) {
                    Bitmap bmp = decodeThumbnail(pic.getAbsolutePath(), size);
                    if (bmp != null) return new BitmapDrawable(context.getResources(), bmp);
                }
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static Bitmap decodeThumbnail(String path, int size) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(path, options);
        if (options.outWidth <= 0 || options.outHeight <= 0) return null;
        options.inSampleSize = StatusThumbnailPolicy.sampleSize(options.outWidth, options.outHeight, size);
        options.inJustDecodeBounds = false;
        return BitmapFactory.decodeFile(path, options);
    }

    private static Bitmap decodeThumbnail(byte[] bytes, int size) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        if (options.outWidth <= 0 || options.outHeight <= 0) return null;
        options.inSampleSize = StatusThumbnailPolicy.sampleSize(options.outWidth, options.outHeight, size);
        options.inJustDecodeBounds = false;
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    private static Drawable toCircleDrawable(Context context, Drawable drawable, int requestedSize) {
        if (drawable == null) return null;
        int size = StatusThumbnailPolicy.targetSize(requestedSize);
        try {
            Bitmap src;
            if (drawable instanceof BitmapDrawable) {
                src = ((BitmapDrawable) drawable).getBitmap();
            } else {
                src = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
                Canvas canvas = new Canvas(src);
                drawable.setBounds(0, 0, size, size);
                drawable.draw(canvas);
            }
            if (src == null || src.getWidth() <= 0 || src.getHeight() <= 0) return null;
            Bitmap output = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
            Canvas canvas = new Canvas(output);
            Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
            android.graphics.BitmapShader shader = new android.graphics.BitmapShader(src,
                    android.graphics.Shader.TileMode.CLAMP, android.graphics.Shader.TileMode.CLAMP);
            float scale = Math.max(size / (float) src.getWidth(), size / (float) src.getHeight());
            Matrix matrix = new Matrix();
            matrix.setScale(scale, scale);
            matrix.postTranslate((size - src.getWidth() * scale) / 2f,
                    (size - src.getHeight() * scale) / 2f);
            shader.setLocalMatrix(matrix);
            paint.setShader(shader);
            float r = size / 2f;
            canvas.drawCircle(r, r, r, paint);
            return new BitmapDrawable(context.getResources(), output);
        } catch (RuntimeException | LinkageError ignored) {
            return null;
        }
    }

    private Drawable createPlusDrawable(Context ctx) {
        int size = dipToPx(14);
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.WHITE);
        paint.setStrokeWidth(dipToPx(2f));
        paint.setStrokeCap(Paint.Cap.ROUND);
        float mid = size / 2f;
        float offset = size * 0.25f;
        canvas.drawLine(mid, mid - offset, mid, mid + offset, paint);
        canvas.drawLine(mid - offset, mid, mid + offset, mid, paint);
        return new BitmapDrawable(ctx.getResources(), bitmap);
    }

    private Drawable createDefaultAvatarDrawable() {
        int size = StatusThumbnailPolicy.targetSize(dipToPx(62));
        boolean dark = isDarkTheme();
        if (defaultAvatarBitmap != null && defaultAvatarBitmap.getWidth() == size && defaultAvatarDark == dark) {
            return new BitmapDrawable(getContext().getResources(), defaultAvatarBitmap);
        }
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint bgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        bgPaint.setColor(dark ? 0xFF2A3942 : 0xFFDFE5E7);
        float radius = size / 2f;
        canvas.drawCircle(radius, radius, radius, bgPaint);

        Paint fgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        fgPaint.setColor(dark ? 0xFF8696A0 : 0xFF667781);
        canvas.drawCircle(radius, size * 0.38f, size * 0.18f, fgPaint);
        RectF bodyRect = new RectF(size * 0.22f, size * 0.62f, size * 0.78f, size * 1.05f);
        canvas.drawRoundRect(bodyRect, size * 0.25f, size * 0.25f, fgPaint);
        defaultAvatarBitmap = bitmap;
        defaultAvatarDark = dark;
        return new BitmapDrawable(getContext().getResources(), bitmap);
    }

    private int dipToPx(float dp) {
        return (int) (dp * getContext().getResources().getDisplayMetrics().density + 0.5f);
    }

    private boolean isDarkTheme() {
        int nightMode = getContext().getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK;
        return nightMode == android.content.res.Configuration.UI_MODE_NIGHT_YES;
    }
}
