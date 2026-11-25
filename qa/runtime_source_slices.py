"""Literal public-runtime extraction for host QA; never supplies private implementations."""
import hashlib


class LiteralSlices:
    def __init__(self, path):
        self.path = path
        self.raw = path.read_bytes()
        self.text = self.raw.decode('utf-8')
        self.spans = []

    def take(self, name, start, end):
        text = self.text[start:end]
        first = len(self.text[:start].encode('utf-8'))
        last = len(self.text[:end].encode('utf-8'))
        assert self.raw[first:last] == text.encode('utf-8')
        self.spans.append({'name': name, 'start_byte': first, 'end_byte_exclusive': last,
                           'first_line': self.text.count('\n', 0, start) + 1,
                           'last_line': self.text.count('\n', 0, end) + 1,
                           'sha256': hashlib.sha256(self.raw[first:last]).hexdigest()})
        return text

    def between(self, name, before, after):
        assert self.text.count(before) == 1, (name, 'start anchor changed')
        start = self.text.index(before)
        end = self.text.index(after, start)
        return self.take(name, start, end)

    def receipt(self, generated, excluded):
        return {'path': str(self.path), 'sha256': hashlib.sha256(self.raw).hexdigest(),
                'literal_spans': self.spans, 'generated_sha256': hashlib.sha256(generated.encode()).hexdigest(),
                'excluded': excluded, 'private_implementations_or_doubles': False,
                'complete_class_compilation': False}


def main_hook_slice(path):
    source = LiteralSlices(path)
    text = source.text
    fields = source.between('runtime fields', '    public static final String RESTART_PERMISSION',
                            '    public static volatile String sModulePath;')
    prefs = source.between('disk preference access', '    public static synchronized XSharedPreferences getPrefs()',
                           '    @SuppressLint("UnspecifiedRegisterReceiverFlag")')
    start = text.index('            Runnable[] pendingInit = new Runnable[1];')
    end = text.index('    /**\n     * A target process may be created', start)
    ending = '        }\n    }\n\n'
    assert text[start:end].endswith(ending)
    initializer = source.take('onCreate initializer and lifecycle registration', start, end - len(ending))
    helpers = source.between('report receivers, observation, deferred delivery',
                             '    private static void showInjectionToastOnFirstVisibleActivity()',
                             '    /**\n     * Identifies the framework')
    errors = source.take('initialization failure presentation',
                         text.index('    private static void showInjectionErrorSheet(Throwable'), text.rfind('\n}'))
    generated = '''package com.waenhancer.xposed;
import android.app.Activity;
import android.app.Application;
import androidx.annotation.NonNull;
import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.widget.Toast;
import java.lang.reflect.Field;
import java.util.function.Consumer;
import java.util.concurrent.atomic.AtomicBoolean;
import java.io.PrintWriter;
import java.io.StringWriter;
import com.waenhancer.app.R;
import com.waenhancer.config.PreferenceSchema;
import com.waenhancer.utils.UiText;
import com.waenhancer.utils.WhatsAppPackageDetector;
import com.waenhancer.xposed.bridge.client.HookProviderIpc;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
import com.waenhancer.xposed.core.FeatureRegistry;
import com.waenhancer.xposed.core.RuntimeReportDispatcher;
import com.waenhancer.xposed.core.RuntimeReportDispatcher.Kind;
import com.waenhancer.xposed.core.RestartPromptController;
import com.waenhancer.xposed.core.VersionGuard;
import com.waenhancer.xposed.core.components.WaexBottomSheet;
import com.waenhancer.xposed.features.updates.WhatsAppUpdateSheet;
import com.waenhancer.xposed.utils.ActivityTracker;
import com.waenhancer.xposed.utils.HookErrors;
import com.waenhancer.xposed.utils.TargetExitReporter;
import de.robv.android.xposed.XSharedPreferences;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
public class MainHook {
''' + fields + prefs + '''
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        String packageName = lpparam.packageName;
        final XSharedPreferences preloadedPrefs = getPrefs();
''' + initializer + '\n    }\n' + helpers + errors + '\n}\n'
    assert 'licensing' not in generated and 'CustomAbPropsRuntime' not in generated
    return generated, source.receipt(generated, [
        'zygote and manager/system hooks', 'target package/process admission',
        'attach callback and private CustomAbPropsRuntime/PropsOverrideHook integration',
        'framework identity detection',
    ])


