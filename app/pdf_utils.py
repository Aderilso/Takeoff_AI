"""
Utilitários para manipulação de PDFs
"""
import os
import hashlib
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import pdfplumber
from PIL import Image
import io

class PDFUtils:
    def __init__(self):
        pass
    
    def get_pdf_info(self, pdf_path: str) -> Dict:
        """Obtém informações básicas do PDF"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = len(pdf.pages)
                first_page = pdf.pages[0]
                width = first_page.width
                height = first_page.height
                
                return {
                    "pages": pages,
                    "width": width,
                    "height": height,
                    "file_size": os.path.getsize(pdf_path),
                    "file_name": os.path.basename(pdf_path)
                }
        except Exception as e:
            return {
                "error": str(e),
                "pages": 0,
                "width": 0,
                "height": 0,
                "file_size": 0,
                "file_name": os.path.basename(pdf_path)
            }
    
    def page_to_image(self, pdf_path: str, page_num: int, dpi: int = 400) -> Optional[Image.Image]:
        """Converte uma página do PDF para imagem PIL"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num >= len(pdf.pages):
                    return None
                
                page = pdf.pages[page_num]
                # Converter para imagem
                img = page.to_image(resolution=dpi)
                return img.original
        except Exception as e:
            print(f"Erro ao converter página para imagem: {e}")
            return None
    
    def crop_page_image(self, image: Image.Image, bbox: Dict[str, int]) -> Image.Image:
        """Recorta uma imagem baseada no bbox"""
        try:
            x0, y0, x1, y1 = bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"]
            return image.crop((x0, y0, x1, y1))
        except Exception as e:
            print(f"Erro ao recortar imagem: {e}")
            return image
    
    def save_image(self, image: Image.Image, output_path: str) -> bool:
        """Salva uma imagem no caminho especificado"""
        try:
            # Criar diretório se não existir
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            image.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"Erro ao salvar imagem: {e}")
            return False
    
    def detect_tables(self, pdf_path: str, page_num: int) -> List[Dict]:
        """Detecta tabelas em uma página do PDF usando pdfplumber"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num >= len(pdf.pages):
                    return []
                
                page = pdf.pages[page_num]
                
                # Detectar tabelas com diferentes configurações
                tables = []
                
                # Tabelas com linhas
                tables.extend(page.find_tables(table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines"
                }))
                
                # Tabelas lattice
                tables.extend(page.find_tables(table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 10
                }))
                
                # Tabelas text
                tables.extend(page.find_tables(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text"
                }))
                
                # Converter para formato padronizado
                result = []
                for i, table in enumerate(tables):
                    bbox = table.bbox
                    result.append({
                        "id": i,
                        "bbox": {
                            "x0": bbox[0],
                            "y0": bbox[1],
                            "x1": bbox[2],
                            "y1": bbox[3]
                        },
                        "rows": len(table.extract()),
                        "confidence": 0.8  # Placeholder
                    })
                
                return result
                
        except Exception as e:
            print(f"Erro ao detectar tabelas: {e}")
            return []
    
    def get_document_fingerprint(self, pdf_path: str) -> str:
        """Gera um fingerprint único para o documento"""
        try:
            # Usar nome do arquivo + tamanho + primeira página como fingerprint
            file_name = os.path.basename(pdf_path)
            file_size = os.path.getsize(pdf_path)
            
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > 0:
                    first_page_text = pdf.pages[0].extract_text()[:1000]  # Primeiros 1000 chars
                else:
                    first_page_text = ""
            
            # Criar hash
            content = f"{file_name}_{file_size}_{first_page_text}"
            return hashlib.md5(content.encode()).hexdigest()
            
        except Exception as e:
            print(f"Erro ao gerar fingerprint: {e}")
            return hashlib.md5(pdf_path.encode()).hexdigest()
    
    def get_template_id(self, pdf_path: str) -> Optional[str]:
        """Tenta identificar o template do PDF (implementação básica)"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > 0:
                    text = pdf.pages[0].extract_text()
                    
                    # Procurar por padrões que indiquem template
                    patterns = [
                        r"modelo\s*[:.]?\s*([a-zA-Z0-9\s]+)",
                        r"template\s*[:.]?\s*([a-zA-Z0-9\s]+)",
                        r"formulário\s*[:.]?\s*([a-zA-Z0-9\s]+)",
                        r"vale\s*v(\d+)",
                        r"versão\s*[:.]?\s*([a-zA-Z0-9\s]+)"
                    ]
                    
                    for pattern in patterns:
                        import re
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            return match.group(1).strip()
            
            return None
            
        except Exception as e:
            print(f"Erro ao identificar template: {e}")
            return None

# Funções utilitárias para o batch runner
def page_to_image(page, dpi: int = 150) -> Image.Image:
    """Converte uma página pdfplumber para imagem PIL"""
    img = page.to_image(resolution=dpi)
    return img.original

def bbox_rel_to_px(bbox_rel: dict, width: int, height: int) -> Tuple[int, int, int, int]:
    """Converte bbox relativo (0-1) para pixels absolutos"""
    x0 = int(bbox_rel["x0"] * width)
    y0 = int(bbox_rel["y0"] * height)
    x1 = int(bbox_rel["x1"] * width)
    y1 = int(bbox_rel["y1"] * height)
    return (x0, y0, x1, y1)
