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

# Importar módulos locais (sem execução de código Streamlit)
import pandas as pd
from app.presets import list_active_presets, preset_label, get_preset_by_id, upsert_preset
from app.gemini_client import GeminiClient, validate_gemini_key, call_gemini_on_image
from app.pdf_utils import PDFUtils
from app.ui_state import UIState
from app.ui_compat import image_full_width
from app.image_utils import as_pil_image
from app.paths import ensure_dirs, OUT_DIR
from app.save_utils import save_crop_image
from app.result_utils import is_empty_extraction, extract_rows_from_model_payload, get_table_name
# aggregate será importado quando necessário (evita execução prematura de st.session_state)

# Garantir que os diretórios necessários existam
ensure_dirs()

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
            
            # Seleção manual de presets
            st.subheader("🎯 Seleção de Preset")
            
            # Listar presets ativos
            active_presets = list_active_presets()
            options = ["Nenhum"] + [f"({p['scope']}) {p['name']}" for p in active_presets]
            
            # Determinar índice selecionado
            selected_idx = 0  # "Nenhum" por padrão
            if st.session_state.selected_preset_id:
                for i, preset in enumerate(active_presets):
                    if preset["id"] == st.session_state.selected_preset_id:
                        selected_idx = i + 1  # +1 porque "Nenhum" é o primeiro
                        break
            
            # Selectbox para escolher preset
            preset_choice = st.selectbox(
                "Escolher preset:",
                options,
                index=selected_idx,
                key="select_manual_preset"
            )
            
            # Aplicar preset selecionado
            if preset_choice != "Nenhum":
                preset_idx = options.index(preset_choice) - 1  # -1 porque "Nenhum" não está na lista de presets
                selected_preset = active_presets[preset_idx]
                
                st.session_state.selected_preset_id = selected_preset["id"]
                ui_state.set_current_preset(selected_preset)
                
                # Aplicar preset à página atual
                bbox_rel = selected_preset["bbox_rel"]
                img_width, img_height = page_image.size
                bbox_abs = (
                    int(bbox_rel["x0"] * img_width),
                    int(bbox_rel["y0"] * img_height),
                    int(bbox_rel["x1"] * img_width),
                    int(bbox_rel["y1"] * img_height)
                )
                st.session_state.bbox = bbox_abs
                ui_state.set_crop_coords(bbox_rel)
                
                # Exibir informações do preset
                ui_state.display_preset_info(selected_preset)
            else:
                # Limpar preset selecionado
                st.session_state.selected_preset_id = None
                ui_state.set_current_preset(None)
                st.session_state.bbox = None
                ui_state.set_crop_coords(None)
            
            # Verificar se há preset aplicável automaticamente (apenas se nenhum foi selecionado manualmente)
            if not st.session_state.selected_preset_id and not ui_state.get_ignore_preset():
                # Por enquanto, não implementamos a lógica de preset automático
                # Pode ser implementada posteriormente se necessário
                pass
            
            # Exibir imagem
            image_full_width(page_image, caption=f"Página {page_num + 1}")
            
            # Ações principais
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
                if st.button("✂️ Delimitar Crop", help="Definir área de corte manualmente"):
                    st.session_state.show_cropper = True
            
            with colC:
                 if st.button("🤖 Processar no Gemini", help="Enviar área selecionada para extração"):
                     if not st.session_state.get("bbox_rel"):
                         st.error("❌ Defina uma área de corte primeiro (Delimitar Crop ou selecione um preset)")
                         st.stop()
                     
                     with st.spinner("Processando no Gemini..."):
                         from app.pipeline import process_pdf_once
                         
                         result = process_pdf_once(
                             pdf_file=uploaded_file,
                             page_index=st.session_state.get("page_idx", 0),
                             bbox_rel=st.session_state["bbox_rel"],
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
                             
                             st.toast(f"Crop salvo em: {result['artifacts']['crop_path']}", icon="✅")
            
            # Divisor para separar ações dos resultados
            st.divider()
            
            # Seções dedicadas para resultados e downloads
            results_section = st.container()     # único lugar para "📊 Dados Extraídos"
            downloads_section = st.container()   # único lugar para "📁 Downloads"
            
            # Cropper interativo
            if st.session_state.get('show_cropper', False):
                st.subheader("✂️ Delimitar Área de Corte")
                
                # Usar streamlit-cropper
                try:
                    from streamlit_cropper import st_cropper
                    
                    # Garantir que temos PIL.Image para o cropper
                    img_for_crop = as_pil_image(page_image)
                    
                    # Cropper
                    cropped_img = st_cropper(
                        img_for_crop,
                        realtime_update=True,
                        box_color='#FF0000',
                        aspect_ratio=None,
                        return_type="box"
                    )
                    
                    if cropped_img:
                        # Converter coordenadas para relativas
                        img_width, img_height = page_image.size
                        bbox_rel = {
                            "x0": cropped_img["left"] / img_width,
                            "y0": cropped_img["top"] / img_height,
                            "x1": (cropped_img["left"] + cropped_img["width"]) / img_width,
                            "y1": (cropped_img["top"] + cropped_img["height"]) / img_height
                        }
                        
                        ui_state.set_crop_coords(bbox_rel)
                        
                        # Salvar bbox absoluto para uso posterior
                        img_width, img_height = page_image.size
                        bbox_abs = {
                            "x0": int(bbox_rel["x0"] * img_width),
                            "y0": int(bbox_rel["y0"] * img_height),
                            "x1": int(bbox_rel["x1"] * img_width),
                            "y1": int(bbox_rel["y1"] * img_height)
                        }
                        st.session_state.bbox = (bbox_abs["x0"], bbox_abs["y0"], bbox_abs["x1"], bbox_abs["y1"])
                        
                        # Recortar e salvar imagem em memória
                        cropped_image = pdf_utils.crop_page_image(page_image, bbox_abs)
                        st.session_state.crop_pil = cropped_image
                        
                        # Mostrar coordenadas
                        st.write("**Coordenadas selecionadas:**")
                        st.json(bbox_rel)
                        
                        # Opções de salvamento
                        st.subheader("💾 Salvar Preset")
                        
                        preset_name = st.text_input("Nome do preset", value="Novo Preset", key="input_preset_name")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            scope = st.selectbox(
                                "Escopo",
                                ["global", "template", "document"],
                                format_func=lambda x: {
                                    "global": "Global (todos os PDFs)",
                                    "template": "Por Modelo",
                                    "document": "Somente neste PDF"
                                }[x],
                                key="select_preset_scope"
                            )
                        
                        with col2:
                            apply_all_pages = st.checkbox("Aplicar em todas as páginas", value=False, key="checkbox_apply_all_pages")
                        
                        if st.button("💾 Salvar Preset", key="btn_save_preset"):
                            # Usar bbox absoluto da sessão se disponível, senão converter do relativo
                            if st.session_state.bbox:
                                bbox_abs = st.session_state.bbox
                                img_width, img_height = page_image.size
                                bbox_rel = {
                                    "x0": round(bbox_abs[0] / img_width, 6),
                                    "y0": round(bbox_abs[1] / img_height, 6),
                                    "x1": round(bbox_abs[2] / img_width, 6),
                                    "y1": round(bbox_abs[3] / img_height, 6),
                                }
                            else:
                                # Fallback para bbox_rel já calculado
                                bbox_rel = bbox_rel
                            
                            import uuid
                            from datetime import datetime
                            
                            preset = {
                                "id": str(uuid.uuid4()),
                                "name": preset_name,
                                "scope": scope,
                                "template_id": ui_state.get_template_name() if scope == "template" else None,
                                "document_fingerprint": None,  # TODO: implementar se necessário
                                "bbox_rel": bbox_rel,
                                "page_filter": "all",
                                "padding_pct": 0.03,
                                "created_at": datetime.now().isoformat(),
                                "updated_at": datetime.now().isoformat(),
                                "use_count": 0,
                                "active": True,
                                "notes": f"Criado na página {page_num + 1}"
                            }
                            
                            upsert_preset(preset)
                            st.success(f"✅ Preset '{preset_name}' salvo com bbox_rel: {bbox_rel}")
                            st.rerun()
                        
                        if st.button("❌ Cancelar", key="btn_cancel_crop"):
                            st.session_state.show_cropper = False
                            st.rerun()
                
                except ImportError:
                    st.error("Biblioteca streamlit-cropper não encontrada. Instale com: pip install streamlit-cropper")
                except Exception as e:
                    st.error(f"Erro no cropper: {e}")
        
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
            if st.session_state.get("output_paths") and data:
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
            st.dataframe(rep_df, use_container_width=True, height=min(400, 120 + 28*len(rep_df)))

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
        st.dataframe(df_rep, use_container_width=True, height=300)

    if not df_rows.empty:
        st.subheader("📊 Dados Agregados (todas as linhas)")
        st.dataframe(df_rows, use_container_width=True, height=min(800, 140 + 28*len(df_rows)))

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
