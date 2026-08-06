# 🤖 Lessan AI
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://youtu.be/ldvDNzwnM8k)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

Lessan AI represents the pinnacle of the assistant series, evolving into a more flexible and robust system. It bridges the gap between the operating system and human intent. Through natural dialogue, Lessan analyzes your screen, processes uploaded documents, and executes complex workflows with a brand-new, adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.
- 🔀 **OpenRouter Integration** — Selected action modules (web search, memory, flight finder, desktop control, and more) now route their LLM calls through OpenRouter's free-tier models. This significantly increases the effective request limit without any additional cost, while Gemini Live continues to handle real-time voice and tool-calling.

---

## ⚡ Quick Start

```bash
git clone https://github.com/FatihMakes/lessan-ai.git
cd lessan-ai
pip install -r requirements.txt
playwright install
python main.py
```

> ⚠️ **Installation Note:** To keep the repository lightweight, some OS-specific dependencies are not bundled in `requirements.txt`. If you run into a `ModuleNotFoundError`, simply install the missing package via `pip install <module_name>` for your specific system.

---

## 🐧 Kali Linux (APT Install)

Lessan AI ships as a **signed apt repository** (GitHub Pages) plus a standalone `.deb`. To install with apt:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://kngetich373-lgtm.github.io/lessan-ai/apt/lessan-ai.gpg -o /etc/apt/keyrings/lessan-ai.gpg
echo 'deb [signed-by=/etc/apt/keyrings/lessan-ai.gpg] https://kngetich373-lgtm.github.io/lessan-ai/apt ./' | sudo tee /etc/apt/sources.list.d/lessan-ai.list
sudo apt update && sudo apt install lessan-ai
```

Full guide (first-run behavior, upgrades, security notes): **[INSTALL_KALI.md](INSTALL_KALI.md)**

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Keys** | Free Gemini API key + Free OpenRouter API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world AI assistant.
⭐ **Star the repository to support the project.**

| Platform | Link |
|---|---|
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |