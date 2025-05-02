import datetime
import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
import io
from streamlit.runtime.scriptrunner import RerunException, RerunData

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------

# Para que la interfaz ocupe toda la pantalla
st.set_page_config(layout='centered')   

CSV_PATH = "src/logs/predicciones_xgboost.csv"
MAPA_PATH = "src/fotos/ParteDeArriba.png"

TIEMPO_VISIBLE_TRANSICIONES = 10  # segundos que se ven las líneas de transición
transiciones = []
ultima_habitacion = None
ultima_posicion = None

# Diccionario de posiciones ESP32
ESP_POSICIONES = {
    "ESP32_1": (100, 360),
    "ESP32_2": (100, 550),
    "ESP32_3": (300, 283),
    "ESP32_4": (50, 40),
    "ESP32_5": (50, 200),
    "ESP32_6": (300, 40),
    "ESP32_7": (550, 550),
    "ESP32_8": (750, 430),
    "ESP32_9": (550, 150),
    "ESP32_10": (990, 290),
}

# Diccionario para dibujar la posición estable en el mapa
POSICIONES = {
    "Cocina_Fregadero":      (70, 70),
    "Cocina_Vitro":          (70, 200),
    "Cocina_Frigorifico":    (320, 65),
    "Salon_Mesa":            (600, 150),
    "Salon_Sofa":            (900, 275),
    "Dormitorio_Cama":       (100, 525),
    "Dormitorio_Escritorio": (100, 400),
    "Baño_Lavabo":           (550, 500),
    "Baño_WC":               (900, 430),
    "Pasillo_Pasillo":       (300, 285),
}

# Mapa de posición a habitación (para el dibujo, no imprescindible)
POSICION_A_HABITACION = {
    "Fregadero":   "Cocina",
    "Vitro":       "Cocina",
    "Frigorifico": "Cocina",
    "Mesa":        "Salon",
    "Sofa":        "Salon",
    "Cama":        "Dormitorio",
    "Escritorio":  "Dormitorio",
    "Lavabo":      "Baño",
    "WC":          "Baño",
    "Pasillo":     "Pasillo"
}

# ----------------------------------------------------------------------
# FILTRO DE OUTLIERS (Combinaciones válidas)
# ----------------------------------------------------------------------
VALID_POSITIONS_BY_ROOM = {
    "Dormitorio":   ["Cama", "Escritorio"],
    "Cocina":       ["Vitro", "Frigorifico", "Fregadero"],
    "Salon":        ["Mesa", "Sofa"],
    "Baño":         ["WC", "Lavabo"],
    "Pasillo":      ["Pasillo"]
}

# ----------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------------------------------------
def format_timedelta(td):
    """Devuelve un string HH:MM:SS a partir de un pandas.Timedelta."""
    total_segundos = int(td.total_seconds())
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    segundos = total_segundos % 60
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

def obtener_ultimas_filas_csv(n=5):
    """Devuelve las últimas n filas del CSV (sin filtrar Duda/outliers)."""
    try:
        df = pd.read_csv(CSV_PATH)
        if not df.empty:
            return df.tail(n)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer el CSV: {e}")
        return pd.DataFrame()

def obtener_3_filas_validas():
    """
    Devuelve las 2 últimas filas que NO tengan 'Duda' (ni en habitacion ni en posicion).
    Si no hay 2 válidas, retorna None.

    (A pesar del nombre '3_filas_validas', aquí en tu código
     realmente se piden 2 últimas filas válidas consecutivas).
    """
    try:
        df = pd.read_csv(CSV_PATH)
        df = df[
            (df["habitacion_predicha"] != "Duda") &
            (df["posicion_predicha"]   != "Duda")
        ]
        # Además, filtramos outliers (combinaciones imposibles)
        df = df[df.apply(
            lambda row: row["posicion_predicha"] in VALID_POSITIONS_BY_ROOM.get(row["habitacion_predicha"], []),
            axis=1
        )]
        if df.empty:
            return None

        ultimas_2 = df.tail(2)
        if len(ultimas_2) < 2:
            return None
        return ultimas_2
    except Exception as e:
        st.error(f"Error al leer el CSV: {e}")
        return None

