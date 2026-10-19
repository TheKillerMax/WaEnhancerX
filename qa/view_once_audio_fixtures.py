"""Explicit Android/host model for the independently verified audio viewer path."""
AUDIO_STUBS = {
'X/Manager.java': '''package X;public class Manager{public androidx.fragment.app.Fragment audio;public String requested;
 public androidx.fragment.app.Fragment byTag(String tag){requested=tag;return tag.equals("view_once_audio")?audio:null;}
 public androidx.fragment.app.Fragment decoyTag(String tag){return audio;}}''',
'X/ActivitySupport.java': '''package X;public class ActivitySupport extends android.app.Activity{
 public Manager manager=new Manager();public RuntimeException failure;public Manager getSupportFragmentManager(){if(failure!=null)throw failure;return manager;}}''',
'X/Audio.java': 'package X;public class Audio extends Media{public Audio(Key k,Data d){super(k,d);}}',
'com/whatsapp/viewonce/ui/messaging/ViewOnceViewerActivity.java': '''package com.whatsapp.viewonce.ui.messaging;
 public class ViewOnceViewerActivity extends X.ActivitySupport{public X.Key key,backupKey;
 public void onCreate(android.os.Bundle b){}public boolean onCreateOptionsMenu(android.view.Menu m){return true;}
 public boolean onPrepareOptionsMenu(android.view.Menu m){return true;}public boolean onOptionsItemSelected(android.view.MenuItem i){return true;}}''',
'com/whatsapp/viewonce/ui/messaging/BaseViewOnceMessageViewerFragment.java': '''package com.whatsapp.viewonce.ui.messaging;
 public class BaseViewOnceMessageViewerFragment extends androidx.fragment.app.Fragment{public X.Message message,decoy; }''',
'com/whatsapp/viewonce/ui/messaging/ViewOnceAudioFragment.java': '''package com.whatsapp.viewonce.ui.messaging;
 public class ViewOnceAudioFragment extends BaseViewOnceMessageViewerFragment{
 public void bind(android.os.Bundle b,android.view.View v){}public void decoyBind(android.os.Bundle b,android.view.View v){}}''',
'com/whatsapp/viewonce/ui/messaging/ViewOnceTextFragment.java': '''package com.whatsapp.viewonce.ui.messaging;
 public class ViewOnceTextFragment extends BaseViewOnceMessageViewerFragment{}''',
}
