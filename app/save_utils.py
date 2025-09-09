from pathlib import Path
from PIL import Image
from datetime import datetime
from app.paths import CROPS_DIR, OUT_DIR
from app.pdf_utils import bbox_rel_to_px, draw_overlay

def sanitize_stem(stem: str) -> str:
    # remove caracteres ruins para nome de arquivo
    bad = '<>:"/\\|?*'
    for ch in bad:
        stem = stem.replace(ch, "_")
    return stem.strip()

def save_crop_image(img_hd: Image.Image, bbox_rel: dict, base_name: str, page_index: int) -> Path:
    """
    Corta na imagem HD usando bbox_rel (frações) e salva JPG.
    Também salva um overlay de debug sobre a imagem HD.
    """
    # Sanitizar nome do arquivo
    clean_name = sanitize_stem(base_name)
    
    w, h = img_hd.size
    x0, y0, x1, y1 = bbox_rel_to_px(bbox_rel, w, h)
    crop = img_hd.crop((x0, y0, x1, y1))
    
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    out = CROPS_DIR / f"{clean_name}_p{page_index}_crop.jpg"
    crop.save(out, quality=95, optimize=True)
    
    # overlay debug em HD
    dbg = draw_overlay(img_hd, bbox_rel)
    dbg_out = OUT_DIR / f"{clean_name}_p{page_index}_overlay_hd.jpg"
    dbg_out.parent.mkdir(parents=True, exist_ok=True)
    dbg.save(dbg_out, quality=85)
    
    return out
