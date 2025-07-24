# app.py - Menú Principal
import streamlit as st

st.set_page_config(page_title="Posicionamiento Indoor", layout="wide")

st.title("🧭 Menú Principal - Posicionamiento Indoor")
st.markdown("Selecciona una opción para navegar:")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("📍 Mapa en Tiempo Real", use_container_width=True):
        st.switch_page("pages/mapa_tiempo_real.py")

with col2:
    if st.button("🔔 Alarmas", use_container_width=True):
        st.switch_page("pages/alarmas.py")

with col3:
    if st.button("📊 Gráficas Comparativas", use_container_width=True):
        st.switch_page("pages/graficas_comparativas.py")

with col4:
    if st.button("📂 Historial", use_container_width=True):
        st.switch_page("pages/historial.py")

with col5:
    if st.button("🔍 Descubrimiento", use_container_width=True):
        st.switch_page("pages/descubrimiento.py")
st.info("📌 Pulsa uno de los botones arriba para navegar entre funcionalidades.")