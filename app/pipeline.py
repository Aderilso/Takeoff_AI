# app/pipeline.py
from __future__ import annotations
from pathlib import Path
import pdfplumber
import pandas as pd
from typing import Any, Dict, Optional, Tuple

from app.settings import PROCESS_DPI
from app.pdf_utils import render_page_pair, bbox_rel_to_px
from app.save_utils import save_crop_image
from app.gemini_client import call_gemini_on_image_json, SHARED_PROMPT
from app.json_utils import loads_loose
from app.result_utils import consolidate_tables
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

    # 1) Renderiza par consistente (HD + preview)
    img_hd, img_prev = render_page_pair(pdf_file, page_index, dpi_hd=PROCESS_DPI)

    # 2) Salvar crop na imagem HD usando bbox_rel
    crop_path = None
    crop_pil = None
    
    # Recortar da imagem HD
    w, h = img_hd.size
    x0, y0, x1, y1 = bbox_rel_to_px(bbox_rel, w, h)
    crop_pil = img_hd.crop((x0, y0, x1, y1))
    
    # Salvar crop em arquivo (se solicitado)
    if save_artifacts:
        crop_path = save_crop_image(img_hd, bbox_rel, base_name, page_index)
        print(f"📁 Crop salvo para processamento: {crop_path}")
    
    # 3) Chamar Gemini usando o crop PIL (não o arquivo salvo)
    # Nota: Enviamos a imagem PIL diretamente para melhor qualidade
    print(f"🤖 Enviando crop para Gemini - Tamanho: {crop_pil.size}")
    raw_text = call_gemini_on_image_json(api_key, crop_pil, SHARED_PROMPT)

    # 5) parse (tolerante à cerca ```json)
    payload = loads_loose(raw_text)

    # 6) normalização -> consolidar todas as tabelas
    df_all = consolidate_tables(payload)
    
    # Extrair nome da tabela do payload (se disponível)
    table_name = "tabela_extraida"
    if payload and isinstance(payload, dict) and "tables" in payload:
        tables = payload["tables"]
        if tables and len(tables) > 0:
            table_name = tables[0].get("name", "tabela_extraida")
    
    artifacts = {
        "crop_path": crop_path, 
        "raw_text": raw_text,
        "table_name": table_name
    }

    # Retorno padronizado
    return {
        "pdf_name": pdf_name,
        "page_index": page_index,
        "bbox_rel": bbox_rel,
        "df": df_all,            # <- agora é o consolidado
        "payload": payload,
        "artifacts": artifacts,
        "is_empty": df_all.empty,
        "rows": df_all.to_dict('records') if not df_all.empty else []
    }
