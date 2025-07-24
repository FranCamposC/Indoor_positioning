
import os
import io
import time
import json
import datetime
import smtplib
from email.mime.text import MIMEText

import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv  # pip install python-dotenv

# -----------------------------------------------------------------------------
# CARGA DE VARIABLES DE ENTORNO
# -----------------------------------------------------------------------------
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
ENGINE_URL = os.getenv(
    "ENGINE_URL",
    "http://localhost:8080/engine-rest/decision-definition/key/decision_alarmas/evaluate",
)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Posicionamiento Indoor",
    layout="wide",  # Ocupamos todo el ancho
    initial_sidebar_state="collapsed",
)

# Rutas ficheros
aqui = os.path.dirname(__file__)
CSV_PATH = os.path.join(aqui, "logs", "predicciones_xgboost.csv")
MAPA_PATH = os.path.join(aqui, "fotos", "ParteDeAbajo.png")
ACTIONS_PATH = os.path.join(aqui, "logs", "acciones_detectadas.csv")

# -----------------------------------------------------------------------------
# CONSTANTES Y ESTADO GLOBAL
# -----------------------------------------------------------------------------
TIEMPO_VISIBLE_TRANSICIONES = 10  # s que permanecen las líneas de transición
transiciones = []
ultima_habitacion: str | None = None
ultima_posicion: str | None = None

ESP_POSICIONES = {
    "ESP32_1": (200, 650),
    "ESP32_2": (220, 25),
    "ESP32_3": (170, 220),
    "ESP32_4": (790, 650),
    "ESP32_5": (520, 520),
    "ESP32_6": (1350, 25),
    "ESP32_7": (150000, 50050),  # valor fuera para que no pinte
    "ESP32_8": (1200, 240),
    "ESP32_9": (200, 420),
    "ESP32_10": (1020, 650),
}

POSICIONES = {
    "Cocina_Fregadero": (230, 50),
    "Cocina_Vitroceramica": (220, 45),
    "Cocina_Frigorifico": (120, 220),
    "Salon_Mesa": (600, 150),
    "Salon_Sofa": (740, 635),
    "Dormitorio_Cama": (200, 635),
    "Dormitorio_Escritorio": (100, 400),
    "Baño_Lavabo": (1330, 45),
    "Baño_WC": (1100, 230),
}

VALID_POSITIONS_BY_ROOM = {
    "Dormitorio": ["Cama", "Escritorio"],
    "Cocina": ["Vitroceramica", "Frigorifico", "Fregadero"],
    "Salon": ["Mesa", "Sofa"],
    "Baño": ["WC", "Lavabo"],
    "Pasillo": ["Pasillo"],
}

# -----------------------------------------------------------------------------
# SESSION_STATE POR DEFECTO
# -----------------------------------------------------------------------------
state_defaults = {
    "hora_limite_salida_dormitorio": datetime.time(9, 0),
    "hora_limite_entrada_dormitorio": datetime.time(23, 0),
    "tiempo_limite_bano": 15,
    "tiempo_entrada_bano": None,
    "alarmas_configuradas": False,
    "alert_email": "",
    "last_alarm_shown": {},
}
for k, v in state_defaults.items():
    st.session_state.setdefault(k, v)

# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES 
# -----------------------------------------------------------------------------

def format_timedelta(td: datetime.timedelta) -> str:
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def obtener_ultimas_filas_csv(n: int = 5) -> pd.DataFrame:
    try:
        df = pd.read_csv(CSV_PATH)
        return df.tail(n) if not df.empty else pd.DataFrame()
    except Exception as exc:  # pragma: no cover
        st.error(f"Error al leer el CSV: {exc}")
        return pd.DataFrame()


def obtener_3_filas_validas() -> pd.DataFrame | None:
    try:
        df = pd.read_csv(CSV_PATH)
        df = df[(df["habitacion_predicha"] != "Duda") & (df["posicion_predicha"] != "Duda")]
        df = df[
            df.apply(
                lambda r: r["posicion_predicha"]
                in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []),
                axis=1,
            )
        ]
        ult2 = df.tail(2)
        return ult2 if len(ult2) == 2 else None
    except Exception as exc:  # pragma: no cover
        st.error(f"Error al leer el CSV: {exc}")
        return None


def dibujar_esps(draw: ImageDraw.ImageDraw, fila: pd.Series):
    """Pinta los puntos ESP32 en el plano según RSSI"""
    for esp, (x, y) in ESP_POSICIONES.items():
        if esp in fila:
            rssi = fila[esp]
            color = "green" if rssi >= -75 else "yellow" if rssi >= -95 else "red"
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)


