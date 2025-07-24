# pages/historial.py
import streamlit as st
from datetime import datetime, time, timedelta
import time as dttime
from io import BytesIO
import pandas as pd
import matplotlib.pyplot as plt
from utils.helpers import ACTIONS_PATH, CSV_PATH, VALID_POSITIONS_BY_ROOM
from utils.data_loader import generar_intervalos

st.title("📂 Descargar Historial")
st.markdown("Selecciona rango de fechas para exportar a Excel")

fi = st.date_input("Fecha inicio")
hi = st.time_input("Hora inicio", value=time(0, 0))
ff = st.date_input("Fecha fin")
hf = st.time_input("Hora fin", value=time(23, 59, 59))

descargar = st.button("Generar fichero")

def generar_intervalos_posicion(path, dt_inicio, dt_fin):
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df = df[(df["time"] >= dt_inicio) & (df["time"] <= dt_fin)]

    # Validar datos válidos
    df = df[df["habitacion_predicha"] != "Duda"]
    df = df.sort_values("time").reset_index(drop=True)

    intervalos = []
    posicion_actual, start_time = None, None

    for _, fila in df.iterrows():
        pos, t = fila["posicion_predicha"], fila["time"]

        if posicion_actual is None:
            # Iniciar primera posición
            posicion_actual, start_time = pos, t
        elif pos == posicion_actual:
            # Seguimos en la misma posición → actualizar hora fin
            continue
        else:
            # Cambio de posición → guardar el intervalo actual
            duracion = (t - start_time).total_seconds()
            if duracion > 5:
                intervalos.append({
                    "Inicio": start_time,
                    "Fin": t,
                    "Posicion": posicion_actual,
                    "Duracion_segundos": duracion,
                })
            # Reiniciar para nueva posición
            posicion_actual, start_time = pos, t

    # Guardar el último intervalo
    if posicion_actual:
        duracion = (df.iloc[-1]["time"] - start_time).total_seconds()
        if duracion > 5:
            intervalos.append({
                "Inicio": start_time,
                "Fin": df.iloc[-1]["time"],
                "Posicion": posicion_actual,
                "Duracion_segundos": duracion,
            })

    return pd.DataFrame(intervalos)

