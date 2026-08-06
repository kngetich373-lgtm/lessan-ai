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
sudo apt install ./lessan-ai_1.0.0-1_amd64.deb
```

## First run

Launch **Lessan AI** from the application menu (or run `lessan-ai`). On first launch:

- A per-user copy of the app is created at `~/.local/share/lessan/app`; your config, memory, and reports live there.
- If a previous `~/Lessan` installation exists, your API keys, memory, and reports are migrated automatically.
- A Python virtualenv is built on first run (system packages install automatically via `postinst`).

## Upgrading after a release

```bash
sudo apt update
sudo apt install --only-upgrade lessan-ai
```

## Security notes

- The repo signing key is a dedicated key for this repository; packages are signature-verified via `[signed-by=...]`.
- The `.deb` contains **no API keys and no personal data** — only a blank `config/api_keys.json.dist` template.