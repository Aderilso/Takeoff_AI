from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"
OUT_DIR = BASE_DIR / "out"
CROPS_DIR = BASE_DIR / "Crop"  # solicitado pelo usuário

def ensure_dirs():
    for d in (CONFIG_DIR, OUT_DIR, CROPS_DIR):
        d.mkdir(parents=True, exist_ok=True)
