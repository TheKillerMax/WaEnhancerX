#!/usr/bin/env python3
"""Discriminating source mutations for the DB/dialog/status privacy contract."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_database_dialog_status_log_privacy as gate


class DatabaseDialogStatusGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {path: (gate.ROOT / path).read_text(encoding='utf-8') for path in gate.FILES}
        cls.catalog = gate.load_catalog()

    def reject(self, path, old, new, behavior=False):
        sources = dict(self.sources)
        self.assertIn(old, sources[path], 'Mutation must actually affect current source')
        sources[path] = sources[path].replace(old, new, 1)
        with self.assertRaises(gate.GateFailure):
            if behavior:
                gate.check_behavior(sources)
            else:
                gate.check_logs(sources, self.catalog)

    def test_reviewed_contract_and_selected_wiring(self):
        self.assertEqual(gate.check_logs(self.sources, self.catalog), 29)
        gate.check_behavior(self.sources)

    def test_all_eight_original_unsafe_expressions_are_rejected(self):
        events = (
            'findStatusListField failed: ', 'findCurrentStatusIndexField failed: ',
            'hookMenuRefreshMethods failed: ', 'hookStatusSeenIcon failed: ',
            'hookStatusSeenIconActivity failed: ', 'Error handling status menu hook: ',
            'hookMethod(menuStatusMethod) failed: ', 'Error setting up status playback hook: ',
        )
        for index, event in enumerate(events):
            with self.subTest(event=event):
                safe = 'TAG + " ' + event + '" + t.getClass().getSimpleName()'
                unsafe = 'TAG + " ' + event + '" + ' + ('Log.getStackTraceString(t)' if index == 7 else 't')
                self.assertEqual(self.sources[gate.STATUS].count(safe), 1)
                mutated = self.sources[gate.STATUS].replace(safe, unsafe)
                self.assertEqual(len(list(gate.shared.log_calls(mutated))), 17)
                self.reject(gate.STATUS, safe, unsafe)

    def test_payload_grammar_rejects_unknown_exception_names_and_stack_renderers(self):
        unsafe = (
            'TAG + " failed " + catastrophicFailure',
            'TAG + " failed " + catastrophicFailure.toString()',
            'TAG + " failed " + catastrophicFailure.getMessage()',
            'TAG + " failed " + Log.getStackTraceString(catastrophicFailure)',
            'TAG + " failed " + Log/**/.getStackTraceString/**/(catastrophicFailure)',
            'TAG + " failed " + String.valueOf(catastrophicFailure)',
        )
        for expression in unsafe:
            with self.subTest(expression=expression), self.assertRaises(gate.GateFailure):
                gate.payload_kind(expression)

    def test_fixed_literal_and_class_categories_are_distinct(self):
        self.assertEqual(gate.payload_kind('TAG + " fixed event"'), 'literal_only')
        self.assertEqual(gate.payload_kind('TAG + " failure " + unusual.getClass().getSimpleName()'), 'exception_class')
        self.assertEqual(gate.payload_kind('"$TAG failure ${unusual.javaClass.simpleName}"', True), 'exception_class')

    def test_count_neutral_unreviewed_event_is_rejected(self):
        self.reject(gate.STATUS, ' StatusPlaybackActivity not found — icon placement unavailable', ' changed event')

    def test_count_neutral_duplicate_and_missing_event_are_rejected(self):
        self.reject(gate.STATUS, ' findStatusListField failed: ', ' findCurrentStatusIndexField failed: ')

    def test_new_literal_event_is_rejected(self):
        self.reject(gate.STATUS, 'public class StatusDownloadHook extends BaseFeature {',
                    'public class StatusDownloadHook extends BaseFeature {\n'
                    'void extra() { XposedBridge.log(TAG + " unreviewed"); }')

    def test_removed_event_is_rejected(self):
        self.reject(gate.STATUS, 'XposedBridge.log(TAG + " findStatusListField failed: " + t.getClass().getSimpleName());', '')

    def test_formatting_and_comments_outside_literals_are_accepted(self):
        sources = dict(self.sources)
        sources[gate.STATUS] = sources[gate.STATUS].replace('XposedBridge.log(', 'XposedBridge /*synthetic*/ . log (\n')
        self.assertEqual(gate.check_logs(sources, self.catalog), 29)

    def test_fake_calls_in_comments_are_not_diagnostics(self):
        sources = dict(self.sources)
        sources[gate.STATUS] += '\n// XposedBridge.log(TAG + syntheticSecret);\n'
        self.assertEqual(gate.check_logs(sources, self.catalog), 29)

    def test_generic_direct_call_cannot_hide_new_diagnostic(self):
        self.reject(gate.STATUS, 'public class StatusDownloadHook extends BaseFeature {',
                    'public class StatusDownloadHook extends BaseFeature {\n'
                    'void extra() { XposedBridge.<String>log(syntheticSecret); }')

    def test_java_unicode_preprocessing_requires_review(self):
        self.reject(gate.STATUS, 'XposedBridge.log(', r'XposedBridge.\u006cog(')

    def test_kotlin_nested_logging_requires_review(self):
        self.reject(gate.DIALOG, 'class NativeWhatsAppDialog',
                    'val hidden = "${XposedBridge/**/.log(syntheticSecret)}"\nclass NativeWhatsAppDialog')

    def test_dynamic_tag_is_rejected(self):
        self.reject(gate.STATUS, 'private static final String TAG = "[WAEX][StatusDownload]";',
                    'private static final String TAG = syntheticPrivateText;')

    def test_additional_tag_assignment_is_rejected(self):
        self.reject(gate.STATUS, 'public class StatusDownloadHook extends BaseFeature {',
                    'public class StatusDownloadHook extends BaseFeature {\nvoid extra() { TAG = syntheticPrivateText; }')

    def test_catalog_cannot_authorize_raw_throwable(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['files'][gate.STATUS]['sites'][0]['expression'] = 'TAG + " failed " + catastrophicFailure'
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_catalog_cannot_authorize_stack_renderer(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['files'][gate.STATUS]['sites'][0]['expression'] = 'TAG + " failed " + Log.getStackTraceString(catastrophicFailure)'
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_catalog_requires_payload_kind_truth(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['files'][gate.STATUS]['sites'][0]['allowed_data'] = 'literal_only'
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_catalog_requires_all_files(self):
        catalog = copy.deepcopy(self.catalog)
        del catalog['files'][gate.STORE]
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_catalog_requires_review_purpose(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['files'][gate.STATUS]['sites'][0]['purpose'] = ''
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_db_exception_message_is_rejected(self):
        self.reject(gate.STORE, '${ex.javaClass.simpleName}', '${ex.message}')

    def test_dialog_dynamic_prefix_is_rejected(self):
        self.reject(gate.DIALOG, '$TAG setTitle error:', '$TAG $syntheticTitle setTitle error:')

    def test_catalog_cannot_authorize_dynamic_kotlin_prefix(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['files'][gate.DIALOG]['sites'][0]['expression'] = '"$TAG $privateText failed ${t.javaClass.simpleName}"'
        with self.assertRaises(gate.GateFailure):
            gate.validate_catalog(catalog)

    def test_failed_export_must_return_false(self):
        self.reject(gate.STATUS, '            return false;\n        }\n    }\n\n    private boolean hasSavedStatus',
                    '            return true;\n        }\n    }\n\n    private boolean hasSavedStatus', behavior=True)

    def test_failed_export_must_not_be_marked_saved(self):
        self.reject(gate.STATUS, 'if (exportStatus(ctx, srcFile)) markStatusSaved(identity);',
                    'exportStatus(ctx, srcFile); markStatusSaved(identity);', behavior=True)

    def test_exporter_cannot_be_replaced_by_comment(self):
        self.reject(gate.STATUS, 'StatusMediaExporter.export(ctx, srcFile);',
                    '/* StatusMediaExporter.export(ctx, srcFile); */', behavior=True)

    def test_localized_failure_resource_cannot_be_only_a_comment(self):
        self.reject(gate.STATUS,
                    'showToast(ctx, UiText.get(R.string.waex_ui_failed_to_download_status,',
                    'showToast(ctx, UiText.get(R.string.synthetic_wrong_resource, '
                    '/* R.string.waex_ui_failed_to_download_status */', behavior=True)

    def test_saved_identity_persistence_cannot_be_only_a_comment(self):
        self.reject(gate.STATUS, 'prefs.edit().putStringSet(PREF_SAVED_IDENTITIES, saved).commit();',
                    '/* prefs.edit().putStringSet(PREF_SAVED_IDENTITIES, saved).commit(); */', behavior=True)

    def test_db_operation_cannot_be_only_a_comment(self):
        self.reject(gate.STORE, 'fun getIdFromKey(', '/* fun getIdFromKey( */ fun syntheticDifferentOperation(', behavior=True)

    def test_dialog_operation_cannot_be_only_a_comment(self):
        self.reject(gate.DIALOG, 'fun setPositiveButton(', '/* fun setPositiveButton( */ fun syntheticDifferentOperation(', behavior=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
