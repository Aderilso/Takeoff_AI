"""
Utilitários de compatibilidade para diferentes versões do Streamlit
"""
import streamlit as st
from typing import Optional, Any

def image_full_width(img: Any, caption: Optional[str] = None):
    """
    Exibe imagem ocupando a largura do container, compatível com versões antigas e novas do Streamlit.
    Tenta a nova API (width='stretch'); se não existir, usa use_container_width=True.
    """
    try:
        # Tentativa: versões novas que aceitam 'stretch'
        st.image(img, caption=caption, width="stretch")
    except TypeError:
        try:
            # Fallback: versões que aceitam use_container_width
            st.image(img, caption=caption, use_container_width=True)
        except TypeError:
            # Fallback final: versões antigas sem parâmetros de largura
            st.image(img, caption=caption)

def dataframe_full_width(df: Any, height: Optional[int] = None):
    """
    Exibe DataFrame ocupando a largura do container, compatível com versões antigas e novas do Streamlit.
    Tenta a nova API (width='stretch'); se não existir, usa use_container_width=True.
    """
    # Calcular altura dinâmica se não fornecida
    if height is None and hasattr(df, '__len__'):
        # Altura base + altura por linha (aproximadamente 36px por linha)
        height = min(720, 120 + 36 * len(df))
    
    try:
        # Tentativa: versões novas que aceitam 'stretch'
        if height:
            st.dataframe(df, width="stretch", height=height, hide_index=False)
        else:
            st.dataframe(df, width="stretch", hide_index=False)
    except TypeError:
        try:
            # Fallback: versões que aceitam use_container_width
            if height:
                st.dataframe(df, use_container_width=True, height=height, hide_index=False)
            else:
                st.dataframe(df, use_container_width=True, hide_index=False)
        except TypeError:
            # Fallback final: versões antigas sem parâmetros de largura
            st.dataframe(df, hide_index=False)
