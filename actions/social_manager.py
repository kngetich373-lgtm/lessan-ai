# actions/social_manager.py
# Lessan AI — Social Media Content Manager
#
# Helps generate, plan, and manage content for:
# YouTube, TikTok, Facebook, Twitter (X), Snapchat, Instagram.
#
# Features:
#   - Content Generation: Scripts, captions, hashtags, thread ideas.
#   - Platform Optimization: Tailors content for specific platform constraints.
#   - Scheduling: Saves planned posts to a local calendar/report.

import datetime
import json
from pathlib import Path

def social_manager(parameters: dict, player=None, speak=None) -> str:
    """
    Manages social media content generation and planning.

    Parameters:
        platform: str (required) — youtube, tiktok, facebook, twitter, snapchat, instagram
        action: str (required) — generate_content, plan_campaign, optimize_profile
        topic: str — what the content is about
        tone: str — e.g., professional, funny, viral, educational
    """
    platform = (parameters.get("platform") or "").lower().strip()
    action = (parameters.get("action") or "generate_content").lower().strip()
    topic = parameters.get("topic", "")
    tone = parameters.get("tone", "engaging")

    if not platform:
        return "Please specify a platform (e.g., YouTube, Twitter)."
    
    if not topic:
        return "Please provide a topic or description for the content."

    try:
        from omniroute import client
        
        system_msg = (
            f"You are an expert Social Media Manager specializing in {platform}. "
            "Your goal is to create high-engagement content that follows the latest trends "
            "and platform-specific algorithms."
        )
        
        prompt = (
            f"Task: {action}\n"
            f"Platform: {platform}\n"
            f"Topic: {topic}\n"
            f"Tone: {tone}\n\n"
            "Provide a detailed response including "
        )
        
        if platform == "youtube":
            prompt += "a catchy title, a video script outline, and a description with SEO keywords."
        elif platform == "twitter" or platform == "x":
            prompt += "a viral thread (5-10 tweets) or a single high-impact tweet with hashtags."
        elif platform == "instagram":
            prompt += "an engaging caption, 30 relevant hashtags, and a Reel/Post concept."
        elif platform == "tiktok":
            prompt += "a short-form video script, trending sound suggestions, and hashtags."
        else:
            prompt += "captions, content ideas, and engagement strategies."

        result = client.chat(prompt, system=system_msg)
        
        # Save to reports
        reports_dir = Path.home() / "Lessan" / "reports" / "social_media"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        save_path = reports_dir / f"{platform}-{action}-{stamp}.md"
        
        report_content = f"# Social Media Plan: {platform.capitalize()}\n"
        report_content += f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
        report_content += f"**Topic:** {topic}\n"
        report_content += f"**Action:** {action}\n\n"
        report_content += "## Generated Content\n\n"
        report_content += result
        
        save_path.write_text(report_content, encoding="utf-8")
        
        return f"📱 **{platform.capitalize()} Content Generated**\n\n{result}\n\n📄 Saved to: {save_path}"

    except Exception as e:
        return f"❌ Social manager failed: {e}"