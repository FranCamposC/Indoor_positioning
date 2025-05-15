import os
from dotenv import load_dotenv  # pip install python-dotenv
import datetime
import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
import io
import smtplib  # Para enviar emails
from email.mime.text import MIMEText  # Para crear el mensaje de email
import streamlit.components.v1 as components  # Para mostrar alertas en HTML
from streamlit.runtime.scriptrunner import RerunException, RerunData

# ----------------------------------------------------------------------
# CARGA DE VARIABLES DE ENTORNO
# ----------------------------------------------------------------------
# Crea un fichero .env (añádelo a .gitignore) con:
# EMAIL_USER=tu_usuario@gmail.com
# EMAIL_PASS=tu_token_o_contraseña
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------
st.set_page_config(layout='centered')

CSV_PATH = "src/logs/predicciones_xgboost.csv"
MAPA_PATH = "src/fotos/ParteDeAbajo.png"
ACTIONS_PATH = "src/logs/acciones_detectadas.csv"

TIEMPO_VISIBLE_TRANSICIONES = 10  # segundos que se ven las líneas de transición
transiciones = []
ultima_habitacion = None
ultima_posicion = None

# ESP_POSICIONES = {
#     "ESP32_1": (100, 360),
#     "ESP32_2": (100, 550),
#     "ESP32_3": (300, 283),
#     "ESP32_4": (50, 40),
#     "ESP32_5": (50, 200),
#     "ESP32_6": (300, 40),
#     "ESP32_7": (550, 550),
#     "ESP32_8": (750, 430),
#     "ESP32_9": (550, 150),
#     "ESP32_10": (990, 290),
# }

ESP_POSICIONES = {
    "ESP32_1": (200, 650),
    "ESP32_2": (220, 25),
    "ESP32_3": (170, 220),
    "ESP32_4": (790, 650),
    "ESP32_5": (520, 520),
    "ESP32_6": (1350, 25),
    "ESP32_7": (150000, 50050),
    "ESP32_8": (1200, 240),
    "ESP32_9": (200, 420),
    "ESP32_10": (1020, 650),
}
 #ARRIBA
# POSICIONES = {
#     "Cocina_Fregadero":      (70, 70),
#     "Cocina_Vitro":          (70, 200),
#     "Cocina_Frigorifico":    (320, 65),
#     "Salon_Mesa":            (600, 150),
#     "Salon_Sofa":            (900, 275),
#     "Dormitorio_Cama":       (100, 525),
#     "Dormitorio_Escritorio": (100, 400),
#     "Baño_Lavabo":           (550, 500),
#     "Baño_WC":               (900, 430),
#     "Pasillo_Pasillo":       (300, 285),
# }

# ABAJO
POSICIONES = {
    "Cocina_Fregadero":      (230, 50),
    "Cocina_Vitroceramica":          (220, 45),
    "Cocina_Frigorifico":    (120, 220),
    "Salon_Mesa":            (600, 150),
    "Salon_Sofa":            (740, 635),
    "Dormitorio_Cama":       (200, 635),
    "Dormitorio_Escritorio": (100, 400),
    "Baño_Lavabo":           (1330, 45),
    "Baño_WC":               (1100, 230),
}
VALID_POSITIONS_BY_ROOM = {
    "Dormitorio":   ["Cama", "Escritorio"],
    "Cocina":       ["Vitroceramica", "Frigorifico", "Fregadero"],
    "Salon":        ["Mesa", "Sofa"],
    "Baño":         ["WC", "Lavabo"],
    "Pasillo":      ["Pasillo"]
}

# ----------------------------------------------------------------------
# INICIALIZAR session_state
# ----------------------------------------------------------------------
if 'last_alarm_shown' not in st.session_state:
    st.session_state['last_alarm_shown'] = {}
if "alert_email" not in st.session_state:
    st.session_state["alert_email"] = ""
if "alarmas_configuradas" not in st.session_state:
    st.session_state["alarmas_configuradas"] = False

