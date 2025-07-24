# pages/mapa_tiempo_real.py

import time
import streamlit as st
from PIL import Image, ImageDraw
import pandas as pd
import os
from utils.helpers import dibujar_mapa
from utils.data_loader import obtener_ultimas_filas_csv
from utils.helpers import dibujar_grafico_rssi

st.title("🗺️ Mapa en Tiempo Real")
st.write("Visualización en tiempo real del posicionamiento indoor.")

MAPA_PATH = os.path.join(os.path.dirname(__file__), "../fotos/ParteDeAbajo.png")

mapa_ph = st.empty()
graf_ph = st.empty()
tab_ph = st.empty()

while True:
    data = obtener_ultimas_filas_csv(5)
    if not data.empty:
        last = data.iloc[-1]
        try:
            img = dibujar_mapa(last)
            mapa_ph.image(img, use_container_width=True)
            fig_rssi = dibujar_grafico_rssi(last)
            if fig_rssi:
                graf_ph.pyplot(fig_rssi, use_container_width=True)
        except Exception as e:
            st.error(f"Error al dibujar el mapa: {e}")
        tab_ph.dataframe(data, use_container_width=True)
    else:
        tab_ph.dataframe(pd.DataFrame(), use_container_width=True)

    time.sleep(1)  # Actualiza cada segundo
