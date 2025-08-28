from pathlib import Path
from PIL import Image
from datetime import datetime

# Definir CROPS_DIR diretamente para evitar import circular
BASE_DIR = Path(__file__).resolve().parents[1]
CROPS_DIR = BASE_DIR / "Crop"

def sanitize_stem(stem: str) -> str:
    # remove caracteres ruins para nome de arquivo
    bad = '<>:"/\\|?*'
    for ch in bad:
        stem = stem.replace(ch, "_")
    return stem.strip()

def crop_filename(pdf_name: str, page_idx: int | None = None) -> Path:
    """
    Ex.: ARG-CE_crop.jpg ou ARG-CE_p0_crop.jpg se page_idx fornecido.
    """
    stem = sanitize_stem(Path(pdf_name).stem)
    if page_idx is None:
        fname = f"{stem}_crop.jpg"
    else:
        fname = f"{stem}_p{page_idx}_crop.jpg"
    return CROPS_DIR / fname

def save_crop_image(pil_img: Image.Image, pdf_name: str, page_idx: int | None = None) -> Path:
    path = crop_filename(pdf_name, page_idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_img.save(path, format="JPEG", quality=95)
    return path
