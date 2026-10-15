<div align="center">

# WaEnhancer X

**UI customization, automation, and privacy engine for WhatsApp on Android**

A modern, clean-room Xposed/LSPosed module that injects interface styling, anti-deletion protection, view-once media tools, and deep customization directly into the official WhatsApp client. No repackaged APKs. No modified binaries.

[![Android Platform](https://img.shields.io/badge/Platform-Android%208.0%2B-3DDC84?style=flat&logo=android&logoColor=white)](https://developer.android.com)
[![Framework](https://img.shields.io/badge/Framework-LSPosed%20%7C%20Zygisk-orange?style=flat)](https://github.com/JingMatrix/LSPosed)
[![WaEnhancerX Downloads](https://img.shields.io/github/downloads/WaEnhancerX/WaEnhancerX/total.svg?label=GitHub%20Downloads&color=blue)](https://github.com/WaEnhancerX/WaEnhancerX/releases)
[![LSPosed Repo Downloads](https://img.shields.io/github/downloads/xposed-Modules-Repo/com.waenhancer/total.svg?label=LSPosed%20Repo%20Downloads&color=purple)](https://github.com/xposed-Modules-Repo/com.waenhancer/releases)
[![Telegram](https://telegram-badge.pages.dev/api/telegram-badge?channelId=@waenhancerx&label=Channel&showOnline=true)](https://t.me/waenhancerx)
[![Telegram](https://telegram-badge.pages.dev/api/telegram-badge?channelId=@waenhancerxhub&label=Community&showOnline=true)](https://t.me/waenhancerxhub)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Development Status](https://img.shields.io/badge/Status-Active%20Development-success.svg)](https://github.com/WaEnhancerX/WaEnhancerX)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**[Latest Release](https://github.com/WaEnhancerX/WaEnhancerX/releases/latest)** · **[Telegram Community](https://t.me/waenhancerx)** · **[Documentation](docs/ARCHITECTURE.md)** · **[Report Bug](https://github.com/WaEnhancerX/WaEnhancerX/issues)**

</div>

---

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=waenhancerx/waenhancerx&type=date&legend=top-left)](https://www.star-history.com/?repos=waenhancerx%2Fwaenhancerx&type=date&legend=top-left)

---

## Contents

- [Star History](#star-history)
- [Why WaEnhancerX](#why-waenhancerx)
- [About V2 Architecture](#about-v2-architecture)
- [Key Features](#key-features)
- [Compatibility & Supported Clients](#compatibility--supported-clients)
- [Requirements](#requirements)
- [Installation Guide](#installation-guide)
- [Building from Source](#building-from-source)
- [Architecture & Design Principles](#architecture--design-principles)
- [Contributors](#contributors)
- [Community & Policies](#community--policies)
- [Important Notice & Disclaimer](#important-notice--disclaimer)
- [License](#license)

---

## Why WaEnhancerX

Most WhatsApp modifications require replacing your official application with suspicious, closed-source third-party repackaged APKs. These third-party APKs pose major account security risks, break safety attestation, and often bundle unwanted bloatware or trackers.

**WaEnhancerX takes the native Xposed framework approach:**

- **Zero Client Tampering:** Works directly on top of the unmodified, genuine WhatsApp client from Google Play.
- **Deep System-Level Integration:** Injects settings natively into WhatsApp's internal preferences screen with full search engine support.
- **Dynamic CSS Theme Engine:** Style message bubbles, action bars, backgrounds, and UI layouts without decompiling or patching XML assets.
- **Privacy Without Compromise:** Keeps your anti-delete logs, view-once media captures, and conversation preferences entirely offline and local to your device.

---

## About V2 Architecture

WaEnhancerX V2 is an independent, clean-room rewrite engineered from the ground up:

- **Clean-Room Implementation:** Not a fork of V1 or any third-party module; zero code, logic, or resource reuse from GPL-licensed projects.
- **Modern Android Stack:** Built with Kotlin, Jetpack Compose, Coroutines/StateFlow, Hilt Dependency Injection, and Material You (Monet) dynamic theming.
- **Multi-OS Runtime Compatibility:** Rock-solid hooking engine verified across Android 8.0 through Android 12, 13, 14, 15, and future releases.
- **Permissive Open-Source Licensing:** Cleanly published under the Apache License 2.0.

---

## Key Features

<div align="center">
<table>
<tr>
<td width="33%" valign="top">

### 🛡️ Privacy & Security
- **Anti-Delete Protection:** Prevent incoming messages from disappearing when sender deletes them.
- **View-Once Freedom:** Open, view, and save view-once photos/videos without restrictions.
- **Self-Delete History:** Maintain local archives of messages you delete for yourself.
- **Receipt Control:** Granular control over blue ticks and delivered receipts.

</td>
<td width="33%" valign="top">

### 🎨 Customization & UI
- **CSS-like View Engine:** Fine-tune bubble colors, radiuses, and backgrounds with declarative rules.
- **Meta AI Cleanup:** Hide intrusive Meta AI icons, floating action buttons, and chat entries.
- **Material You (Monet):** Dynamic color theming aligned with system wallpaper palettes.
- **WA Plus / Pro Enhancements:** Native UI toggles and layout modifications.

</td>
<td width="33%" valign="top">

### ⚡ System & Integration
- **Native Settings Injection:** Integrated right inside WhatsApp’s official settings hierarchy.
- **Built-in Search:** Instantly locate any tweak via native search bar indexing.
- **Safe Restart Policy:** Graceful, reliable WhatsApp process restart directly from the dashboard.
- **Tasker Automation (Upcoming):** Control features and privacy profiles via Android broadcast intents.

</td>
</tr>
</table>
</div>

---

## Compatibility & Supported Clients

WaEnhancerX incorporates a dedicated **Multi-Client Compatibility Layer** and strict **Version Gate** to prevent crashes caused by unexpected host obfuscation changes.

| Target Package | Client Name | Supported Versions | Status |
| :--- | :--- | :--- | :--- |
| `com.whatsapp` | WhatsApp Messenger | Stable releases (Google Play) | Full Support |
| `com.whatsapp.w4b` | WhatsApp Business | Supported versions | Active Support |


*For in-depth versioning and client compatibility policies, consult the [Client Compatibility Guide](docs/client-compatibility.md).*

---

## Requirements

Before installing WaEnhancerX, ensure your setup meets the following prerequisites:

1. **Root Access:** A rooted Android device running **Magisk** (v24+) or **KernelSU** / **APatch**.
2. **Xposed Environment:** A functional **LSPosed** installation running on Zygisk (*EdXposed is deprecated and not supported*).
3. **Target Application:** Official WhatsApp or WhatsApp Business installed from Google Play.
4. **Android Version:** Android 8.0 (API Level 26) through Android 15+.

---

## Installation Guide

Follow these steps to set up WaEnhancerX:

```text
[1. Download APK] ──> [2. Install on Device] ──> [3. Enable in LSPosed] ──> [4. Set Scope] ──> [5. Soft Reboot]
```

1. **Download:** Grab the latest `WaEnhancerX-v2.x.x.apk` from [GitHub Releases](https://github.com/WaEnhancerX/WaEnhancerX/releases).
2. **Install:** Install the downloaded APK onto your Android device.
3. **Activate Module:** Open the **LSPosed Manager** application and toggle on **WaEnhancerX**.
4. **Configure Scope:** Check both **System Framework** and **WhatsApp** (`com.whatsapp` / `com.whatsapp.w4b`) in the module's target scope.
5. **Restart:** Reboot your device or perform a soft reboot / system restart.
6. **Enjoy:** Open WhatsApp and navigate to the main **Settings** page — WaEnhancerX options will appear integrated natively.

---

## Building from Source

To compile WaEnhancerX yourself:

### Prerequisites
- **Android Studio:** Ladybug (2024.2.1) or newer
- **JDK:** Java 17 or higher
- **Android SDK:** API 34+ (compileSdk 36)

### Build Commands
```bash
# Clone the repository
git clone https://github.com/WaEnhancerX/WaEnhancerX.git
cd WaEnhancerX

# Build debug APK
./gradlew assembleDebug

# Output APK location:
# app/build/outputs/apk/debug/app-debug.apk
```

---

## Architecture & Design Principles

WaEnhancerX follows strict architectural layering to prevent dependency leaks and decouple hooks from business features:

```
[ UI / Jetpack Compose ]  ──>  [ Feature Layer ]  ──>  [ API Contracts ]
                                                            │
                                                            ▼
[ Host Client Hook Adapters ]  <──  [ Core Compatibility Provider & Version Gate ]
```

- **Clean Separation:** UI, hooks, core engine, and API contracts communicate via strict unidirectional abstractions.
- **Isolated Hook Guards:** Return-type checks and class relocation guards safeguard against host app updates.
- **Read more in our documentation:**
  - [Architecture Specification](docs/ARCHITECTURE.md)
  - [Client Compatibility & Version Policy](docs/client-compatibility.md)
  - [Plugin & Preference Design](docs/preference-architecture.md)

---

## Contributors

Thank you to everyone who has contributed code, reported issues, tested builds, or improved the documentation for WaEnhancerX!

<div align="center">

<a href="https://github.com/WaEnhancerX/WaEnhancerX/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=WaEnhancerX/WaEnhancerX" alt="Contributors" />
</a>

<br/><br/>

Contributions of all kinds are welcome! Check out our [Contributing Guidelines](CONTRIBUTING.md) to get started.

</div>

---

## Community & Policies

Join the community, contribute improvements, or review our standards:

- 💬 **Telegram:** [Join @waenhancerx](https://t.me/waenhancerx)
- 🤝 **Contributing:** [Contribution Guidelines](CONTRIBUTING.md)
- 📜 **Code of Conduct:** [Community Standards](CODE_OF_CONDUCT.md)
- 🔒 **Security:** [Security Policy & Disclosures](SECURITY.md)
- ♿ **Accessibility:** [Accessibility Statement](ACCESSIBILITY.md)

---

## Important Notice & Disclaimer

Please read this disclaimer carefully before using the software:

- **Educational & Research Purpose:** WaEnhancerX is a proof-of-concept project intended strictly for reverse-engineering research, Android UI/UX experimentation, and educational purposes.
- **No Affiliation:** This project is independent and is not affiliated with, authorized, sponsored, or endorsed by Meta Platforms, WhatsApp LLC, or any of their affiliates.
- **Use at Your Own Discretion:** Modifying client runtimes may violate third-party Terms of Service. The maintainers and contributors assume no liability for account bans, data loss, device instability, or any consequences resulting from the use of this tool.

---

## License

WaEnhancerX is distributed under the terms of the **[Apache License 2.0](LICENSE)**.

```text
Copyright 2026 Mubashar Dev and the WaEnhancerX Organization.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