def app_listener_slice(path):
    source = LiteralSlices(path)
    listener = source.between('preference listener', '    private val preferenceListener =',
                              '    override fun attachBaseContext')
    registration = source.between('listener registration and version observation',
                                  '        PreferenceStores.publicStore(this).apply {',
                                  '        DiagnosticsRecorder.installManagerCrashCapture(this)')
    notify = source.between('targeted configuration notification',
                            '    private fun notifyHookedPackages(changedKey: String?)',
                            '    companion object {')
    constants = source.between('notification constants', '        private val PREFERENCES_URI:', '\n    }')
    generated = '''package com.waenhancer.app
import android.app.Application
import android.content.SharedPreferences
import android.content.Intent
import android.net.Uri
import com.waenhancer.config.PreferenceStores
import com.waenhancer.config.PreferenceRestartTracker
import com.waenhancer.config.PreferenceSyncPolicy
import com.waenhancer.utils.WhatsAppPackageDetector
class WaexApp : Application() {
''' + listener + '    override fun onCreate() {\n' + registration + '\n    }\n' + notify + \
        '    companion object {\n' + constants + '\n    }\n}\n'
    assert 'licensing' not in generated
    return generated, source.receipt(generated, [
        'application initialization except listener registration/version preference',
        'private keybox setup, locale, crash capture, recording import and singleton publication',
    ])


def provider_telemetry_slice(path):
    source = LiteralSlices(path)
    text = source.text
    fields = source.between('constants, onCreate and public preference access',
                            '    public static final String AUTHORITY',
                            '    /** The WhatsApp variant the caller is')
    prefix = source.between('Binder identity and authorization before clearCallingIdentity',
                            '    public Bundle call(@NonNull String method',
                            '            if ("request_update_check".equals(method))')
    reports = source.between('runtime registration, health and hook inventory persistence',
                             '            if ("register_hooked_package".equals(method))',
                             '            if ("report_target_exit_history".equals(method)')
    helpers = source.between('status normalization and caller ownership',
                             '    private static String allowedRuntimeStatus',
                             '    private Bundle encodePreferences')
    footer_start = text.rfind('            return null;\n        } finally {', 0,
                             text.index('    private static String allowedRuntimeStatus'))
    footer = source.take('identity restoration', footer_start, text.index('    @Nullable\n    private static String allowedRuntimeStatus', footer_start))
    generated = '''package com.waenhancer.xposed.bridge;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import java.util.Arrays;
import java.util.HashSet;
import com.waenhancer.utils.WhatsAppPackageDetector;
import com.waenhancer.utils.DiagnosticsRecorder;
public class HookProvider extends ContentProvider {
''' + fields + prefix + reports + footer + helpers + '''
    public Cursor query(Uri u,String[] p,String s,String[] a,String o){throw new UnsupportedOperationException("Outside telemetry slice");}
    public String getType(Uri u){throw new UnsupportedOperationException("Outside telemetry slice");}
    public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException("Outside telemetry slice");}
    public int delete(Uri u,String s,String[] a){throw new UnsupportedOperationException("Outside telemetry slice");}
    public int update(Uri u,ContentValues v,String s,String[] a){throw new UnsupportedOperationException("Outside telemetry slice");}
}
'''
    assert 'licensing' not in generated and 'ProFeatureGate' not in generated
    return generated, source.receipt(generated, [
        'other provider methods, generic configuration writes and entitlement materialization',
        'message, recording, theme, transcription and update services',
    ])


