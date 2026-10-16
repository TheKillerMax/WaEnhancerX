# Wa Enhancer X - Architecture Documentation

This document serves as the **single source of truth** for the architectural design and rules of **Wa Enhancer X** (WAEX). All future development must strictly follow these structural principles, package divisions, and layering boundaries.

---

## 🏗️ Folder/Package Responsibilities

WAEX is structured as a single Gradle `:app` module using package-level modularity. The package structure inside `app/src/main/java/com/waenhancer/` consists of:

```text
com.waenhancer/
 ├── core/
 │    ├── engine/         # Central orchestration, Hilt DI module, and app booting
 │    ├── feature/        # WaexFeature implementations and WaexFeatureRegistryImpl
 │    ├── preferences/    # Namespace-based preference management (WaexPreferenceManagerImpl)
 │    ├── licensing/      # Licensing status (WaexLicenseManagerImpl)
 │    ├── search/         # Case-insensitive settings searching (WaexSearchEngineImpl)
 │    ├── dashboard/      # Dynamic Bento card providers (WaexDashboardProviderImpl)
 │    ├── loader/         # Asynchronous, sandboxed classloading of external plugin DEX/APKs
 │    ├── security/       # Signature checks, integrity verification, and permission validation
 │    ├── compatibility/  # Client and version compatibility gating (WaexClientDetector, WaexClientVersionDetector, WaexVersionRegistry, WaexVersionGate, WaexCompatibilityProvider)
 │
 ├── hooks/
 │    ├── whatsapp/       # WhatsApp process injection & adapters (WhatsAppAdapter, WhatsAppBusinessAdapter)
 │    ├── system/         # Android OS services method interception (e.g. process names, resources)
 │
 ├── features/
 │    ├── message/        # Message-related modular enhancements (auto-responder, scheduling)
 │    ├── media/          # Media-related modular enhancements (HQ uploads, auto-downloads)
 │
 ├── api/
 │    ├── contracts/      # Pure Java interfaces, client enums, capability mappings, and DTOs
 │
 ├── ui/
 │    ├── mvvm/           # Jetpack Compose layouts and reactive ViewModels with StateFlow
 │
 ├── plugins/
 │    ├── runtime/        # Sandboxed plugin state machines, lifecycle, and active runtime tracking
 ```

---

## 🚫 Dependency and Coupling Rules

To maintain high maintainability and prevent compilation circularity, imports across packages must follow strict boundaries:

```
                       +-------------------+
                       |    UI (Kotlin)    |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       | Features (Kotlin) |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       |  API Contracts    | <-----------------+
                       +---------+---------+                   |
                                 ^                             |
                                 |                             |
                       +---------+---------+         +---------+---------+
                       |    Core (Java)    |         |   Hooks (Java)    |
                       +-------------------+         +-------------------+
```

### Strict Rules:
1.  **Core Layer**: Must remain pure logic with **no Android UI dependencies** and **no feature dependencies**. It communicates with features and plugins only via registries defined in the API contracts.
2.  **Hooks Layer**: Must **never import features directly**. Hooks intercept the system or target process, wrap execution details into DTOs, and trigger callback listeners registered via the API contracts.
3.  **Features Layer**: Must depend only on API contracts. Features register themselves to the Core Engine registry using the contracts, ensuring they are decoupled from both Hooks and the UI.
4.  **API contracts Layer**: Contains **only interfaces and DTOs**. No business logic is permitted inside this package.
5.  **UI Layer**: Implements strict MVVM. ViewModels manage screen-specific states. ViewModels must **never access Core Engine internals** or call registries directly. Feature registrations must be handled via Application startup/Hilt initializers.

---

## 🔌 Future Plugin System Design Intent

*   **Sandbox Isolation**: Plugins must execute under a custom `DexClassLoader` hierarchy. To prevent classloader leakage, the parent classloader must be restricted to system library capabilities (e.g. `ClassLoader.getSystemClassLoader().getParent()`), exposing only basic Android framework classes.
*   **Zero Direct Coupling**: Plugins must only import `com.waenhancer.api.contracts` and standard Java/Android APIs. They must not have compile-time dependencies on the Core or Hooks implementations.
*   **Interface Communication**: Plugins receive an implementation of `WaexHostApi` upon loading, through which they can query registries and log information.

---

## ⚡ Hook System Design Intent

*   **Hook Registries**: Hook points are defined via Xposed-style signatures (class name, method name, signature) and registered dynamically using `WaexHookRegistry`.
*   **Interceptor Flow**:
    *   **BeforeCall**: Invoked before target method runs. Can return a custom result or throwable, stopping execution early if necessary.
    *   **AfterCall**: Invoked after target method completes. Can inspect or modify return parameters or handle errors.
*   **Decoupled Triggers**: Triggering hook event callbacks must route through `WaexEngine` without direct knowledge of which features or plugins are consuming the hook events.

---

## 📱 Multi-Client Compatibility & Version Gating Design Intent

### 1. Phase 3A.5 Compatibility Model
The compatibility model defines a strict provider-adapter relationship. The core feature layer interacts only with the abstract `WaexCompatibilityProvider` and `WaexCapabilityRegistry` contracts. Target package identities are completely hidden from the feature implementations, achieving total client environment decoupling.

### 2. Client Abstraction System
Clients are represented by the `WaexClientType` enum (`WHATSAPP`, `WHATSAPP_BUSINESS`, `FUTURE_CLIENT`, `UNKNOWN`). Adapters (e.g., `WhatsAppAdapter`, `WhatsAppBusinessAdapter`) implement the generic `WaexHookAdapter` interface. This allows new target clients to be added by implementing a new adapter class and registering it, with absolutely zero changes required in features or UI code.

### 3. Version-Controlled Compatibility Rules
Version verification is gated using manual, immutable configurations through the `WaexSupportedVersionConfig` model. It defines:
*   Allowed version ranges or exact allowed version lists for each `WaexClientType`.
*   Future override rules (e.g., `allow-future-beta=false`).
Auto-detection guesses are prohibited. Gating evaluates during early boot, halting hooks injection and placing the app into a blocked warning state if constraints are violated.

### 4. Capability-Based Design Rules
Features must never check package names or version codes directly. They declare their requirements via `WaexCapability` flags (e.g., `CHAT_MESSAGES`, `STATUS`, `MEDIA`, `CALLS`, `BUSINESS_TOOLS`, `COMMUNITIES`). The `WaexCompatibilityProvider` resolves these capabilities at runtime against the active client adapter, determining whether a feature is permitted to load and run.


