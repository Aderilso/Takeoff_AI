from __future__ import annotations
from typing import List
import streamlit as st
import pdfplumber
from app.paths import OUT_DIR
from app.settings import PROCESS_DPI, FALLBACK_DPI
from app.pdf_utils import page_to_image, bbox_rel_to_px
from app.save_utils import save_crop_image
from app.gemini_client import call_gemini_on_image
from app.result_utils import extract_rows_from_model_payload, is_empty_extraction, get_table_name
from app.aggregate import add_rows, add_report_entry

SYSTEM_PROMPT = (
    "Você é um extrator de TABELAS genérico. Retorne ESTRITAMENTE JSON no envelope "
    "{\"tables\":[{\"name\":...,\"columns_detected\":...,\"rows\":[{...}]}]}. "
    "Mapeie sinônimos (material/descricao/dimensoes_unidade/qtd/peso_unidade_kg/peso_total_kg). "
    "Quando não existir, use null. Sem texto fora do JSON."
)

def process_single_pdf(file, *, bbox_rel: dict, api_key: str, page_index: int = 0) -> int:
    """Retorna qtd de linhas extraídas (0 se vazio). Lança exceção se falhar geral."""
    with pdfplumber.open(file) as pdf:
        page = pdf.pages[page_index]
        try:
            page_hi = page_to_image(page, PROCESS_DPI)
        except Exception:
            page_hi = page_to_image(page, FALLBACK_DPI)

    w, h = page_hi.size
    bbox_px = bbox_rel_to_px(bbox_rel, w, h)
    crop_pil = page_hi.crop(bbox_px)

    # Salva para auditoria (não usa o arquivo no envio; enviamos PIL)
    save_crop_image(crop_pil, getattr(file, "name", "lote.pdf"), page_index)

    # Chamar modelo
    raw_text = call_gemini_on_image(api_key, crop_pil, SYSTEM_PROMPT)

    # Tentar JSON -> payload
    import json
    try:
        payload = json.loads(raw_text)
    except Exception:
        # Deixa estourar pro caller tratar como "erro"
        raise RuntimeError("Resposta do modelo não é JSON válido.")

    if is_empty_extraction(payload):
        return 0

    rows = extract_rows_from_model_payload(payload)
    tname = get_table_name(payload)
    add_rows(st, rows, source_pdf=getattr(file, "name", "lote.pdf"), page_idx=page_index, table_name=tname)
    return len(rows)

def run_batch(files: List, *, bbox_rel: dict, api_key: str):
    n = len(files)
    if n == 0:
        st.warning("Selecione ao menos um PDF.")
        return

    # Placeholders dinâmicos (em tempo real)
    status_box = st.status("Processando lote…", expanded=True)
    progress_ph = st.progress(0.0)
    table_ph = st.empty()
    log_ph = st.empty()

    ok = 0
    empty = 0
    err = 0

    for i, f in enumerate(files):
        pdfname = getattr(f, "name", f"pdf_{i+1}.pdf")
        add_report_entry(st, pdf=pdfname, status="processando", rows=0)

        # Atualiza tabela de status
        from app.aggregate import to_df_report
        table_ph.dataframe(to_df_report(st), use_container_width=True, height=300)

        try:
            count = process_single_pdf(f, bbox_rel=bbox_rel, api_key=api_key, page_index=0)
            if count == 0:
                empty += 1
                st.toast(f"{pdfname}: tabela vazia.", icon="⚠️")
                # Atualiza linha
                st.session_state["agg_report"][-1].update({"status":"vazio","linhas":0})
            else:
                ok += 1
                st.toast(f"{pdfname}: {count} linha(s) extraída(s).", icon="✅")
                st.session_state["agg_report"][-1].update({"status":"ok","linhas":count})
        except Exception as e:
            err += 1
            st.toast(f"{pdfname}: erro — {e}", icon="❌")
            st.session_state["agg_report"][-1].update({"status":"erro","erro":str(e)})

        # Atualiza progress
        progress_ph.progress((i+1)/n)
        # Atualiza grid
        from app.aggregate import to_df_report
        table_ph.dataframe(to_df_report(st), use_container_width=True, height=300)
        # Log resumido
        log_ph.info(f"Concluído {i+1}/{n}: {pdfname}")

    status_box.update(label=f"Lote finalizado: ok={ok}, vazios={empty}, erros={err}", state="complete")
