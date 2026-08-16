from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_packaging_stages_redesigned_ui_entrypoint():
    script = (ROOT / "packaging" / "build_deb.sh").read_text(encoding="utf-8")
    assert "lessan_ui.py" in script
    assert "for item in main.py lessan_ui.py" in script


def test_runtime_entrypoint_uses_redesigned_ui():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    ui = (ROOT / "lessan_ui.py").read_text(encoding="utf-8")
    assert "from lessan_ui import LessanUI" in main
    assert 'self.settings_btn = QPushButton("⚙  Settings")' in ui
