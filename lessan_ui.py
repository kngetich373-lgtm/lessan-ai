from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QKeySequence, pyqtSignal, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)
from config.runtime_overrides import install_genai_overrides

install_genai_overrides()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"
DEFAULT_CONFIG = {
    "gemini_api_key": "", "openrouter_api_key": "", "providers": [], "models": [],
    "voice": {"enabled": True, "provider": "gemini", "model": "gemini-3.1-flash-live-preview", "voice": "Kore"},
}
PROVIDER_PRESETS = {
    "Gemini": ("gemini", "https://generativelanguage.googleapis.com/v1beta"),
    "OpenAI": ("openai", "https://api.openai.com/v1"),
    "OpenRouter": ("openrouter", "https://openrouter.ai/api/v1"),
    "DeepSeek": ("deepseek", "https://api.deepseek.com/v1"),
    "Kimi / Moonshot": ("kimi", "https://api.moonshot.cn/v1"),
    "Ollama": ("ollama", "http://localhost:11434"),
    "LM Studio": ("lmstudio", "http://localhost:1234/v1"),
    "Custom OpenAI-compatible": ("custom_openai", ""),
}
GEMINI_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Leda", "Orus", "Puck", "Zephyr"]

def _apply_voice_environment(data: dict) -> None:
    voice = data.get("voice", {}) or {}
    os.environ["LESSAN_GEMINI_LIVE_MODEL"] = str(voice.get("model") or DEFAULT_CONFIG["voice"]["model"])
    os.environ["LESSAN_GEMINI_VOICE"] = str(voice.get("voice") or "Kore")
    os.environ["LESSAN_GEMINI_VOICE_ENABLED"] = "1" if voice.get("enabled", True) else "0"

def load_config() -> dict:
    data = json.loads(json.dumps(DEFAULT_CONFIG))
    if API_FILE.exists():
        try:
            raw = json.loads(API_FILE.read_text("utf-8")); data.update(raw)
            data["voice"] = {**DEFAULT_CONFIG["voice"], **raw.get("voice", {})}
        except Exception: pass
    _apply_voice_environment(data); return data

def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True); API_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try: os.chmod(API_FILE, 0o600)
    except OSError: pass
    _apply_voice_environment(data)

