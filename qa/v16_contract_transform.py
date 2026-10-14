"""Apply reviewed hook-only changes to pinned source; no hidden downloads/writes."""
from pathlib import Path

RECEIPT_INSTALL = r'''                // A job also declares retry, initialization and serialization methods.
                // Suppress only its uniquely identified execution body, never every method.
                final Class<?> resolvedJobClass = sendJobClass;
                final Method executionMethod = resolveReadReceiptExecution(resolvedJobClass);
                if (executionMethod == null) {
                    XposedBridge.log(TAG + " Status receipt execution contract unavailable; job privacy coverage incomplete");
                    return;
                }
                XposedBridge.hookMethod(executionMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (!ReceiptJobExecutionPolicy.isExecutionCall(
                                resolvedJobClass, executionMethod, param.method,
                                param.thisObject, param.args)) return;
                        Object job = param.thisObject;
                        if (Boolean.TRUE.equals(XposedHelpers.getAdditionalInstanceField(
                                job, "waex_hide_status_view"))) {
                            param.setResult(null);
                            return;
                        }
                        String jid = extractJidString(job, "jid");
                        String participant = extractJidString(job, "participant");
                        if (isStatusTarget(jid, participant)) {
                            String target = participant != null && !participant.contains("@broadcast")
                                    ? participant : jid;
                            if (shouldHideStatusView(target)) param.setResult(null);
                        }
                    }
                });
'''

RECEIPT_RESOLVER = r'''    private Method resolveReadReceiptExecution(final Class<?> jobClass) {
        Method method = DexSearchEngine.getInstance().findMethodWithCache(
                context, classLoader, "wpp_send_read_receipt_execution_v1",
                (bridge, loader) -> {
                    // The reviewed 2.26.39.79 body builds a "receipt" stanza and
                    // handles receiptClass="status". No obfuscated method name is pinned.
                    MethodDataList matches = bridge.findMethod(FindMethod.create()
                            .matcher(MethodMatcher.create()
                                    .declaredClass(jobClass.getName())
                                    .paramCount(0)
                                    .returnType("void")
                                    .addUsingString("receipt", StringMatchType.Equals)
                                    .addUsingString("status", StringMatchType.Equals)));
                    if (matches.size() != 1) return null;
                    Method candidate = matches.get(0).getMethodInstance(loader);
                    return ReceiptJobExecutionPolicy.isExecutionMethod(jobClass, candidate)
                            ? candidate : null;
                });
        // Revalidate descriptors restored from the positive cache as well.
        return ReceiptJobExecutionPolicy.isExecutionMethod(jobClass, method) ? method : null;
    }

'''

PRESENCE = r'''    private void hookIncomingPresence() {
        try {
            Method presenceMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context, classLoader, "wpp_presence_message_handler_v3",
                    (bridge, loader) -> {
                        // The old available literal belongs to a multiplexed Runnable.
                        // Match the Handler envelope instead, including both event branches.
                        MethodDataList matches = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .name("handleMessage")
                                        .paramTypes("android.os.Message")
                                        .returnType("void")
                                        .addUsingString("MessageHandler/handleConnectionThreadReady connectionready",
                                                StringMatchType.Equals)
                                        .addUsingString("lastSeen", StringMatchType.Equals)
                                        .addUsingString("presence", StringMatchType.Equals)));
                        if (matches.size() != 1) return null;
                        Method candidate = matches.get(0).getMethodInstance(loader);
                        return isPresenceHandler(candidate) ? candidate : null;
                    });
            if (!isPresenceHandler(presenceMethod)) {
                XposedBridge.log(TAG + " Presence handler contract unavailable; online notifications not installed");
                return;
            }
            XposedBridge.hookMethod(presenceMethod, new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    // Observe only successfully handled host events. Never cancel/mutate them.
                    if (param.hasThrowable()) return;
                    PresenceEventPolicy.Event event = decodePresenceEvent(param.args);
                    if (event == null) return;
                    boolean transition = PresenceStateStore.update(event.jid, event.online);
                    if (transition && event.online && isOnlineToastEnabled()) {
                        asyncExecutor.execute(() -> {
                            String name = ContactNameResolver.INSTANCE.resolveName(context, event.jid, null, null);
                            showToastSafely(name + " is online");
                        });
                    }
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking presence toasts: " + t.getClass().getSimpleName());
        }
    }

    private static boolean isPresenceHandler(Method method) {
        if (method == null || !Handler.class.isAssignableFrom(method.getDeclaringClass())) return false;
        int flags = method.getModifiers();
        Class<?>[] parameters = method.getParameterTypes();
        return java.lang.reflect.Modifier.isPublic(flags)
                && !java.lang.reflect.Modifier.isStatic(flags)
                && !java.lang.reflect.Modifier.isAbstract(flags)
                && !java.lang.reflect.Modifier.isNative(flags)
                && !method.isBridge() && !method.isSynthetic()
                && "handleMessage".equals(method.getName()) && method.getReturnType() == void.class
                && parameters.length == 1 && parameters[0] == Message.class;
    }

    private static PresenceEventPolicy.Event decodePresenceEvent(Object[] args) {
        if (args == null || args.length != 1 || !(args[0] instanceof Message)) return null;
        Message message = (Message) args[0];
        if (message.what != PresenceEventPolicy.EVENT_FAMILY
                || !PresenceEventPolicy.isPresenceCode(message.arg1)
                || !(message.obj instanceof BaseBundle)) return null;
        try {
            BaseBundle payload = (BaseBundle) message.obj;
            return PresenceEventPolicy.decode(message.what, message.arg1,
                    payload.get("jid"), payload.get("presence"));
        } catch (RuntimeException unreadablePayload) {
            return null;
        }
    }

'''

def apply(root, topic):
    root = Path(root)
    features = root / 'app/src/main/java/com/waenhancer/xposed/features'
    if topic == 'receipts':
        path = features / 'privacy/HideReceiptsHook.java'
        text = path.read_text(encoding='utf-8')
        start = text.index('                // Hook all methods on SendReadReceiptJob to cancel execution when tagged')
        end = text.index('            }\n        } catch (Throwable t)', start)
        assert text[start:end].count('sendJobClass.getDeclaredMethods()') == 1
        text = text[:start] + RECEIPT_INSTALL + text[end:]
        marker = '    private boolean isManualSeenTickEnabled()'
        assert text.count(marker) == 1 and 'private Method resolveReadReceiptExecution(' not in text
        text = text.replace(marker, RECEIPT_RESOLVER + marker)
    elif topic == 'presence':
        path = features / 'automation/PresenceToastsHook.java'
        text = path.read_text(encoding='utf-8')
        start = text.index('    private void hookIncomingPresence()')
        end = text.index('    /**\n     * Hooks StatusReceiptStore', start)
        assert 'findCapturedJid' in text[start:end]
        text = text[:start] + PRESENCE + text[end:]
        marker = 'import org.luckypray.dexkit.result.MethodData;'
        assert text.count(marker) == 1
        text = text.replace(marker, marker + '\nimport org.luckypray.dexkit.result.MethodDataList;')
        text = text.replace('    private static final java.util.concurrent.atomic.AtomicInteger PRESENCE_DIAGNOSTICS = new java.util.concurrent.atomic.AtomicInteger();\n', '')
    else:
        raise ValueError('Unknown topic')
    path.write_text(text, encoding='utf-8')
