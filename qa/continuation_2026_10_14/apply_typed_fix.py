from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve(); src=root/'app/src/main/java/com/waenhancer'
p=src/'core/preferences/WaexPreferenceManager.java';s=p.read_text();anchor='    public java.util.Set<String> getStringSet(String key, java.util.Set<String> defaultValue) {'
addition='''    /**
     * Commit a schema-declared public STRING and report persistence failure.
     * Existing void setters keep their contract. A false result is not a disk or
     * in-memory rollback guarantee: SharedPreferences may update memory first.
     */
    public boolean putPublicString(String key, String value) {
        if (value == null || !isPublicType(key, PreferenceSchema.Type.STRING)) return false;
        try {
            if (!PreferenceStores.publicStore(context).edit().putString(key, value).commit()) {
                return false;
            }
            notifyChange();
            return true;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    /** Commit a defensive snapshot of a public STRING_SET, notifying only on success. */
    public boolean putPublicStringSet(String key, java.util.Set<String> value) {
        if (value == null || !isPublicType(key, PreferenceSchema.Type.STRING_SET)) return false;
        try {
            java.util.Set<String> snapshot = new java.util.LinkedHashSet<>();
            for (Object element : value) {
                if (!(element instanceof String)) return false;
                snapshot.add((String) element);
            }
            if (!PreferenceStores.publicStore(context).edit().putStringSet(key, snapshot).commit()) {
                return false;
            }
            notifyChange();
            return true;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private static boolean isPublicType(String key, PreferenceSchema.Type type) {
        if (key == null || key.isEmpty()) return false;
        PreferenceSchema.Entry entry = PreferenceSchema.entry(key);
        return entry != null && entry.type == type && entry.store == PreferenceSchema.Store.PUBLIC;
    }

'''
assert s.count(anchor)==1;s=s.replace(anchor,addition+anchor);p.write_text(s)
p=src/'ui/screens/settings/StylesSettingsScreen.kt';s=p.read_text();anchor='''    onSaved: () -> Unit
) {
    when (key) {'''
rep='''    onSaved: () -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val completeSave: (Boolean) -> Unit = { saved ->
        if (saved) {
            onSaved()
        } else {
            // Keep the editor and its input open so the user can retry.
            Toast.makeText(context, "Unable to save setting", Toast.LENGTH_SHORT).show()
        }
    }
    when (key) {'''
assert s.count(anchor)==1;s=s.replace(anchor,rep)
replacements={
'preferenceManager.putString("css_theme", it.trim()); onSaved()':'completeSave(preferenceManager.putPublicString("css_theme", it.trim()))',
'preferenceManager.putString("change_dpi", it.trim()); onSaved()':'completeSave(preferenceManager.putPublicString("change_dpi", it.trim()))',
'preferenceManager.putString("chatfilter", it); onSaved()':'completeSave(preferenceManager.putPublicString("chatfilter", it))',
'preferenceManager.putString("waex_menu_style", it); onSaved()':'completeSave(preferenceManager.putPublicString("waex_menu_style", it))',
'preferenceManager.putStringSet("hidetabs", it); onSaved()':'completeSave(preferenceManager.putPublicStringSet("hidetabs", it))'}
for a,b in replacements.items(): assert s.count(a)==1;s=s.replace(a,b)
p.write_text(s)
p=root/'qa/test_media_preference_sync.py';s=p.read_text();s=s.replace(' String getString(String key, String fallback);',' String getString(String key, String fallback);\n java.util.Set<String> getStringSet(String key, java.util.Set<String> fallback);');s=s.replace('  Editor putString(String key, String value);','  Editor putString(String key, String value);\n  Editor putStringSet(String key, java.util.Set<String> value);');p.write_text(s)
p=root/'qa/TestMediaPreferenceBatch.java';s=p.read_text();s=s.replace('        boolean throwCommit;','        boolean throwCommit;\n        boolean applyBeforeFailure;\n        boolean throwEdit;')
a='''        @Override public int getInt(String key, int fallback) {''';b='''        @Override @SuppressWarnings("unchecked")
        public java.util.Set<String> getStringSet(String key, java.util.Set<String> fallback) {
            Object value = values.get(key);
            if (value == null) return fallback;
            if (!(value instanceof java.util.Set)) throw new ClassCastException();
            return (java.util.Set<String>) value;
        }
''';assert s.count(a)==1;s=s.replace(a,b+a)
s=s.replace('@Override public SharedPreferences.Editor edit() { return new Batch(); }','''@Override public SharedPreferences.Editor edit() {
            if (throwEdit) throw new IllegalStateException("Editor unavailable");
            return new Batch();
        }''')
a='''            @Override public Editor putInt(String key, int value)''';b='''            @Override public Editor putStringSet(String key, java.util.Set<String> value) {
                // Retain the reference deliberately: the manager must snapshot its input.
                adds.put(key, value); return this;
            }
''';assert s.count(a)==1;s=s.replace(a,b+a)
s=s.replace('if (failCommit) return false;', 'if (failCommit && !applyBeforeFailure) return false;')
s=s.replace('''                return true;
            }
        }
    }''','''                return !failCommit;
            }
        }
    }''',1)
