#!/usr/bin/env python3
"""Require compiled behavioral rejection of unsafe receipt-notification variants.

Uses the public source-only fixture. This does not execute WhatsApp or Android.
Writes a JSON evidence report to the requested output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


AREA = Path('app/src/main/java/com/waenhancer/xposed/features/automation')
MUTATIONS = [
    ('delivery_announced_read', [
        ('ReceiptObservationPolicy.java', 'type != READ_RECEIPT', '(type != READ_RECEIPT && type != 5)'),
        ('ReceiptObservationContract.java', 'code != ReceiptObservationPolicy.READ_RECEIPT || time <= 0L',
         '(code != ReceiptObservationPolicy.READ_RECEIPT && code != 5) || time <= 0L')]),
    ('foreign_message_announced_own', [('ReceiptObservationPolicy.java', ' || !fromMe', '')]),
    ('host_exception_ignored', [('PresenceToastsHook.java', 'if (param.hasThrowable() || !(snapshot instanceof List)) return;',
                               'if (!(snapshot instanceof List)) return;')]),
    ('message_relabelled_status', [('PresenceToastsHook.java', 'receiptText.format(event.kind, name)',
                                  'receiptText.format(ReceiptObservationPolicy.Kind.STATUS, name)')]),
    ('cancel_consumes_identity', [('ReceiptObservationPolicy.java',
        'if (reservation != null && pending.get(reservation.event) == reservation)\n                pending.remove(reservation.event);',
        'delivered(reservation);')]),
    ('delivery_ignores_switch', [('ReceiptToastDispatch.java', 'shown = !cancelled && enabled.getAsBoolean() && sink.show(message);',
                                'shown = !cancelled && sink.show(message);')]),
    ('cancelled_task_still_runs', [('ReceiptToastDispatch.java', 'cancelled = true;', 'cancelled = false;')]),
    ('queue_stranded_without_worker', [('ReceiptToastDispatch.java', 'executor.execute(next);',
                                      'executor.getQueue().offer(next);')]),
    ('failed_locale_cached', [('ReceiptToastText.java',
        'Context nextContext = module.createConfigurationContext(next);\n                configuration = next;',
        'configuration = next;\n                Context nextContext = module.createConfigurationContext(next);')]),
    ('foreign_resource_table_accepted', [('ReceiptToastText.java',
        'if (moduleContext && expected.equals(actual))', 'if (true)')]),
    ('wrong_named_resource_accepted', [('ReceiptToastText.java',
        'if (moduleContext && expected.equals(actual))', 'if (moduleContext && actual.startsWith("com.waenhancer:string/"))')]),
    ('ambiguous_sender_accepted', [('PresenceToastsHook.java', 'senders.size() != 1', 'senders.isEmpty()')]),
    ('broken_batch_partially_published', [('ReceiptObservationContract.java',
        '} catch (ReflectiveOperationException | RuntimeException | LinkageError unreadable) {\n                return Collections.emptyList();',
        '} catch (ReflectiveOperationException | RuntimeException | LinkageError unreadable) {\n                return Collections.unmodifiableList(result);')]),
    ('self_status_announced', [('ReceiptObservationContract.java',
        'provider == null || !Boolean.FALSE.equals(invoke(selfPredicate, null, provider, args[0]))', 'provider == null')]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name, changes in [('control', [])] + MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='waex_receipt_mutation_') as directory:
            candidate = Path(directory)
            shutil.copytree(root / AREA, candidate / AREA)
            for folder in ('values', 'values-es', 'values-b+es+419'):
                target = candidate / 'app/src/main/res' / folder
                target.mkdir(parents=True)
                shutil.copy2(root / 'app/src/main/res' / folder / 'receipt_toasts.xml', target)
            hashes = {}
            for filename, old, new in changes:
                target = candidate / AREA / filename
                original = target.read_text()
                assert original.count(old) == 1, 'Mutation anchor must remain unique: ' + name
                target.write_text(original.replace(old, new))
                hashes[filename] = hashlib.sha256(target.read_bytes()).hexdigest()
            run = subprocess.run(['python3', str(root / 'qa/test_receipt_observation.py'), '--source-root', str(candidate)],
                                 text=True, capture_output=True, timeout=90)
            output = run.stdout + run.stderr
            (out / (name + '.log')).write_text(output)
            rejected = 'Exception in thread "main" java.lang.AssertionError:' in output
            if changes:
                assert run.returncode != 0 and rejected, 'Mutant must compile and fail a Java behavioral assertion: ' + name
                assertion = next(line for line in output.splitlines() if 'java.lang.AssertionError:' in line)
            else:
                assert run.returncode == 0, 'Unmodified control must pass: ' + output[-2000:]
                assertion = None
            result = {'name': name, 'returncode': run.returncode, 'compiled_behaviorally_rejected': rejected,
                      'assertion': assertion, 'mutated_source_sha256': hashes}
            results.append(result)
            print(('REJECTED: ' if changes else 'PASS: ') + name, flush=True)
    (out / 'receipt-mutations.json').write_text(json.dumps({'scope': 'Production Java with explicit JVM doubles; not Android/host SQL',
                                                          'results': results}, indent=2) + '\n')
    print('PASS: control plus ' + str(len(MUTATIONS)) + ' compiled unsafe mutants rejected')


if __name__ == '__main__':
    main()
