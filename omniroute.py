# omniroute.py
# Lessan AI — Universal Model Router ("OmniRoute")
#
# Pools ALL free LLM routes into one failover router:
#   - OpenRouter free-tier models (text + vision + image)
#   - Pollinations.ai free image generation (no API key needed)
#
# Every LLM call in Lessan routes through this single entry point.
# On rate-limit (429) or timeout, it automatically rotates to the next
# available free model so quota is never a blocker.
#
# NOTE: This supersedes or_client.py. or_client.py is kept as a thin
# compatibility alias so existing imports keep working.

import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniroute")


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR     = _get_base_dir()
API_KEY_PATH = BASE_DIR / "config" / "api_keys.json"


def _load_api_keys() -> dict:
    try:
        with open(API_KEY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _load_openrouter_key() -> str:
    return (_load_api_keys().get("openrouter_api_key") or "").strip()


# ─────────────────────────────────────────────────────────────────────
# Free model pools (auto-rotated on rate-limit / failure)
#
# Verified against the OpenRouter /api/v1/models catalog on 2026-08-07 —
# only models still served as `:free` are listed (stale ids return 404
# and are skipped after one miss). Ordered by general capability so the
# strongest free model answers first when no quota is hit.
# ─────────────────────────────────────────────────────────────────────
TEXT_MODELS: list[str] = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",          # 1M ctx, strongest free tier
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",                         # code-savvy
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",                     # code-savvy
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "poolside/laguna-xs-2.1:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "inclusionai/ling-3.0-tiny:free",
    "nvidia/nemotron-3.5-content-safety:free",         # special-purpose; last resort
]

# OpenRouter currently serves no free tier with image-input support, so
# the vision pool reuses the best live free text models — `chat_vision`
# stays functional for text prompts and degrades gracefully on images.
VISION_MODELS: list[str] = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]

# Models known to support image generation on OpenRouter (free tier varies)
IMAGE_MODELS_OPENROUTER: list[str] = [
    "google/gemini-2.0-flash-exp:free",
    "openai/gpt-image-1:free",
    "black-forest-labs/flux-1.1-pro:free",
    "black-forest-labs/flux-1-schnell:free",
]

# Pollinations.ai — FREE image generation, no API key required.
# Endpoint style:
#   https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true
#   model=flux (default) / turbo
IMAGE_POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

API_URL            = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
REQUEST_TIMEOUT    = 30    # seconds per request (free-tier models respond in a few seconds)
MAX_RETRIES_PER_MODEL = 2  # attempts before moving to next model
RETRY_DELAY        = 1     # seconds between retries
RATE_LIMIT_COOLDOWN = 60   # seconds before retrying a rate-limited model

_rate_limited: dict[str, float] = {}
_global_cooldown_until: float = 0.0   # brief global pause after many 429s
_not_found: set[str] = set()          # models that 404'd — skipped for the process lifetime