a='''        System.out.println("PASS: " + checks + " production manager atomicity, schema and failure checks");'''
b='''        testTypedWrites();
        System.out.println("PASS: " + checks + " production manager/schema/failure checks (Android doubles)");''';assert s.count(a)==1;s=s.replace(a,b)
anchor='''    public static void main(String[] args) {'''
tests='''    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void testTypedWrites() {
        FakeContext c = new FakeContext();
        WaexPreferenceManager m = new WaexPreferenceManager(c);
        String[][] inputs = {{"css_theme", "#title {color: #112233;}"},
                {"change_dpi", "320"}, {"chatfilter", "1"}, {"waex_menu_style", "icons"}};
        for (String[] input : inputs) {
            int commits = c.publicStore.commits, notifications = c.resolver.notifications;
            check(m.putPublicString(input[0], input[1]), "valid typed string rejected");
            check(input[1].equals(m.getString(input[0], "")), "typed string not persisted");
            check(c.publicStore.commits == commits + 1, "typed string commits exactly once");
            check(c.resolver.notifications == notifications + 1, "typed string notification");
        }
        java.util.Set<String> tabs = new java.util.LinkedHashSet<>(java.util.Arrays.asList("300", "600"));
        check(m.putPublicStringSet("hidetabs", tabs), "valid typed set rejected");
        tabs.add("400");
        check(!m.getStringSet("hidetabs", Collections.emptySet()).contains("400"), "caller mutated stored set");
        java.util.Set<String> read = m.getStringSet("hidetabs", Collections.emptySet());
        read.clear();
        check(m.getStringSet("hidetabs", Collections.emptySet()).size() == 2, "read leaked mutable storage");
        check(m.putPublicStringSet("hidetabs", Collections.emptySet()), "empty typed set rejected");
        check(m.getStringSet("hidetabs", tabs).isEmpty(), "empty set did not reset tabs");
        check(m.putPublicString("css_theme", ""), "empty CSS reset rejected");
        int commits = c.publicStore.commits, notifications = c.resolver.notifications;
        for (String key : new String[]{null, "", "unknown_typed_setting", "imagequality", "hidetabs", "app_theme_mode"}) {
            check(!m.putPublicString(key, "invalid"), "unknown, private or wrong-type string accepted: " + key);
        }
        check(!m.putPublicString("css_theme", null), "null string accepted");
        for (String key : new String[]{null, "", "unknown_typed_setting", "css_theme", "imagequality", "app_theme_mode"}) {
            check(!m.putPublicStringSet(key, tabs), "unknown, private or wrong-type set accepted: " + key);
        }
        check(!m.putPublicStringSet("hidetabs", null), "null set accepted");
        check(!m.putPublicStringSet("hidetabs", new java.util.HashSet<>(java.util.Arrays.asList("300", null))), "null element accepted");
        java.util.Set raw = new java.util.HashSet(); raw.add(Integer.valueOf(300));
        check(!m.putPublicStringSet("hidetabs", raw), "non-string element accepted");
        check(c.publicStore.commits == commits, "rejected data reached storage");
        check(c.privateStore.commits == 0, "typed writer reached private store");
        check(c.resolver.notifications == notifications, "rejected input notified");
        for (boolean mutateMemory : new boolean[]{false, true}) {
            c.publicStore.failCommit = true; c.publicStore.applyBeforeFailure = mutateMemory;
            check(!m.putPublicString("css_theme", "failed-save"), "failed string commit reported success");
            check(!m.putPublicStringSet("hidetabs", tabs), "failed set commit reported success");
            check(c.resolver.notifications == notifications, "failed commit notified");
            if (mutateMemory) check("failed-save".equals(m.getString("css_theme", "")),
                    "test must model Android memory-before-disk failure; rollback is not guaranteed");
        }
        c.publicStore.failCommit = false; c.publicStore.applyBeforeFailure = false;
        c.publicStore.throwCommit = true;
        check(!m.putPublicString("css_theme", "error"), "commit exception escaped string writer");
        check(!m.putPublicStringSet("hidetabs", tabs), "commit exception escaped set writer");
        c.publicStore.throwCommit = false; c.publicStore.throwEdit = true;
        check(!m.putPublicString("css_theme", "error"), "editor exception escaped string writer");
        check(!m.putPublicStringSet("hidetabs", tabs), "editor exception escaped set writer");
        check(c.resolver.notifications == notifications, "exception triggered notification");
        c.publicStore.throwEdit = false;
        check(m.putPublicString("css_theme", "retry"), "string retry failed");
        check(m.putPublicStringSet("hidetabs", tabs), "set retry failed");
        check(c.resolver.notifications == notifications + 2, "successful retries not notified");
    }

''';assert s.count(anchor)==1;s=s.replace(anchor,tests+anchor);p.write_text(s)
print('Updated manager, UI, Android test doubles and production-method regression tests')

(root/"qa/test_style_non_boolean_guard.py").write_bytes((Path(__file__).parent/"typed_guard.py").read_bytes())