# ----------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------------------------------------
def format_timedelta(td):
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def obtener_ultimas_filas_csv(n=5):
    try:
        df = pd.read_csv(CSV_PATH)
        return df.tail(n) if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer el CSV: {e}")
        return pd.DataFrame()

def obtener_3_filas_validas():
    try:
        df = pd.read_csv(CSV_PATH)
        df = df[(df["habitacion_predicha"]!="Duda") & (df["posicion_predicha"]!="Duda")]
        df = df[df.apply(
            lambda r: r["posicion_predicha"] in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []),
            axis=1
        )]
        ult2 = df.tail(2)
        return ult2 if len(ult2)==2 else None
    except Exception as e:
        st.error(f"Error al leer el CSV: {e}")
        return None

def dibujar_esps(draw, fila):
    for esp,(x,y) in ESP_POSICIONES.items():
        if esp in fila:
            rssi = fila[esp]
            color = "green" if rssi>=-75 else "yellow" if rssi>=-95 else "red"
            draw.ellipse((x-6,y-6,x+6,y+6), fill=color)

def dibujar_transiciones(img):
    overlay = Image.new("RGBA", img.size, (255,255,255,0))
    od = ImageDraw.Draw(overlay)
    now = time.time()
    for x1,y1,x2,y2,t in list(transiciones):
        e = now - t
        if e>TIEMPO_VISIBLE_TRANSICIONES:
            transiciones.remove((x1,y1,x2,y2,t))
            continue
        alpha = 255 if e< TIEMPO_VISIBLE_TRANSICIONES/2 else int(255*(1-(e-TIEMPO_VISIBLE_TRANSICIONES/2)/(TIEMPO_VISIBLE_TRANSICIONES/2)))
        od.line([(x1,y1),(x2,y2)], fill=(255,0,0,alpha), width=3)
    return Image.alpha_composite(img, overlay)

def dibujar_grafico_rssi(fila):
    if fila.empty: return None
    vals = {esp:100+max(v,-100) for esp,v in fila.items() if esp.startswith("ESP32_")}
    fig,ax = plt.subplots(figsize=(8,2.5))
    ax.bar(vals.keys(), vals.values())
    ax.set_ylim(0,100); ax.set_ylabel("RSSI (dBm)"); ax.set_title("Señal ESP32")
    ax.set_xticks(range(len(vals))); ax.set_xticklabels(vals.keys(), rotation=45)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    return fig

def posicion_estable():
    v = obtener_3_filas_validas()
    if v is None: return None
    h = v["habitacion_predicha"].unique()
    p = v["posicion_predicha"].unique()
    return (h[0],p[0]) if len(h)==1 and len(p)==1 else None

def dibujar_mapa(fila):
    global ultima_habitacion, ultima_posicion, transiciones
    img = Image.open(MAPA_PATH).convert("RGBA")
    d = ImageDraw.Draw(img)
    dibujar_esps(d, fila)
    nueva = posicion_estable()
    old_hab,old_pos = ultima_habitacion,ultima_posicion
    if nueva:
        ultima_habitacion,ultima_posicion = nueva
    if ultima_habitacion and ultima_posicion:
        coords = POSICIONES.get(f"{ultima_habitacion}_{ultima_posicion}",(0,0))
    else:
        coords = (0,0)
    if coords!=(0,0) and old_hab and old_pos:
        o = POSICIONES.get(f"{old_hab}_{old_pos}",(0,0))
        if o!=(0,0) and o!=coords:
            transiciones.append((*o,coords[0],coords[1],time.time()))
    if coords!=(0,0):
        x,y = coords; r=14
        d.ellipse([x-r,y-r,x+r,y+r], fill="blue")
    return dibujar_transiciones(img)