def discover_models(kind: str, base_url: str, api_key: str) -> list[dict]:
    kind = kind.lower().strip()
    if kind == "gemini":
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": api_key}, timeout=20); r.raise_for_status()
        return [{"id": m.get("name", "").removeprefix("models/"), "name": m.get("displayName") or m.get("name", ""), "provider": "gemini", "capabilities": m.get("supportedGenerationMethods", []), "context_length": m.get("inputTokenLimit", 0)} for m in r.json().get("models", []) if m.get("name")]
    if kind == "ollama":
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=15); r.raise_for_status()
        return [{"id": m.get("name", ""), "name": m.get("name", ""), "provider": "ollama"} for m in r.json().get("models", []) if m.get("name")]
    r = requests.get(base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {api_key}"} if api_key else {}, timeout=20); r.raise_for_status()
    return [{"id": m.get("id", ""), "name": m.get("id", ""), "provider": kind, "context_length": m.get("context_length", 0)} for m in r.json().get("data", []) if m.get("id")]

class SettingsDialog(QDialog):
    config_saved = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Lessan Settings"); self.resize(820, 620); self.config=load_config(); self.setStyleSheet(self._style())
        root=QVBoxLayout(self); title=QLabel("Settings"); title.setObjectName("title"); root.addWidget(title); sub=QLabel("Configure providers, import models, and select Gemini Live voice."); sub.setObjectName("muted"); root.addWidget(sub)
        tabs=QTabWidget(); root.addWidget(tabs,1)
        tab=QWidget(); pv=QVBoxLayout(tab); form=QFormLayout(); self.provider_name=QComboBox(); self.provider_name.addItems(PROVIDER_PRESETS.keys()); self.base_url=QLineEdit(); self.api_key=QLineEdit(); self.api_key.setEchoMode(QLineEdit.EchoMode.Password); self.api_key.setPlaceholderText("API key; leave empty for local providers"); show=QCheckBox("Show"); row=QHBoxLayout(); row.addWidget(self.api_key,1); row.addWidget(show); show.toggled.connect(lambda on:self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)); self.provider_name.currentTextChanged.connect(self._preset_changed); form.addRow("Provider",self.provider_name); form.addRow("Base URL",self.base_url); form.addRow("API key",row); pv.addLayout(form)
        actions=QHBoxLayout(); self.add_provider_btn=QPushButton("Add / Update Provider"); self.discover_btn=QPushButton("Discover Models"); self.discover_btn.setObjectName("primary"); self.remove_provider_btn=QPushButton("Remove Provider"); [actions.addWidget(x) for x in (self.add_provider_btn,self.discover_btn,self.remove_provider_btn)]; pv.addLayout(actions)
        self.provider_list=QListWidget(); pv.addWidget(QLabel("Connected providers")); pv.addWidget(self.provider_list,1); self.model_list=QListWidget(); pv.addWidget(QLabel("Imported models")); pv.addWidget(self.model_list,2); self.add_provider_btn.clicked.connect(self._save_provider); self.remove_provider_btn.clicked.connect(self._remove_provider); self.discover_btn.clicked.connect(self._discover_models); self.provider_list.itemClicked.connect(self._select_provider); tabs.addTab(tab,"Providers & Models")
        voice=QWidget(); vv=QVBoxLayout(voice); vf=QFormLayout(); self.voice_enabled=QCheckBox("Use Gemini Live voice"); self.voice_enabled.setChecked(bool(self.config["voice"].get("enabled",True))); self.voice_model=QLineEdit(self.config["voice"].get("model",DEFAULT_CONFIG["voice"]["model"])); self.voice_name=QComboBox(); self.voice_name.addItems(GEMINI_VOICES); self.voice_name.setCurrentText(self.config["voice"].get("voice","Kore")); vf.addRow("Voice",self.voice_enabled); vf.addRow("Live model",self.voice_model); vf.addRow("Voice name",self.voice_name); vv.addLayout(vf); note=QLabel("Gemini Live provides bidirectional audio with native audio output. The selected model must support Live API audio."); note.setWordWrap(True); note.setObjectName("muted"); vv.addWidget(note); test=QPushButton("Save voice configuration"); test.setObjectName("primary"); test.clicked.connect(self._save_all); vv.addWidget(test); vv.addStretch(); tabs.addTab(voice,"Voice")
        use=QWidget(); uv=QVBoxLayout(use); info=QLabel("This redesign applies Nielsen's 10 heuristics: visible status, familiar language, user control, consistency, error prevention, recognition over recall, flexibility, minimalist presentation, recovery, and help."); info.setWordWrap(True); uv.addWidget(info); reset=QPushButton("Reset settings to defaults"); reset.clicked.connect(self._reset); uv.addWidget(reset); uv.addStretch(); tabs.addTab(use,"Usability")
        footer=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); footer.accepted.connect(self._save_all); footer.rejected.connect(self.reject); root.addWidget(footer); self._refresh_lists(); self._preset_changed(self.provider_name.currentText())
    def _style(self): return """QDialog,QWidget{background:#0b1020;color:#e7ecff;}QTabWidget::pane{border:1px solid #24304d;border-radius:10px;}QTabBar::tab{padding:10px 16px;color:#9aa8c7;}QTabBar::tab:selected{color:#fff;border-bottom:2px solid #7c8cff;}QLineEdit,QComboBox,QListWidget{background:#111a2e;border:1px solid #2b3a5d;border-radius:8px;padding:8px;color:#eef2ff;}QPushButton{background:#18233d;border:1px solid #33466e;border-radius:8px;padding:9px 14px;color:#eaf0ff;}QPushButton:hover{border-color:#7c8cff;background:#202e4e;}QPushButton#primary{background:#5b5bd6;border-color:#7c8cff;font-weight:600;}QLabel#title{font-size:22px;font-weight:700;}QLabel#muted{color:#8f9bb6;}"""
    def _preset_changed(self,name): self.base_url.setText(PROVIDER_PRESETS[name][1])
    def _save_provider(self):
        display=self.provider_name.currentText(); kind,preset=PROVIDER_PRESETS[display]; base=self.base_url.text().strip() or preset; key=self.api_key.text().strip(); self.config["providers"]=[p for p in self.config.get("providers",[]) if p.get("id")!=kind]; self.config["providers"].append({"id":kind,"name":display,"base_url":base,"api_key":key,"enabled":True});
        if kind=="gemini" and key:self.config["gemini_api_key"]=key
        if kind=="openrouter" and key:self.config["openrouter_api_key"]=key
        save_config(self.config); self._refresh_lists()
    def _remove_provider(self):
        item=self.provider_list.currentItem()
        if not item:return
        kind=item.data(Qt.ItemDataRole.UserRole); self.config["providers"]=[p for p in self.config.get("providers",[]) if p.get("id")!=kind]; save_config(self.config); self._refresh_lists()
    def _select_provider(self,item):
        kind=item.data(Qt.ItemDataRole.UserRole)
        for p in self.config.get("providers",[]):
            if p.get("id")==kind:
                for name,(pk,_) in PROVIDER_PRESETS.items():
                    if pk==kind:self.provider_name.setCurrentText(name);break
                self.base_url.setText(p.get("base_url",""));self.api_key.setText(p.get("api_key",""));break
    def _discover_models(self):
        kind,preset=PROVIDER_PRESETS[self.provider_name.currentText()]; base=self.base_url.text().strip() or preset; key=self.api_key.text().strip() or (self.config.get("gemini_api_key","") if kind=="gemini" else ""); self.discover_btn.setEnabled(False); self.discover_btn.setText("Discovering…"); QApplication.processEvents()
        try:
            models=discover_models(kind,base,key); existing={(m.get("provider"),m.get("id")):m for m in self.config.get("models",[])}; [existing.__setitem__((m["provider"],m["id"]),m) for m in models]; self.config["models"]=list(existing.values()); save_config(self.config); self._refresh_lists(); QMessageBox.information(self,"Discovery complete",f"Imported {len(models)} models from {kind}.")
        except Exception as exc: QMessageBox.critical(self,"Model discovery failed",str(exc))
        finally:self.discover_btn.setEnabled(True);self.discover_btn.setText("Discover Models")
    def _refresh_lists(self):
        self.provider_list.clear();self.model_list.clear();
        for p in self.config.get("providers",[]): item=QListWidgetItem(f"● {p.get('name',p.get('id'))} — {p.get('base_url','')}");item.setData(Qt.ItemDataRole.UserRole,p.get("id"));self.provider_list.addItem(item)
        for m in self.config.get("models",[]):self.model_list.addItem(f"{m.get('provider','?')} · {m.get('name') or m.get('id')}")
    def _save_all(self):
        self.config["voice"]={"enabled":self.voice_enabled.isChecked(),"provider":"gemini","model":self.voice_model.text().strip() or DEFAULT_CONFIG["voice"]["model"],"voice":self.voice_name.currentText()};save_config(self.config);self.config_saved.emit(self.config);self.accept()
    def _reset(self): self.config=json.loads(json.dumps(DEFAULT_CONFIG));save_config(self.config);self._refresh_lists();self.voice_enabled.setChecked(True);self.voice_model.setText(DEFAULT_CONFIG["voice"]["model"]);self.voice_name.setCurrentText("Kore")

