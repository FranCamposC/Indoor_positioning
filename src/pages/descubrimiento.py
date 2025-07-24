import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from graphviz import Digraph
from utils.helpers import CSV_PATH

st.set_page_config(page_title="Descubrimiento", layout="wide")

st.title("📊 Descubrimiento")
st.markdown("Compara recorridos de varios días y visualiza la secuencia de habitaciones estables.")

fi = st.date_input("Fecha inicio")
ff = st.date_input("Fecha fin")

generar = st.button("Generar EventLog XES")

def detectar_habitaciones_estables(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["habitacion_predicha"] != "Duda"].sort_values("time").reset_index(drop=True)

    secuencia = []
    habitacion_actual = None
    inicio_actual = None

    for _, fila in df.iterrows():
        h, t = fila["habitacion_predicha"], fila["time"]
        if habitacion_actual is None:
            habitacion_actual = h
            inicio_actual = t
        elif h == habitacion_actual:
            continue
        else:
            duracion = (t - inicio_actual).total_seconds() / 60
            if duracion >= 1:  # mínimo 1 minuto
                secuencia.append({
                    "habitacion": habitacion_actual,
                    "inicio": inicio_actual,
                    "fin": t,
                    "duracion_min": round(duracion, 1),
                })
            habitacion_actual = h
            inicio_actual = t

    # Último tramo
    if habitacion_actual and inicio_actual:
        duracion = (df.iloc[-1]["time"] - inicio_actual).total_seconds() / 60
        if duracion >= 1:
            secuencia.append({
                "habitacion": habitacion_actual,
                "inicio": inicio_actual,
                "fin": df.iloc[-1]["time"],
                "duracion_min": round(duracion, 1),
            })

    return pd.DataFrame(secuencia)

def generar_xes(df_filtrado):
    df_filtrado = df_filtrado[df_filtrado["habitacion_predicha"] != "Duda"]
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")


    xes = '<?xml version="1.0" encoding="UTF-8" ?>\n'
    xes += '<log xes.version="1.0" xes.features="nested-attributes" openxes.version="1.0RC7" xmlns="http://www.xes-standard.org/">\n'

    for fecha, grupo in df_filtrado.groupby("fecha"):
        secuencia = detectar_habitaciones_estables(grupo)
        if len(secuencia) < 1:
            continue
        xes += '  <trace>\n'
        xes += f'    <string key="concept:name" value="{fecha}" />\n'
        for _, fila in secuencia.iterrows():
            xes += '    <event>\n'
            xes += f'      <string key="concept:name" value="{fila["habitacion"]}" />\n'
            xes += f'      <date key="time:timestamp" value="{fila["inicio"].isoformat()}" />\n'
            xes += '    </event>\n'
        xes += '  </trace>\n'
    xes += '</log>'
    return xes

if generar:
    try:
        df = pd.read_csv(CSV_PATH)
        df["time"] = pd.to_datetime(df["time"],format="%d/%m/%Y %H:%M:%S", errors="coerce")
        df.dropna(subset=["time"], inplace=True)

        df = df[df["habitacion_predicha"] != "Duda"]
        df = df[(df["time"] >= datetime.combine(fi, datetime.min.time())) &
                (df["time"] <= datetime.combine(ff, datetime.max.time()))]

        if df.empty:
            st.warning("⚠️ No hay datos válidos en el rango seleccionado.")
        else:
            st.subheader("🗓 Visualización diaria de habitaciones estables")
            df["fecha"] = df["time"].dt.date
            dias_unicos = df["fecha"].unique()

            for dia in dias_unicos:
                st.markdown(f"### 📅 {dia.strftime('%d/%m/%Y')}")
                df_dia = df[df["fecha"] == dia]
                secuencia = detectar_habitaciones_estables(df_dia)

                if len(secuencia) < 2:
                    st.info("No hay suficientes cambios estables en este día.")
                    continue

                dot = Digraph()

                for _, fila in secuencia.iterrows():
                    dot.node(fila["habitacion"], f'{fila["habitacion"]}\n({fila["duracion_min"]} min)')

                for i in range(len(secuencia) - 1):
                    origen = secuencia.iloc[i]["habitacion"]
                    destino = secuencia.iloc[i + 1]["habitacion"]
                    dot.edge(origen, destino)

                st.graphviz_chart(dot)

            # Botón de descarga XES
            xes_string = generar_xes(df)
            if xes_string.strip():
                b = BytesIO()
                b.write(xes_string.encode("utf-8"))
                b.seek(0)
                st.subheader("📥 Exportar log en formato XES")
                st.download_button(
                    label="Descargar archivo XES",
                    data=b,
                    file_name="eventlog_habitaciones.xes",
                    mime="application/xml",
                    use_container_width=True
                )
            else:
                st.info("No se pudo generar el archivo XES porque no hay datos suficientes.")

    except Exception as e:
        st.error(f"❌ Error: {e}")

if st.button("Volver al Menú"):
    st.switch_page("app.py")