def runtime_model_slices(root):
    base = root / 'app/src/main/java/com/waenhancer/utils'
    detector = LiteralSlices(base / 'WhatsAppPackageDetector.kt')
    model = detector.between('runtime and scope model/delegates', 'data class InjectedHookItem(',
                              'object WhatsAppPackageDetector')
    constant = detector.between('module identity constant', '    private const val MODULE_PACKAGE =',
                                 '\n\n')
    select = detector.between('candidate selection', '    internal fun selectCandidates(',
                               '\n\n    /**')
    model = 'package com.waenhancer.utils\n' + model + 'object WhatsAppPackageDetector {\n' + constant + '\n' + select + '\n}\n'
    manager = LiteralSlices(base / 'TargetAppManager.kt')
    probe = manager.between('module state and shared root probe', 'enum class ModuleSignal {',
                             '/**\n * Universal source of truth')
    probe = ('package com.waenhancer.utils\nimport android.content.Context\n'
             'import android.os.SystemClock\nimport com.waenhancer.xposed.utils.AppRestartHelper\n') + probe
    reader = LiteralSlices(base / 'LsposedScopeReader.kt')
    scope = reader.between('scope snapshot model', 'data class LsposedScopeSnapshot(',
                            '/**\n * Reads the module')
    scope = 'package com.waenhancer.utils\nimport android.content.Context\n' + scope + '''
// Explicit SQLite/staging boundary. The framework UID suite never opens a database or runs root.
object LsposedScopeReader {
 const val STAGED_OK_MARKER="WAEX_LSPOSED_DB_OK"
 fun stageCommand(context:Context)="fixture_scope_stage"
 fun parseStaged(context:Context,staged:Boolean)=LsposedScopeSnapshot("com.waenhancer",emptySet(),false,LsposedScopeSnapshot.Source.UNAVAILABLE)
}
'''
    return {'RuntimeModel.kt': model, 'RootProbe.kt': probe, 'Scope.kt': scope}, [
        detector.receipt(model, ['detector Android/Compose transport methods']),
        manager.receipt(probe, ['TargetAppManager coroutine and UI lifecycle coordination']),
        reader.receipt(scope, ['scope SQLite staging/reading, replaced by unavailable scope boundary']),
    ]


def registry_reporting_slice(path):
    """Retain the actual dispatcher binding and JSON/IPC method; exclude feature installation."""
    source = LiteralSlices(path)
    field = source.between('per-registry report dispatcher',
                            '    private final RuntimeReportDispatcher hookReports;', '\n\n')
    constructors = source.between('default and shared-dispatcher constructor binding',
                                   '    public FeatureRegistry(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {',
                                   '        this.prefs = prefs;')
    delivery = source.take('default dispatcher and complete catalogue report method',
                            source.text.index('    private static final RuntimeReportDispatcher HOOK_REPORTS ='),
                            source.text.rfind('\n}'))
    generated = '''package com.waenhancer.xposed.core;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import androidx.annotation.NonNull;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.json.JSONArray;
import org.json.JSONObject;
import com.waenhancer.xposed.bridge.client.HookProviderIpc;
import de.robv.android.xposed.XposedBridge;
public class FeatureRegistry {
 public static final AtomicInteger attempted=new AtomicInteger(),initialized=new AtomicInteger();
 public static boolean fail,expectedFresh=true;
 private final SharedPreferences p;
 private final List<FeatureEntry> features=new ArrayList<>();
 private final String hookingMode="fixture";
 // Explicit feature-installation boundary: no private catalogue or HookingEngine substitute.
 private static class FeatureEntry {
  String name,className,category,status,error;
 }
''' + field + '\n' + constructors + '''
        this.p = prefs;
    }
 public void initializeAll(){
  attempted.incrementAndGet();
  if(p.getBoolean("fresh",false)!=expectedFresh)throw new AssertionError("unexpected initial preference snapshot");
  initialized.incrementAndGet();if(fail)throw new IllegalStateException("fixture initialization");
 }
 public boolean hasFailures(){return false;}
''' + delivery + '\n}\n'
    assert 'com.waenhancer.licensing' not in generated and 'import com.waenhancer.hooking' not in generated
    return generated, source.receipt(generated, [
        'private feature catalogue/constructors and installation/lifecycle bodies',
        'feature metadata values supplied by an explicit empty catalogue',
        'JSON serialization and provider endpoint are explicit transport boundaries',
    ])