def dibujar_esps(draw, fila):
    """Dibuja cada ESP32 con un color en función del RSSI."""
    for esp, (x, y) in ESP_POSICIONES.items():
        if esp in fila:
            rssi = fila[esp]
            # Verde si rssi >= -75, amarillo entre -95 y -76, rojo menos de -95
            color = "green" if rssi >= -75 else "yellow" if -95 <= rssi <= -76 else "red"
            r = 6
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

def dibujar_transiciones(base_image):
    """
    Dibuja líneas de transición que desaparecen tras TIEMPO_VISIBLE_TRANSICIONES.
    """
    overlay = Image.new("RGBA", base_image.size, (255, 255, 255, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    now = time.time()
    for (x1, y1, x2, y2, t) in list(transiciones):
        elapsed = now - t
        if elapsed > TIEMPO_VISIBLE_TRANSICIONES:
            transiciones.remove((x1, y1, x2, y2, t))
            continue

        # Opacidad decrece en la segunda mitad del tiempo
        if elapsed < TIEMPO_VISIBLE_TRANSICIONES / 2:
            alpha = 255
        else:
            factor = 1 - (elapsed - (TIEMPO_VISIBLE_TRANSICIONES / 2)) / (TIEMPO_VISIBLE_TRANSICIONES / 2)
            alpha = int(255 * factor)

        color = (255, 0, 0, alpha)
        draw_overlay.line([(x1, y1), (x2, y2)], fill=color, width=3)

    return Image.alpha_composite(base_image, overlay)

def dibujar_grafico_rssi(fila):
    """Bar chart con los RSSI de la última fila."""
    if fila.empty:
        return None

    rssi_values = {}
    for esp in fila.index:
        if "ESP32_" in esp:
            val = fila[esp]
            val = max(val, -100)  # límite inferior
            rssi_values[esp] = 100 + val  # shift para que -100 -> 0

    fig, ax = plt.subplots(figsize=(8, 2.5))
    ax.bar(rssi_values.keys(), rssi_values.values(), color='blue')
    ax.set_xlabel("ESP32")
    ax.set_ylabel("Intensidad RSSI (dBm)")
    ax.set_title("Intensidad de señal de ESP32 en tiempo real")
    ax.set_ylim(0, 100)

    # Se definen primero los 'ticks' de forma explícita,
    # y luego las etiquetas para evitar el warning de Matplotlib
    x_positions = range(len(rssi_values.keys()))
    ax.set_xticks(x_positions)
    ax.set_xticklabels(rssi_values.keys(), rotation=45)

    ax.grid(axis="y", linestyle="--", alpha=0.7)
    return fig

def posicion_estable():
    """
    Revisa las últimas filas válidas (sin 'Duda' ni outliers).
    Si las 2 últimas coinciden en habitacion_predicha y posicion_predicha,
    devolvemos (habitacion, posicion).
    """
    validas = obtener_3_filas_validas()
    if validas is None:
        return None

    habs = validas["habitacion_predicha"].unique()
    poss = validas["posicion_predicha"].unique()
    if len(habs) == 1 and len(poss) == 1:
        return (habs[0], poss[0])
    return None

def dibujar_mapa(fila):
    """
    Dibuja el mapa con la última posición estable (si la hay).
    """
    global ultima_habitacion, ultima_posicion, transiciones

    base_img = Image.open(MAPA_PATH).convert("RGBA")
    draw = ImageDraw.Draw(base_img)

    # Dibuja ESPs
    dibujar_esps(draw, fila)

    # Averigua posición estable
    nueva_pos = posicion_estable()
    old_hab, old_pos = ultima_habitacion, ultima_posicion

    if nueva_pos is not None:
        ultima_habitacion, ultima_posicion = nueva_pos

    # Obtiene coords
    if ultima_habitacion and ultima_posicion:
        coords = POSICIONES.get(f"{ultima_habitacion}_{ultima_posicion}", (0, 0))
    else:
        coords = (0, 0)

    # Transición si hay cambio
    if coords != (0, 0) and old_hab and old_pos:
        old_coords = POSICIONES.get(f"{old_hab}_{old_pos}", (0, 0))
        if old_coords != (0, 0) and old_coords != coords:
            transiciones.append((*old_coords, coords[0], coords[1], time.time()))

    # Dibuja punto azul
    if coords != (0, 0):
        r = 14
        x, y = coords
        draw.ellipse([x - r, y - r, x + r, y + r], fill="blue")

    return dibujar_transiciones(base_img)

# ----------------------------------------------------------------------
# FUNCIÓN PARA GENERAR INTERVALOS
# ----------------------------------------------------------------------
def generar_intervalos_separados(CSV_PATH, dt_inicio, dt_fin, min_filas=3):
    """
    Devuelve dos DataFrames:
      1) df_posiciones: intervalos agrupados consecutivamente por (Habitación, Posición).
         *Solo* se considera válido un intervalo si contiene >= min_filas consecutivas.
      2) df_habitaciones: intervalos agrupados consecutivamente por Habitación (a partir de los intervalos válidos).
    """

    # 1) Leemos el CSV y parseamos tiempos
    df = pd.read_csv(CSV_PATH)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df.dropna(subset=["time"], inplace=True)

    # 2) Quitamos "Duda" y outliers
    df = df[
        (df["habitacion_predicha"] != "Duda") &
        (df["posicion_predicha"]   != "Duda")
    ]
    df = df[
        df.apply(
            lambda row: row["posicion_predicha"] 
                        in VALID_POSITIONS_BY_ROOM.get(row["habitacion_predicha"], []),
            axis=1
        )
    ]

    # 3) Ordenamos por tiempo
    df.sort_values(by="time", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # --------------------------------------------------------------------
    # CREAR INTERVALOS POR (Habitación, Posición) CON >= min_filas CONSECUTIVAS
    # --------------------------------------------------------------------
    intervalos = []

    clave_actual = None
    inicio_actual = None
    # Contador de filas consecutivas con la misma clave
    count_consecutivo = 0

    for i, row in df.iterrows():
        hab = row["habitacion_predicha"]
        pos = row["posicion_predicha"]
        t   = row["time"]

        clave = (hab, pos)

        # Si es la primera fila
        if clave_actual is None:
            clave_actual = clave
            inicio_actual = t
            count_consecutivo = 1
        else:
            if clave == clave_actual:
                # Seguimos en la misma combinación
                count_consecutivo += 1
            else:
                # Ha cambiado la combinación
                # Comprobamos si el bloque anterior cumplía el mínimo
                if count_consecutivo >= min_filas:
                    # Lo registramos
                    h_prev, p_prev = clave_actual
                    intervalos.append({
                        "Habitacion":      h_prev,
                        "Posicion":        p_prev,
                        "Fecha_Entrada_dt": inicio_actual,
                        "Fecha_Salida_dt":  t
                    })

                # Empezamos un nuevo bloque
                clave_actual = clave
                inicio_actual = t
                count_consecutivo = 1

    # Al terminar el bucle, cerramos el último bloque
    if clave_actual is not None and inicio_actual is not None:
        if count_consecutivo >= min_filas:
            h_prev, p_prev = clave_actual
            t_fin_csv = df["time"].iloc[-1]
            intervalos.append({
                "Habitacion":      h_prev,
                "Posicion":        p_prev,
                "Fecha_Entrada_dt": inicio_actual,
                "Fecha_Salida_dt":  t_fin_csv
            })

    # Convertimos intervalos a DataFrame
    df_posiciones = pd.DataFrame(intervalos)
    if df_posiciones.empty:
        # Devuelve vacío si nada cumplió el mínimo
        return pd.DataFrame(), pd.DataFrame()

    # 4) Filtramos por [dt_inicio, dt_fin] y recortamos
    mask = (df_posiciones["Fecha_Salida_dt"]   >= dt_inicio) & \
           (df_posiciones["Fecha_Entrada_dt"] <= dt_fin)
    df_posiciones = df_posiciones[mask].copy()
    df_posiciones["Fecha_Entrada_dt"] = df_posiciones["Fecha_Entrada_dt"].clip(
        lower=dt_inicio, 
        upper=dt_fin
    )
    df_posiciones["Fecha_Salida_dt"]  = df_posiciones["Fecha_Salida_dt"].clip(
        lower=dt_inicio, 
        upper=dt_fin
    )

    # Añadimos columna "Tiempo_en_la_posicion_td"
    df_posiciones["Tiempo_en_la_posicion_td"] = (
        df_posiciones["Fecha_Salida_dt"] - df_posiciones["Fecha_Entrada_dt"]
    )

    # --------------------------------------------------------------------
    # AGRUPAR ESOS INTERVALOS POR HABITACIÓN (CONSECUTIVOS)
    # --------------------------------------------------------------------
    df_posiciones.reset_index(drop=True, inplace=True)

    if df_posiciones.empty:
        # Si después del filtro por fecha queda vacío, terminamos
        return pd.DataFrame(), pd.DataFrame()

    chunks = []
    chunk_start_idx = 0
    hab_actual = df_posiciones.loc[0, "Habitacion"]
    hab_chunk_start = df_posiciones.loc[0, "Fecha_Entrada_dt"]

    for i in range(1, len(df_posiciones)):
        row_hab = df_posiciones.loc[i, "Habitacion"]
        if row_hab != hab_actual:
            # Cerramos chunk anterior
            hab_chunk_end = df_posiciones.loc[i-1, "Fecha_Salida_dt"]
            chunks.append((chunk_start_idx, i-1, hab_actual, hab_chunk_start, hab_chunk_end))

            # Empezamos uno nuevo
            chunk_start_idx = i
            hab_actual = row_hab
            hab_chunk_start = df_posiciones.loc[i, "Fecha_Entrada_dt"]

    # Cerrar último chunk
    hab_chunk_end = df_posiciones.loc[len(df_posiciones)-1, "Fecha_Salida_dt"]
    chunks.append((chunk_start_idx, len(df_posiciones)-1, hab_actual, hab_chunk_start, hab_chunk_end))

    # Construimos df_habitaciones
    lista_hab = []
    for (start_i, end_i, hab, c_start_dt, c_end_dt) in chunks:
        lista_hab.append({
            "Habitacion": hab,
            "Fecha_Entrada_dt": c_start_dt,
            "Fecha_Salida_dt":  c_end_dt,
            "Tiempo_en_la_habitacion_td": c_end_dt - c_start_dt
        })

    df_habitaciones = pd.DataFrame(lista_hab)
    if df_habitaciones.empty:
        return df_posiciones, pd.DataFrame()

    # --------------------------------------------------------------------
    # FORMATEO FINAL (columnas de texto)
    # --------------------------------------------------------------------
    # df_posiciones
    df_posiciones["Fecha_Entrada"] = df_posiciones["Fecha_Entrada_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_posiciones["Fecha_Salida"]  = df_posiciones["Fecha_Salida_dt"].dt.strftime("%d/%m/%Y %H:%M:%S")

    df_posiciones["Tiempo_en_la_posicion"] = df_posiciones["Tiempo_en_la_posicion_td"].apply(
        lambda td: format_timedelta(td) if pd.notnull(td) else ""
    )

    df_posiciones = df_posiciones[[
        "Habitacion",
        "Posicion",
        "Fecha_Entrada",
        "Fecha_Salida",
        "Tiempo_en_la_posicion"
    ]]

    # df_habitaciones
    df_habitaciones["Fecha_Entrada"] = df_habitaciones["Fecha_Entrada_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_habitaciones["Fecha_Salida"]  = df_habitaciones["Fecha_Salida_dt"].dt.strftime("%d/%m/%y %H:%M:%S")
    df_habitaciones["Tiempo_en_la_habitacion"] = df_habitaciones["Tiempo_en_la_habitacion_td"].apply(
        lambda td: format_timedelta(td) if pd.notnull(td) else ""
    )

    df_habitaciones = df_habitaciones[[
        "Habitacion",
        "Fecha_Entrada",
        "Fecha_Salida",
        "Tiempo_en_la_habitacion"
    ]]

    return df_posiciones, df_habitaciones

# ----------------------------------------------------------------------
# AÑADIMOS FUNCIÓN PARA COMPROBAR ALARMAS
# ----------------------------------------------------------------------
# Añadir esta función al principio (sin cambiar lo demás)
def lanzar_alarma(mensaje):
    js_code = f"<script>alert('Localhost dice: Alarma: {mensaje}');</script>"
    current_time = time.time()
    last_alarm = st.session_state.get('last_alarm_time', 0)

    if current_time - last_alarm > 60:
        st.components.v1.html(js_code)
        st.session_state['last_alarm_time'] = current_time

# Al principio del script inicializa session_state
if 'last_alarm_time' not in st.session_state:
    st.session_state['last_alarm_time'] = 0

# Modifica solo esta función en tu código:
def comprobar_alarmas():
    """
    Comprueba las alarmas definidas (hora límite salida Dormitorio,
    hora límite entrada Dormitorio y tiempo máximo en Baño),
    basándose en la posición estable (sin 'Duda') y la hora actual.
    """

    pos_estable = posicion_estable()
    if pos_estable is None:
        return

    habitacion, _ = pos_estable

    ahora = datetime.datetime.now().time()
    hora_lim_salida = st.session_state.get("hora_limite_salida_dormitorio", datetime.time(9, 0, 0))
    hora_lim_entrada = st.session_state.get("hora_limite_entrada_dormitorio", datetime.time(23, 0, 0))
    tiempo_lim_bano = st.session_state.get("tiempo_limite_bano", 15)

    # ALARMA 1: No se ha levantado (pasa de la hora limite de salida y sigue en Dormitorio)
    if ahora > hora_lim_salida and pos_estable[0] == "Dormitorio":
        lanzar_alarma("¡No se ha levantado, va llegar tarde!")

    # ALARMA 2: Aún no se ha acostado
    if ahora > hora_lim_entrada and pos_estable[0] != "Dormitorio":
        lanzar_alarma("¡Aún no se ha acostado!")

    # ALARMA 3: Límite de tiempo en Baño
    if pos_estable[0] == "Baño":
        if st.session_state["tiempo_entrada_bano"] is None:
            st.session_state["tiempo_entrada_bano"] = datetime.datetime.now()
        else:
            tiempo_en_bano = (datetime.datetime.now() - st.session_state["tiempo_entrada_bano"]).total_seconds() / 60.0
            if tiempo_en_bano > tiempo_lim_bano:
                lanzar_alarma("¡Lleva demasiado tiempo en el baño!")
    else:
        st.session_state["tiempo_entrada_bano"] = None
# ----------------------------------------------------------------------
# STREAMLIT APP
# ----------------------------------------------------------------------
# Inicializamos ciertas variables en session_state si no existen
if "hora_limite_salida_dormitorio" not in st.session_state:
    st.session_state["hora_limite_salida_dormitorio"] = datetime.time(9, 0, 0)
if "hora_limite_entrada_dormitorio" not in st.session_state:
    st.session_state["hora_limite_entrada_dormitorio"] = datetime.time(23, 0, 0)
if "tiempo_limite_bano" not in st.session_state:
    st.session_state["tiempo_limite_bano"] = 15
if "tiempo_entrada_bano" not in st.session_state:
    st.session_state["tiempo_entrada_bano"] = None
if "mostrar_alarmas" not in st.session_state:
    st.session_state["mostrar_alarmas"] = False

st.title("Posicionamiento Indoor")
st.write("Visualización en tiempo real con tiempos de posición y habitación.")

# Botón para mostrar/ocultar configuración de alarmas
if st.button("ALARMAS"):
    st.session_state["mostrar_alarmas"] = not st.session_state["mostrar_alarmas"] 


# Si se ha pulsado el botón, mostramos el formulario de configuración
if st.session_state["mostrar_alarmas"]:
    st.subheader("Configuración de ALARMAS")
    st.write("Establece aquí las horas límite y el tiempo máximo en el baño:")

    # --- Iniciamos el formulario ---
    with st.form("form_alarmas"):
        nueva_hora_salida = st.time_input(
            "Hora límite para SALIR del dormitorio (levantarse)",
            value=st.session_state["hora_limite_salida_dormitorio"]
        )
        nueva_hora_entrada = st.time_input(
            "Hora límite para ENTRAR al dormitorio (acostarse)",
            value=st.session_state["hora_limite_entrada_dormitorio"]
        )
        nuevo_tiempo_bano = st.number_input(
            "Tiempo máximo en el baño (minutos)",
            min_value=1,
            max_value=180,
            value=st.session_state["tiempo_limite_bano"]
        )

        # Botón dentro del formulario para guardar
        submitted = st.form_submit_button("Guardar alarmas")

        if submitted:
            st.session_state["hora_limite_salida_dormitorio"] = nueva_hora_salida
            st.session_state["hora_limite_entrada_dormitorio"] = nueva_hora_entrada
            st.session_state["tiempo_limite_bano"] = nuevo_tiempo_bano
            st.success("¡Nuevas alarmas guardadas!")

# Creamos columnas para el mapa y la parte de descargas
col_left, col_right = st.columns([3,1])

with col_right:
    st.subheader("Descargar intervalos con tiempos")

    fecha_inicio = st.date_input("Fecha inicio", value=datetime.date(2025, 2, 4))
    hora_inicio = st.time_input("Hora inicio", value=datetime.time(0, 0, 0))
    dt_inicio = datetime.datetime.combine(fecha_inicio, hora_inicio)

    fecha_fin = st.date_input("Fecha fin", value=datetime.date(2025, 2, 4))
    hora_fin = st.time_input("Hora fin", value=datetime.time(23, 59, 59))
    dt_fin = datetime.datetime.combine(fecha_fin, hora_fin)

    if st.button("Guardar archivo"):
        try:
            df_pos, df_hab = generar_intervalos_separados(CSV_PATH, dt_inicio, dt_fin)
            if df_pos.empty and df_hab.empty:
                st.warning("No se han encontrado intervalos válidos en ese rango.")
            else:
                # Guardar df_pos en un Excel
                output_pos = io.BytesIO()
                with pd.ExcelWriter(output_pos, engine='xlsxwriter') as writer:
                    df_pos.to_excel(writer, index=False, sheet_name="Intervalos")
                output_pos.seek(0)

                st.download_button(
                    label="Descargar Excel posiciones",
                    data=output_pos,
                    file_name="intervalos_posiciones.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # Guardar df_hab en otro Excel
                output_hab = io.BytesIO()
                with pd.ExcelWriter(output_hab, engine='xlsxwriter') as writer:
                    df_hab.to_excel(writer, index=False, sheet_name="Habitaciones")
                output_hab.seek(0)

                st.download_button(
                    label="Descargar Excel Habitaciones",
                    data=output_hab,
                    file_name="intervalos_habitaciones.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        except Exception as e:
            st.error(f"Error al generar el Excel: {e}")

mapa_placeholder = col_left.empty()
grafico_placeholder = col_left.empty()
tabla_placeholder = col_left.empty()

# Bucle "tiempo real" para refrescar:
while True:
    raw_data = obtener_ultimas_filas_csv(n=5)

    if not raw_data.empty:
        ultima_fila = raw_data.iloc[-1]
        mapa = dibujar_mapa(ultima_fila)
        mapa_placeholder.image(mapa, caption="Estado del posicionamiento", use_container_width=True)

        grafico = dibujar_grafico_rssi(ultima_fila)
        if grafico:
            grafico_placeholder.pyplot(grafico)

        tabla_placeholder.dataframe(raw_data)
    else:
        tabla_placeholder.dataframe(raw_data)

    # Cada ciclo comprobamos si salta alguna alarma
    comprobar_alarmas()

    # Pequeña pausa de 1 segundo para que no se dispare el bucle sin control
    time.sleep(1)
