# actions/file_organizer.py
# Lessan AI — Smart File Organizer
#
# Two features on top of the existing file_controller:
#
#  1. organize  — Group files in a messy folder into neat subfolders
#                 by type (Images, Documents, Videos, Music, Archives, Code, Data).
#
#  2. smart_rename — Use OmniRoute (free LLM) to understand the CONTENT of a
#                 file and give it a meaningful, human-readable name based on
#                 what's actually inside.
#
# Orientation: everything is GUIDED. Nothing is moved or renamed without
# user confirmation (or `auto: true` explicitly requested).

import json
import re
import shutil
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".ico"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".wma", ".opus"}
ARCHIVE_EXTS = {".zip", ".rar", ".tar", ".gz", ".7z", ".bz2", ".xz"}
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".java",
             ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
             ".kt", ".sh", ".bash", ".ps1", ".lua", ".sql", ".yaml", ".toml"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".ppt",
            ".pptx", ".xls", ".xlsx", ".csv", ".ods", ".json", ".xml"}
DATA_EXTS = {".csv", ".tsv", ".xls", ".xlsx", ".json", ".xml"}

FOLDER_MAP = {
    "Images":    IMAGE_EXTS,
    "Videos":    VIDEO_EXTS,
    "Music":     AUDIO_EXTS,
    "Archives":  ARCHIVE_EXTS,
    "Code":      CODE_EXTS,
    "Data":      DATA_EXTS,
    "Documents": DOC_EXTS - DATA_EXTS,
}

# Files the organizer will never touch
IGNORED_NAMES = {".", ".."}
IGNORED_STEMS = {"desktop.ini", "thumbs.db", ".ds_store", "$recycle.bin"}


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
REPORT_DIR = BASE_DIR / "reports"


# ─────────────────────────────────────────────────────────────────────
# 1. Organize by category
# ─────────────────────────────────────────────────────────────────────
def organize_files(parameters: dict) -> str:
    """
    Groups a folder's files into neat subfolders by category.

    Parameters:
        path: str (required) — the folder to organize ("desktop" allowed)
        auto: bool (default False) — if True, executes moves automatically;
              otherwise prints a preview and asks for confirmation.
        confirm_file: str (optional) — if set, the tool writes the plan to a
              confirm file instead of moving (for interactive flows).
    """
    folder = _resolve_folder(parameters.get("path", ""))
    if not folder.exists():
        return f"Folder not found: {folder}"
    if not folder.is_dir():
        return f"Not a directory: {folder}"

    auto = bool(parameters.get("auto", False))

    # Gather files (non-recursive, files only)
    files = [f for f in folder.iterdir() if f.is_file()]
    files = [f for f in files if f.name.lower() not in IGNORED_STEMS]

    if not files:
        return f"No files found in {folder}"

    # Categorize
    plan: dict[str, list[Path]] = {}
    skipped = []
    for f in files:
        ext = f.suffix.lower()
        target = None
        for category, exts in FOLDER_MAP.items():
            if ext in exts:
                target = category
                break
        if target:
            plan.setdefault(target, []).append(f)
        else:
            skipped.append(f.name)

    if not plan:
        return f"No categorizable files found in {folder}."

    # ── Preview or execute ──────────────────────────────────────────
    if not auto:
        lines = [f"📁 {folder} — proposed organization:\n"]
        for category, flist in sorted(plan.items()):
            lines.append(f"  {category}/ ({len(flist)} files)")
            for f in flist[:8]:
                lines.append(f"    - {f.name}")
            if len(flist) > 8:
                lines.append(f"    ... and {len(flist) - 8} more")
        lines.append("\nRun again with auto: true to apply these moves.")
        return "\n".join(lines)

    # Execute
    moved = 0
    for category, flist in sorted(plan.items()):
        dest = folder / category
        dest.mkdir(exist_ok=True)
        for f in flist:
            target = dest / f.name
            # Avoid collision by appending a number
            counter = 1
            while target.exists():
                target = dest / f"{f.stem}_{counter}{f.suffix}"
                counter += 1
            shutil.move(str(f), str(target))
            moved += 1

    return (
        f"✅ Organized {moved} files into {len(plan)} categories in {folder}.\n"
        + "\n".join(f"  - {category}/ ({len(flist)} files)"
                    for category, flist in sorted(plan.items()))
        + (f"\n\n⏭️ Skipped (unknown type): {', '.join(skipped[:10])}"
           if skipped else "")
    )


