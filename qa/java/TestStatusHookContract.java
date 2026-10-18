import com.waenhancer.xposed.features.privacy.StatusHookContract;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Collections;

/** Reflection/transport contracts with explicit host-shaped fixtures, not an Android test. */
public final class TestStatusHookContract {
    // Deliberately reordered: selecting ordinal zero would acknowledge DIDNT_STORE.
    enum Result { DIDNT_STORE, FAILED_TO_STORE, STORED_ORPHAN, STORED }
    enum UnknownResult { STORED, STORED_ORPHAN, FAILED_TO_STORE, RENAMED }
    enum ExtendedResult { STORED, STORED_ORPHAN, FAILED_TO_STORE, DIDNT_STORE, EXTRA }
    static class KeyParent { Object nestedKey; static String ignoredId; static boolean ignoredOwner; }
    static class Key extends KeyParent {
        final String id;
        final boolean fromMe;
        Key(String id, boolean fromMe) { this.id = id; this.fromMe = fromMe; }
    }
    static class AmbiguousId extends Key { String anotherId; AmbiguousId() { super("id", false); } }
    static class AmbiguousOwner extends Key { boolean anotherFlag; AmbiguousOwner() { super("id", false); } }
    static class MissingOwner { String id; }
    static class Manager {
        Result revoke(Key metadata, Key target, boolean incoming) { return Result.DIDNT_STORE; }
        Result wrongOrder(Key metadata, boolean incoming, Key target) { return Result.DIDNT_STORE; }
        Result wrongFirst(Object metadata, Key target, boolean incoming) { return Result.DIDNT_STORE; }
        Result wrongTarget(Key metadata, Object target, boolean incoming) { return Result.DIDNT_STORE; }
        Result boxed(Key metadata, Key target, Boolean incoming) { return Result.DIDNT_STORE; }
        Result shortCall(Key metadata, Key target) { return Result.DIDNT_STORE; }
        String wrongResult(Key metadata, Key target, boolean incoming) { return ""; }
        UnknownResult unknown(Key metadata, Key target, boolean incoming) { return null; }
        ExtendedResult extended(Key metadata, Key target, boolean incoming) { return null; }
        static Result staticCall(Key metadata, Key target, boolean incoming) { return Result.DIDNT_STORE; }
        Result ambiguousId(AmbiguousId metadata, AmbiguousId target, boolean incoming) { return null; }
        Result ambiguousOwner(AmbiguousOwner metadata, AmbiguousOwner target, boolean incoming) { return null; }
    }
    static class OtherManager { Result second(Key metadata, Key target, boolean incoming) { return null; } }
    abstract static class AbstractManager { abstract Result revoke(Key metadata, Key target, boolean incoming); }
    static class Status {}
    static class Message {}
    static class SpecificMessage extends Message {}
    interface Projection<T extends Message> { T convert(Status status); }
    static class SyntheticMapper implements Projection<SpecificMessage> {
        public SpecificMessage convert(Status status) { return null; }
    }
    static class Mapper {
        Message convert(Status status) { return new Message(); }
        String wrongResult(Status status) { return ""; }
        Message wrongParameter(Object status) { return new Message(); }
        Message primitive(int status) { return new Message(); }
        static Message staticCall(Status status) { return new Message(); }
    }
    static class OtherMapper { Message convert(Status status) { return new Message(); } }
    static int checks;
    static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    static Method method(Class<?> owner, String name, Class<?>... parameters) throws Exception {
        return owner.getDeclaredMethod(name, parameters);
    }
    static Method revoke(String name) throws Exception {
        return method(Manager.class, name, Key.class, Key.class, boolean.class);
    }

