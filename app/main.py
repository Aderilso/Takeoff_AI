"""
Takeoff AI Multi v2 - Aplicação Principal
"""
# --- bootstrap de path: garante que o pacote "app" é importável ---
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # D:\POCs\Takeoff_AI_Multi_v2
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
# -------------------------------------------------------------------

from app.pageconfig import configure
configure()

import streamlit as st
import tempfile
import os
from pathlib import Path
from PIL import Image
import io

# Configurar PIL para aceitar imagens grandes
Image.MAX_IMAGE_PIXELS = None

def _prepare_canvas_bg(img_prev: Image.Image, target_w: int = 1100) -> Image.Image:
    """
    Prepara a imagem para o canvas:
    - converte para RGB
    - redimensiona para 'target_w' mantendo proporção
    """
    if img_prev is None:
        return None
    im = img_prev.convert("RGB").copy()
    target_w = max(400, int(target_w))  # limite mínimo seguro
    if im.width != target_w:
        new_h = int(round(im.height * (target_w / im.width)))
        im = im.resize((target_w, max(1, new_h)), Image.LANCZOS)
    im.load()
    return im

def _pil_to_png_bytes(img: Image.Image) -> bytes:
    """Converte PIL Image para bytes PNG"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# Importar módulos locais (sem execução de código Streamlit)
import pandas as pd
from app.presets import list_active_presets, preset_label, get_preset_by_id, upsert_preset
from app.gemini_client import GeminiClient, validate_gemini_key, call_gemini_on_image
from app.pdf_utils import PDFUtils, bbox_rel_to_px, draw_overlay, render_page_pair, render_pdf_page
from app.ui_state import UIState
from app.ui_compat import image_fluid, dataframe_fluid, patch_streamlit_image_to_url, pil_to_data_url
from app.image_utils import as_pil_image
from app.paths import ensure_dirs, OUT_DIR, CROPS_DIR
from app.save_utils import save_crop_image
from app.result_utils import is_empty_extraction, extract_rows_from_model_payload, get_table_name
from app.settings import PROCESS_DPI
# aggregate será importado quando necessário (evita execução prematura de st.session_state)

def _bbox_ready(b):
    """Verifica se bbox_rel está pronto para uso"""
    return isinstance(b, dict) and all(k in b for k in ("x0", "y0", "x1", "y1"))

# Import do streamlit_cropper e drawable_canvas
try:
    from streamlit_cropper import st_cropper
except Exception:
    pass  # já deve estar instalado no requirements

try:
    # Aplica o patch de compatibilidade antes de importar o canvas
    patch_streamlit_image_to_url()
    from streamlit_drawable_canvas import st_canvas
except Exception:
    pass  # fallback para cropper se não disponível

# fragment compat (usa a versão estável se existir; senão a experimental)
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)

@_fragment
def crop_editor_fragment(img_prev: Image.Image, target_w: int, page_idx: int):
    """
    Renderiza APENAS o editor (canvas) sem afetar o resto da página.
    update_streamlit=False => não atualiza a cada movimento; usamos um botão para capturar.
    """
    # detectar troca de largura e limpar desenho antigo
    prev_w = st.session_state.get("prev_canvas_w")
    width_changed = prev_w is not None and prev_w != int(target_w)
    if width_changed:
        st.session_state["crop_canvas_json"] = None
        st.session_state["crop_coords_px_preview"] = None

    bg_img = _prepare_canvas_bg(img_prev, target_w=int(target_w))
    w_prev, h_prev = bg_img.size

    data_url = pil_to_data_url(bg_img, fmt="PNG")
    prev_json = st.session_state.get("crop_canvas_json") or {}
    prev_objs = [o for o in prev_json.get("objects", []) if o.get("type") != "image"]
    if width_changed:
        prev_objs = []

    # injeta a imagem como objeto fabric (fundo robusto, sem "preto")
    bg_obj = {
        "type": "image",
        "left": 0, "top": 0, "width": w_prev, "height": h_prev,
        "scaleX": 1, "scaleY": 1, "angle": 0,
        "flipX": False, "flipY": False, "opacity": 1,
        "selectable": False, "evented": False, "hasControls": False, "hasBorders": False,
        "src": data_url,
    }
    initial_drawing = {"objects": [bg_obj] + prev_objs}

    st.caption("Desenhe um retângulo e depois clique em **📌 Capturar seleção**.")

    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_color="#ff4d4f",
        stroke_width=2,
        background_image=bg_img,  # PIL.Image do preview
        width=w_prev,
        height=h_prev,
        drawing_mode="rect",
        display_toolbar=True,
        update_streamlit=True,  # <- OBRIGATÓRIO para receber json_data
        key="crop_canvas",  # <- chave estável
        initial_drawing=st.session_state.get("crop_canvas_json"),
    )

    # Função para salvar crop em 400 DPI
    def _save_crop_400dpi(pdf_path: Path, page_idx: int, bbox_rel: dict) -> Path:
        pdf_path = Path(pdf_path)
        img_full = render_pdf_page(pdf_path, page_index=page_idx, dpi=400)  # PIL.Image
        x0 = int(round(bbox_rel["x0"] * img_full.width))
        y0 = int(round(bbox_rel["y0"] * img_full.height))
        x1 = int(round(bbox_rel["x1"] * img_full.width))
        y1 = int(round(bbox_rel["y1"] * img_full.height))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(img_full.width, x1), min(img_full.height, y1)
        box = (x0, y0, x1, y1)

        CROPS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CROPS_DIR / f"{pdf_path.stem}_p{page_idx}_crop.jpg"
        img_full.crop(box).convert("RGB").save(out_path, "JPEG", quality=95, optimize=True)
        return out_path

    # --- Botões do editor ---
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("📌 Capturar seleção", key="btn_capture_rect"):
            data = canvas.json_data
            if not data:
                st.error("Não recebi a seleção do canvas. Desenhe o retângulo e tente novamente.")
            else:
                rects = [o for o in data.get("objects", []) if o.get("type") == "rect"]
                # fallback: usar objeto ativo se disponível
                if not rects and data.get("activeObject", {}).get("type") == "rect":
                    rects = [data["activeObject"]]

                if not rects:
                    st.warning("Nenhum retângulo encontrado. Desenhe e clique em Capturar seleção.")
                else:
                    r = rects[-1]
                    # considerar escala do Fabric
                    sx = float(r.get("scaleX", 1) or 1)
                    sy = float(r.get("scaleY", 1) or 1)
                    w = int(max(1, round((r.get("width") or 0) * sx)))
                    h = int(max(1, round((r.get("height") or 0) * sy)))
                    x = int(max(0, round(r.get("left") or 0)))
                    y = int(max(0, round(r.get("top") or 0)))

                    # clampa ao preview
                    w = min(w, w_prev - x)
                    h = min(h, h_prev - y)

                    st.session_state["crop_canvas_json"] = data
                    st.session_state["crop_coords_px_preview"] = {"left": x, "top": y, "width": w, "height": h}

                    bbox_rel = {
                        "x0": x / w_prev,
                        "y0": y / h_prev,
                        "x1": (x + w) / w_prev,
                        "y1": (y + h) / h_prev,
                    }
                    st.session_state["bbox_rel"] = bbox_rel

                    st.success(
                        f"📐 Coordenadas: "
                        f"x0={bbox_rel['x0']:.4f}, y0={bbox_rel['y0']:.4f}, "
                        f"x1={bbox_rel['x1']:.4f}, y1={bbox_rel['y1']:.4f}"
                    )

                    # salva recorte 400 DPI imediatamente
                    pdf_path = None
                    for k in ("current_pdf_path", "single_pdf_path", "pdf_path"):
                        v = st.session_state.get(k)
                        if v:
                            pdf_path = v
                            break
                    page_idx = st.session_state.get("page_idx", 0)
                    if pdf_path:
                        out_path = _save_crop_400dpi(pdf_path, page_idx, bbox_rel)
                        st.session_state["last_crop_saved_path"] = str(out_path)
                        st.toast(f"💾 Crop salvo: {out_path.name}", icon="💾")
                    else:
                        st.warning("PDF não disponível para salvar o recorte agora.")

    with c2:
        if st.button("↺ Limpar retângulo", key="btn_clear_rect"):
            st.session_state["crop_canvas_json"] = None
            st.session_state["crop_coords_px_preview"] = None
            st.session_state["bbox_rel"] = None
            st.session_state["last_crop_saved_path"] = None

    with c3:
        if st.button("❌ Fechar editor", key="btn_close_editor"):
            st.session_state["crop_step"] = "idle"
            st.rerun()



    st.session_state["prev_canvas_w"] = w_prev
    return w_prev, h_prev, bg_img

# Garantir que os diretórios necessários existam
ensure_dirs()

# --- helpers para resolver fontes e converter em PIL ---

def _to_pil(img_like):
    """Converte bytes / UploadedFile / PIL.Image em PIL.Image (RGB)."""
    if img_like is None:
        return None
    if isinstance(img_like, Image.Image):
        return img_like.convert("RGB")
    # UploadedFile do Streamlit expõe .read() e .getvalue()
    if hasattr(img_like, "read") and not isinstance(img_like, (bytes, bytearray)):
        try:
            data = img_like.getvalue() if hasattr(img_like, "getvalue") else img_like.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return None
    if isinstance(img_like, (bytes, bytearray)):
        return Image.open(io.BytesIO(img_like)).convert("RGB")
    return None

def _resolve_pdf_ref_and_page():
    """Tenta achar um PDF (caminho ou UploadedFile) + page_idx em várias chaves comuns."""
    page_idx = st.session_state.get("page_idx", 0)
    # caminhos (strings/Path)
    for k in ("current_pdf_path", "single_pdf_path", "pdf_path"):
        v = st.session_state.get(k)
        if v:
            return v, page_idx
    # UploadedFile ou file-like
    for k in ("uploaded_file", "pdf_file", "single_uploaded_file"):
        v = st.session_state.get(k)
        if v is not None:
            return v, page_idx
    return None, page_idx

def ensure_preview_and_hd():
    """
    Garante st.session_state['img_prev'] e ['img_hd'].
    1) Se 'current_page_image' existir, usa como preview direto.
    2) Se houver referência ao PDF, renderiza (HD + preview).
    3) Se só houver preview, duplica como HD (fallback).
    Retorna (img_prev, img_hd).
    """
    img_prev = st.session_state.get("img_prev")
    img_hd   = st.session_state.get("img_hd")

    # 1) tente usar a imagem já renderizada pela UI
    if img_prev is None:
        cand = st.session_state.get("current_page_image")
        cand = _to_pil(cand)
        if cand is not None:
            img_prev = cand
            st.session_state["img_prev"] = img_prev

    # 2) se não há HD, tente renderizar a partir do PDF
    if img_hd is None:
        pdf_ref, page_idx = _resolve_pdf_ref_and_page()
        if pdf_ref is not None:
            try:
                hd, pv = render_page_pair(pdf_ref, page_idx, dpi_hd=PROCESS_DPI)
                img_hd = hd
                st.session_state["img_hd"] = img_hd
                if img_prev is None:
                    img_prev = pv
                    st.session_state["img_prev"] = img_prev
            except Exception:
                # segue para fallback
                pass

    # 3) fallback final: se ainda não houver HD, clone o preview
    if img_hd is None and img_prev is not None:
        st.session_state["img_hd"] = img_prev.copy()
        img_hd = st.session_state["img_hd"]

    return img_prev, img_hd

# Inicialização do session_state
default_session_vars = {
    "template_name": "",
    "ignore_preset": False,
    "processing_result": None,
    "bbox": None,
    "cropping": False,
    "show_cropper": False,
    "editing_preset": False,
    "pdf_name": "",
    "page_idx": 0,
    "crop_pil": None,
    "selected_preset_id": None,
    "results_rendered": False,
    "output_paths": {},
    "bbox_rel": None,
    "creating_new_preset": False,
    "crop_confirmed": False,
    "crop_coords_px_preview": None,
    # Novos estados para drawable-canvas
    "crop_mode": False,
    "crop_canvas_json": None,
    "img_hd": None,
    "img_prev": None,
    "page_idx_changed": False,
    # Estados do fluxo de crop
    "crop_step": "idle",  # idle | edit | confirm
    "crop_preview_width": 1100,
    "prev_canvas_w": None,
    # Buffer da imagem de prévia congelada (mostrada na etapa 'confirm')
    "crop_preview_png": None,
    "crop_preview_w_h": None,  # (w_prev, h_prev) usados no preview
    # nonce para forçar rerun manual do canvas (sem live updates)
    "canvas_refresh_nonce": 0,
    "canvas_last_json": None,  # último json do canvas
    "capture_pending": False,  # flag de captura em 2 fases
    "last_crop_saved_path": None,  # path do jpg salvo
}

for key, default in default_session_vars.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Inicializar componentes
@st.cache_resource
def init_components():
    """Inicializa os componentes principais"""
    try:
        gemini_client = GeminiClient()
        pdf_utils = PDFUtils()
        ui_state = UIState()
        return gemini_client, pdf_utils, ui_state
    except Exception as e:
        st.error(f"Erro ao inicializar componentes: {e}")
        return None, None, None

gemini_client, pdf_utils, ui_state = init_components()

if not all([gemini_client, pdf_utils, ui_state]):
    st.stop()

# Validação de credenciais da API Gemini
def validate_credentials():
    """Valida se as credenciais da API Gemini estão configuradas e são válidas"""
    try:
        # Verificar se a API key existe
        if not gemini_client.api_key:
            st.error("❌ **Erro:** A chave da API Gemini não foi encontrada.")
            st.markdown("""
            **Como resolver:**
            1. Copie o arquivo `config\\env_template.txt` para `config\\.env`
            2. Edite o arquivo `config\\.env` e adicione sua chave:
               ```
               GEMINI_API_KEY=sua_chave_aqui
               ```
            3. Reinicie a aplicação
            """)
            st.stop()
        
        # Validar se a chave é válida
        if not validate_gemini_key(gemini_client.api_key):
            st.error("❌ **Erro:** A chave da API Gemini é inválida ou não foi possível autenticar.")
            st.markdown("""
            **Possíveis causas:**
            - A chave da API está incorreta
            - A API não está ativada no Google Cloud Console
            - A quota da API foi excedida
            - Problemas de conectividade
            
            **Como resolver:**
            1. Verifique se a chave está correta no arquivo `config\\.env`
            2. Confirme se a API Gemini está ativada no Google Cloud Console
            3. Verifique sua quota de API
            4. Teste a conectividade com a internet
            """)
            st.stop()
        
        return True
        
    except Exception as e:
        st.error(f"❌ **Erro:** Erro inesperado na validação de credenciais: {str(e)}")
        st.stop()

# Executar validação de credenciais
validate_credentials()

# Título e descrição
st.title("📊 Takeoff AI Multi v2")
st.markdown("""
**Extração inteligente de tabelas de PDFs usando IA (Gemini) com sistema de presets**