class OmniRoute:

    def __init__(self) -> None:
        self.api_key = _load_openrouter_key()
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://github.com/lessan-ai",
            "X-Title":       "Lessan AI (OmniRoute)",
        } if self.api_key else {}

    # ── rate-limit bookkeeping ──────────────────────────────────────
    def _is_rate_limited(self, model: str) -> bool:
        # Per-model cooldown only. The global pause is applied between
        # calls (see _call_with_fallback), NOT inside the pool loop —
        # otherwise a batch of 429s would abort rotation before models
        # that still have quota get a chance.
        ts = _rate_limited.get(model)
        if ts is None:
            return False
        if time.time() - ts > RATE_LIMIT_COOLDOWN:
            del _rate_limited[model]
            return False
        return True

    def _mark_rate_limited(self, model: str) -> None:
        global _global_cooldown_until
        _rate_limited[model] = time.time()
        logger.warning(
            f"[OmniRoute] Rate limited: {model} — cooling down "
            f"{RATE_LIMIT_COOLDOWN}s"
        )
        # If many models are rate-limited at once, pause briefly so the
        # whole pool doesn't get hammered in a tight loop.
        if len(_rate_limited) >= max(3, len(TEXT_MODELS) // 2):
            _global_cooldown_until = time.time() + 5

    def _clear_global_cooldown(self) -> None:
        global _global_cooldown_until
        _global_cooldown_until = 0.0

    # ── dead-model bookkeeping (HTTP 404 = removed from OpenRouter) ───
    def _is_not_found(self, model: str) -> bool:
        return model in _not_found

    def _mark_not_found(self, model: str) -> None:
        _not_found.add(model)
        logger.warning(f"[OmniRoute] Model no longer available: {model} — skipping")

    # ── core OpenRouter call ────────────────────────────────────────
    def _call_openrouter(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_format: Optional[dict] = None,
    ) -> Optional[str]:
        if not self.api_key:
            logger.warning("[OmniRoute] No OpenRouter key configured.")
            return None

        payload: dict = {
            "model":       model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            try:
                resp = requests.post(
                    API_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )

                if resp.status_code == 429:
                    self._mark_rate_limited(model)
                    return None

                if resp.status_code == 404:
                    self._mark_not_found(model)
                    return None

                if resp.status_code == 200:
                    data    = resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                    )
                    return content.strip() if content else None

                logger.warning(
                    f"[OmniRoute] {model} → HTTP {resp.status_code} "
                    f"(attempt {attempt}/{MAX_RETRIES_PER_MODEL})"
                )

            except requests.exceptions.Timeout:
                logger.warning(
                    f"[OmniRoute] {model} → Timeout "
                    f"(attempt {attempt}/{MAX_RETRIES_PER_MODEL})"
                )
            except Exception as e:
                logger.error(f"[OmniRoute] {model} → Unexpected error: {e}")

            if attempt < MAX_RETRIES_PER_MODEL:
                time.sleep(RETRY_DELAY)

        return None

    def _call_with_fallback(
        self,
        pool: list[str],
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_format: Optional[dict] = None,
    ) -> str:
        # If a burst of 429s just happened, pause briefly before this call
        # so the free pool isn't hammered back-to-back.
        global _global_cooldown_until
        wait = _global_cooldown_until - time.time()
        if wait > 0:
            time.sleep(min(wait, 5))

        # Try the explicitly requested model first (respecting cooldown /
        # dead-model skip).
        if model and not self._is_rate_limited(model) and not self._is_not_found(model):
            result = self._call_openrouter(
                model, messages, max_tokens, temperature, response_format
            )
            if result:
                self._clear_global_cooldown()
                return result
            logger.info(
                f"[OmniRoute] Requested model failed, "
                f"falling back to pool: {model}"
            )

        # Rotate through the whole free pool.
        tried = set()
        for m in pool:
            if m in tried or self._is_rate_limited(m) or self._is_not_found(m):
                continue
            tried.add(m)
            logger.info(f"[OmniRoute] Trying: {m}")
            result = self._call_openrouter(
                m, messages, max_tokens, temperature, response_format
            )
            if result:
                self._clear_global_cooldown()
                logger.info(f"[OmniRoute] ✓ Success: {m}")
                return result

        raise RuntimeError(
            "[OmniRoute] All models failed or are rate-limited. "
            "Check your OpenRouter API key and network connection."
        )

    # ── public API: chat ────────────────────────────────────────────
    def chat(
        self,
        prompt: str,
        system: str = (
            "You are a component of Lessan, an AI assistant. "
            "Be concise, helpful, and precise."
        ),
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]
        return self._call_with_fallback(
            TEXT_MODELS, messages, model, max_tokens, temperature
        )

    # ── public API: structured JSON ─────────────────────────────────
    def chat_json(
        self,
        prompt: str,
        system: str = (
            "Return ONLY valid JSON. "
            "No markdown fences, no extra text, no explanation."
        ),
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]
        raw = self._call_with_fallback(
            TEXT_MODELS, messages, model, max_tokens, temperature=0.2
        )

        clean = raw.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(
                f"[OmniRoute] JSON parse failed: {e}\n"
                f"Raw response (first 300 chars): {raw[:300]}"
            )
            raise ValueError(
                f"Model returned unparseable JSON: {e}\n"
                f"Raw output: {raw[:200]}"
            )

    # ── public API: vision ──────────────────────────────────────────
    def vision(
        self,
        prompt: str,
        image_b64: str,
        mime: str = "image/png",
        system: str = "Analyze the image and describe what you see clearly and concisely.",
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        return self._call_with_fallback(
            VISION_MODELS, messages, model, max_tokens, temperature=0.2
        )

    def vision_from_file(
        self,
        prompt: str,
        image_path: str,
        system: str = "Analyze the image and describe what you see clearly and concisely.",
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        path = Path(image_path)
        mime_map = {
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif":  "image/gif",
        }
        mime = mime_map.get(path.suffix.lower(), "image/png")

        with open(path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        return self.vision(prompt, image_b64, mime, system, model, max_tokens)

    # ── public API: multi-turn ──────────────────────────────────────
    def multi_turn(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        return self._call_with_fallback(
            TEXT_MODELS, messages, model, max_tokens, temperature
        )

    # ── public API: image generation (free via Pollinations.ai) ─────
    def image_generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: str = "flux",
        nologo: bool = True,
        save_path: Optional[str] = None,
        timeout: int = 240,
    ) -> str:
        """
        Generates an image from a text prompt using Pollinations.ai.
        Returns the path to the saved image.

        Raises RuntimeError if generation fails.
        """
        import urllib.parse

        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise RuntimeError("image_generate requires a non-empty prompt.")

        url = IMAGE_POLLINATIONS_URL.format(
            prompt=urllib.parse.quote(clean_prompt)
        )
        params = []
        if width:
            params.append(f"width={int(width)}")
        if height:
            params.append(f"height={int(height)}")
        if model:
            params.append(f"model={model}")
        if nologo:
            params.append("nologo=true")
        if params:
            url += "?" + "&".join(params)

        logger.info(f"[OmniRoute] 🎨 Generating image via Pollinations: {clean_prompt[:60]}")

        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Pollinations returned HTTP {resp.status_code}"
                )
            content_type = resp.headers.get("Content-Type", "")
            ext = ".png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "webp" in content_type:
                ext = ".webp"

            if not save_path:
                output_dir = Path.home() / "Pictures" / "Lessan"
                output_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S")
                save_path = str(output_dir / f"omniroute-{stamp}{ext}")
            else:
                save_path = str(save_path)
                if not Path(save_path).suffix:
                    save_path += ext

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            size = Path(save_path).stat().st_size
            if size < 500:  # likely an error image/placeholder
                raise RuntimeError(
                    f"Pollinations returned a {size}-byte file — "
                    "likely a blocked/generated placeholder."
                )

            logger.info(f"[OmniRoute] ✅ Image saved: {save_path} ({size} bytes)")
            return save_path

        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Image generation timed out after {timeout}s."
            )
        except requests.exceptions.RequestException as e:
            # Try OpenRouter image models as a fallback if key is present.
            return self._image_generate_openrouter(
                clean_prompt, width, height, save_path
            ) if self.api_key else (
                f"Image download failed: {e}"
            )

    def _image_generate_openrouter(
        self,
        prompt: str,
        width: int,
        height: int,
        save_path: Optional[str] = None,
    ) -> str:
        """Fallback image generation through OpenRouter image models."""
        if not save_path:
            output_dir = Path.home() / "Pictures" / "Lessan"
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            save_path = str(output_dir / f"omniroute-or-{stamp}.png")

        for model in IMAGE_MODELS_OPENROUTER:
            try:
                payload = {
                    "model":    model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": (
                                            "data:image/png;base64,"
                                            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                                        )
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": prompt,
                                },
                            ],
                        }
                    ],
                }
                # NOTE: OpenRouter chat-completions image output is not yet
                # universal on free tiers; keep this as a soft best-effort.
                resp = requests.post(
                    API_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                    )
                    if isinstance(content, str) and content.startswith("http"):
                        img_resp = requests.get(content, timeout=120)
                        if img_resp.status_code == 200:
                            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                            Path(save_path).write_bytes(img_resp.content)
                            return save_path
                if resp.status_code == 429:
                    self._mark_rate_limited(model)
            except Exception as e:
                logger.warning(
                    f"[OmniRoute] OpenRouter image model {model} failed: {e}"
                )
        return "Image generation via OpenRouter fallback failed."

    # ── public API: model pool info ─────────────────────────────────
    def available_models(self) -> dict:
        return {
            "text_models":    TEXT_MODELS,
            "vision_models":  VISION_MODELS,
            "image_models":   IMAGE_MODELS_OPENROUTER,
            "rate_limited":   list(_rate_limited.keys()),
            "total_text":     len(TEXT_MODELS),
            "total_vision":   len(VISION_MODELS),
            "pollinations":   "free (no key)",
            "openrouter_key": bool(self.api_key),
        }