    public static void main(String[] args) throws Exception {
        Method valid = revoke("revoke");
        StatusHookContract contract = StatusHookContract.resolveRevoke(valid, Key.class);
        check(contract != null, "verified shape should resolve");
        check(contract.acknowledgement() == Result.STORED, "acknowledgement must use native STORED by name");
        check(((Enum<?>) contract.acknowledgement()).ordinal() == 3, "native caller can dereference result");
        check(StatusHookContract.resolveRevoke(null, Key.class) == null, "missing method");
        check(StatusHookContract.resolveRevoke(valid, null) == null, "missing key class");
        check(StatusHookContract.resolveRevoke(valid, Object.class) == null, "key type must be exact");
        for (String name : new String[]{"wrongResult", "unknown", "extended", "staticCall"}) {
            check(StatusHookContract.resolveRevoke(revoke(name), Key.class) == null, "reject " + name);
        }
        check(StatusHookContract.resolveRevoke(method(Manager.class, "wrongOrder", Key.class,
                boolean.class, Key.class), Key.class) == null, "wrong argument order");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "wrongFirst", Object.class,
                Key.class, boolean.class), Key.class) == null, "unverified first type");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "wrongTarget", Key.class,
                Object.class, boolean.class), Key.class) == null, "unverified target type");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "boxed", Key.class,
                Key.class, Boolean.class), Key.class) == null, "boxed boolean is a changed host contract");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "shortCall", Key.class,
                Key.class), Key.class) == null, "missing incoming parameter");
        check(StatusHookContract.resolveRevoke(method(AbstractManager.class, "revoke", Key.class,
                Key.class, boolean.class), Key.class) == null, "abstract callback");
        check(!StatusHookContract.supportsKeyClass(AmbiguousId.class), "inherited duplicate ID is ambiguous");
        check(!StatusHookContract.supportsKeyClass(AmbiguousOwner.class), "inherited duplicate ownership is ambiguous");
        check(!StatusHookContract.supportsKeyClass(MissingOwner.class), "ownership cannot be guessed");
        check(!StatusHookContract.supportsKeyClass(null), "missing key cannot resolve");
        check(StatusHookContract.supportsKeyClass(Key.class), "ignore static fields and nested legacy keys");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "ambiguousId", AmbiguousId.class,
                AmbiguousId.class, boolean.class), AmbiguousId.class) == null, "reject ambiguous ID at install");
        check(StatusHookContract.resolveRevoke(method(Manager.class, "ambiguousOwner", AmbiguousOwner.class,
                AmbiguousOwner.class, boolean.class), AmbiguousOwner.class) == null, "reject ambiguous owner at install");
        check(valid.equals(StatusHookContract.selectRevokeMethod(Arrays.asList(revoke("wrongResult"), valid), Key.class)),
                "skip a first-parameter-only decoy");
        check(valid.equals(StatusHookContract.selectRevokeMethod(Arrays.asList(valid, valid), Key.class)),
                "same inherited method is not a second candidate");
        Method other = method(OtherManager.class, "second", Key.class, Key.class, boolean.class);
        check(StatusHookContract.selectRevokeMethod(Arrays.asList(valid, other), Key.class) == null,
                "multiple valid manager candidates must fall through");
        check(StatusHookContract.selectRevokeMethod(Collections.emptyList(), Key.class) == null, "no candidate");

        Key metadata = new Key("revoke-envelope", true);
        Key target = new Key("target-story", false);
        StatusHookContract.Target preserved = contract.incomingTarget(new Object[]{metadata, target, true});
        check(preserved != null && preserved.key == target && preserved.id.equals("target-story"),
                "second key is target regardless of first-key identity/ownership");
        check(contract.incomingTarget(new Object[]{null, target, true}) != null, "nullable metadata is valid");
        Object[][] rejected = {
                null, {}, {metadata, target}, {metadata, target, true, null},
                {metadata, target, false}, {metadata, target, null}, {metadata, target, "true"},
                {metadata, null, true}, {metadata, new Object(), true}, {new Object(), target, true},
                {metadata, new Key("own-story", true), true},
                {metadata, new Key(null, false), true}, {metadata, new Key("", false), true}
        };
        for (Object[] invalid : rejected) check(contract.incomingTarget(invalid) == null,
                "unsupported/local/self/unidentified invocation retains host behavior");

        Method mapper = method(Mapper.class, "convert", Status.class);
        Method bridge = Arrays.stream(SyntheticMapper.class.getDeclaredMethods()).filter(Method::isBridge)
                .findFirst().orElseThrow();
        check(bridge.isSynthetic(), "fixture must be a genuine compiler-generated bridge");
        check(mapper.equals(StatusHookContract.selectStatusMapper(Arrays.asList(bridge, mapper), Message.class)),
                "reject a synthetic mapper even when it is first");
        check(mapper.equals(StatusHookContract.selectStatusMapper(Arrays.asList(mapper, bridge), Message.class)),
                "mapper resolution is order independent");
        check(mapper.equals(StatusHookContract.selectStatusMapper(Arrays.asList(mapper, mapper), Message.class)),
                "duplicate mapper identity is harmless");
        check(StatusHookContract.selectStatusMapper(Arrays.asList(mapper,
                method(OtherMapper.class, "convert", Status.class)), Message.class) == null, "ambiguous mapper");
        check(!StatusHookContract.isStatusMapper(null, Message.class), "missing mapper");
        check(!StatusHookContract.isStatusMapper(mapper, null), "unknown message class");
        check(!StatusHookContract.isStatusMapper(method(Mapper.class, "wrongResult", Status.class), Message.class),
                "mapper must return a message");
        check(!StatusHookContract.isStatusMapper(method(Mapper.class, "wrongParameter", Object.class), Message.class),
                "Object input is not a verified status model");
        check(!StatusHookContract.isStatusMapper(method(Mapper.class, "primitive", int.class), Message.class),
                "primitive input is not a status model");
        check(!StatusHookContract.isStatusMapper(method(Mapper.class, "staticCall", Status.class), Message.class),
                "mapper receiver must match constructor capture");
        System.out.println(checks + " status hook reflection/argument/acknowledgement checks passed");
    }
}