class MainWindow(QMainWindow):
    user_input_submitted=pyqtSignal(str,str); mute_toggled=pyqtSignal(bool)
    def __init__(self,face_path:str="face.png"): super().__init__();self.setWindowTitle("Lessan AI");self.resize(1280,820);self.setMinimumSize(980,640);self.config=load_config();self._build_ui()
    def _build_ui(self):
        self.setStyleSheet("""QMainWindow,QWidget{background:#0a0f1d;color:#edf2ff;}QFrame#sidebar,QFrame#inspector{background:#0f1728;border:1px solid #1f2d49;border-radius:12px;}QLabel#brand{font-size:20px;font-weight:700;}QLabel#section{color:#8794ae;font-size:11px;font-weight:600;}QLabel#status{color:#8fe0bd;}QPushButton{background:#17223a;border:1px solid #2a3a5c;border-radius:8px;padding:9px 12px;}QPushButton:hover{border-color:#7285ff;background:#1c2a48;}QPushButton#primary{background:#5b5bd6;border-color:#7788ff;font-weight:700;}QLineEdit{background:#111b30;border:1px solid #2b3b5f;border-radius:10px;padding:11px;}QTextEdit{background:#0b1426;border:1px solid #1f2d49;border-radius:10px;padding:10px;}QComboBox{background:#111b30;border:1px solid #2b3b5f;border-radius:8px;padding:8px;}""")
        central=QWidget();root=QHBoxLayout(central);root.setContentsMargins(14,14,14,14);root.setSpacing(12);self.setCentralWidget(central)
        side=QFrame(objectName="sidebar");side.setFixedWidth(210);sv=QVBoxLayout(side);sv.addWidget(QLabel("LESSAN AI",objectName="brand"));sv.addWidget(QLabel("CONTROL CENTER",objectName="section"));self.home_btn=QPushButton("⌂  Home");self.models_btn=QPushButton("◈  Models");self.settings_btn=QPushButton("⚙  Settings");self.help_btn=QPushButton("?  Help");[sv.addWidget(x) for x in (self.home_btn,self.models_btn,self.settings_btn,self.help_btn)];sv.addSpacing(12);sv.addWidget(QLabel("SYSTEM",objectName="section"));self.status_label=QLabel("●  Ready",objectName="status");sv.addWidget(self.status_label);self.provider_label=QLabel("0 providers");self.model_label=QLabel("0 models");self.voice_label=QLabel("Gemini voice: ready");[sv.addWidget(x) for x in (self.provider_label,self.model_label,self.voice_label)];sv.addStretch();self.clear_btn=QPushButton("Clear conversation");sv.addWidget(self.clear_btn);root.addWidget(side)
        center=QFrame();cv=QVBoxLayout(center);hdr=QHBoxLayout();t=QLabel("Assistant");t.setStyleSheet("font-size:18px;font-weight:700;");hdr.addWidget(t);hdr.addStretch();self.model_combo=QComboBox();self.model_combo.setMinimumWidth(260);hdr.addWidget(QLabel("Model"));hdr.addWidget(self.model_combo);cv.addLayout(hdr);self.chat=QTextEdit();self.chat.setReadOnly(True);self.chat.setPlaceholderText("Conversation will appear here.");cv.addWidget(self.chat,1);row=QHBoxLayout();self.attach_btn=QPushButton("Attach");self.input_field=QLineEdit();self.input_field.setPlaceholderText("Message Lessan…");self.mic_btn=QPushButton("🎙 Voice");self.send_btn=QPushButton("Send");self.send_btn.setObjectName("primary");row.addWidget(self.attach_btn);row.addWidget(self.input_field,1);row.addWidget(self.mic_btn);row.addWidget(self.send_btn);cv.addLayout(row);self.file_label=QLabel("No file attached");self.file_label.setStyleSheet("color:#7f8ba6;");cv.addWidget(self.file_label);root.addWidget(center,1)
        insp=QFrame(objectName="inspector");insp.setFixedWidth(220);iv=QVBoxLayout(insp);iv.addWidget(QLabel("CURRENT SESSION",objectName="section"));self.session_status=QLabel("Listening");self.session_status.setStyleSheet("font-size:18px;font-weight:700;");iv.addWidget(self.session_status);iv.addSpacing(10);iv.addWidget(QLabel("Provider"));self.active_provider=QLabel("—");iv.addWidget(self.active_provider);iv.addWidget(QLabel("Voice"));self.active_voice=QLabel("Gemini / Kore");iv.addWidget(self.active_voice);iv.addSpacing(16);iv.addWidget(QLabel("USABILITY",objectName="section"));[iv.addWidget(QLabel(x)) for x in ("✓ Clear labels and visible state","✓ Consistent button actions","✓ User-controlled conversation","✓ Helpful errors and recovery","✓ Progressive disclosure")];iv.addStretch();root.addWidget(insp)
        self.send_btn.clicked.connect(self._submit);self.input_field.returnPressed.connect(self._submit);self.mic_btn.setCheckable(True);self.mic_btn.toggled.connect(self._on_mic_toggled);self.attach_btn.clicked.connect(self._attach);self.clear_btn.clicked.connect(self.chat.clear);self.settings_btn.clicked.connect(self.open_settings);self.models_btn.clicked.connect(self.open_settings);self.help_btn.clicked.connect(self._show_help);QShortcut(QKeySequence("Ctrl+,"),self).activated.connect(self.open_settings);self.current_file=None;self._refresh_model_combo()
    def _refresh_model_combo(self):
        self.config=load_config();self.model_combo.clear();models=self.config.get("models",[])
        for m in models:self.model_combo.addItem(f"{m.get('provider')} · {m.get('name') or m.get('id')}",m.get('id'))
        if not models:self.model_combo.addItem("Configure a provider in Settings","")
        self.provider_label.setText(f"{len(self.config.get('providers',[]))} providers");self.model_label.setText(f"{len(models)} models");v=self.config.get("voice",{});self.voice_label.setText("Gemini voice: enabled" if v.get("enabled") else "Gemini voice: disabled");self.active_voice.setText(f"Gemini / {v.get('voice','Kore')}");self.active_provider.setText(self.config["providers"][0].get("name","Configured") if self.config.get("providers") else "—")
    def open_settings(self):dlg=SettingsDialog(self);dlg.config_saved.connect(lambda _:self._refresh_model_combo());dlg.exec()
    def _attach(self):path,_=QFileDialog.getOpenFileName(self,"Attach file",str(Path.home()));self.current_file=path or None;self.file_label.setText(f"Attached: {Path(path).name}" if path else "No file attached")
    def _submit(self):
        text=self.input_field.text().strip();file=self.current_file
        if text or file:
            if text:self.chat.append(f"<b>You</b>: {text}")
            if file:self.chat.append(f"<i>Attachment</i>: {Path(file).name}")
            self.user_input_submitted.emit(text,file or "");self.input_field.clear();self.current_file=None;self.file_label.setText("No file attached")
    def _on_mic_toggled(self,checked):self.mic_btn.setText("🔇 Stop voice" if checked else "🎙 Voice");self.mute_toggled.emit(not checked)
    def _show_help(self):QMessageBox.information(self,"Lessan Help","Enter sends. Attach adds a file. Voice toggles the microphone. Settings configures providers, imports models, and selects Gemini Live voice. Ctrl+, opens Settings.")
    def set_state(self,state):self.session_status.setText(state.title());self.status_label.setText(f"●  {state.title()}")
    def write_log(self,message):self.chat.append(message)
    def append_stream_chunk(self,chunk):self.chat.moveCursor(self.chat.textCursor().MoveOperation.End);self.chat.insertPlainText(chunk);self.chat.ensureCursorVisible()

class LessanUI:
    def __init__(self,face_image="face.png"):
        self._app=QApplication.instance() or QApplication([]);self._app.setApplicationName("Lessan AI");self._window=MainWindow(face_image);self.muted=False;self.current_file=None;self.on_text_command=None;self._window.user_input_submitted.connect(self._on_user_input);self._window.mute_toggled.connect(self._on_mute_toggled);self._window.show()
    def _on_user_input(self,text,file_path):self.current_file=file_path or None;self.on_text_command(text) if self.on_text_command and text else None
    def _on_mute_toggled(self,muted):self.muted=muted
    @property
    def root(self):return self._window
    def set_state(self,state):self._window.set_state(state)
    def write_log(self,message):self._window.write_log(message)
    def append_stream_chunk(self,chunk):self._window.append_stream_chunk(chunk)
    def wait_for_api_key(self):
        cfg=load_config()
        if cfg.get("gemini_api_key") or cfg.get("openrouter_api_key") or cfg.get("providers"):return
        SettingsDialog(self._window).exec()
    def run(self):self._app.exec()

def run_ui():LessanUI().run()
if __name__=="__main__":run_ui()
