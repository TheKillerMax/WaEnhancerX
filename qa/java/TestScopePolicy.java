package com.waenhancer.xposed.bridge;
import java.util.*;
public class TestScopePolicy {
 static void check(boolean ok, String msg){ if(!ok) throw new AssertionError(msg); }
 public static void main(String[] args){
  Set<String> scope = new HashSet<>(Arrays.asList(args));
  int module = 1000, caller = 2000;
  for(String target:Arrays.asList("com.whatsapp", "com.whatsapp.w4b", "com.gbwhatsapp", "com.yowhatsapp", "com.aero")) {
    check(scope.contains(target), "missing declared scope: " + target);
    check(CallerScopePolicy.isTrusted(caller,module,new String[]{target},scope), "rejects allowed app: " + target);
    check(CallerScopePolicy.ownsPackage(caller,module,new String[]{target},target), "ownership rejected: " + target);
  }
  check(CallerScopePolicy.isTrusted(module,module,null,scope), "module UID should be authorized");
  check(!CallerScopePolicy.isTrusted(caller,module,new String[]{"com.evil.whatsapp"},scope), "substring impersonation");
  check(!CallerScopePolicy.isTrusted(caller,module,null,scope), "missing package list");
  check(!CallerScopePolicy.isTrusted(caller,module,new String[]{"com.whatsapp"},Collections.emptySet()), "empty scope");
  check(!CallerScopePolicy.ownsPackage(caller,module,new String[]{"com.gbwhatsapp"},"com.whatsapp"), "caller registered another package");
  check(CallerScopePolicy.ownsPackage(module,module,null,"com.whatsapp"),"module-owned registration");
  System.out.println("CallerScopePolicy: official, Business, clone and rejection checks passed");
 }
}
