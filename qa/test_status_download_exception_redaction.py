#!/usr/bin/env python3
"""Execute exact StatusDownload diagnostic expressions with synthetic exceptions.

Seven original leaks execute ordinary Java Throwable string conversion. The
eighth uses a JDK-only model of Android Log.getStackTraceString's documented
formatting contract; that result is NOT an Android/Xposed runtime test. Candidate
expressions need only ordinary Java. No user data or Android application is read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_source_contract as parser

STATUS = 'app/src/main/java/com/waenhancer/xposed/features/media/StatusDownloadHook.java'
CONTRACT_URL = 'https://developer.android.com/reference/android/util/Log#getStackTraceString(java.lang.Throwable)'
FIXTURE = r'''
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.UnknownHostException;

public class CLASS_NAME {
    private static final String TAG = "[WAEX][StatusDownload]";
    private static final String JID = "SYNTHETIC_CONTACT_20261110@s.whatsapp.net";
    private static final String PATH = "/synthetic/private/status-fixture.jpg";
    // Model of the documented formatting contract, not android.util.Log.
    private static final class Log {
        static String getStackTraceString(Throwable input) {
            if (input == null) return "";
            for (Throwable cause = input; cause != null; cause = cause.getCause()) {
                if (cause instanceof UnknownHostException) return "";
            }
            StringWriter text = new StringWriter();
            input.printStackTrace(new PrintWriter(text));
            return text.toString();
        }
    }
    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }
    private static String[] evaluate(Throwable t, Throwable failure) {
        return new String[] { EXPRESSIONS };
    }
    public static void main(String[] ignored) {
        Throwable cause = new IllegalArgumentException("synthetic_secret_cause");
        Throwable failure = new IllegalStateException("jid=" + JID + " path=" + PATH, cause);
        failure.setStackTrace(new StackTraceElement[] {
            new StackTraceElement("synthetic.SecretStackFrame", "load", "SyntheticStatusFrame.java", 4242)
        });
        require(Log.getStackTraceString(null).isEmpty(), "model null contract");
        require(Log.getStackTraceString(new RuntimeException(new UnknownHostException())).isEmpty(),
                "model UnknownHostException cause contract");
        String model = Log.getStackTraceString(failure);
        require(model.contains(JID) && model.contains(PATH) && model.contains("synthetic_secret_cause")
                && model.contains("SyntheticStatusFrame.java:4242"), "non-empty stack model positive control");
        String[] values = evaluate(failure, failure);
        String[] prefixes = new String[] { PREFIXES };
        require(values.length == 17 && prefixes.length == 17, "all reviewed events must execute");
        int messages = 0, stacks = 0, categories = 0;
        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            require(value.startsWith(prefixes[i]), "event prefix changed at index " + i);
            boolean category = value.contains("IllegalStateException");
            require(category == (i != 10), "exception category missing/added at index " + i);
            if (category) categories++;
            if (value.contains(JID) || value.contains(PATH) || value.contains("synthetic_secret_cause")) messages++;
            if (value.contains("synthetic.SecretStackFrame") || value.contains("SyntheticStatusFrame.java:4242")) stacks++;
        }
        require(messages == EXPECTED_MESSAGES, "private-text discriminator");
        require(stacks == EXPECTED_STACKS, "stack discriminator");
        require(categories == 16, "retain all sixteen exception-category diagnostics");
        System.out.println("{\"events\":17,\"exception_categories\":" + categories
                + ",\"message_leaks\":" + messages + ",\"stack_leaks\":" + stacks + "}");
    }
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(path):
    data = path.read_bytes()
    source = data.decode('utf-8').replace('\r\n', '\n')
    expressions = [expression for _, expression in parser.log_calls(source)]
    parser.require(len(expressions) == 17, 'Fixture requires the seventeen reviewed events')
    return source, expressions, {'path': str(path.resolve()), 'raw_sha256': digest(data),
                                'lf_sha256': digest(source.encode())}


def skeleton(source, expressions):
    for index, expression in enumerate(expressions):
        parser.require(source.count(expression) == 1, 'Expression must identify one callsite')
        source = source.replace(expression, f'"SYNTHETIC_EVENT_{index}"', 1)
    return source.replace('import android.util.Log;\n', '')


def generated(name, expressions, messages, stacks):
    prefixes = []
    for expression in expressions:
        values = parser.signature(expression)
        parser.require(values[:2] == ('TAG', '+') and values[2].startswith('"'), 'Unexpected event prefix')
        prefixes.append('TAG + ' + values[2])
    return (FIXTURE.replace('CLASS_NAME', name).replace('EXPRESSIONS', ',\n            '.join(expressions))
            .replace('PREFIXES', ',\n            '.join(prefixes))
            .replace('EXPECTED_MESSAGES', str(messages)).replace('EXPECTED_STACKS', str(stacks)))


def execute(argv, cwd):
    result = subprocess.run(argv, cwd=cwd, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, timeout=60)
    parser.require(result.returncode == 0, f'Command failed: {argv[0]}\n{result.stdout}\n{result.stderr}')
    return {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument('--baseline-file', type=Path, required=True)
    options.add_argument('--candidate-file', type=Path, default=Path(__file__).resolve().parents[1] / STATUS)
    options.add_argument('--javac', default=shutil.which('javac'))
    options.add_argument('--java', default=shutil.which('java'))
    options.add_argument('--evidence-dir', type=Path)
    args = options.parse_args()
    parser.require(args.javac and args.java, 'Java compiler/runtime required; provide --javac and --java')
    before, old, before_identity = inspect(args.baseline_file)
    after, new, after_identity = inspect(args.candidate_file)
    parser.require(skeleton(before, old) == skeleton(after, new), 'Non-diagnostic production flow changed')
    parser.require(sum(a != b for a, b in zip(old, new)) == 8, 'Exactly eight reviewed payload changes required')
    parser.require(old[:7] == [expression.rsplit(' + ', 1)[0] + ' + t' for expression in new[:7]],
                   'The seven original raw-Throwable controls differ')
    parser.require(old[7] == new[7].rsplit(' + ', 1)[0] + ' + Log.getStackTraceString(t)',
                   'The original Android stack-rendering control differs')
    parser.require(old[8:] == new[8:], 'Previously safe events changed')
    for expression in new[:8]:
        parser.require(expression.endswith(' + t.getClass().getSimpleName()'), 'Candidate lost exception category')
    with tempfile.TemporaryDirectory(prefix='waex-status-log-') as scratch:
        work = Path(scratch)
        generated_sources = {
            'StatusRedactionBefore.java': generated('StatusRedactionBefore', old, 8, 1),
            'StatusRedactionAfter.java': generated('StatusRedactionAfter', new, 0, 0)
        }
        for name, text in generated_sources.items():
            (work / name).write_text(text, encoding='utf-8')
        compiler_version = execute([args.javac, '-version'], work)
        runtime_version = execute([args.java, '-version'], work)
        compiled = execute([args.javac, '-encoding', 'UTF-8', '-d', str(work), *generated_sources], work)
        runs = {name: execute([args.java, '-cp', str(work), name], work)
                for name in ('StatusRedactionBefore', 'StatusRedactionAfter')}
        receipt = {
            'status': 'PASS', 'production_delta_only': True, 'baseline': before_identity,
            'candidate': after_identity, 'before': json.loads(runs['StatusRedactionBefore']['stdout']),
            'after': json.loads(runs['StatusRedactionAfter']['stdout']),
            'scope': 'Exact Java expressions; 7 native Throwable conversions plus 1 explicitly modeled Android stack-format contract. No Xposed/Android execution.',
            'stack_model_contract': CONTRACT_URL,
            'runner_sha256': digest(Path(__file__).read_bytes()),
            'generated_sha256': {name: digest(text.encode()) for name, text in generated_sources.items()},
            'compiler_version': compiler_version, 'runtime_version': runtime_version,
            'compile': compiled, 'runs': runs
        }
        if args.evidence_dir:
            args.evidence_dir.mkdir(parents=True, exist_ok=False)
            for name, text in generated_sources.items():
                (args.evidence_dir / name).write_text(text, encoding='utf-8')
            (args.evidence_dir / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (parser.GateFailure, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