if descargar:
    dt_i = datetime.combine(fi, hi)
    dt_f = datetime.combine(ff, hf)
    if dt_i > dt_f:
        st.warning("La fecha de inicio no puede ser posterior a la de fin.")
    else:
        try:
            # Cargar datos
            df = pd.read_csv(CSV_PATH)
            df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
            df.dropna(subset=["time"], inplace=True)
            df = df[
                (df["habitacion_predicha"] != "Duda") &
                (df["posicion_predicha"] != "Duda")
            ]
            df = df[
                df.apply(
                    lambda r: r["posicion_predicha"]
                    in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []),
                    axis=1,
                )
            ]

            # Filtrar por rango
            df_rango = df[(df["time"] >= dt_i) & (df["time"] <= dt_f)]

            

            # Intervalos por posición
            df_pos = generar_intervalos_posicion(CSV_PATH, dt_i, dt_f)
            df_pos = df_pos[df_pos["Posicion"] != "Duda"]
            df_pos = df_pos[df_pos["Duracion_segundos"] >= 16].reset_index(drop=True)
            if not df_pos.empty:
                # (opcional) ordenar por inicio, por si llegaran desordenados
                df_pos = df_pos.sort_values("Inicio").reset_index(drop=True)

                # NUEVO → fusionar solo los intervalos consecutivos de la misma posición
                df_pos["grupo"] = (df_pos["Posicion"] != df_pos["Posicion"].shift()).cumsum()
                df_pos = (
                    df_pos.groupby(["grupo", "Posicion"], as_index=False)
                        .agg(
                            Inicio=("Inicio", "min"),
                            Fin=("Fin", "max"),
                            Duracion_segundos=("Duracion_segundos", "sum"),
                        )
                        .drop(columns="grupo")
                )
                df_pos["Fecha_Entrada"] = df_pos["Inicio"].dt.strftime("%d/%m/%Y %H:%M:%S")
                df_pos["Fecha_Salida"] = df_pos["Fin"].dt.strftime("%d/%m/%Y %H:%M:%S")
                df_pos["Tiempo_en_la_posicion"] = df_pos["Duracion_segundos"].apply(lambda x: str(timedelta(seconds=x)))
                df_pos = df_pos[["Posicion", "Fecha_Entrada", "Fecha_Salida", "Tiempo_en_la_posicion"]]

            # Intervalos por habitación (resumidos)

            df_hab = generar_intervalos(CSV_PATH, dt_i, dt_f)

            df_hab = df_hab[df_hab["Duracion_segundos"] >= 35].reset_index(drop=True)
            if not df_hab.empty:
                # ordenar por inicio por si acaso
                df_hab = df_hab.sort_values("Inicio").reset_index(drop=True)

                # Cada vez que cambia la habitación empezamos un grupo nuevo
                df_hab["grupo"] = (df_hab["Habitacion"] != df_hab["Habitacion"].shift()).cumsum()

                # Agrupamos por 'grupo' y 'Habitacion'
                df_hab = (
                    df_hab.groupby(["grupo", "Habitacion"], as_index=False)
                        .agg(
                            Inicio=("Inicio", "min"),
                            Fin=("Fin", "max"),
                            Duracion_segundos=("Duracion_segundos", "sum"),
                        )
                        .drop(columns="grupo")       # ya no lo necesitamos
                )


            df_hab["Fecha_Entrada"] = df_hab["Inicio"].dt.strftime("%d/%m/%Y %H:%M:%S")
            df_hab["Fecha_Salida"] = df_hab["Fin"].dt.strftime("%d/%m/%Y %H:%M:%S")
            df_hab["Tiempo_en_la_habitacion"] = df_hab["Duracion_segundos"].apply(lambda x: str(timedelta(seconds=x)))
            df_hab = df_hab[["Habitacion", "Fecha_Entrada", "Fecha_Salida", "Tiempo_en_la_habitacion"]]

            # Acciones detectadas
            try:
                df_acciones = pd.read_csv(ACTIONS_PATH)
                df_acciones["time"] = pd.to_datetime(df_acciones["time"], errors="coerce")
                df_acciones = df_acciones[(df_acciones["time"] >= dt_i) & (df_acciones["time"] <= dt_f)]
            except Exception:
                df_acciones = pd.DataFrame()

            # Mostrar resumen
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Intervalos de Posición", len(df_pos))
            with col2:
                st.metric("Intervalos de Habitación", len(df_hab))
            with col3:
                st.metric("Acciones Detectadas", len(df_acciones))

            # Pestañas de descarga
            tab1, tab2, tab3 = st.tabs(["📁 Posiciones", "🏠 Habitaciones", "⚙️ Acciones"])

            with tab1:
                if not df_pos.empty:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df_pos.to_excel(writer, index=False, sheet_name="Intervalos por Posición")
                    data = output.getvalue()
                    st.download_button(
                        "Descargar Intervalos de Posición",
                        data=data,
                        file_name="intervalos_posicion.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.dataframe(df_pos, use_container_width=True)
                else:
                    st.info("No hay datos de posiciones en este rango.")

            with tab2:
                if not df_hab.empty:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df_hab.to_excel(writer, index=False, sheet_name="Habitaciones")
                    data = output.getvalue()
                    st.download_button(
                        "Descargar Intervalos de Habitación",
                        data=data,
                        file_name="intervalos_habitacion.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.dataframe(df_hab, use_container_width=True)
                else:
                    st.info("No hay datos de habitaciones en este rango.")

            with tab3:
                if not df_acciones.empty:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df_acciones.to_excel(writer, index=False, sheet_name="Acciones")
                    data = output.getvalue()
                    st.download_button(
                        "Descargar Acciones Detectadas",
                        data=data,
                        file_name="acciones_detectadas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.dataframe(df_acciones, use_container_width=True)
                else:
                    st.info("No hay acciones detectadas en este rango.")

        except Exception as exc:
            st.error(f"❌ Error al generar Excel: {exc}")

if st.button("Volver al Menú"):
    st.switch_page("app.py")
