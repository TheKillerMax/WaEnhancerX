import com.waenhancer.xposed.core.devkit.HookReturnTypeGuard;
import java.lang.reflect.Method;

public final class TestHookReturnTypeGuard {
    static class Candidate {
        void forwardingAction(String target) {}
        String getName() {return "";}
        int getLimit() {return 5;}
        Integer boxedLimit() {return 5;}
        boolean mayRevoke() {return true;}
        Boolean boxedRevoke() {return true;}
        void setLimit(int limit) {}
        void setLimitBoxed(Integer limit) {}
        void setOther(String name) {}
    }

    private static Method method(String name, Class<?>... args) throws Exception {
        return Candidate.class.getDeclaredMethod(name, args);
    }
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        // Regression: the observed "forward_limit" anchor matches void methods.
        check(!HookReturnTypeGuard.returnsInteger(method("forwardingAction", String.class)),
                "void callback should never return a forced integer");
        check(!HookReturnTypeGuard.returnsInteger(method("getName")),
                "string result should never be replaced with an integer");
        check(HookReturnTypeGuard.returnsInteger(method("getLimit")), "int result rejected");
        check(HookReturnTypeGuard.returnsInteger(method("boxedLimit")), "Integer result rejected");
        check(HookReturnTypeGuard.returnsBoolean(method("mayRevoke")), "boolean result rejected");
        check(HookReturnTypeGuard.returnsBoolean(method("boxedRevoke")), "Boolean result rejected");
        check(!HookReturnTypeGuard.returnsBoolean(method("getLimit")), "int result accepted as boolean");
        check(HookReturnTypeGuard.firstParameterIsInteger(method("setLimit", int.class)), "int param rejected");
        check(HookReturnTypeGuard.firstParameterIsInteger(method("setLimitBoxed", Integer.class)), "Integer param rejected");
        check(!HookReturnTypeGuard.firstParameterIsInteger(method("setOther", String.class)), "String param accepted");
        check(!HookReturnTypeGuard.firstParameterIsInteger(method("getLimit")), "missing param accepted");
        check(!HookReturnTypeGuard.returnsInteger(null), "null method accepted");
        System.out.println("12 method contract regression checks passed");
    }
}
