from __future__ import annotations
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import List, Dict, Any

AGG_ROWS = "agg_rows"               # lista de dicts (linhas)
AGG_REPORT = "agg_report"           # lista de dicts (status por arquivo)

def ensure_state(st):
    if AGG_ROWS not in st.session_state:
        st.session_state[AGG_ROWS] = []
    if AGG_REPORT not in st.session_state:
        st.session_state[AGG_REPORT] = []

def reset(st):
    st.session_state[AGG_ROWS] = []
    st.session_state[AGG_REPORT] = []

def add_rows(st, rows: List[Dict[str, Any]], *, source_pdf: str, page_idx: int, table_name: str | None):
    ensure_state(st)
    for r in rows:
        r2 = dict(r)
        r2["_source_pdf"] = source_pdf
        r2["_page_idx"] = page_idx
        r2["_table_name"] = table_name
        st.session_state[AGG_ROWS].append(r2)

def add_report_entry(st, *, pdf: str, status: str, rows: int = 0, error: str | None = None):
    ensure_state(st)
    st.session_state[AGG_REPORT].append({
        "arquivo": pdf,
        "status": status,           # "processando" | "vazio" | "ok" | "erro"
        "linhas": rows,
        "erro": error or ""
    })

def to_df_rows(st) -> pd.DataFrame:
    ensure_state(st)
    return pd.DataFrame(st.session_state[AGG_ROWS])

def to_df_report(st) -> pd.DataFrame:
    ensure_state(st)
    return pd.DataFrame(st.session_state[AGG_REPORT])

def save_csv_rows(st, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"all_extracted_{ts}.csv"
    df = to_df_rows(st)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path

def save_csv_report(st, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"batch_report_{ts}.csv"
    df = to_df_report(st)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
