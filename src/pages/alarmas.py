import copy
import streamlit as st
import time
from streamlit_autorefresh import st_autorefresh
from utils.helpers import posicion_estable
from utils.dmn_client import enviar_email, lanzar_alarma
from datetime import datetime, time

# Configuración de la página
st.set_page_config(page_title="Configuración de Alarmas", layout="wide")
st.title("🔔 Configuración de Alarmas")
st.markdown("Añade, edita o elimina reglas de alerta de forma interactiva.")

# Inicializar estado de alarmas
if "alarmas" not in st.session_state:
    st.session_state.alarmas = []

# Inicializar estado temporal de edición
if "editando_alarmas" not in st.session_state:
    st.session_state.editando_alarmas = copy.deepcopy(st.session_state.alarmas)

# Mostrar posición estable actual
pos = posicion_estable()
if pos:
    st.info(f"📍 Posición estable actual: {pos[0]} - {pos[1]}")
else:
    st.warning("⚠️ No se ha detectado una posición estable")

st.markdown("---")

# Botón para añadir nueva alarma
if st.button("➕ Añadir Alarma", key="btn_add_alarma"):
    nueva_alarma = {
        "habitacion": "Dormitorio",
        "tipo_alerta": "Salida tarde",
        "umbral": time(9, 0),
        "email": "",
        "repetir_diariamente": True,
    }
    st.session_state.editando_alarmas.append(nueva_alarma)
    st.rerun()

st.markdown("### Alarmas configuradas")

# Mostrar cada alarma como tarjeta editable
for idx, alarma in enumerate(st.session_state.editando_alarmas):
    with st.container():
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 3, 1, 1])

        # Habitación
        alarma["habitacion"] = col1.selectbox(
            "Habitación",
            ["Dormitorio", "Cocina", "Salón", "Baño", "Pasillo"],
            index=["Dormitorio", "Cocina", "Salón", "Baño", "Pasillo"].index(alarma["habitacion"]),
            key=f"hab_{idx}"
        )

        # Tipo de alerta
        alarma["tipo_alerta"] = col2.selectbox(
            "Tipo de alerta",
            ["Entrada tarde", "Salida tarde", "Tiempo máximo en habitación"],
            index=["Entrada tarde", "Salida tarde", "Tiempo máximo en habitación"].index(alarma["tipo_alerta"]),
            key=f"tipo_{idx}"
        )

        # Umbral
        if alarma["tipo_alerta"] in ["Entrada tarde", "Salida tarde"]:
            hora_default = alarma["umbral"]
            if isinstance(hora_default, str):
                try:
                    hora_default = datetime.strptime(hora_default, "%H:%M").time()
                except ValueError:
                    hora_default = time(9, 0)
            elif not isinstance(hora_default, time):
                hora_default = time(9, 0)

            alarma["umbral"] = col3.time_input(
                "Hora límite",
                value=hora_default,
                key=f"time_{idx}"
            )
        else:
            umbral_default = alarma["umbral"]
            if isinstance(umbral_default, time):
                umbral_default = 30
            elif isinstance(umbral_default, str):
                try:
                    umbral_default = int(umbral_default)
                except ValueError:
                    umbral_default = 30

            alarma["umbral"] = col3.number_input(
                "Umbral (min)",
                min_value=1,
                max_value=240,
                value=umbral_default,
                key=f"num_{idx}"
            )

        # Email
        alarma["email"] = col4.text_input(
            "Email para recibir alertas",
            value=alarma["email"],
            key=f"email_{idx}"
        )

        # Repetir diariamente
        alarma["repetir_diariamente"] = col5.checkbox(
            "🔁",
            value=alarma.get("repetir_diariamente", True),
            key=f"rep_{idx}"
        )

        # Botón eliminar
        if col6.button("🗑️", key=f"del_{idx}"):
            st.session_state.editando_alarmas.pop(idx)
            st.rerun()

        st.markdown("---")

# Guardar configuración
if st.button("💾 Guardar todas las alarmas"):
    st.session_state["last_alarm_shown"] = {}
    st.session_state.alarmas = [dict(a) for a in st.session_state.editando_alarmas]
    st.success("✅ Alarmas guardadas en sesión.")

st.markdown("---")

# Auto-refresco silencioso cada 30 segundos
st_autorefresh(interval=30_000, key="alarma_refresh")

# Lógica de disparo de alarmas
def check_local_alarms():
    pos = posicion_estable()
    if not pos:
        return
    room, _ = pos
    ahora = datetime.now()

    for idx, alarma in enumerate(st.session_state.alarmas):
        triggered = False
        mensaje = ""

        key = f"alert_sent_{idx}"

        # Si ya se lanzó y no se repite, no hacer nada
        if not alarma.get("repetir_diariamente", False) and st.session_state["last_alarm_shown"].get(key, False):
            continue

        # Comprobar si es hora de lanzarla
        if alarma["tipo_alerta"] == "Entrada tarde" and room != alarma["habitacion"]:
            hora_limite = alarma["umbral"]
            if isinstance(hora_limite, str):
                hora_limite = datetime.strptime(hora_limite, "%H:%M").time()
            if ahora.time() > hora_limite:
                triggered = True
                mensaje = f"Entrada tarde en {alarma['habitacion']}"

        elif alarma["tipo_alerta"] == "Salida tarde" and room == alarma["habitacion"]:
            hora_limite = alarma["umbral"]
            if isinstance(hora_limite, str):
                hora_limite = datetime.strptime(hora_limite, "%H:%M").time()
            if ahora.time() > hora_limite:
                triggered = True
                mensaje = f"Salida tarde de {alarma['habitacion']}"

        elif alarma["tipo_alerta"] == "Tiempo máximo en habitación" and room == alarma["habitacion"]:
            # Aquí iría la lógica de tiempo prolongado
            triggered = True
            mensaje = f"Tiempo prolongado en {alarma['habitacion']} (más de {alarma['umbral']} min)"

        if triggered:
            lanzar_alarma(mensaje, alarma["email"])
            st.session_state["last_alarm_shown"][key] = True

# Ejecutar la lógica de comprobación de alarmas
check_local_alarms()