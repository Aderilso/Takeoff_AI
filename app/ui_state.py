"""
Gerenciamento de estado da interface Streamlit
"""
import streamlit as st
from typing import Dict, List, Optional, Any
import json
import pandas as pd
from datetime import datetime
import os
# Removido import de dataframe_full_width pois agora usamos st.dataframe diretamente

class UIState:
    def __init__(self):
        self._init_session_state()
    
    def _init_session_state(self):
        """Inicializa o estado da sessão"""
        if 'pdf_uploaded' not in st.session_state:
            st.session_state.pdf_uploaded = False
        
        if 'pdf_path' not in st.session_state:
            st.session_state.pdf_path = None
        
        if 'pdf_info' not in st.session_state:
            st.session_state.pdf_info = None
        
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 0
        
        if 'page_image' not in st.session_state:
            st.session_state.page_image = None
        
        if 'crop_coords' not in st.session_state:
            st.session_state.crop_coords = None
        
        if 'current_preset' not in st.session_state:
            st.session_state.current_preset = None
        
        if 'detected_tables' not in st.session_state:
            st.session_state.detected_tables = []
        
        if 'processing_result' not in st.session_state:
            st.session_state.processing_result = None
        
        if 'template_name' not in st.session_state:
            st.session_state.template_name = ""
        
        if 'ignore_preset' not in st.session_state:
            st.session_state.ignore_preset = False
    
    def set_pdf_uploaded(self, pdf_path: str, pdf_info: Dict):
        """Define que um PDF foi carregado"""
        st.session_state.pdf_uploaded = True
        st.session_state.pdf_path = pdf_path
        st.session_state.pdf_info = pdf_info
        st.session_state.current_page = 0
        st.session_state.page_image = None
        st.session_state.crop_coords = None
        st.session_state.current_preset = None
        st.session_state.detected_tables = []
        st.session_state.processing_result = None
        st.session_state.ignore_preset = False
    
    def set_page_image(self, image):
        """Define a imagem da página atual"""
        st.session_state.page_image = image
    
    def set_crop_coords(self, coords: Dict[str, float]):
        """Define as coordenadas do crop"""
        st.session_state.crop_coords = coords
    
    def set_current_preset(self, preset: Optional[Dict]):
        """Define o preset atual"""
        st.session_state.current_preset = preset
    
    def set_detected_tables(self, tables: List[Dict]):
        """Define as tabelas detectadas"""
        st.session_state.detected_tables = tables
    
    def set_processing_result(self, result: Dict):
        """Define o resultado do processamento"""
        st.session_state.processing_result = result
    
    def set_template_name(self, name: str):
        """Define o nome do template"""
        st.session_state.template_name = name
    
    def set_ignore_preset(self, ignore: bool):
        """Define se deve ignorar o preset"""
        st.session_state.ignore_preset = ignore
    
    def get_pdf_uploaded(self) -> bool:
        return st.session_state.pdf_uploaded
    
    def get_pdf_path(self) -> Optional[str]:
        return st.session_state.pdf_path
    
    def get_pdf_info(self) -> Optional[Dict]:
        return st.session_state.pdf_info
    
    def get_current_page(self) -> int:
        return st.session_state.current_page
    
    def set_current_page(self, page: int):
        st.session_state.current_page = page
    
    def get_page_image(self):
        return st.session_state.page_image
    
    def get_crop_coords(self) -> Optional[Dict[str, float]]:
        return st.session_state.crop_coords
    
    def get_current_preset(self) -> Optional[Dict]:
        return st.session_state.current_preset
    
    def get_detected_tables(self) -> List[Dict]:
        return st.session_state.detected_tables
    
    def get_processing_result(self) -> Optional[Dict]:
        return st.session_state.processing_result
    
    def get_template_name(self) -> str:
        return st.session_state.template_name
    
    def get_ignore_preset(self) -> bool:
        return st.session_state.ignore_preset
    
    def save_outputs(self, data: List[Dict], raw_response: str, output_dir: str = "out") -> Dict[str, str]:
        """Salva os outputs em diferentes formatos"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Criar diretório se não existir
        os.makedirs(output_dir, exist_ok=True)
        
        output_files = {}
        
        try:
            # Salvar JSON bruto
            raw_json_path = os.path.join(output_dir, f"raw_{timestamp}.json")
            with open(raw_json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": timestamp,
                    "raw_response": raw_response,
                    "parsed_data": data
                }, f, indent=2, ensure_ascii=False)
            output_files["raw_json"] = raw_json_path
            
            # Salvar JSONL
            jsonl_path = os.path.join(output_dir, f"tabela_{timestamp}.jsonl")
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for row in data:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
            output_files["jsonl"] = jsonl_path
            
            # Salvar CSV
            csv_path = os.path.join(output_dir, f"tabela_{timestamp}.csv")
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            output_files["csv"] = csv_path
            
        except Exception as e:
            st.error(f"Erro ao salvar outputs: {e}")
        
        return output_files
    
    # Função create_download_buttons removida - agora renderizada diretamente no app.py
    # para evitar duplicação e garantir layout centralizado
    
    # Função display_processing_result removida - agora renderizada diretamente no app.py
    # para evitar duplicação e garantir layout centralizado
    
    def display_preset_info(self, preset: Dict):
        """Exibe informações sobre o preset aplicado"""
        if not preset:
            return
        
        scope_names = {
            "global": "Global",
            "template": "Por Modelo",
            "document": "Somente neste PDF"
        }
        
        scope_name = scope_names.get(preset["scope"], preset["scope"])
        
        st.info(f"🎯 **Preset aplicado**: {preset['name']} ({scope_name})")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("✏️ Editar", key="btn_edit_preset"):
                st.session_state.editing_preset = True
        
        with col2:
            if st.button("🚫 Ignorar nesta sessão", key="btn_ignore_preset"):
                self.set_ignore_preset(True)
                st.rerun()
        
        with col3:
            if st.button("🔄 Redefinir", key="btn_reset_preset"):
                self.set_current_preset(None)
                self.set_crop_coords(None)
                st.rerun()
