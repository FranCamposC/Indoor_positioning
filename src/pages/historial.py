# pages/historial.py
import streamlit as st
from datetime import datetime, time, timedelta
from io import BytesIO
import pandas as pd

from utils.helpers import ACTIONS_PATH, CSV_PATH
from utils.data_loader import generar_intervalos   # ← ya la tenías

st.set_page_config(page_title='Historial', page_icon='📂', layout='wide')
st.title('📂 Descargar Historial')
st.markdown('Selecciona rango de fechas para exportar a Excel')

# ─────────────── Parámetros de filtrado ───────────────
fi = st.date_input('Fecha inicio')
hi = st.time_input('Hora inicio', value=time(0, 0))
ff = st.date_input('Fecha fin')
hf = st.time_input('Hora fin',  value=time(23, 59, 59))
generar = st.button('Generar fichero')

# ─────────────── Helpers ───────────────
def generar_intervalos_posicion(path: str,
                                dt_inicio: datetime,
                                dt_fin: datetime) -> pd.DataFrame:
    """Intervalos brutos por posición (sin fusionar/filtrar)."""
    df = pd.read_csv(path)
    df['time'] = pd.to_datetime(df['time'],
                                format='%d/%m/%Y %H:%M:%S',
                                errors='coerce')
    df = df[(df['time'] >= dt_inicio) & (df['time'] <= dt_fin)]

    # Datos válidos solamente
    df = df[(df['habitacion_predicha'] != 'Duda') &
            (df['posicion_predicha']   != 'Duda')]

    df = df.sort_values('time').reset_index(drop=True)

    intervalos, pos_actual, start = [], None, None
    for _, r in df.iterrows():
        pos, t = r['posicion_predicha'], r['time']
        if pos_actual is None:
            pos_actual, start = pos, t
        elif pos == pos_actual:
            continue
        else:
            intervalos.append(
                dict(Inicio=start,
                     Fin=t,
                     Posicion=pos_actual,
                     Duracion_segundos=(t-start).total_seconds())
            )
            pos_actual, start = pos, t

    if pos_actual is not None:          # último tramo
        intervalos.append(
            dict(Inicio=start,
                 Fin=df.iloc[-1]['time'],
                 Posicion=pos_actual,
                 Duracion_segundos=(df.iloc[-1]['time']-start).total_seconds())
        )

    return pd.DataFrame(intervalos)


def fusionar_intervalos(df_int: pd.DataFrame,
                        etiqueta: str,
                        umbral: int) -> pd.DataFrame:
    """
    Elimina intervalos < umbral y vuelve a fusionar los consecutivos
    con la misma etiqueta.
    """
    if df_int.empty:
        return df_int

    df = df_int[df_int['Duracion_segundos'] >= umbral].copy()
    if df.empty:
        return df

    df = df.sort_values('Inicio').reset_index(drop=True)
    df['grupo'] = (df[etiqueta] != df[etiqueta].shift()).cumsum()

    df = (df.groupby(['grupo', etiqueta], as_index=False)
            .agg(Inicio=('Inicio', 'min'),
                 Fin   =('Fin',    'max'))
            .drop(columns='grupo'))

    df['Duracion_segundos'] = (df['Fin'] - df['Inicio']).dt.total_seconds()
    return df


