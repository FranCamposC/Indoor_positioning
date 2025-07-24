# pages/graficas_comparativas.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, time
import time as dttime
from utils.data_loader import generar_datos_diarios
from utils.helpers import CSV_PATH

st.title("📊 Gráficas Comparativas")
st.markdown("Selecciona rango de fechas para generar gráficas")



fi_graf = st.date_input("Fecha inicio", key="fi_graf")
hi_graf = st.time_input("Hora inicio", value=time(0, 0))
ff_graf = st.date_input("Fecha fin", key="ff_graf")
hf_graf = st.time_input("Hora fin", value=time(23, 59, 59))

generar = st.button("Generar gráfica")

if generar:
    dt_i_graf = datetime.combine(fi_graf, hi_graf)
    dt_f_graf = datetime.combine(ff_graf, hf_graf)

    if dt_i_graf > dt_f_graf:
        st.warning("La fecha de inicio no puede ser posterior a la de fin.")
    else:
        try:
            from io import BytesIO
            df_comp = generar_datos_diarios(CSV_PATH)
            df_comp["Fecha_dt"] = pd.to_datetime(df_comp["Fecha"])
            df_rango = df_comp[(df_comp["Fecha_dt"] >= dt_i_graf) & (df_comp["Fecha_dt"] <= dt_f_graf)]

            if df_rango.empty:
                st.warning("No hay datos en el rango seleccionado.")
            else:
                # Barras apiladas
                df_pos = df_rango.groupby(["Fecha", "Posicion"])["Duracion_segundos"].sum().unstack(fill_value=0) / 60
            col1, col2 = st.columns(2)

            with col1:
                fig_barras, ax = plt.subplots(figsize=(6, 4))        
                df_pos.plot(kind="bar", stacked=True, ax=ax)
                ax.set_title("Tiempo total por posición (min)")
                ax.set_ylabel("Minutos")
                ax.set_xlabel("Fecha")
                ax.legend(title="Posición")
                ax.grid(True)
                plt.xticks(rotation=45)
                st.pyplot(fig_barras, use_container_width=True)

            pie_cols = [col2, col1]   
            for i, fecha in enumerate(df_rango["Fecha"].unique()):
                df_fecha = df_rango[df_rango["Fecha"] == fecha]
                serie = df_fecha.groupby("Posicion")["Duracion_segundos"].sum() / 60
                if not serie.empty:
                    fig_pie, ax_pie = plt.subplots(figsize=(4, 4))
                    serie.plot.pie(ax=ax_pie, autopct="%1.1f%%")
                    ax_pie.set_ylabel("")
                    ax_pie.set_title(f"Uso por posición – {fecha}")
                    # Elegimos la columna intercalando 0,1,0,1…
                    pie_cols[i % 2].pyplot(fig_pie, use_container_width=True)
        except Exception as exc:
            st.error(f"Error al generar gráficas: {exc}")

if st.button("Volver al Menú"):
    st.switch_page("app.py")

