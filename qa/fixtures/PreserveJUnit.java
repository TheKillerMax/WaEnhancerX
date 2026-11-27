package com.waenhancer.audit;

import org.junit.internal.TextListener;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

/** Preserve JUnit's summary and stack traces; also identify every SDK variant and non-execution. */
public final class PreserveJUnit {
    private static void event(String kind, Description test) {
        System.out.printf("%nQA %s %s%n", kind, test.getMethodName());
    }

    public static void main(String[] args) throws ClassNotFoundException {
        JUnitCore core = new JUnitCore();
        core.addListener(new TextListener(System.out));
        core.addListener(new RunListener() {
            @Override public void testStarted(Description test) { event("start", test); }
            @Override public void testFinished(Description test) { event("end", test); }
            @Override public void testIgnored(Description test) { event("skip", test); }
            @Override public void testAssumptionFailure(Failure f) { event("skip", f.getDescription()); }
            @Override public void testFailure(Failure f) {
                event(f.getException() instanceof AssertionError ? "assertion" : "error", f.getDescription());
            }
        });
        Result result = core.run(Class.forName(args[0], false, PreserveJUnit.class.getClassLoader()));
        System.exit(result.wasSuccessful() ? 0 : 1);
    }
}
