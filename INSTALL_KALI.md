# Install Lessan AI on Kali Linux

Lessan AI is published as a **signed apt repository** hosted on GitHub Pages, plus a GitHub Release with the standalone `.deb`.

## Option 1 — apt repository (recommended)

After this one-time setup, `sudo apt install lessan-ai` works and later versions arrive via `sudo apt upgrade`.

```bash
# 1. Trust the repository signing key
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://kngetich373-lgtm.github.io/lessan-ai/apt/lessan-ai.gpg \
    -o /etc/apt/keyrings/lessan-ai.gpg

# 2. Add the repository
echo 'deb [signed-by=/etc/apt/keyrings/lessan-ai.gpg] https://kngetich373-lgtm.github.io/lessan-ai/apt ./' \
    | sudo tee /etc/apt/sources.list.d/lessan-ai.list

# 3. Install
sudo apt update
sudo apt install lessan-ai
```

## Option 2 — standalone .deb

Download from the latest [GitHub Release](https://github.com/kngetich373-lgtm/lessan-ai/releases) and install:

```bash
sudo apt install ./lessan-ai_1.0.1-2_amd64.deb
```

## First run

Launch **Lessan AI** from the application menu (or run `lessan-ai`). On first launch:

- A per-user copy of the app is created at `~/.local/share/lessan/app`; your config, memory, and reports live there. On upgrades the code is re-synced while your state is preserved.
- If a previous `~/Lessan` installation exists, your API keys, memory, and reports are migrated automatically.
- A **per-user Python virtualenv** is built at `~/.local/share/lessan/venv` on first launch (no root needed). It installs `requirements.txt` and self-heals if any dependency goes missing. Log: `~/.local/state/lessan/lessan-bootstrap.log`.
- Playwright Chromium (browser/WhatsApp features) is downloaded **in the background** on first launch into `~/.local/share/lessan/ms-playwright`; the app starts immediately. The `nmap` Python package has no Python 3.13 release and is skipped automatically — the system `nmap` binary (installed as a dependency) is used instead.
- **A built-in setup screen** appears on first launch asking for your API keys:
  - **Gemini API key** (for voice/live chat) - get one free at <https://aistudio.google.com/app/apikey\>.
  - **OpenAI / OpenRouter API key** (for OmniRoute text routing) - get one at <https://openrouter.ai/keys\>.
  - **Enter at least one key**, or use **"Continue without keys"** to run on free OmniRoute models. Lessan launches the moment you save your choice.
- Keys are stored in `~/.local/share/lessan/app/config/api_keys.json`; add or change them any time by re-running the setup screen.

## Upgrading after a release

```bash
sudo apt update
sudo apt install --only-upgrade lessan-ai
```

## Security notes

- The repo signing key is a dedicated key for this repository; packages are signature-verified via `[signed-by=...]`.
- The `.deb` contains **no API keys and no personal data** — only a blank `config/api_keys.json.dist` template.