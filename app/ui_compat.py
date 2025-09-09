"""
Utilitários de compatibilidade para diferentes versões do Streamlit
"""
import streamlit as st
from typing import Optional, Any
import base64
import io
import inspect
from PIL import Image

def image_fluid(img, caption=None, clamp=False):
    """
    Exibe imagem ocupando a largura do container, compatível com versões
    antigas (use_column_width) e novas (use_container_width) do Streamlit.
    """
    params = inspect.signature(st.image).parameters
    if "use_container_width" in params:
        return st.image(img, caption=caption, use_container_width=True, clamp=clamp)
    elif "use_column_width" in params:
        return st.image(img, caption=caption, use_column_width=True, clamp=clamp)
    # Fallback sem argumento de largura (caso a API mude no futuro)
    return st.image(img, caption=caption, clamp=clamp)

def dataframe_fluid(df, height=None):
    """
    Exibe DataFrame ocupando a largura do container, compatível com versões antigas e novas do Streamlit.
    Tenta a nova API (width='stretch'); se não existir, usa use_container_width=True.
    """
    try:
        return st.dataframe(df, use_container_width=True, height=height)
    except TypeError:
        return st.dataframe(df, use_column_width=True, height=height)

def patch_streamlit_image_to_url():
    """
    Injeta image_to_url no módulo streamlit.elements.image para compatibilidade
    com streamlit-drawable-canvas em versões recentes do Streamlit.
    Aceita a assinatura longa usada pelo pacote (inclui image_id).
    """
    try:
        import streamlit.elements.image as st_image
    except Exception:
        return

    if getattr(st_image, "image_to_url", None) is not None:
        return  # já existe, não faz nada

    def _ensure_pil(x):
        if isinstance(x, Image.Image):
            return x
        if hasattr(x, "getvalue"):  # UploadedFile
            return Image.open(io.BytesIO(x.getvalue()))
        if hasattr(x, "read"):      # file-like
            return Image.open(io.BytesIO(x.read()))
        if isinstance(x, (bytes, bytearray)):
            return Image.open(io.BytesIO(x))
        raise TypeError("Tipo de imagem não suportado para image_to_url")

    def _image_to_url(img,
                      width=None, clamp=False, channels="RGB",
                      output_format="PNG", image_id=None, *args, **kwargs):
        """
        Compatível com: image_to_url(img, width, clamp, channels, output_format, image_id)
        Retorna sempre um data URL válido.
        """
        pil = _ensure_pil(img)
        # canais
        try:
            if channels:
                pil = pil.convert(channels)
            else:
                pil = pil.convert("RGB")
        except Exception:
            pil = pil.convert("RGB")

        # resize se width for fornecido
        if isinstance(width, (int, float)) and width and width > 0 and pil.width != int(width):
            new_w = int(width)
            new_h = max(1, int(round(pil.height * (new_w / pil.width))))
            pil = pil.resize((new_w, new_h), Image.LANCZOS)

        fmt = (output_format or "PNG").upper()
        if fmt == "AUTO":
            fmt = "PNG"
        mime = "image/png" if fmt == "PNG" else f"image/{fmt.lower()}"

        buf = io.BytesIO()
        pil.save(buf, format=fmt)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    st_image.image_to_url = _image_to_url

def pil_to_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    """Converte PIL.Image em data URL (data:image/png;base64,...)"""
    fmt = (fmt or "PNG").upper()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/png" if fmt == "PNG" else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{b64}"
