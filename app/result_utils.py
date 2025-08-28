from typing import Any, Dict, List

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
