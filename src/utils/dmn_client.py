# utils/dmn_client.py
import json
import os
from datetime import time
from dotenv import load_dotenv
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import streamlit as st
import streamlit.components.v1 as components

from utils.helpers import posicion_estable

load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
ENGINE_URL = os.getenv(
    "ENGINE_URL",
    "http://localhost:8080/engine-rest/decision-definition/key/decision_alarmas/evaluate"
)

state_defaults = {
    "hora_limite_salida_dormitorio": time(9, 0),
    "hora_limite_entrada_dormitorio": time(23, 0),
    "tiempo_limite_bano": 15,
    "tiempo_entrada_bano": None,
    "alarmas_configuradas": True,  # Activadas por defecto
    "alert_email": "",
    "last_alarm_shown": {},
    "last_alarm_time": {},  # Nuevo: momento de la última alarma
}
for k, v in state_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def enviar_email(mensaje: str, destino: str):
    if not destino:
        return
    msg = MIMEText(f"Alerta generada:\n\n{mensaje}")
    msg["Subject"] = f"[IndoorPositioning] Alerta: {mensaje}"
    msg["From"] = EMAIL_USER
    msg["To"] = destino
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
    except Exception as exc:
        st.error(f"Error al enviar email: {exc}")


def lanzar_alarma(mensaje: str, email: str = ""):
    key = f"alert_sent_{mensaje}"
    if st.session_state["last_alarm_shown"].get(key, False):
        return

    now = datetime.now()
    st.session_state["last_alarm_time"][key] = now

    components.html(f"<script>alert('Alerta: {mensaje}');</script>")
    if email:
        enviar_email(mensaje, email)

    st.session_state["last_alarm_shown"][key] = True