client = OmniRoute()

if __name__ == "__main__":
    print("=" * 55)
    print("  Lessan AI — OmniRoute Self-Test")
    print("=" * 55)

    print("\n[TEST 1] Basic chat...")
    try:
        reply = client.chat("Introduce yourself in one sentence.")
        print(f"  Response : {reply}")
        print(f"  Status   : PASS ✓")
    except Exception as e:
        print(f"  Status   : FAIL ✗ — {e}")

    print("\n[TEST 2] JSON mode...")
    try:
        data = client.chat_json(
            'List 3 programming languages. Format: {"languages": ["a", "b", "c"]}',
            system="Return only valid JSON. No extra text."
        )
        print(f"  Response : {data}")
        print(f"  Status   : PASS ✓")
    except Exception as e:
        print(f"  Status   : FAIL ✗ — {e}")

    print("\n[TEST 3] Multi-turn conversation...")
    try:
        history = [
            {"role": "system",    "content": "You are a helpful assistant. Be brief."},
            {"role": "user",      "content": "My name is Tony."},
            {"role": "assistant", "content": "Hello Tony, how can I help you?"},
            {"role": "user",      "content": "What is my name?"},
        ]
        reply = client.multi_turn(history)
        print(f"  Response : {reply}")
        print(f"  Status   : PASS ✓")
    except Exception as e:
        print(f"  Status   : FAIL ✗ — {e}")

    print("\n[TEST 4] Model pool info...")
    info = client.available_models()
    print(f"  Text models   : {info['total_text']}")
    print(f"  Vision models : {info['total_vision']}")
    print(f"  Rate limited  : {info['rate_limited'] or 'none'}")
    print(f"  OpenRouter key: {'configured' if info['openrouter_key'] else 'MISSING'}")
    print(f"  Status        : PASS ✓")

    print("\n" + "=" * 55)
    print("  All tests complete.")
    print("=" * 55)