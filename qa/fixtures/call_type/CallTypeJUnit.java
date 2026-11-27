package qa;
import java.util.ArrayList;
import java.util.List;
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

/** Keep assertion failures distinct from compilation, initialization and environment errors. */
public final class CallTypeJUnit {
    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r") + "\"";
    }
    public static void main(String[] args) throws Exception {
        List<Class<?>> suites = new ArrayList<>();
        for (String name : args) suites.add(Class.forName(name));
        final int[] assumptions = {0};
        JUnitCore runner = new JUnitCore();
        runner.addListener(new RunListener() {
            @Override public void testAssumptionFailure(Failure failure) { assumptions[0]++; }
        });
        Result result = runner.run(suites.toArray(new Class<?>[0]));
        int assertions = 0;
        StringBuilder failed = new StringBuilder("[");
        for (Failure failure : result.getFailures()) {
            if (failure.getException() instanceof AssertionError) assertions++;
            if (failed.length() > 1) failed.append(",");
            failed.append(quote(failure.getDescription().getMethodName()));
            System.out.println(failure.getTrace());
        }
        failed.append("]");
        System.out.println("WAEX_TEST_SUMMARY {\"tests\":" + result.getRunCount()
                + ",\"failures\":" + result.getFailureCount() + ",\"assertion_failures\":" + assertions
                + ",\"errors\":" + (result.getFailureCount() - assertions)
                + ",\"skipped\":" + (result.getIgnoreCount() + assumptions[0])
                + ",\"failed_tests\":" + failed + "}");
        System.exit(result.wasSuccessful() ? 0 : 1);
    }
}
