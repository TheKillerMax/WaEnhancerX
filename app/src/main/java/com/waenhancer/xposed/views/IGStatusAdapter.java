package com.waenhancer.xposed.views;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
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
        return IGStatusHook.items.size();
    }

    @NonNull
    @Override
    public View getView(int position, @Nullable View convertView, @NonNull ViewGroup parent) {
        if (position >= IGStatusHook.items.size()) {
            return convertView != null ? convertView : new View(getContext());
        }

        Object item = IGStatusHook.items.get(position);
        ViewHolder holder;
        if (convertView == null) {
            holder = new ViewHolder();
            convertView = createItemView(holder);
            convertView.setTag(holder);
        } else {
            holder = (ViewHolder) convertView.getTag();
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
        XposedBridge.log(TAG + " onItemClicked: isMyStatus=" + holder.isMyStatus + ", targetJid=" + holder.targetJid);
        Activity activity = ActivityTracker.getCurrentActivity();
        if (activity == null && getContext() instanceof Activity) {
            activity = (Activity) getContext();
        }
        if (activity == null) {
            XposedBridge.log(TAG + " onItemClicked: activity is null");
            return;
        }

        if (holder.isMyStatus) {
            showMyStatusPickerSheet(activity);
            return;
        }

        if (holder.targetJid != null && !holder.targetJid.isEmpty()) {
            launchStatusPlayback(activity, holder.targetJid);
        } else {
            XposedBridge.log(TAG + " onItemClicked: targetJid is null or empty");
        }
    }

    private void showMyStatusPickerSheet(Activity activity) {
        try {
            WaexBottomSheet sheet = new WaexBottomSheet(activity);
            sheet.setTitle("Select Status Type");

            LinearLayout optionsContainer = new LinearLayout(activity);
            optionsContainer.setOrientation(LinearLayout.VERTICAL);
            int pad = dipToPx(16);
            optionsContainer.setPadding(pad, pad, pad, pad);

            // 1. View My Statuses
            addOptionRow(optionsContainer, "View My Status", "ic_waex_logo", () -> {
                try {
                    Class<?> myStatusAct = XposedHelpers.findClassIfExists(
                            "com.whatsapp.status.playback.MyStatusesActivity", activity.getClassLoader());
                    if (myStatusAct != null) {
                        Intent intent = new Intent(activity, myStatusAct);
                        activity.startActivity(intent);
                    }
                } catch (Throwable t) {
                    Toast.makeText(activity, "Error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
                }
            });

            // 2. Open Camera
            addOptionRow(optionsContainer, "Open Camera", "ic_waex_camera", () -> {
                try {
                    Class<?> cameraAct = XposedHelpers.findClassIfExists(
                            "com.whatsapp.camera.ui.CameraActivity", activity.getClassLoader());
                    if (cameraAct == null) {
                        cameraAct = XposedHelpers.findClassIfExists(
                                "com.whatsapp.camera.CameraActivity", activity.getClassLoader());
                    }
                    if (cameraAct != null) {
                        Intent intent = new Intent(activity, cameraAct);
                        intent.putExtra("jid", "status@broadcast");
                        intent.putExtra("camera_origin", 4);
                        intent.putExtra("is_coming_from_chat", false);
                        intent.putExtra("media_sharing_user_journey_origin", 32);
                        intent.putExtra("media_sharing_user_journey_start_target", 9);
                        intent.putExtra("media_sharing_user_journey_chat_type", 4);
                        activity.startActivity(intent);
                    }
                } catch (Throwable t) {
                    Toast.makeText(activity, "Error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
                }
            });

            // 3. Text Status Composer
            addOptionRow(optionsContainer, "Write Text Status", "ic_waex_edit", () -> {
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
                    Toast.makeText(activity, "Error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
                }
            });

            sheet.setView(optionsContainer);
            sheet.create().show();
        } catch (Throwable t) {
            XposedBridge.log(TAG + " showMyStatusPickerSheet failed: " + t.getMessage());
        }
    }

    private void addOptionRow(LinearLayout parent, String label, String iconName, Runnable onClick) {
        Context ctx = parent.getContext();
        LinearLayout row = new LinearLayout(ctx);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        int padV = dipToPx(12);
        int padH = dipToPx(8);
        row.setPadding(padH, padV, padH, padV);

        ImageView icon = new ImageView(ctx);
        int iconSize = dipToPx(24);
        LinearLayout.LayoutParams iconParams = new LinearLayout.LayoutParams(iconSize, iconSize);
        iconParams.rightMargin = dipToPx(16);
        icon.setLayoutParams(iconParams);
        Drawable d = MenuIconLoader.load(ctx, iconName);
        if (d != null) {
            icon.setImageDrawable(d);
        }
        row.addView(icon);

        TextView tv = new TextView(ctx);
        tv.setText(label);
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f);
        tv.setTextColor(isDarkTheme() ? Color.WHITE : Color.BLACK);
        row.addView(tv);

        row.setOnClickListener(v -> onClick.run());
        parent.addView(row);
    }

    private void launchStatusPlayback(Activity activity, String rawJid) {
        try {
            XposedBridge.log(TAG + " launchStatusPlayback for rawJid=" + rawJid);
            Class<?> statusPlayback = XposedHelpers.findClassIfExists(
                    "com.whatsapp.status.playback.StatusPlaybackActivity", activity.getClassLoader());
            if (statusPlayback != null) {
                Intent intent = new Intent(activity, statusPlayback);
                intent.putExtra("jid", rawJid);
                activity.startActivity(intent);
            } else {
                XposedBridge.log(TAG + " launchStatusPlayback: StatusPlaybackActivity class not found");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " launchStatusPlayback error: " + t.getMessage());
            Toast.makeText(activity, "Error opening status: " + t.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private View createItemView(ViewHolder holder) {
        Context ctx = getContext();

        RelativeLayout root = new RelativeLayout(ctx);
        root.setLayoutParams(new RelativeLayout.LayoutParams(dipToPx(86), ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout frame = new FrameLayout(ctx);
        frame.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout column = new LinearLayout(ctx);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setGravity(Gravity.CENTER_HORIZONTAL);
        column.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        RelativeLayout avatarBox = new RelativeLayout(ctx);
        avatarBox.setLayoutParams(new RelativeLayout.LayoutParams(dipToPx(64), dipToPx(64)));

        ImageView photoView;
        if (contactStatusThumbnailClazz != null) {
            try {
                Constructor<?> ctor = contactStatusThumbnailClazz.getConstructor(Context.class);
                photoView = (ImageView) ctor.newInstance(ctx);
            } catch (Throwable t) {
                photoView = new ImageView(ctx);
            }
        } else {
            photoView = new ImageView(ctx);
        }

        RelativeLayout.LayoutParams photoParams = new RelativeLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        photoView.setLayoutParams(photoParams);
        int pad = dipToPx(2.5f);
        photoView.setPadding(pad, pad, pad, pad);
        photoView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        holder.photoView = photoView;

        try {
            XposedHelpers.callMethod(photoView, "setBorderSize", (float) dipToPx(2.5f));
            XposedHelpers.callMethod(photoView, "setCornerRadius", (float) dipToPx(80f));
            XposedHelpers.setObjectField(photoView, "A02", Color.GRAY);
            XposedHelpers.setObjectField(photoView, "A03", 0xFF25D366);
        } catch (Throwable ignored) {}

        RelativeLayout addBadge = new RelativeLayout(ctx);
        RelativeLayout.LayoutParams badgeParams = new RelativeLayout.LayoutParams(dipToPx(22), dipToPx(22));
        badgeParams.addRule(RelativeLayout.ALIGN_PARENT_BOTTOM);
        badgeParams.addRule(RelativeLayout.ALIGN_PARENT_END);
        addBadge.setLayoutParams(badgeParams);

        GradientDrawable badgeBg = new GradientDrawable();
        badgeBg.setShape(GradientDrawable.OVAL);
        badgeBg.setColor(0xFF25D366);
        addBadge.setBackground(badgeBg);

        ImageView addIcon = new ImageView(ctx);
        int iconSize = dipToPx(14);
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

        return root;
    }

    private class ViewHolder {
        ImageView photoView;
        RelativeLayout addBadge;
        TextView nameView;
        boolean isMyStatus = false;
        String targetJid = null;

        void bindMyStatus() {
            this.isMyStatus = true;
            this.targetJid = "status@broadcast";
            if (addBadge != null) addBadge.setVisibility(View.VISIBLE);
            if (nameView != null) nameView.setText("My Status");

            Drawable myPhoto = loadMyPhoto();
            if (myPhoto != null && photoView != null) {
                photoView.setImageDrawable(myPhoto);
            } else if (photoView != null) {
                Drawable placeholder = MenuIconLoader.load(getContext(), "ic_waex_user_foreground");
                if (placeholder != null) {
                    photoView.setImageDrawable(placeholder);
                } else {
                    photoView.setImageDrawable(createDefaultAvatarDrawable());
                }
            }
            setCount(0, 0);
        }

        void bindItem(Object item) {
            this.isMyStatus = false;
            if (addBadge != null) addBadge.setVisibility(View.GONE);

            String jid = null;
            int unseen = 0;
            int total = 0;

            try {
                Object statusInfo = null;
                // Item is either C42610Irb or has statusInfo directly
                for (Field f : item.getClass().getDeclaredFields()) {
                    f.setAccessible(true);
                    Object val = f.get(item);
                    if (val != null && (statusInfoClazz.isInstance(val) || val.getClass().getName().contains("EaO"))) {
                        statusInfo = val;
                        break;
                    }
                }
                if (statusInfo == null && statusInfoClazz.isInstance(item)) {
                    statusInfo = item;
                }

                if (statusInfo != null) {
                    for (Field f : statusInfo.getClass().getDeclaredFields()) {
                        f.setAccessible(true);
                        Object val = f.get(statusInfo);
                        if (val != null && val.getClass().getName().contains("jid")) {
                            Method getRaw = val.getClass().getMethod("getRawString");
                            jid = (String) getRaw.invoke(val);
                            break;
                        }
                    }
                    if (jid == null) {
                        // inspect fields for JID pattern
                        for (Field f : statusInfo.getClass().getDeclaredFields()) {
                            f.setAccessible(true);
                            Object val = f.get(statusInfo);
                            if (val != null) {
                                String str = val.toString();
                                if (str.contains("@s.whatsapp.net") || str.contains("@lid")) {
                                    jid = str.replaceAll(".*([0-9]+@[a-z\\.]+).*", "$1");
                                    break;
                                }
                            }
                        }
                    }

                    // unread / total count
                    try {
                        Method mUnread = statusInfo.getClass().getMethod("A02");
                        unseen = (Integer) mUnread.invoke(statusInfo);
                        Method mTotal = statusInfo.getClass().getMethod("A01");
                        total = (Integer) mTotal.invoke(statusInfo);
                    } catch (Throwable ignored) {
                        unseen = 1;
                        total = 1;
                    }
                }
            } catch (Throwable t) {
                XposedBridge.log(TAG + " bindItem extraction error: " + t.getMessage());
            }

            this.targetJid = jid;
            XposedBridge.log(TAG + " bindItem for item=" + item.getClass().getName() + " -> targetJid=" + jid);
            String resolvedName = jid != null ? ContactNameResolver.INSTANCE.resolveName(getContext(), jid, null, null) : "Contact";
            if (nameView != null) nameView.setText(resolvedName);

            Drawable contactPhoto = jid != null ? loadContactPhoto(jid) : null;
            if (contactPhoto != null && photoView != null) {
                photoView.setImageDrawable(contactPhoto);
            } else if (photoView != null) {
                Drawable placeholder = MenuIconLoader.load(getContext(), "ic_waex_user_foreground");
                if (placeholder != null) {
                    photoView.setImageDrawable(placeholder);
                } else {
                    photoView.setImageDrawable(createDefaultAvatarDrawable());
                }
            }

            setCount(unseen, total);
        }

        private void setCount(int countUnseen, int total) {
            if (setCountStatusMethod != null && photoView != null) {
                try {
                    setCountStatusMethod.invoke(photoView, total, countUnseen, total);
                } catch (Throwable ignored) {}
            }
        }
    }

    private Drawable loadMyPhoto() {
        try {
            File filesDir = getContext().getFilesDir();
            File me = new File(filesDir, "me.jpg");
            if (me.exists()) {
                return Drawable.createFromPath(me.getAbsolutePath());
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private Drawable loadContactPhoto(String jid) {
        try {
            String user = jid.contains("@") ? jid.substring(0, jid.indexOf("@")) : jid;
            File cacheDir = getContext().getCacheDir();
            File picDir = new File(cacheDir, "Profile Pictures");
            if (picDir.exists()) {
                File pic = new File(picDir, user + ".jpg");
                if (pic.exists()) {
                    Bitmap bmp = BitmapFactory.decodeFile(pic.getAbsolutePath());
                    if (bmp != null) return new BitmapDrawable(getContext().getResources(), bmp);
                }
            }
        } catch (Throwable ignored) {}
        return null;
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
        int size = dipToPx(64);
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint bgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        bgPaint.setColor(isDarkTheme() ? 0xFF2A3942 : 0xFFDFE5E7);
        float radius = size / 2f;
        canvas.drawCircle(radius, radius, radius, bgPaint);

        Paint fgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        fgPaint.setColor(isDarkTheme() ? 0xFF8696A0 : 0xFF667781);
        canvas.drawCircle(radius, size * 0.38f, size * 0.18f, fgPaint);
        RectF bodyRect = new RectF(size * 0.22f, size * 0.62f, size * 0.78f, size * 1.05f);
        canvas.drawRoundRect(bodyRect, size * 0.25f, size * 0.25f, fgPaint);
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
