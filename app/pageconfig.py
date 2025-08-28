# app/pageconfig.py
import streamlit as st

def configure():
    # Precisa ser a PRIMEIRA chamada de Streamlit no app
    st.set_page_config(
        page_title="Takeoff | PDF → Tabela → Gemini",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # (Opcional) CSS global
    st.markdown("""
    <style>
      .block-container {max-width: 1600px; padding-top: 1rem; padding-bottom: 2rem;}
    </style>
    """, unsafe_allow_html=True)
