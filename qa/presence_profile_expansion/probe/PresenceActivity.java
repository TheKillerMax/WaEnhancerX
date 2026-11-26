package org.waex.qa.presence.host;

import android.app.Activity;
import android.os.Bundle;
import android.widget.FrameLayout;

/** A real window for the synthetic row, with no host application or services. */
public final class PresenceActivity extends Activity {
    public FrameLayout content;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        content = new FrameLayout(this);
        setContentView(content);
    }
}
