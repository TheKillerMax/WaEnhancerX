import com.waenhancer.xposed.core.devkit.HookReturnTypeGuard;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

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

    interface MediaResponseView { void close(); }
    static class ConcreteMediaResponse implements MediaResponseView {
        @Override public void close() {}
    }
    static class MediaDownloadCandidate {
        ConcreteMediaResponse getConcreteResponse() { return new ConcreteMediaResponse(); }
        MediaResponseView getInterfaceResponse() { return new ConcreteMediaResponse(); }
        Object getObjectResponse() { return new ConcreteMediaResponse(); }
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
        Object interfaceProxy = Proxy.newProxyInstance(
                TestHookReturnTypeGuard.class.getClassLoader(),
                new Class<?>[]{MediaResponseView.class},
                (instance, invoked, values) -> null);
        Method concrete = MediaDownloadCandidate.class.getDeclaredMethod("getConcreteResponse");
        Method byInterface = MediaDownloadCandidate.class.getDeclaredMethod("getInterfaceResponse");
        Method byObject = MediaDownloadCandidate.class.getDeclaredMethod("getObjectResponse");
        boolean concreteCastRejected = false;
        try {
            concrete.getReturnType().cast(interfaceProxy);
        } catch (ClassCastException expected) {
            concreteCastRejected = true;
        }
        check(concreteCastRejected, "negative control: incompatible proxy was castable to concrete response");
        check(!HookReturnTypeGuard.canSetObjectResult(concrete, interfaceProxy),
                "interface-only proxy accepted as concrete media response");
        check(HookReturnTypeGuard.canSetObjectResult(byInterface, interfaceProxy),
                "valid interface media response rejected");
        check(HookReturnTypeGuard.canSetObjectResult(byObject, interfaceProxy),
                "valid Object media response rejected");
        check(!HookReturnTypeGuard.canSetObjectResult(concrete, null),
                "null replacement proxy incorrectly accepted");
        System.out.println("17 method contract regression checks passed");
    }
}