Este app permite:
1. 📄 **Upload de PDF** e seleção de página
2. 🎯 **Delimitar área de corte** com cropper interativo
3. 💾 **Salvar presets** para reutilização automática
4. 🤖 **Processar no Gemini** e extrair dados estruturados
5. 📁 **Exportar** em múltiplos formatos (JSON, JSONL, CSV)
""")

# Sidebar para configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Status da API Gemini
    st.success("✅ API Gemini configurada e válida")
    st.info("A chave da API foi validada com sucesso!")
    
    # Template name
    template_name = st.text_input(
        "Nome do Template (opcional)",
        value=ui_state.get_template_name(),
        help="Nome para identificar este tipo de documento (ex: 'Modelo Vale v3')",
        key="input_template_name"
    )
    ui_state.set_template_name(template_name)
    
    # Seção de presets
    st.header("💾 Presets")
    from app.presets import load_presets
    presets = load_presets()
    
    if presets:
        st.write(f"**{len(presets)} presets salvos:**")
        for preset in presets:
            scope_icon = {"global": "🌍", "template": "📋", "document": "📄"}.get(preset["scope"], "❓")
            st.write(f"{scope_icon} {preset['name']} ({preset['scope']})")
    else:
        st.info("Nenhum preset salvo ainda")

# Upload de PDF
st.header("📄 Upload do PDF")

# Upload individual
uploaded_file = st.file_uploader(
    "Selecione um arquivo PDF",
    type=['pdf'],
    help="Arraste um arquivo PDF ou clique para selecionar"
)

# Fluxo de processamento individual
if uploaded_file is not None:
    # Salvar arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        pdf_path = tmp_file.name
    
    # Salvar nome do arquivo para uso posterior
    st.session_state.pdf_name = uploaded_file.name
    st.session_state.current_pdf_path = pdf_path
    
    # Obter informações do PDF
    pdf_info = pdf_utils.get_pdf_info(pdf_path)
    
    if "error" in pdf_info:
        st.error(f"Erro ao processar PDF: {pdf_info['error']}")
    else:
        # Atualizar estado
        ui_state.set_pdf_uploaded(pdf_path, pdf_info)
        
        # Exibir informações do PDF
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Páginas", pdf_info["pages"])
        with col2:
            st.metric("Largura", f"{pdf_info['width']:.0f}px")
        with col3:
            st.metric("Altura", f"{pdf_info['height']:.0f}px")
        with col4:
            st.metric("Tamanho", f"{pdf_info['file_size'] / 1024:.1f}KB")
        
        # Seleção de página
        st.subheader("📖 Seleção de Página")
        current_page = ui_state.get_current_page()
        page_num = st.selectbox(
            "Página (0-index)",
            range(pdf_info["pages"]),
            index=current_page,
            format_func=lambda x: f"Página {x + 1}",
            key="select_page_number"
        )
        ui_state.set_current_page(page_num)
        st.session_state.page_idx = page_num
        
        # Carregar imagem da página
        page_image = pdf_utils.page_to_image(pdf_path, page_num)
        if page_image:
            ui_state.set_page_image(page_image)
            
            # Exibir miniatura
            st.subheader("🖼️ Miniatura da Página")
            
            # Seleção de Preset ou Novo Preset
            st.subheader("🎯 Seleção de Preset")
            
            # Listar presets ativos
            active_presets = list_active_presets()
            options = ["Nenhum", "➕ Novo Preset"] + [f"({p['scope']}) {p['name']}" for p in active_presets]
            
            # Determinar índice selecionado
            selected_idx = 0  # "Nenhum" por padrão
            if st.session_state.get("creating_new_preset"):
                selected_idx = 1  # "Novo Preset"
            elif st.session_state.selected_preset_id:
                for i, preset in enumerate(active_presets):
                    if preset["id"] == st.session_state.selected_preset_id:
                        selected_idx = i + 2  # +2 porque "Nenhum" e "Novo Preset" vêm primeiro
                        break
            
            # Selectbox para escolher preset
            preset_choice = st.selectbox(
                "Escolher preset:",
                options,
                index=selected_idx,
                key="select_manual_preset"
            )
            
            # Controlar estado baseado na seleção
            if preset_choice == "➕ Novo Preset":
                st.session_state.creating_new_preset = True
                st.session_state.selected_preset_id = None
                st.session_state.bbox_rel = None
                ui_state.set_current_preset(None)
                ui_state.set_crop_coords(None)
            elif preset_choice != "Nenhum" and not preset_choice.startswith("➕"):
                # Aplicar preset existente
                st.session_state.creating_new_preset = False
                preset_idx = options.index(preset_choice) - 2  # -2 porque "Nenhum" e "Novo Preset" vêm primeiro
                selected_preset = active_presets[preset_idx]
                
                st.session_state.selected_preset_id = selected_preset["id"]
                ui_state.set_current_preset(selected_preset)
                
                # Aplicar preset à página atual
                bbox_rel = selected_preset["bbox_rel"]
                st.session_state.bbox_rel = bbox_rel
                ui_state.set_crop_coords(bbox_rel)
                
                # Exibir informações do preset
                st.success(f"✅ Preset aplicado: **{selected_preset['name']}** ({selected_preset['scope']})")
                bbox_rel = st.session_state.get("bbox_rel")
                if _bbox_ready(bbox_rel):
                    st.info(
                        f"📐 Coordenadas: "
                        f"x0={bbox_rel['x0']:.3f}, y0={bbox_rel['y0']:.3f}, "
                        f"x1={bbox_rel['x1']:.3f}, y1={bbox_rel['y1']:.3f}"
                    )
                else:
                    st.caption("Defina o retângulo e clique em **Usar este recorte** para gerar as coordenadas.")
                
                # Mostrar preview do preset aplicado
                if st.session_state.get("img_prev"):
                    preview_with_preset = draw_overlay(st.session_state["img_prev"], bbox_rel)
                    image_fluid(preview_with_preset, caption=f"Preview do preset: {selected_preset['name']}")
            else:
                # Nenhum selecionado
                st.session_state.creating_new_preset = False
                st.session_state.selected_preset_id = None
                st.session_state.bbox_rel = None
                ui_state.set_current_preset(None)
                ui_state.set_crop_coords(None)
            
            # Verificar se há preset aplicável automaticamente (apenas se nenhum foi selecionado manualmente)
            if not st.session_state.selected_preset_id and not ui_state.get_ignore_preset():
                # Por enquanto, não implementamos a lógica de preset automático
                # Pode ser implementada posteriormente se necessário
                pass
            
            # Exibir imagem
            image_fluid(page_image, caption=f"Página {page_num + 1}")
            
            # Seção de Cropping (apenas se "Novo Preset" estiver selecionado)
            if st.session_state.get("creating_new_preset", False):
                st.markdown("### ✂️ Delimitar Área de Corte")

                # Garante preview/HD, independente de qual chave foi setada na página de upload
                img_prev, img_hd = ensure_preview_and_hd()

                # ====== IDLE => botão para entrar no editor ======
                if st.session_state["crop_step"] == "idle":
                    if st.button("✏️ Entrar no modo de corte", key="btn_enter_crop"):
                        st.session_state["crop_step"] = "edit"
                        st.rerun()

                # ====== EDITAR: mostra slider + canvas ======
                elif st.session_state["crop_step"] == "edit":
                    if img_prev is None:
                        st.error("Imagem de preview não disponível. Carregue um PDF e selecione a página.")
                    else:
                        c_zoom, c_fit, c_reset = st.columns([3,1,1])
                        with c_zoom:
                            st.session_state["crop_preview_width"] = st.slider(
                                "Largura do preview (px)",
                                min_value=600, max_value=1600, step=50,
                                value=int(st.session_state["crop_preview_width"]),
                                help="Ajuste para ver toda a prancha ou aproximar."
                            )
                        with c_fit:
                            if st.button("🔍 Ajustar"):
                                st.session_state["crop_preview_width"] = min(1200, img_prev.width)
                                st.rerun()
                        with c_reset:
                            if st.button("↺ 100%"):
                                st.session_state["crop_preview_width"] = min(img_prev.width, 1600)
                                st.rerun()

                        target_w = int(st.session_state["crop_preview_width"])
                        prev_w = st.session_state.get("prev_canvas_w")
                        width_changed = prev_w is not None and prev_w != target_w
                        if width_changed:
                            # Limpa somente no modo edit ao trocar largura
                            st.session_state["crop_canvas_json"] = None
                            st.session_state["crop_coords_px_preview"] = None

                        bg_img = _prepare_canvas_bg(img_prev, target_w=target_w)
                        w_prev, h_prev = bg_img.size

                        from app.ui_compat import pil_to_data_url, image_fluid
                        from streamlit_drawable_canvas import st_canvas

                        data_url = pil_to_data_url(bg_img, fmt="PNG")
                        prev_json = st.session_state.get("crop_canvas_json") or {}
                        prev_objs = [o for o in prev_json.get("objects", []) if o.get("type") != "image"]
                        if width_changed:
                            prev_objs = []

                        bg_obj = {
                            "type": "image",
                            "left": 0, "top": 0, "width": w_prev, "height": h_prev,
                            "scaleX": 1, "scaleY": 1, "angle": 0,
                            "flipX": False, "flipY": False, "opacity": 1,
                            "selectable": False, "evented": False, "hasControls": False, "hasBorders": False,
                            "src": data_url,
                        }
                        initial_drawing = {"objects": [bg_obj] + prev_objs}

                        st.caption("Desenhe um retângulo sobre a imagem para definir a área de recorte.")
                        canvas_key = f"canvas_crop_p{st.session_state.get('page_idx',0)}_w{w_prev}"

                        canvas = st_canvas(
                            fill_color="rgba(0,0,0,0)",
                            stroke_width=3,
                            stroke_color="#ff4b4b",
                            background_color="#ffffff",
                            height=h_prev,
                            width=w_prev,
                            drawing_mode="rect",
                            initial_drawing=initial_drawing,
                            key=canvas_key,
                            update_streamlit=False,   # <<< DESLIGA live update (fim do flicker)
                        )

                        # Botão de captura manual (sem live update)
                        st.caption("Desenhe um retângulo e depois clique em **📌 Capturar seleção**.")
                        
                        c_capture, c_clear, c_close = st.columns(3)
                        with c_capture:
                            if st.button("📌 Capturar seleção", key="btn_capture_rect"):
                                # força um rerun controlado
                                st.session_state["canvas_refresh_nonce"] += 1
                                st.rerun()
                        with c_clear:
                            if st.button("↺ Limpar retângulo", key="btn_clear_rect"):
                                st.session_state["crop_canvas_json"] = None
                                st.session_state["crop_coords_px_preview"] = None
                                st.rerun()
                        with c_close:
                            if st.button("❌ Fechar editor", key="btn_close_editor"):
                                st.session_state["crop_step"] = "idle"
                                st.rerun()

                        # Após o rerun (disparado por "Capturar"), o canvas.json_data já vem atualizado
                        if canvas.json_data is not None:
                            st.session_state["crop_canvas_json"] = canvas.json_data
                            rects = [o for o in canvas.json_data.get("objects", []) if o.get("type") == "rect"]
                            if rects:
                                r = rects[-1]
                                st.session_state["crop_coords_px_preview"] = {
                                    "left": int(r.get("left", 0)),
                                    "top": int(r.get("top", 0)),
                                    "width": int(r.get("width", 0)),
                                    "height": int(r.get("height", 0)),
                                }

                        # Exibe coordenadas se houver
                        bbox_rel = st.session_state.get("bbox_rel")
                        if _bbox_ready(bbox_rel):
                            st.info(
                                f"📐 Coordenadas: "
                                f"x0={bbox_rel['x0']:.3f}, y0={bbox_rel['y0']:.3f}, "
                                f"x1={bbox_rel['x1']:.3f}, y1={bbox_rel['y1']:.3f}"
                            )
                            
                        # Exibe badge do crop salvo se houver
                        crop_path = st.session_state.get("last_crop_saved_path")
                        if crop_path:
                            st.success(f"📂 Crop salvo em: {Path(crop_path).name}")

                        # "Usar este recorte" só avança se bbox_rel existir
                        bbox_rel = st.session_state.get("bbox_rel")
                        disabled_use = not (isinstance(bbox_rel, dict) and all(k in bbox_rel for k in ("x0", "y0", "x1", "y1")))
                        if st.button("✅ Usar este recorte", key="btn_use_crop", disabled=disabled_use):
                            st.session_state["crop_step"] = "confirm"
                            st.rerun()

                        # feedback visual
                        if bbox_rel:
                            st.info(
                                f"📐 Atual: x0={bbox_rel['x0']:.4f}, y0={bbox_rel['y0']:.4f}, "
                                f"x1={bbox_rel['x1']:.4f}, y1={bbox_rel['y1']:.4f}"
                            )
                        if st.session_state.get("last_crop_saved_path"):
                            st.success(f"📂 Ultimo crop salvo: {Path(st.session_state['last_crop_saved_path']).name}")

                        st.session_state["prev_canvas_w"] = w_prev

                # ====== CONFIRMAR: sem canvas; mostra prévia congelada + salvar preset ======
                elif st.session_state["crop_step"] == "confirm":
                    st.success("Recorte definido. Confira a prévia abaixo e salve como preset.")
                    png_bytes = st.session_state.get("crop_preview_png")
                    if png_bytes:
                        image_fluid(png_bytes, caption="Prévia do recorte")
                    bbox_rel = st.session_state.get("bbox_rel")
                    if _bbox_ready(bbox_rel):
                        st.caption(
                            f"Preset ativo (rel): "
                            f"x0={bbox_rel['x0']:.4f}, y0={bbox_rel['y0']:.4f}, "
                            f"x1={bbox_rel['x1']:.4f}, y1={bbox_rel['y1']:.4f}"
                        )
                    else:
                        st.caption("Defina o retângulo e clique em **Usar este recorte** para gerar as coordenadas.")

                    c1, c2 = st.columns(2)
                    with c1:
                        # Seção para salvar o preset
                        st.subheader("💾 Salvar Novo Preset")
                        
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            preset_name = st.text_input(
                                "Nome do Preset",
                                placeholder="Ex: Tabela Principal - Modelo Vale v3",
                                key="new_preset_name"
                            )
                        
                        with col2:
                            preset_scope = st.selectbox(
                                "Escopo",
                                ["global", "template", "document"],
                                format_func=lambda x: {
                                    "global": "🌍 Global",
                                    "template": "📋 Por Modelo", 
                                    "document": "📄 Somente neste PDF"
                                }[x],
                                key="new_preset_scope"
                            )
                        
                        if st.button("💾 Salvar Preset", key="btn_save_preset", type="primary"):
                            bbox_rel = st.session_state.get("bbox_rel")
                            if not _bbox_ready(bbox_rel):
                                st.error("Recorte ainda não definido. Clique em **Usar este recorte** primeiro.")
                            elif not preset_name.strip():
                                st.error("❌ Digite um nome para o preset")
                            else:
                                # Criar novo preset
                                import uuid
                                new_preset = {
                                    "id": str(uuid.uuid4()),
                                    "name": preset_name.strip(),
                                    "scope": preset_scope,
                                    "bbox_rel": bbox_rel,
                                    "template_name": st.session_state.get("template_name", ""),
                                    "pdf_name": st.session_state.get("pdf_name", "") if preset_scope == "document" else "",
                                    "active": True,
                                    "created_at": pd.Timestamp.now().isoformat()
                                }
                                
                                # Salvar preset
                                upsert_preset(new_preset)
                                
                                # Aplicar o preset recém-criado
                                st.session_state.selected_preset_id = new_preset["id"]
                                st.session_state.creating_new_preset = False
                                st.session_state.crop_step = "idle"
                                
                                st.success(f"✅ Preset **{preset_name}** salvo com sucesso!")
                                st.balloons()
                                st.rerun()
                    
                    with c2:
                        if st.button("✏️ Voltar e editar", key="btn_back_to_edit"):
                            st.session_state["crop_step"] = "edit"
                            st.rerun()
            
            # Ações principais (sempre visíveis)
            st.subheader("🎯 Ações")
            
            colA, colB, colC = st.columns([1, 1, 1])
            
            with colA:
                if st.button("🔍 Detectar Tabelas", help="Detectar automaticamente tabelas na página"):
                    detected_tables = pdf_utils.detect_tables(pdf_path, page_num)
                    ui_state.set_detected_tables(detected_tables)
                    
                    if detected_tables:
                        st.success(f"Detectadas {len(detected_tables)} tabelas")
                        for i, table in enumerate(detected_tables):
                            st.write(f"Tabela {i+1}: {table['rows']} linhas")
                    else:
                        st.info("Nenhuma tabela detectada automaticamente")
            
            with colB:
                # Botão desabilitado se não houver área definida
                bbox_rel = st.session_state.get("bbox_rel")
                if not _bbox_ready(bbox_rel):
                    st.button("✂️ Defina área primeiro", disabled=True, help="Selecione um preset ou crie um novo preset primeiro")
                else:
                    st.success("✅ Área definida")
            
            with colC:
                if st.button("🤖 Processar no Gemini", help="Enviar área selecionada para extração"):
                    # Garantir que temos bbox_rel e img_hd
                    bbox_rel = st.session_state.get("bbox_rel")
                    if not _bbox_ready(bbox_rel):
                        st.error("❌ Defina uma área de corte primeiro (selecione um preset ou crie um novo)")
                        st.stop()
                    
                    # Garantir que temos as imagens necessárias
                    img_prev, img_hd = ensure_preview_and_hd()
                    if img_hd is None:
                        st.error("❌ Não foi possível obter a imagem em alta resolução. Recarregue o PDF.")
                        st.stop()
                    
                    # Validação de sanidade
                    if not (0 <= bbox_rel["x0"] < bbox_rel["x1"] <= 1 and 0 <= bbox_rel["y0"] < bbox_rel["y1"] <= 1):
                        st.error("❌ BBox inválida. Ajuste o retângulo de recorte.")
                        st.stop()
                    
                    area = (bbox_rel["x1"] - bbox_rel["x0"]) * (bbox_rel["y1"] - bbox_rel["y0"])
                    if area < 0.02:
                        st.warning("⚠️ Área de recorte muito pequena. Ajuste o retângulo.")
                    
                    with st.spinner("Processando no Gemini..."):
                        # Salvar crop usando a imagem HD
                        pdf_name = getattr(uploaded_file, "name", "documento.pdf")
                        base_name = Path(pdf_name).stem
                        crop_path = save_crop_image(
                            img_hd,
                            bbox_rel,
                            base_name,
                            st.session_state.get("page_idx", 0)
                        )
                        
                        from app.pipeline import process_pdf_once
                        
                        result = process_pdf_once(
                            pdf_file=uploaded_file,
                            page_index=st.session_state.get("page_idx", 0),
                            bbox_rel=bbox_rel,
                            api_key=gemini_client.api_key,
                            template_name=st.session_state.get("template_name"),
                            save_artifacts=True,
                        )
                        
                        if result["is_empty"]:
                            st.warning("⚠️ Nenhum item encontrado: a lista de materiais está vazia neste PDF/crop.")
                            st.session_state.results_rendered = False
                            st.session_state.output_paths = {}
                        else:
                            # Salvar outputs apenas se houver dados
                            output_files = ui_state.save_outputs(
                                result["rows"], result["artifacts"]["raw_text"]
                            )
                            # Salvar paths na sessão para downloads
                            st.session_state.output_paths = output_files
                            st.session_state.results_rendered = True
                            
                            # Adicionar ao agregador para lote futuro
                            from app.aggregate import add_rows
                            add_rows(st, result["rows"], source_pdf=result["pdf_name"], page_idx=result["page_index"], table_name=result["artifacts"]["table_name"])
                            
                            st.toast(f"Crop salvo em: {crop_path}", icon="✅")
            
            # Divisor para separar ações dos resultados
            st.divider()
            
            # Seções dedicadas para resultados e downloads
            results_section = st.container()     # único lugar para "📊 Dados Extraídos"
            downloads_section = st.container()   # único lugar para "📁 Downloads"
            
            # Status da área selecionada
            if st.session_state.get("bbox_rel"):
                br = st.session_state["bbox_rel"]
                st.success(f"✅ **Área definida:** x0={br['x0']:.3f}, y0={br['y0']:.3f}, x1={br['x1']:.3f}, y1={br['y1']:.3f}")
            else:
                st.info("ℹ️ Selecione um preset existente ou crie um novo preset para definir a área de corte")
        
        else:
            st.error("❌ Erro ao carregar imagem da página")
            
        # Renderizar resultados apenas no results_section
        if st.session_state.get("results_rendered") and st.session_state.get("output_paths"):
            with results_section:
                st.subheader("📊 Dados Extraídos")
                # Os dados já foram processados pelo pipeline, apenas mostrar o resultado
                # O DataFrame será renderizado quando o usuário clicar em "Processar no Gemini"
                st.info("✅ Dados processados com sucesso! Use os botões de download abaixo.")
        
        # Renderizar downloads apenas no downloads_section (apenas se houver dados)
            if st.session_state.get("output_paths") and st.session_state.get("processing_result"):
                with downloads_section:
                    st.subheader("📁 Downloads")
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        if "raw_json" in st.session_state.output_paths:
                            with open(st.session_state.output_paths["raw_json"], 'r', encoding='utf-8') as f:
                                st.download_button(
                                    label="⬇️ JSON Bruto",
                                    data=f.read(),
                                    file_name=os.path.basename(st.session_state.output_paths["raw_json"]),
                                    mime="application/json",
                                    key="download_raw_json"
                                )
                    
                    with col2:
                        if "jsonl" in st.session_state.output_paths:
                            with open(st.session_state.output_paths["jsonl"], 'r', encoding='utf-8') as f:
                                st.download_button(
                                    label="⬇️ JSONL",
                                    data=f.read(),
                                    file_name=os.path.basename(st.session_state.output_paths["jsonl"]),
                                    mime="text/plain",
                                    key="download_jsonl"
                                )
                    
                    with col3:
                        if "csv" in st.session_state.output_paths:
                            with open(st.session_state.output_paths["csv"], 'r', encoding='utf-8') as f:
                                st.download_button(
                                    label="⬇️ CSV",
                                    data=f.read(),
                                    file_name=os.path.basename(st.session_state.output_paths["csv"]),
                                    mime="text/csv",
                                    key="download_csv"
                                )

# Seção de processamento em lote
st.divider()
batch_section = st.container()
agg_section = st.container()

with batch_section:
    st.subheader("🧩 Processamento em Lote")
    # Seleção de múltiplos arquivos
    multi_files = st.file_uploader(
        "Selecione vários PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="uploader_lote"
    )

    # Seletor de preset para o lote
    from app.presets import list_active_presets

    st.markdown("#### 🎛️ Preset do Lote")

    _active = list_active_presets()
    preset_labels = ["(usar crop atual)"] + [f'{p.get("name","(sem nome)")} ({p.get("scope","global")})' for p in _active]

    # Estado padrão
    st.session_state.setdefault("bbox_rel", None)
    st.session_state.setdefault("selected_preset_id", None)

    # Pré-seleção: se já houver preset escolhido
    idx_default = 0
    if st.session_state.get("selected_preset_id"):
        try:
            ids = [p.get("id") for p in _active]
            idx_default = 1 + ids.index(st.session_state["selected_preset_id"])
        except ValueError:
            idx_default = 0

    sel = st.selectbox(
        "Escolha o preset para o processamento em lote",
        options=preset_labels, index=idx_default, key="batch_preset_select"
    )

    if sel != "(usar crop atual)":
        chosen = _active[preset_labels.index(sel) - 1]
        st.session_state["selected_preset_id"] = chosen.get("id")
        st.session_state["bbox_rel"] = chosen.get("bbox_rel")
        # (Opcional) badge
        st.caption(f"Preset ativo: **{chosen.get('name')}** — bbox_rel: "
                   f"{chosen.get('bbox_rel',{})}")
    else:
        if not st.session_state.get("bbox_rel"):
            st.info("Usando o crop atual: delimite o crop acima caso não queira aplicar um preset.")

    # Botões de ação
    colb1, colb2, colb3 = st.columns([1,1,1])
    
    with colb1:
        # Mostrar "Resetar relatório do lote" apenas quando existir relatório
        from app.aggregate import to_df_report, reset as agg_reset
        if not to_df_report(st).empty:
            st.button("🧹 Limpar relatório do lote", key="btn_reset_lote", on_click=lambda: agg_reset(st))
    
    with colb2:
        _can_run_batch = bool(multi_files) and bool(st.session_state.get("bbox_rel"))

        def run_batch_cascata(files, *, bbox_rel, api_key):
            if not files:
                st.warning("Selecione ao menos um PDF.")
                return

            status = st.status("Processando lote…", expanded=True)
            pbar = st.progress(0.0)
            rep_rows = []   # relatório por arquivo
            dfs = []        # dataframes para concatenar

            total = len(files)
            for i, f in enumerate(files):
                fname = getattr(f, "name", f"pdf_{i+1}.pdf")
                try:
                    from app.pipeline import process_pdf_once
                    r = process_pdf_once(
                        pdf_file=f, page_index=0, bbox_rel=bbox_rel,
                        api_key=api_key, template_name=st.session_state.get("template_name"),
                        save_artifacts=True,
                    )
                    if r["is_empty"]:
                        rep_rows.append({"arquivo": fname, "status": "vazio", "linhas": 0, "erro": ""})
                        st.toast(f"{fname}: tabela vazia.", icon="⚠️")
                    else:
                        dfs.append(r["df"].assign(_source_pdf=fname, _page_idx=r["page_index"], _table_name=r["artifacts"]["table_name"]))
                        rep_rows.append({"arquivo": fname, "status": "ok", "linhas": len(r["df"]), "erro": ""})
                        st.toast(f"{fname}: {len(r['df'])} linha(s).", icon="✅")
                except Exception as e:
                    rep_rows.append({"arquivo": fname, "status": "erro", "linhas": 0, "erro": str(e)})
                    st.toast(f"{fname}: erro — {e}", icon="❌")

                pbar.progress((i+1)/total)

            # Tabela de relatório
            rep_df = pd.DataFrame(rep_rows)
            st.subheader("📒 Relatório do Lote (ao vivo)")
            dataframe_fluid(rep_df, height=min(400, 120 + 28*len(rep_df)))

            # CSV único agregado
            if dfs:
                big = pd.concat(dfs, ignore_index=True)
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                out_csv = OUT_DIR / "lote_all_extracted.csv"  # se preferir, coloque timestamp
                big.to_csv(out_csv, index=False, encoding="utf-8-sig")

                st.success(f"✅ Lote concluído. Total de linhas: {len(big)}")
                st.download_button(
                    "⬇️ CSV único (lote)", data=open(out_csv, "rb").read(),
                    file_name=out_csv.name, mime="text/csv", key="dl_lote_csv",
                )
            else:
                st.warning("Processo concluído, mas nenhum PDF continha itens na lista de materiais.")

        st.button(
            "🧩 Processar Lote (CSV único)",
            key="btn_process_batch",
            disabled=not _can_run_batch,
            on_click=lambda: run_batch_cascata(
                multi_files, bbox_rel=st.session_state["bbox_rel"], api_key=gemini_client.api_key
            )
        )

    # Mensagens de status
    if not multi_files:
        st.warning("Adicione PDFs para o lote.")
    elif not st.session_state.get("bbox_rel"):
        st.error("Defina um preset (acima) ou delimite o crop para habilitar o lote.")

with agg_section:
    from app.aggregate import to_df_rows, to_df_report
    df_rows = to_df_rows(st)
    df_rep = to_df_report(st)

    if not df_rep.empty:
        st.subheader("📒 Relatório do Lote (ao vivo)")
        dataframe_fluid(df_rep, height=300)

    if not df_rows.empty:
        st.subheader("📊 Dados Agregados (todas as linhas)")
        dataframe_fluid(df_rows, height=min(800, 140 + 28*len(df_rows)))

# Downloads do lote
if not df_rows.empty or not df_rep.empty:
    st.subheader("📁 Downloads do Lote")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if not df_rows.empty:
            from app.aggregate import save_csv_rows
            path_rows = save_csv_rows(st, OUT_DIR)
            st.download_button("⬇️ CSV único (lote)", data=open(path_rows, "rb").read(),
                               file_name=path_rows.name, mime="text/csv", key="dl_csv_lote")

    with col2:
        if not df_rep.empty:
            from app.aggregate import save_csv_report
            path_rep = save_csv_report(st, OUT_DIR)
            st.download_button("⬇️ Relatório do lote (CSV)", data=open(path_rep, "rb").read(),
                               file_name=path_rep.name, mime="text/csv", key="dl_rep_lote")

# Limpeza de arquivos temporários
def cleanup_temp_files():
    """Limpa arquivos temporários"""
    try:
        if ui_state.get_pdf_path() and os.path.exists(ui_state.get_pdf_path()):
            os.unlink(ui_state.get_pdf_path())
    except:
        pass

# Registrar função de limpeza
import atexit
atexit.register(cleanup_temp_files)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>Takeoff AI Multi v2 - MVP para extração inteligente de tabelas</p>
    <p>Desenvolvido com Streamlit e Google Gemini AI</p>
</div>
""", unsafe_allow_html=True)