# ----------------------------------------------------------------------
# GENERACIÓN DE INTERVALOS (igual que antes)
# ----------------------------------------------------------------------
def generar_intervalos_separados(CSV_PATH, dt_inicio, dt_fin, min_filas=3):
    df = pd.read_csv(CSV_PATH)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df.dropna(subset=["time"], inplace=True)
    df = df[(df["habitacion_predicha"]!="Duda") & (df["posicion_predicha"]!="Duda")]
    df = df[df.apply(lambda r: r["posicion_predicha"] in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []), axis=1)]
    df.sort_values("time", inplace=True); df.reset_index(drop=True, inplace=True)

    intervalos = []
    clave,inicio,count = None,None,0
    for _,row in df.iterrows():
        hab,pos,t = row["habitacion_predicha"],row["posicion_predicha"],row["time"]
        key = (hab,pos)
        if clave is None:
            clave,inicio,count = key,t,1
        elif key==clave:
            count+=1
        else:
            if count>=min_filas:
                intervalos.append({"Habitacion":clave[0],"Posicion":clave[1],
                                   "Fecha_Entrada_dt":inicio,"Fecha_Salida_dt":t})
            clave,inicio,count = key,t,1
    if clave and count>=min_filas:
        tfin = df["time"].iloc[-1]
        intervalos.append({"Habitacion":clave[0],"Posicion":clave[1],
                           "Fecha_Entrada_dt":inicio,"Fecha_Salida_dt":tfin})

    df_pos = pd.DataFrame(intervalos)
    if df_pos.empty: return pd.DataFrame(),pd.DataFrame()
    mask = (df_pos["Fecha_Salida_dt"]>=dt_inicio)&(df_pos["Fecha_Entrada_dt"]<=dt_fin)
    df_pos = df_pos[mask].copy()
    df_pos["Fecha_Entrada_dt"]=df_pos["Fecha_Entrada_dt"].clip(lower=dt_inicio,upper=dt_fin)
    df_pos["Fecha_Salida_dt"]=df_pos["Fecha_Salida_dt"].clip(lower=dt_inicio,upper=dt_fin)
    df_pos["Tiempo_en_la_posicion_td"]=df_pos["Fecha_Salida_dt"]-df_pos["Fecha_Entrada_dt"]
    df_pos.reset_index(drop=True,inplace=True)

    # Agrupar por habitación...
    chunks=[]; start=0; hab=df_pos.loc[0,"Habitacion"]; ts=df_pos.loc[0,"Fecha_Entrada_dt"]
    for i in range(1,len(df_pos)):
        if df_pos.loc[i,"Habitacion"]!=hab:
            te=df_pos.loc[i-1,"Fecha_Salida_dt"]
            chunks.append((start,i-1,hab,ts,te))
            start,hab,ts = i,df_pos.loc[i,"Habitacion"],df_pos.loc[i,"Fecha_Entrada_dt"]
    te=df_pos.loc[len(df_pos)-1,"Fecha_Salida_dt"]
    chunks.append((start,len(df_pos)-1,hab,ts,te))

    lista_hab=[]
    for a,b,h,stt,ett in chunks:
        lista_hab.append({"Habitacion":h,
                          "Fecha_Entrada_dt":stt,
                          "Fecha_Salida_dt":ett,
                          "Tiempo_en_la_habitacion_td":ett-stt})
    df_hab = pd.DataFrame(lista_hab)
    if df_hab.empty: return df_pos, pd.DataFrame()

    # Formateo de salida
    df_pos["Fecha_Entrada"]=df_pos["Fecha_Entrada_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_pos["Fecha_Salida"]=df_pos["Fecha_Salida_dt"].dt.strftime("%d/%m/%Y %H:%M:%S")
    df_pos["Tiempo_en_la_posicion"]=df_pos["Tiempo_en_la_posicion_td"].apply(format_timedelta)
    df_pos = df_pos[["Habitacion","Posicion","Fecha_Entrada","Fecha_Salida","Tiempo_en_la_posicion"]]

    df_hab["Fecha_Entrada"]=df_hab["Fecha_Entrada_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_hab["Fecha_Salida"]=df_hab["Fecha_Salida_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_hab["Tiempo_en_la_habitacion"]=df_hab["Tiempo_en_la_habitacion_td"].apply(format_timedelta)
    df_hab = df_hab[["Habitacion","Fecha_Entrada","Fecha_Salida","Tiempo_en_la_habitacion"]]

    return df_pos, df_hab

# ----------------------------------------------------------------------
# ENVÍO DE EMAIL
# ----------------------------------------------------------------------
def enviar_email(mensaje, destino):
    if not destino: return
    msg = MIMEText(f"Alerta generada:\n\n{mensaje}")
    msg['Subject'] = f"[IndoorPositioning] Alerta: {mensaje}"
    msg['From'] = EMAIL_USER
    msg['To'] = destino
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        st.error(f"Error al enviar email: {e}")

# ----------------------------------------------------------------------
# LÓGICA DE ALARMAS
# ----------------------------------------------------------------------
def lanzar_alarma(mensaje):
    key = f"alert_sent_{mensaje}"
    if st.session_state['last_alarm_shown'].get(key, False):
        return
    components.html(f"<script>alert('Alerta: {mensaje}');</script>")
    enviar_email(mensaje, st.session_state.get("alert_email"))
    st.session_state['last_alarm_shown'][key] = True

def comprobar_alarmas():
    if not st.session_state["alarmas_configuradas"]:
        return
    pe = posicion_estable()
    if not pe: return
    hab,_ = pe
    ahora = datetime.datetime.now().time()
    hs = st.session_state.get("hora_limite_salida_dormitorio", datetime.time(9,0))
    he = st.session_state.get("hora_limite_entrada_dormitorio", datetime.time(23,0))
    tb = st.session_state.get("tiempo_limite_bano", 15)
    if ahora>hs and hab=="Dormitorio":
        lanzar_alarma("¡No se ha levantado, va a llegar tarde!")
    if ahora>he and hab!="Dormitorio":
        lanzar_alarma("¡Aún no se ha acostado!")
    if hab=="Baño":
        if st.session_state["tiempo_entrada_bano"] is None:
            st.session_state["tiempo_entrada_bano"] = datetime.datetime.now()
        else:
            m = (datetime.datetime.now() - st.session_state["tiempo_entrada_bano"]).total_seconds()/60
            if m>tb:
                lanzar_alarma("¡Lleva demasiado tiempo en el baño!")
    else:
        st.session_state["tiempo_entrada_bano"] = None

# ----------------------------------------------------------------------
# STREAMLIT APP
# ----------------------------------------------------------------------
if "hora_limite_salida_dormitorio" not in st.session_state:
    st.session_state["hora_limite_salida_dormitorio"] = datetime.time(9,0)
if "hora_limite_entrada_dormitorio" not in st.session_state:
    st.session_state["hora_limite_entrada_dormitorio"] = datetime.time(23,0)
if "tiempo_limite_bano" not in st.session_state:
    st.session_state["tiempo_limite_bano"] = 15
if "tiempo_entrada_bano" not in st.session_state:
    st.session_state["tiempo_entrada_bano"] = None

st.title("Posicionamiento Indoor")
st.write("Visualización en tiempo real con tiempos de posición y habitación.")

if st.button("ALARMAS"):
    st.session_state["mostrar_alarmas"] = not st.session_state.get("mostrar_alarmas", False)

if st.session_state.get("mostrar_alarmas", False):
    st.subheader("Configuración de ALARMAS")
    st.write("Establece horas límite, tiempo en baño y email para alertas:")
    with st.form("form_alarmas"):
        hs = st.time_input("Hora límite SALIR dormitorio", value=st.session_state["hora_limite_salida_dormitorio"])
        he = st.time_input("Hora límite ENTRAR dormitorio", value=st.session_state["hora_limite_entrada_dormitorio"])
        tb = st.number_input("Tiempo máximo en baño (min)", min_value=1, max_value=180, value=st.session_state["tiempo_limite_bano"])
        email = st.text_input("Email para recibir alertas", value=st.session_state["alert_email"])
        if st.form_submit_button("Guardar alarmas"):
            st.session_state["hora_limite_salida_dormitorio"] = hs
            st.session_state["hora_limite_entrada_dormitorio"] = he
            st.session_state["tiempo_limite_bano"] = tb
            st.session_state["alert_email"] = email
            st.session_state["alarmas_configuradas"] = True
            st.success("¡Alarmas guardadas!")

col_left, col_right = st.columns([3,1])
with col_right:
    st.subheader("Descargar intervalos con tiempos")
    fi = st.date_input("Fecha inicio")
    hi = st.time_input("Hora inicio", value=datetime.time(0,0))
    dt_i = datetime.datetime.combine(fi,hi)
    ff = st.date_input("Fecha fin")
    hf = st.time_input("Hora fin", value=datetime.time(23,59,59))
    dt_f = datetime.datetime.combine(ff,hf)
    if st.button("Guardar archivo"):
        try:
            df_pos, df_hab = generar_intervalos_separados(CSV_PATH, dt_i, dt_f)
            if df_pos.empty and df_hab.empty:
                st.warning("No hay intervalos válidos en ese rango.")
            else:
                buf1 = io.BytesIO()
                with pd.ExcelWriter(buf1, engine='xlsxwriter') as w:
                    df_pos.to_excel(w, index=False, sheet_name="Intervalos")
                buf1.seek(0)
                st.download_button("Descargar Excel posiciones", data=buf1,
                                   file_name="intervalos_posiciones.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                buf2 = io.BytesIO()
                with pd.ExcelWriter(buf2, engine='xlsxwriter') as w:
                    df_hab.to_excel(w, index=False, sheet_name="Habitaciones")
                buf2.seek(0)
                st.download_button("Descargar Excel habitaciones", data=buf2,
                                   file_name="intervalos_habitaciones.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                df_acc = pd.read_csv(
                    ACTIONS_PATH,
                    parse_dates=[['Fecha','Hora']],
                    dayfirst=True,              # porque tu formato es DD/MM/YYYY
                    encoding='utf-8'
                )
                # renombramos la columna Fecha_Hora a time para homogeneidad
                df_acc.rename(columns={'Fecha_Hora':'time'}, inplace=True)

                # 3.2) Filtramos en base al intervalo dt_i–dt_f
                df_acc = df_acc[(df_acc['time'] >= dt_i) & (df_acc['time'] <= dt_f)]

                if df_acc.empty:
                    st.warning("No hay acciones en ese rango.")
                else:
                    # extrae fecha y hora de la columna datetime
                    df_acc['Fecha'] = df_acc['time'].dt.strftime('%d/%m/%Y')
                    df_acc['Hora']   = df_acc['time'].dt.strftime('%H:%M:%S')

                    # ahora incluimos Fecha y Hora junto a la Descripción
                    df_desc = df_acc[['Descripción', 'Fecha', 'Hora']]

                    # 3.4) Volcar a Excel y botón de descarga
                    buf3 = io.BytesIO()
                    with pd.ExcelWriter(buf3, engine='xlsxwriter') as w:
                        df_desc.to_excel(w, index=False, sheet_name="Acciones")
                    buf3.seek(0)
                    st.download_button(
                        "Descargar Excel acciones",
                        data=buf3,
                        file_name="acciones_intervalo.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        except Exception as e:
            st.error(f"Error al generar Excel: {e}")

mapa_ph = col_left.empty()
graf_ph = col_left.empty()
tab_ph  = col_left.empty()

while True:
    data = obtener_ultimas_filas_csv(5)
    if not data.empty:
        last = data.iloc[-1]
        mapa_ph.image(dibujar_mapa(last), use_container_width=True)
        fig = dibujar_grafico_rssi(last)
        if fig: graf_ph.pyplot(fig)
        tab_ph.dataframe(data)
    else:
        tab_ph.dataframe(data)
    comprobar_alarmas()
    time.sleep(1)
