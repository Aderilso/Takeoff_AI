"""
Cliente da API Gemini para extração de tabelas
"""
import os
import json
import re
import io
from typing import Dict, List, Optional, Any, Union
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# Prompt compartilhado para extração de tabelas
SHARED_PROMPT = (
    "Você é um extrator de TABELAS genérico. Retorne ESTRITAMENTE JSON no envelope "
    "{\"tables\":[{\"name\":...,\"columns_detected\":...,\"rows\":[{...}]}]}. "
    "Mapeie sinônimos (material/descricao/dimensoes_unidade/qtd/peso_unidade_kg/peso_total_kg). "
    "Quando não existir, use null. Sem texto fora do JSON."
)

def _ensure_pil(img: Union[Image.Image, bytes, bytearray, str, os.PathLike]) -> Image.Image:
    """Garante que a entrada seja convertida para PIL.Image"""
    if isinstance(img, Image.Image):
        pil = img
    elif isinstance(img, (bytes, bytearray)):
        pil = Image.open(io.BytesIO(img))
    else:
        # caminho no disco
        pil = Image.open(str(img))
    if pil.mode not in ("RGB", "L"):
        pil = pil.convert("RGB")
    return pil

def call_gemini_on_image(
    api_key: str,
    img: Union[Image.Image, bytes, bytearray, str, os.PathLike],
    prompt: str,
    model_name: str = DEFAULT_MODEL,
) -> str:
    """
    Sempre envia PIL.Image ao SDK. NÃO envia bytes crus.
    """
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY ausente.")

    genai.configure(api_key=api_key)
    pil_img = _ensure_pil(img)

    model = genai.GenerativeModel(model_name)

    # Enviar como parte multimodal: [prompt, PIL.Image]
    resp = model.generate_content([prompt, pil_img])
    return resp.text or ""

def call_gemini_on_image_json(
    api_key: str,
    img: Union[Image.Image, bytes, bytearray, str, os.PathLike],
    prompt: str = SHARED_PROMPT,
    model_name: str = DEFAULT_MODEL,
) -> str:
    """
    Versão especializada para extração de tabelas em JSON.
    Usa o prompt compartilhado por padrão.
    """
    return call_gemini_on_image(api_key, img, prompt, model_name)

class GeminiClient:
    def __init__(self, config_dir: str = "config"):
        load_dotenv(f"{config_dir}/.env")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY não encontrada. Configure o arquivo .env")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
    
    def extract_table_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        Extrai tabela de uma imagem usando Gemini
        Retorna: {"success": bool, "data": List[Dict], "raw_response": str, "error": str}
        """
        try:
            # Verificar se a imagem existe
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "data": [],
                    "raw_response": "",
                    "error": f"Imagem não encontrada: {image_path}"
                }
            
            # Usar diretamente o caminho da imagem - será convertido para PIL.Image
            return self._process_image_with_gemini(image_path)
                
        except Exception as e:
            return {
                "success": False,
                "data": [],
                "raw_response": "",
                "error": f"Erro na API: {str(e)}"
            }
    
    def extract_table_from_image_pil(self, pil_image) -> Dict[str, Any]:
        """
        Extrai tabela de uma imagem PIL usando Gemini
        Retorna: {"success": bool, "data": List[Dict], "raw_response": str, "error": str}
        """
        try:
            # Usar diretamente a PIL.Image - não converter para bytes
            return self._process_image_with_gemini(pil_image)
                
        except Exception as e:
            return {
                "success": False,
                "data": [],
                "raw_response": "",
                "error": f"Erro na API: {str(e)}"
            }
    
    def _process_image_with_gemini(self, image_data: bytes) -> Dict[str, Any]:
        """
        Processa imagem com Gemini (método interno)
        """
        # Preparar o prompt do sistema
        system_prompt = """
        Você é um especialista em extração de dados de tabelas. Sua tarefa é:
        
        1. Analisar a imagem da tabela fornecida
        2. Extrair todos os dados em formato JSON
        3. Retornar APENAS o JSON, sem texto adicional
        4. Normalizar cabeçalhos (remover espaços extras, caracteres especiais)
        5. Preencher células vazias com null
        6. Manter a estrutura de colunas consistente
        
        Formato esperado:
        [
            {"coluna1": "valor1", "coluna2": "valor2", ...},
            {"coluna1": "valor3", "coluna2": "valor4", ...}
        ]
        
        IMPORTANTE: Retorne apenas o JSON válido, sem cercas de código ou texto explicativo.
        """
        
        # Usar a nova função que garante PIL.Image
        try:
            raw_response = call_gemini_on_image(self.api_key, image_data, system_prompt, self.model_name)
            raw_response = raw_response.strip()
        except Exception as e:
            return {
                "success": False,
                "data": [],
                "raw_response": "",
                "error": f"Erro na API: {str(e)}"
            }
        
        # Tentar extrair JSON da resposta
        json_data = self._extract_json_from_response(raw_response)
        
        if json_data:
            return {
                "success": True,
                "data": json_data,
                "raw_response": raw_response,
                "error": None
            }
        else:
            return {
                "success": False,
                "data": [],
                "raw_response": raw_response,
                "error": "Não foi possível extrair JSON válido da resposta"
            }
    
    def _extract_json_from_response(self, response_text: str) -> Optional[List[Dict]]:
        """
        Extrai JSON da resposta do Gemini, tratando diferentes formatos
        """
        # Remover espaços em branco
        text = response_text.strip()
        
        # Tentar diferentes padrões de extração
        
        # 1. JSON direto
        try:
            return json.loads(text)
        except:
            pass
        
        # 2. JSON com cercas de código
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\[.*\]',  # Array JSON
            r'\{.*\}',  # Objeto JSON
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    # Limpar o match
                    cleaned = match.strip()
                    if cleaned.startswith('[') or cleaned.startswith('{'):
                        return json.loads(cleaned)
                except:
                    continue
        
        # 3. Tentar encontrar array JSON no texto
        try:
            # Procurar por arrays JSON
            array_match = re.search(r'\[[\s\S]*\]', text)
            if array_match:
                return json.loads(array_match.group())
        except:
            pass
        
        # 4. Última tentativa: tentar parse do texto completo
        try:
            # Remover possíveis prefixos/sufixos
            cleaned_text = re.sub(r'^[^{[]*', '', text)
            cleaned_text = re.sub(r'[^}\]]*$', '', cleaned_text)
            
            if cleaned_text.startswith('[') or cleaned_text.startswith('{'):
                return json.loads(cleaned_text)
        except:
            pass
        
        return None
    
    def validate_api_key(self) -> bool:
        """Valida se a API key está funcionando"""
        try:
            # Teste simples
            response = self.model.generate_content("Teste de conexão")
            return response.text is not None
        except Exception as e:
            print(f"Erro na validação da API key: {e}")
            return False

def validate_gemini_key(api_key: str) -> bool:
    """
    Valida se a chave da API Gemini é válida
    Args:
        api_key: Chave da API Gemini
    Returns:
        bool: True se a chave for válida, False caso contrário
    """
    try:
        if not api_key or not api_key.strip():
            return False
        
        # Configurar a API com a chave fornecida
        genai.configure(api_key=api_key)
        
        # Criar um modelo temporário para teste
        temp_model = genai.GenerativeModel("gemini-1.5-pro")
        
        # Fazer uma requisição simples de teste
        response = temp_model.generate_content("Teste de conexão")
        
        # Se chegou até aqui sem erro, a chave é válida
        return response.text is not None
        
    except Exception as e:
        print(f"Erro na validação da chave Gemini: {e}")
        return False
