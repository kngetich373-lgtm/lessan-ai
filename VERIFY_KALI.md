# Lessan AI — final Kali verification

This checklist is the **manual** verification step. GitHub Actions validates the offline Python suite, but it cannot verify your physical microphone, speakers, display server, local model services, or desktop integration.

## 1. Prepare Kali

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nmap portaudio19-dev libsndfile1 ffmpeg
```

## 2. Get the latest repository

```bash
git clone https://github.com/kngetich373-lgtm/lessan-ai.git
cd lessan-ai
```

If the repository already exists locally:

```bash
git pull --ff-only origin main
```

## 3. Create the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest
```

## 4. Run the offline suite first

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -m "not live"
```

**Expected:** the command finishes without failures.

## 5. Configure one model provider

Copy the template:

```bash
cp .env.example .env
```

Fill in at least one supported provider key, or use the packaged setup screen described in `INSTALL_KALI.md`.

Never commit `.env` or `config/api_keys.json`.

## 6. Run live gateway checks (optional)

These tests can contact external services and may consume API quota:

```bash
python -m pytest -m live
```

Only run these when you intentionally want an external-provider check.

## 7. Desktop verification

Launch Lessan using the normal project/package launcher described in `INSTALL_KALI.md`.

Verify manually:

- application opens without crashing;
- chat input accepts a complete message;
- a configured model returns a response;
- provider fallback works when the preferred provider is unavailable;
- microphone/voice features work if configured;
- browser/Playwright features work after the browser dependency is installed;
- system telemetry displays correctly;
- tool actions respect confirmation/permission boundaries;
- application can close cleanly without leaving runaway processes.

## 8. Report failures

If any command fails, copy the **full terminal error** and send it back. Do not delete project files or reinstall the whole system first; the error output is the fastest way to identify the exact remaining integration issue.
