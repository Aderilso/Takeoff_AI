import pandas as pd
from typing import Any, Dict, List

SAFE_DEFAULT_COLUMNS = ["material","descricao","dimensoes_unidade","qtd","peso_unidade_kg","peso_total_kg"]

def _safe_name(x: str) -> str:
    return (x or "").strip().lower().replace(" ", "_").replace("__","_")

def extract_rows_from_model_payload(payload: Any) -> List[Dict]:
    """
    Aceita:
      - lista pura de linhas (legado)
      - dict com {"tables":[{"rows":[...]}], ...}
    Retorna lista de linhas (dicts) ou [].
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        tables = payload.get("tables") or []
        if isinstance(tables, list) and tables:
            # usa a primeira tabela por padrão; caller pode escolher outra
            first = tables[0] or {}
            rows = first.get("rows") or []
            return rows if isinstance(rows, list) else []
    return []

def is_empty_extraction(payload: Any) -> bool:
    return len(extract_rows_from_model_payload(payload)) == 0

def get_table_name(payload: Any) -> str | None:
    if isinstance(payload, dict):
        tables = payload.get("tables") or []
        if isinstance(tables, list) and tables:
            return (tables[0] or {}).get("name")
    return None

def extract_tables_to_dfs(payload: Dict[str, Any]) -> List[pd.DataFrame]:
    tables = payload.get("tables", []) or []
    dfs = []
    for t in tables:
        name = t.get("name") or t.get("header_in_image") or "tabela"
        name = _safe_name(name)
        rows = t.get("rows", []) or []
        if not isinstance(rows, list):
            continue
        df = pd.json_normalize(rows, sep="_")
        # garantir colunas comuns (se não existirem, cria com None)
        for c in SAFE_DEFAULT_COLUMNS:
            if c not in df.columns:
                df[c] = None
        df["_table_name"] = name
        dfs.append(df)
    return dfs

def consolidate_tables(payload: Dict[str, Any]) -> pd.DataFrame:
    dfs = extract_tables_to_dfs(payload)
    if not dfs:
        return pd.DataFrame(columns=SAFE_DEFAULT_COLUMNS + ["_table_name"])
    cols = sorted(set().union(*[set(d.columns) for d in dfs]))
    return pd.concat([d.reindex(columns=cols) for d in dfs], ignore_index=True)
