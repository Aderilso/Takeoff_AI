# app/json_utils.py
import json
import re
from typing import Any

def loads_loose(text: str) -> Any:
    """
    Parse JSON de forma tolerante, removendo cercas de código e ruído.
    """
    if not text:
        return None
    
    # Limpar o texto
    cleaned = text.strip()
    
    # Remover cercas de código ```json ... ```
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    match = re.search(code_block_pattern, cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    
    # Remover "json" no início se existir
    if cleaned.lower().startswith('json'):
        cleaned = cleaned[4:].strip()
    
    # Tentar parse direto
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Se falhou, tentar encontrar JSON válido no texto
    # Procurar por arrays ou objetos JSON
    patterns = [
        r'\[.*\]',  # Array JSON
        r'\{.*\}',  # Objeto JSON
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
    
    # Se nada funcionou, retornar None
    return None