# ─────────────────────────────────────────────────────────────────────
# 2. Content-based smart rename (uses OmniRoute)
# ─────────────────────────────────────────────────────────────────────
def smart_rename(parameters: dict, speak=None) -> str:
    """
    Intelligently renames ONE file based on its contents using OmniRoute.

    Parameters:
        file_path: str (required)
        style: "descriptive" (default) | "short" | "professional" — name style
        auto: bool (default True) — if False, returns suggested names only
        max_chars: int (default 50) — max filename length (without extension)
    """
    file_str = (parameters.get("file_path") or "").strip()
    if not file_str:
        return "No file path provided."

    path = Path(file_str)
    if not path.exists():
        return f"File not found: {file_str}"
    if not path.is_file():
        return f"Not a file: {file_str}"

    style = (parameters.get("style") or "descriptive").lower()
    auto  = parameters.get("auto", True)
    max_chars = int(parameters.get("max_chars", 50))

    content_preview = _peek_content(path, max_chars=6000)

    try:
        from omniroute import client
        result = client.chat_json(
            json.dumps({
                "filename": path.name,
                "extension": path.suffix,
                "size_bytes": path.stat().st_size,
                "content_preview": content_preview[:2500],
            }),
            system=(
                "You are a file-naming assistant. Look at the CONTENT preview and "
                "invent 3 meaningful, human-readable filenames that describe what "
                "the file actually contains.\n\n"
                f"Style: {style}. Max {max_chars} characters per name (no extension).\n"
                "Rules:\n"
                "- Names must be descriptive, not generic (no 'New File 1').\n"
                "- Use Title Case with underscores or spaces.\n"
                "- Preserve the original extension.\n"
                "- NEVER include the original filename.\n"
                "- Return ONLY valid JSON: {\"names\": [\"a\", \"b\", \"c\"]}"
            ),
            temperature=0.3,
            max_tokens=256,
        )
    except Exception as e:
        # Fallback: heuristic name based on extension
        fallback = _heuristic_name(path)
        return f"AI naming unavailable ({e}). Suggesting: {fallback}"

    names = [n for n in result.get("names", []) if n]
    if not names:
        return f"AI returned no valid names. Suggestion: {_heuristic_name(path)}"

    # Sanitize each suggested name
    cleaned = []
    for n in names:
        n = re.sub(r'[\\/:*?"<>|]', "_", n)
        n = n.strip(" .")
        if n and n.lower() != path.stem.lower():
            cleaned.append(n)
    if not cleaned:
        cleaned = [path.stem]

    if not auto:
        out = f"💡 Suggested names for '{path.name}':\n"
        for i, n in enumerate(cleaned, 1):
            out += f"  {i}. {n}{path.suffix}\n"
        out += "\nCall with auto: true to apply the first suggestion."
        return out

    # Apply the best name
    new_name = cleaned[0][:max_chars].rstrip(" .") + path.suffix
    target   = path.with_name(new_name)
    counter  = 1
    while target.exists() and target != path:
        target = path.with_name(f"{cleaned[0][:max_chars].rstrip(' .')}_{counter}{path.suffix}")
        counter += 1
        if counter > 20:
            return "Could not find a unique name after 20 attempts."

    if target == path:
        return f"File already has a good name: {path.name}"

    shutil.move(str(path), str(target))
    return f"✅ Renamed: '{path.name}' → '{target.name}'"