# ─────────────── Ejecución ───────────────
if generar:
    dt_i, dt_f = datetime.combine(fi, hi), datetime.combine(ff, hf)
    if dt_i > dt_f:
        st.warning('La fecha de inicio no puede ser posterior a la de fin.')
        st.stop()

    try:
        # ---------- POSICIONES ----------
        df_pos_raw = generar_intervalos_posicion(CSV_PATH, dt_i, dt_f)
        df_pos     = fusionar_intervalos(df_pos_raw, 'Posicion', umbral=46)

        # ---------- HABITACIONES ----------
        df_hab_raw = generar_intervalos(CSV_PATH, dt_i, dt_f)  # ya existente
        df_hab_raw = df_hab_raw[df_hab_raw['Habitacion'] != 'Duda']
        df_hab     = fusionar_intervalos(df_hab_raw, 'Habitacion', umbral=70)

        # ---------- ACCIONES ----------
        try:
            df_acc = pd.read_csv(ACTIONS_PATH)
            df_acc['time'] = pd.to_datetime(df_acc['time'], errors='coerce')
            df_acc = df_acc[(df_acc['time'] >= dt_i) & (df_acc['time'] <= dt_f)]
        except Exception:
            df_acc = pd.DataFrame()

        # ---------- Métricas resumen ----------
        c1, c2, c3 = st.columns(3)
        c1.metric('Intervalos de Posición',   len(df_pos))
        c2.metric('Intervalos de Habitación', len(df_hab))
        c3.metric('Acciones Detectadas',      len(df_acc))

        # ---------- Tabs ----------
        tab_pos, tab_hab, tab_acc = st.tabs(['📁 Posiciones',
                                             '🏠 Habitaciones',
                                             '⚙️ Acciones'])

        # POSICIONES
        with tab_pos:
            if df_pos.empty:
                st.info('No hay datos de posiciones en este rango.')
            else:
                dfp = df_pos.copy()
                dfp['Fecha_Entrada']  = dfp['Inicio'].dt.strftime('%d/%m/%Y %H:%M:%S')
                dfp['Fecha_Salida']   = dfp['Fin']   .dt.strftime('%d/%m/%Y %H:%M:%S')
                dfp['Tiempo_en_la_posicion'] = dfp['Duracion_segundos'].apply(
                    lambda x: str(timedelta(seconds=int(x))))
                dfp = dfp[['Posicion', 'Fecha_Entrada',
                           'Fecha_Salida', 'Tiempo_en_la_posicion']]

                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                    dfp.to_excel(w, index=False, sheet_name='Posiciones')
                st.download_button('Descargar Intervalos de Posición',
                                   data=out.getvalue(),
                                   file_name='intervalos_posicion.xlsx',
                                   mime=('application/vnd.openxmlformats-'
                                         'officedocument.spreadsheetml.sheet'),
                                   use_container_width=True)
                st.dataframe(dfp, use_container_width=True)

        # HABITACIONES
        with tab_hab:
            if df_hab.empty:
                st.info('No hay datos de habitaciones en este rango.')
            else:
                dfh = df_hab.copy()
                dfh['Fecha_Entrada'] = dfh['Inicio'].dt.strftime('%d/%m/%Y %H:%M:%S')
                dfh['Fecha_Salida']  = dfh['Fin']   .dt.strftime('%d/%m/%Y %H:%M:%S')
                dfh['Tiempo_en_la_habitacion'] = dfh['Duracion_segundos'].apply(
                    lambda x: str(timedelta(seconds=int(x))))
                dfh = dfh[['Habitacion', 'Fecha_Entrada',
                           'Fecha_Salida', 'Tiempo_en_la_habitacion']]

                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                    dfh.to_excel(w, index=False, sheet_name='Habitaciones')
                st.download_button('Descargar Intervalos de Habitación',
                                   data=out.getvalue(),
                                   file_name='intervalos_habitacion.xlsx',
                                   mime=('application/vnd.openxmlformats-'
                                         'officedocument.spreadsheetml.sheet'),
                                   use_container_width=True)
                st.dataframe(dfh, use_container_width=True)

        # ACCIONES
        with tab_acc:
            if df_acc.empty:
                st.info('No hay acciones detectadas en este rango.')
            else:
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                    df_acc.to_excel(w, index=False, sheet_name='Acciones')
                st.download_button('Descargar Acciones Detectadas',
                                   data=out.getvalue(),
                                   file_name='acciones_detectadas.xlsx',
                                   mime=('application/vnd.openxmlformats-'
                                         'officedocument.spreadsheetml.sheet'),
                                   use_container_width=True)
                st.dataframe(df_acc, use_container_width=True)

    except Exception as e:
        st.error(f'❌ Error al generar Excel: {e}')

# ─────────────── Navegación ───────────────
if st.button('Volver al Menú'):
    st.switch_page('app.py')
