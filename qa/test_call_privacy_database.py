#!/usr/bin/env python3
"""Compile the real locator and the exact CallPrivacyHook selector method.

This is a strict JVM Context contract test, not Android or WhatsApp execution.
Run with a JDK 17+ compiler. A module-compiler fallback is explicitly reported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PACKAGE = "com.waenhancer.xposed.features.privacy"
SOURCE_DIR = Path("app/src/main/java") / PACKAGE.replace(".", "/")
CONTEXT = r'''
package android.content;
import java.io.File;
public abstract class Context {
    public abstract File getDatabasePath(String name);
    public File getFilesDir() {
        throw new AssertionError("Forbidden getFilesDir: database location belongs to Context.getDatabasePath");
    }
}
'''
TEST = r'''
package com.waenhancer.xposed.features.privacy;
import android.content.Context;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CallPrivacyDatabaseTest {
    private static int checks;
    private static int cases;
    private static final class ScopedContext extends Context {
        final Path databases;
        int databaseCalls;
        int forbiddenCalls;
        File answer;
        boolean fixedAnswer;
        boolean deny;
        ScopedContext(Path databases) { this.databases = databases; }
        @Override public File getDatabasePath(String name) {
            databaseCalls++;
            if (deny) throw new SecurityException("Synthetic denied Context");
            return fixedAnswer ? answer : databases.resolve(name).toFile();
        }
        @Override public File getFilesDir() {
            forbiddenCalls++;
            return super.getFilesDir();
        }
    }
    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    private static File find(ScopedContext context, String name) {
        return new CallPrivacyDatabaseSubject(context).find(name);
    }
    private static void seed(Path path, String marker) throws Exception {
        Files.createDirectories(path.getParent());
        Files.write(path, marker.getBytes(StandardCharsets.UTF_8));
    }
    private static void selected(ScopedContext context, String marker) throws Exception {
        int before = context.databaseCalls;
        File actual = find(context, "probe.db");
        check(actual != null, "existing database must resolve");
        check(actual.toPath().equals(context.databases.resolve("probe.db")), "wrong profile/package database");
        check(new String(Files.readAllBytes(actual.toPath()), StandardCharsets.UTF_8).equals(marker), "wrong synthetic marker");
        check(context.databaseCalls == before + 1, "exactly one scoped path request");
        check(context.forbiddenCalls == 0, "no filesDir path inference");
        cases++;
    }
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]);
        ScopedContext owner = new ScopedContext(root.resolve("user/0/com.whatsapp/databases"));
        ScopedContext work = new ScopedContext(root.resolve("user/10/com.whatsapp/databases"));
        ScopedContext business = new ScopedContext(root.resolve("user/10/com.whatsapp.w4b/databases"));
        ScopedContext clone = new ScopedContext(root.resolve("adopted-volume/user/11/example.clone/databases"));
        ScopedContext[] contexts = {owner, work, business, clone};
        String[] markers = {"owner", "work", "business", "clone"};
        for (int i = 0; i < contexts.length; i++) seed(contexts[i].databases.resolve("probe.db"), markers[i]);
        for (int i = 0; i < contexts.length; i++) selected(contexts[i], markers[i]);

        Files.delete(work.databases.resolve("probe.db"));
        check(find(work, "probe.db") == null, "missing work DB must not use owner/business/clone DB");
        check(Files.exists(owner.databases.resolve("probe.db")), "foreign positive control still exists");
        check(work.forbiddenCalls == 0, "missing database must not infer paths");
        cases++;
        seed(work.databases.resolve("probe.db"), "restored-work");
        selected(work, "restored-work");

        Files.createDirectories(work.databases.resolve("directory.db"));
        check(find(work, "directory.db") == null, "directory is not a database file");
        cases++;

        ScopedContext unreadable = new ScopedContext(root);
        unreadable.fixedAnswer = true;
        unreadable.answer = new File("synthetic-unreadable") {
            @Override public boolean isFile() { return true; }
            @Override public boolean canRead() { return false; }
        };
        check(find(unreadable, "probe.db") == null, "non-readable file must not resolve");
        cases++;
        ScopedContext nullPath = new ScopedContext(root);
        nullPath.fixedAnswer = true;
        check(find(nullPath, "probe.db") == null, "null path must not resolve");
        cases++;

        String[] invalid = {null, "", ".", "..", "/absolute.db", "../owner.db", "dir/name.db", "dir\\name.db"};
        for (String name : invalid) {
            int before = work.databaseCalls;
            boolean rejected = false;
            try { find(work, name); } catch (IllegalArgumentException expected) { rejected = true; }
            check(rejected, "invalid database name must be rejected");
            check(work.databaseCalls == before, "invalid name must fail before Context access");
            cases++;
        }
        ScopedContext denied = new ScopedContext(root);
        denied.deny = true;
        boolean threw = false;
        try { find(denied, "probe.db"); } catch (SecurityException expected) { threw = true; }
        check(threw, "denial must not trigger another package/user fallback");
        check(denied.databaseCalls == 1 && denied.forbiddenCalls == 0, "denied path queried only once");
        cases++;
        boolean nullRejected = false;
        try { new CallPrivacyDatabaseSubject(null).find("probe.db"); }
        catch (NullPointerException expected) { nullRejected = true; }
        check(nullRejected, "null Context rejected");
        cases++;
        for (ScopedContext context : contexts) check(context.forbiddenCalls == 0, "no swallowed forbidden access");
        System.out.println("PASS: " + cases + " cases; " + checks + " assertions; strict Context + synthetic files");
    }
}
'''


def selector_method(source):
    found = re.findall(r"^    private File findDatabase\(String dbName\) \{\n.*?^    \}", source, re.M | re.S)
    if len(found) != 1:
        raise AssertionError("Expected one complete CallPrivacyHook selector method")
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default=None)
    args = parser.parse_args()
    repo = args.repo.resolve()
    hook = repo / SOURCE_DIR / "CallPrivacyHook.java"
    locator = repo / SOURCE_DIR / "CallPrivacyDatabaseLocator.java"
    subject = ("package " + PACKAGE + ";\nimport java.io.File;\nimport android.content.Context;\n"
               "final class CallPrivacyDatabaseSubject {\n private final Context context;\n"
               " CallPrivacyDatabaseSubject(Context context) { this.context = context; }\n"
               " File find(String name) { return findDatabase(name); }\n"
               + selector_method(hook.read_text(encoding="utf-8")) + "\n}\n")
    javac = args.javac or shutil.which("javac")
    compiler = [javac, "--release", "17"] if javac else [args.java, "-m", "jdk.compiler/com.sun.tools.javac.Main", "-source", "17", "-target", "17"]
    contract = "--release17" if javac else "source17-target17; compiler-runtime-library (not --release17)"
    with tempfile.TemporaryDirectory(prefix="waex-call-db-") as temp:
        workspace = Path(temp)
        sources = []
        for name, text in {"android/content/Context.java": CONTEXT,
                           PACKAGE.replace(".", "/") + "/CallPrivacyDatabaseSubject.java": subject,
                           PACKAGE.replace(".", "/") + "/CallPrivacyDatabaseTest.java": TEST}.items():
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            sources.append(str(target))
        if locator.is_file():
            sources.append(str(locator))
        classes = workspace / "classes"
        subprocess.run([*compiler, "-d", str(classes), *sources], check=True, timeout=60)
        subprocess.run([args.java, "-cp", str(classes), PACKAGE + ".CallPrivacyDatabaseTest", str(workspace / "data")], check=True, timeout=60)
    print(json.dumps({"status": "PASS", "compiler_contract": contract,
                      "hook_sha256": hashlib.sha256(hook.read_bytes()).hexdigest(),
                      "locator_sha256": hashlib.sha256(locator.read_bytes()).hexdigest() if locator.is_file() else None,
                      "coverage": "real selector method and locator; strict JVM Context; no Android/SQLite/call execution"}, sort_keys=True))


if __name__ == "__main__":
    main()
