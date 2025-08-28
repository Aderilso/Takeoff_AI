# app/pipeline.py
from __future__ import annotations
from pathlib import Path
import pdfplumber
import pandas as pd
from typing import Any, Dict, Optional, Tuple

from app.settings import PROCESS_DPI, FALLBACK_DPI
from app.pdf_utils import page_to_image, bbox_rel_to_px
from app.save_utils import save_crop_image
from app.gemini_client import call_gemini_on_image_json, SHARED_PROMPT
from app.json_utils import loads_loose
from app.result_utils import extract_rows_from_model_payload, is_empty_extraction, get_table_name
from app.paths import OUT_DIR

def process_pdf_once(
    *,
    pdf_file,                      # st.uploaded_file OR Path
    page_index: int,
    bbox_rel: Dict[str, float],
    api_key: str,
    template_name: Optional[str] = None,
    save_artifacts: bool = True,
) -> Dict[str, Any]:
    """
    Executa o MESMO percurso do fluxo individual:
    1) render page em 400dpi (fallback 340)
    2) aplicar crop pela bbox_rel
    3) chamar Gemini em JSON mode
    4) parse resiliente para JSON
    5) normalizar em rows/DataFrame
    Retorna dicionário com rows/df/payload e caminhos salvos.
    """
    # Nome do arquivo amigável
    pdf_name = getattr(pdf_file, "name", str(pdf_file))
    base_name = Path(pdf_name).stem

    # 1) abrir pdf e renderizar página em alta
    with pdfplumber.open(pdf_file) as pdf:
        page = pdf.pages[page_index]
        try:
            page_hi = page_to_image(page, PROCESS_DPI)
        except Exception:
            page_hi = page_to_image(page, FALLBACK_DPI)

    # 2) crop
    w, h = page_hi.size
    x0, y0, x1, y1 = bbox_rel_to_px(bbox_rel, w, h)
    crop_pil = page_hi.crop((x0, y0, x1, y1))

    crop_path = None
    if save_artifacts:
        crop_path = save_crop_image(crop_pil, pdf_name, page_index)

    # 3) chamar Gemini (JSON mode)
    raw_text = call_gemini_on_image_json(api_key, crop_pil, SHARED_PROMPT)

    # 4) parse (tolerante à cerca ```json)
    payload = loads_loose(raw_text)

    # 5) normalização -> rows/df
    rows = extract_rows_from_model_payload(payload)
    tname = get_table_name(payload)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    artifacts = {"crop_path": crop_path, "raw_text": raw_text, "table_name": tname}

    # (opcional) salvar CSV/JSON do individual aqui se já havia essa lógica
    # Retorno padronizado
    return {
        "pdf_name": pdf_name,
        "page_index": page_index,
        "bbox_rel": bbox_rel,
        "rows": rows,
        "df": df,
        "payload": payload,
        "artifacts": artifacts,
        "is_empty": len(rows) == 0,
    }
