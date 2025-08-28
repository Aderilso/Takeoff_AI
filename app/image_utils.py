from PIL import Image
import io
from typing import Any

def as_pil_image(obj: Any) -> Image.Image:
    """
    Converte diferentes entradas (PIL.Image, bytes, file-like) em PIL.Image.
    Garante modo RGB.
    """
    if isinstance(obj, Image.Image):
        img = obj
    elif isinstance(obj, (bytes, bytearray)):
        img = Image.open(io.BytesIO(obj))
    elif hasattr(obj, "read"):  # file-like
        data = obj.read()
        img = Image.open(io.BytesIO(data))
    else:
        raise TypeError(f"Tipo de imagem não suportado para cropper: {type(obj)}")

    # Normaliza modo
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img
