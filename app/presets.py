# app/presets.py
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Optional

# Diretórios/arquivos do projeto
PROJECT_ROOT = Path(__file__).resolve().parents[1]                  # ...\Takeoff_AI_Multi_v2
PRESETS_DIR  = PROJECT_ROOT / "config"
PRESETS_PATH = PRESETS_DIR / "presets.json"

def ensure_store():
    """Garante que config/ e presets.json existam."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    if not PRESETS_PATH.exists():
        PRESETS_PATH.write_text("[]", encoding="utf-8")

def load_presets() -> List[Dict]:
    """Carrega a lista de presets do arquivo JSON."""
    ensure_store()
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        # Corrupção? Zera com lista vazia.
        PRESETS_PATH.write_text("[]", encoding="utf-8")
        return []

def save_presets(presets: List[Dict]) -> None:
    ensure_store()
    PRESETS_PATH.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")

def list_active_presets() -> List[Dict]:
    return [p for p in load_presets() if p.get("active", True)]

def get_preset_by_id(pid: str) -> Optional[Dict]:
    for p in load_presets():
        if p.get("id") == pid:
            return p
    return None

def upsert_preset(preset: Dict) -> None:
    """Inclui/atualiza um preset pelo campo 'id'."""
    presets = load_presets()
    pid = preset.get("id")
    if not pid:
        raise ValueError("Preset precisa de campo 'id'.")
    found = False
    for i, p in enumerate(presets):
        if p.get("id") == pid:
            presets[i] = preset
            found = True
            break
    if not found:
        presets.append(preset)
    save_presets(presets)

def set_active(pid: str, active: bool) -> None:
    presets = load_presets()
    for p in presets:
        if p.get("id") == pid:
            p["active"] = bool(active)
            break
    save_presets(presets)

def preset_label(p: Dict) -> str:
    return f'{p.get("name","(sem nome)")} ({p.get("scope","global")})'