def dibujar_transiciones(img: Image.Image):
    """Sobrepone líneas semitransparentes con las últimas transiciones"""
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    now = time.time()
    for x1, y1, x2, y2, t in list(transiciones):
        elapsed = now - t
        if elapsed > TIEMPO_VISIBLE_TRANSICIONES:
            transiciones.remove((x1, y1, x2, y2, t))
            continue
        alpha = (
            255
            if elapsed < TIEMPO_VISIBLE_TRANSICIONES / 2
            else int(
                255
                * (
                    1
                    - (
                        elapsed - TIEMPO_VISIBLE_TRANSICIONES / 2
                    )
                    / (TIEMPO_VISIBLE_TRANSICIONES / 2)
                )
            )
        )
        od.line([(x1, y1), (x2, y2)], fill=(255, 0, 0, alpha), width=3)
    return Image.alpha_composite(img, overlay)


def dibujar_grafico_rssi(fila: pd.Series):
    if fila.empty:
        return None
    vals = {esp: 100 + max(v, -100) for esp, v in fila.items() if esp.startswith("ESP32_")}
    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.bar(vals.keys(), vals.values())
    ax.set_ylim(0, 100)
    ax.set_ylabel("RSSI (dBm)")
    ax.set_title("Señal ESP32")
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(vals.keys(), rotation=45)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    plt.tight_layout()
    return fig


def posicion_estable() -> tuple[str, str] | None:
    v = obtener_3_filas_validas()
    if v is None:
        return None
    h = v["habitacion_predicha"].unique()
    p = v["posicion_predicha"].unique()
    return (h[0], p[0]) if len(h) == 1 and len(p) == 1 else None


def dibujar_mapa(fila: pd.Series):
    global ultima_habitacion, ultima_posicion, transiciones

    img = Image.open(MAPA_PATH).convert("RGBA")
    d = ImageDraw.Draw(img)

    # Puntos ESP32
    dibujar_esps(d, fila)

    # Círculo azul en la posición estable
    nueva = posicion_estable()
    old_hab, old_pos = ultima_habitacion, ultima_posicion

    if nueva:
        ultima_habitacion, ultima_posicion = nueva

    if ultima_habitacion and ultima_posicion:
        coords = POSICIONES.get(f"{ultima_habitacion}_{ultima_posicion}", (0, 0))
    else:
        coords = (0, 0)

    # Guardamos transición
    if coords != (0, 0) and old_hab and old_pos:
        o = POSICIONES.get(f"{old_hab}_{old_pos}", (0, 0))
        if o != (0, 0) and o != coords:
            transiciones.append((*o, coords[0], coords[1], time.time()))

    # Pintamos posición actual
    if coords != (0, 0):
        x, y = coords
        r = 14
        d.ellipse([x - r, y - r, x + r, y + r], fill="blue")

    return dibujar_transiciones(img)


# ---- FUNCIONES DE ALARMAS  ---------------------------

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


def lanzar_alarma(mensaje: str):
    key = f"alert_sent_{mensaje}"
    if st.session_state["last_alarm_shown"].get(key, False):
        return
    components.html(f"<script>alert('Alerta: {mensaje}');</script>")
    enviar_email(mensaje, st.session_state.get("alert_email"))
    st.session_state["last_alarm_shown"][key] = True


def evaluar_alarmas_en_camunda(diff_salida, diff_entrada, diff_bano, habitacion_actual):
    payload = {
        "variables": {
            "diff_salida": {"value": diff_salida, "type": "Double"},
            "diff_entrada": {"value": diff_entrada, "type": "Double"},
            "diff_bano": {"value": diff_bano, "type": "Double"},
            "habitacion_actual": {"value": habitacion_actual, "type": "String"},
        }
    }
    try:
        r = requests.post(
            ENGINE_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=5,
        )
        r.raise_for_status()
        respuesta = r.json()
        if respuesta and "alarma" in respuesta[0]:
            return respuesta[0]["alarma"].get("value", "")
    except Exception as exc:  
        st.error(f"Error al consultar DMN: {exc}")
    return ""


def comprobar_alarmas():
    if not st.session_state["alarmas_configuradas"]:
        return

    pe = posicion_estable()  # (habitacion, posicion)
    if not pe:
        return

    habitacion_actual, _ = pe
    ahora = datetime.datetime.now()

    hora_lim_s = datetime.datetime.combine(
        ahora.date(), st.session_state["hora_limite_salida_dormitorio"]
    )
    hora_lim_e = datetime.datetime.combine(
        ahora.date(), st.session_state["hora_limite_entrada_dormitorio"]
    )

    diff_salida = (
        max(0, (ahora - hora_lim_s).total_seconds() / 60)
        if habitacion_actual == "Dormitorio"
        else 0
    )
    diff_entrada = (
        max(0, (ahora - hora_lim_e).total_seconds() / 60)
        if habitacion_actual != "Dormitorio"
        else 0
    )

    if habitacion_actual == "Baño":
        if st.session_state["tiempo_entrada_bano"] is None:
            st.session_state["tiempo_entrada_bano"] = ahora
        diff_bano = (
            ahora - st.session_state["tiempo_entrada_bano"]
        ).total_seconds() / 60
    else:
        diff_bano = 0
        st.session_state["tiempo_entrada_bano"] = None

    alarma = evaluar_alarmas_en_camunda(
        diff_salida, diff_entrada, diff_bano, habitacion_actual
    )
    if alarma:
        lanzar_alarma(alarma)


