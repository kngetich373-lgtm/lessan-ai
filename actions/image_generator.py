# actions/image_generator.py
# Lessan AI — Image Generation
#
# Uses OmniRoute (Pollinations.ai free tier) to generate images from prompts.

import datetime
from pathlib import Path

def generate_image(parameters: dict, player=None) -> str:
    """
    Generates an image from a text prompt.

    Parameters:
        prompt: str (required) — description of the image
        style: str (optional) — e.g., "photorealistic", "anime", "oil painting"
        width: int (optional) — image width in pixels (default 1024)
        height: int (optional) — image height in pixels (default 1024)
        model: str (optional) — "flux" (default) or "turbo"
        save_path: str (optional) — where to save the image
    """
    prompt = (parameters.get("prompt") or "").strip()
    if not prompt:
        return "No prompt provided."

    style = (parameters.get("style") or "").strip()
    full_prompt = f"{prompt}, {style}" if style else prompt

    save_path = parameters.get("save_path")
    if not save_path:
        reports_dir = Path.home() / "Lessan" / "reports" / "images"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        save_path = str(reports_dir / f"gen-{stamp}.png")

    try:
        from omniroute import client
        result = client.image_generate(
            prompt=full_prompt,
            width=int(parameters.get("width", 1024)),
            height=int(parameters.get("height", 1024)),
            model=parameters.get("model", "flux"),
            save_path=save_path,
        )
        return f"✅ Image generated successfully: {result}"

    except Exception as e:
        return f"❌ Image generation failed: {e}"