def _peek_content(path: Path, max_chars: int = 6000) -> str:
    """Extracts a small preview of the file's content based on its type."""
    ext = path.suffix.lower()

    # Text-like files — read directly
    text_exts = {".txt", ".md", ".csv", ".json", ".xml", ".log", ".py", ".js",
                 ".ts", ".html", ".css", ".sh", ".yaml", ".yml", ".toml",
                 ".ini", ".cfg", ".java", ".c", ".cpp", ".rs", ".go", ".sql"}
    if ext in text_exts:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""

    # PDF
    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(
                    (page.extract_text() or "") for page in pdf.pages[:4]
                )[:max_chars]
        except Exception:
            try:
                import PyPDF2
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join(
                        (page.extract_text() or "") for page in reader.pages[:4]
                    )[:max_chars]
            except Exception:
                return ""

    # DOCX
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)[:max_chars]
        except Exception:
            return ""

    # Images — no native OCR here; return header info to help the model
    if ext in IMAGE_EXTS:
        try:
            from PIL import Image
            img = Image.open(path)
            return (
                f"[Image: {img.format}, {img.size[0]}x{img.size[1]}px, "
                f"mode: {img.mode}]"
            )
        except Exception:
            return "[Image file]"

    # Audio/Video — use metadata if possible
    if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
        try:
            from mutagen import File
            meta = File(path)
            if meta:
                info = {
                    "title": str(meta.get("title", "")),
                    "artist": str(meta.get("artist", "")),
                    "album": str(meta.get("album", "")),
                    "duration_sec": round(float(getattr(meta.info, "length", 0)), 1),
                }
                return json.dumps({k: v for k, v in info.items() if v})
        except Exception:
            pass
        return f"[{('Audio' if ext in AUDIO_EXTS else 'Video')} file]"

    # Unknown — just return filename
    return f"[Unknown file type: {ext}]"


def _heuristic_name(path: Path) -> str:
    """Renames based purely on type/metadata when AI is unavailable."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return f"screenshot-{path.stem[:20]}"
    if ext in DOC_EXTS:
        return f"document-{path.stem[:20]}"
    if ext in AUDIO_EXTS:
        return f"audio-{path.stem[:20]}"
    if ext in VIDEO_EXTS:
        return f"video-{path.stem[:20]}"
    return f"file-{path.stem[:20]}"


def _resolve_folder(path: str) -> Path:
    p = (path or "").strip().lower()
    home = Path.home()
    if p in ("desktop", "~"):
        return home / "Desktop" if (home / "Desktop").exists() else home / "桌面"
    if p.startswith("~"):
        return home / p[2:]
    return Path(path) if path else home


# ─────────────────────────────────────────────────────────────────────
# Public entry point used by main.py / executor
# ─────────────────────────────────────────────────────────────────────
def file_organizer(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "").lower()

    if action == "organize":
        return organize_files(parameters)

    if action == "rename" or action == "smart_rename":
        return smart_rename(parameters, speak)

    if action == "clean_desktop":
        # Full desktop organization flow
        params = dict(parameters)
        params["path"] = "desktop"
        params["auto"] = True
        return organize_files(params)

    return (
        "Unknown organizer action. Use 'organize', 'smart_rename', or 'clean_desktop'."
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Lessan File Organizer")
    ap.add_argument("--path", help="Folder to organize")
    ap.add_argument("--action", default="organize",
                    choices=["organize", "rename", "clean_desktop"])
    ap.add_argument("--auto", action="store_true", help="Apply automatically")
    ap.add_argument("--file", help="File to rename")
    args = ap.parse_args()

    if args.action == "rename":
        if not args.file:
            print("--file required for rename")
        else:
            print(smart_rename({"file_path": args.file, "auto": True}))
    else:
        if not args.path:
            args.path = "desktop"
        print(organize_files({"path": args.path, "auto": args.auto}))