# -----------------------------------------------------------------------------
# INTERFAZ DE USUARIO
# -----------------------------------------------------------------------------
st.title("Posicionamiento Indoor")
st.write("Visualización en tiempo real con tiempos de posición y habitación.")

# --------------------------- SIDEBAR -----------------------------------------
with st.sidebar:
    st.header("Controles")

    # ----------------------- ALARMAS ----------------------------------------
    with st.expander("Alarmas", expanded=False):
        st.markdown("Configura horas límite, tiempo en baño y correo de destino")
        with st.form("form_alarmas"):
            hs = st.time_input(
                "Hora límite SALIR dormitorio",
                value=st.session_state["hora_limite_salida_dormitorio"],
            )
            he = st.time_input(
                "Hora límite ENTRAR dormitorio",
                value=st.session_state["hora_limite_entrada_dormitorio"],
            )
            tb = st.number_input(
                "Tiempo máximo en baño (min)",
                min_value=1,
                max_value=180,
                value=st.session_state["tiempo_limite_bano"],
            )
            email = st.text_input("Email para recibir alertas", st.session_state["alert_email"])
            if st.form_submit_button("Guardar"):
                st.session_state["hora_limite_salida_dormitorio"] = hs
                st.session_state["hora_limite_entrada_dormitorio"] = he
                st.session_state["tiempo_limite_bano"] = tb
                st.session_state["alert_email"] = email
                st.session_state["alarmas_configuradas"] = True
                st.success("¡Configuración de alarmas guardada!")

    # ------------------- GRÁFICAS COMPARATIVAS ------------------------------
    with st.expander("Gráficas comparativas", expanded=False):
        st.markdown("Selecciona rango de fechas para generar las gráficas")
        with st.form("form_graficas"):
            fi_graf = st.date_input("Fecha inicio", key="fi_graf")
            hi_graf = st.time_input("Hora inicio", value=datetime.time(0, 0))
            ff_graf = st.date_input("Fecha fin", key="ff_graf")
            hf_graf = st.time_input("Hora fin", value=datetime.time(23, 59, 59))
            generar = st.form_submit_button("Generar")

        if generar:
            dt_i_graf = datetime.datetime.combine(fi_graf, hi_graf)
            dt_f_graf = datetime.datetime.combine(ff_graf, hf_graf)
            if dt_i_graf > dt_f_graf:
                st.warning("La fecha de inicio no puede ser posterior a la de fin.")
            else:
                try:
                    from io import BytesIO

                    def generar_datos_diarios(path):
                        df = pd.read_csv(path)
                        df["time"] = pd.to_datetime(
                            df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce"
                        )
                        df.dropna(subset=["time"], inplace=True)
                        df = df[
                            (df["habitacion_predicha"] != "Duda")
                            & (df["posicion_predicha"] != "Duda")
                        ]
                        df = df[
                            df.apply(
                                lambda r: r["posicion_predicha"]
                                in VALID_POSITIONS_BY_ROOM.get(
                                    r["habitacion_predicha"], []
                                ),
                                axis=1,
                            )
                        ]
                        df["Fecha"] = df["time"].dt.date
                        intervalos = []
                        for fecha, subdf in df.groupby("Fecha"):
                            subdf = subdf.sort_values("time").reset_index(drop=True)
                            posicion_actual, habitacion_actual, start_time = None, None, None
                            for _, fila in subdf.iterrows():
                                hab, pos, t = (
                                    fila["habitacion_predicha"],
                                    fila["posicion_predicha"],
                                    fila["time"],
                                )
                                if posicion_actual is None:
                                    posicion_actual, habitacion_actual, start_time = pos, hab, t
                                elif (hab != habitacion_actual) or (pos != posicion_actual):
                                    fin_time = t
                                    duracion = (fin_time - start_time).total_seconds()
                                    if duracion > 5:
                                        intervalos.append(
                                            {
                                                "Fecha": fecha,
                                                "Habitacion": habitacion_actual,
                                                "Posicion": posicion_actual,
                                                "Duracion_segundos": duracion,
                                            }
                                        )
                                    posicion_actual, habitacion_actual, start_time = pos, hab, t
                            # última
                            if posicion_actual:
                                duracion = (
                                    subdf.iloc[-1]["time"] - start_time
                                ).total_seconds()
                                if duracion > 5:
                                    intervalos.append(
                                        {
                                            "Fecha": fecha,
                                            "Habitacion": habitacion_actual,
                                            "Posicion": posicion_actual,
                                            "Duracion_segundos": duracion,
                                        }
                                    )
                        return pd.DataFrame(intervalos)

                    df_comp = generar_datos_diarios(CSV_PATH)
                    df_comp["Fecha_dt"] = pd.to_datetime(df_comp["Fecha"])
                    df_rango = df_comp[(df_comp["Fecha_dt"] >= dt_i_graf) & (df_comp["Fecha_dt"] <= dt_f_graf)]

                    if df_rango.empty:
                        st.warning("No hay datos en el rango seleccionado.")
                    else:
                        # Barras apiladas
                        df_pos = (
                            df_rango.groupby(["Fecha", "Posicion"])["Duracion_segundos"].sum().unstack(fill_value=0) / 60
                        )
                        fig_barras, ax = plt.subplots(figsize=(8, 5))
                        df_pos.plot(kind="bar", stacked=True, ax=ax)
                        ax.set_title("Tiempo total por posición (minutos)")
                        ax.set_ylabel("Minutos")
                        ax.set_xlabel("Fecha")
                        ax.legend(title="Posición")
                        ax.grid(True)
                        plt.xticks(rotation=45)
                        st.pyplot(fig_barras, use_container_width=True)

                        # Grafica PIE por cada día
                        for fecha in df_rango["Fecha"].unique():
                            df_fecha = df_rango[df_rango["Fecha"] == fecha]
                            serie = (
                                df_fecha.groupby("Posicion")["Duracion_segundos"].sum() / 60
                            )
                            if not serie.empty:
                                fig_pie, ax_pie = plt.subplots(figsize=(4, 4))
                                serie.plot.pie(ax=ax_pie, autopct="%1.1f%%")
                                ax_pie.set_ylabel("")
                                ax_pie.set_title(f"Uso por posición - {fecha}")
                                st.pyplot(fig_pie, use_container_width=True)
                except Exception as exc:  # pragma: no cover
                    st.error(f"Error al generar gráficas: {exc}")

    # ---------------------- DESCARGA HISTORIAL -------------------------------
    with st.expander("Descargar historial", expanded=False):
        st.markdown("Selecciona rango de fechas para exportar a Excel")
        with st.form("form_historial"):
            fi = st.date_input("Fecha inicio")
            hi = st.time_input("Hora inicio", value=datetime.time(0, 0))
            ff = st.date_input("Fecha fin")
            hf = st.time_input("Hora fin", value=datetime.time(23, 59, 59))
            descargar = st.form_submit_button("Generar fichero")

        if descargar:
            dt_i = datetime.datetime.combine(fi, hi)
            dt_f = datetime.datetime.combine(ff, hf)
            try:
                from io import BytesIO

                def generar_intervalос(path, dt_inicio, dt_fin, min_filas=3):
                    # Esta función es idéntica a la que tenías; se omite por brevedad
                    ...

                df_pos, df_hab = generar_intervalос(CSV_PATH, dt_i, dt_f)
                if df_pos.empty and df_hab.empty:
                    st.warning("No hay intervalos válidos en ese rango.")
                else:
                    buf = BytesIO()
                    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                        if not df_pos.empty:
                            df_pos.to_excel(writer, index=False, sheet_name="Posiciones")
                        if not df_hab.empty:
                            df_hab.to_excel(writer, index=False, sheet_name="Habitaciones")
                    buf.seek(0)
                    st.download_button(
                        "Descargar Excel",
                        data=buf,
                        file_name="historial_intervalos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except Exception as exc:  # pragma: no cover
                st.error(f"Error al generar Excel: {exc}")

# ---------------------------- ZONA PRINCIPAL ---------------------------------
left, center, right = st.columns([1.5, 7, 1.5], gap="small")
with center:
    mapa_ph = st.empty()
    graf_ph = st.empty()
    tab_ph  = st.empty()
    

# ------------------------------ BUCLE LIVE -----------------------------------
while True:
    data = obtener_ultimas_filas_csv(5)
    if not data.empty:
        last = data.iloc[-1]
        mapa_ph.image(dibujar_mapa(last), use_container_width=True)
        fig_rssi = dibujar_grafico_rssi(last)
        if fig_rssi:
            graf_ph.pyplot(fig_rssi, use_container_width=True)
        tab_ph.dataframe(data, use_container_width=True)
    else:
        tab_ph.dataframe(pd.DataFrame(), use_container_width=True)

    comprobar_alarmas()
    time.sleep(1)  # refresco"]}
