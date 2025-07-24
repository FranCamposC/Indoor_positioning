# utils/data_loader.py
import pandas as pd
import os
from datetime import datetime
from utils.helpers import CSV_PATH

from utils.helpers import VALID_POSITIONS_BY_ROOM



def obtener_ultimas_filas_csv(n: int = 5):
    try:
        df = pd.read_csv(CSV_PATH)
        return df.tail(n) if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def generar_datos_diarios(path):
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df.dropna(subset=["time"], inplace=True)
    df = df[
        (df["habitacion_predicha"] != "Duda")
        & (df["posicion_predicha"] != "Duda")
    ]
    df = df[
        df.apply(
            lambda r: r["posicion_predicha"]
            in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []),
            axis=1,
        )
    ]
    df["Fecha"] = df["time"].dt.date
    intervalos = []
    for fecha, subdf in df.groupby("Fecha"):
        subdf = subdf.sort_values("time").reset_index(drop=True)
        posicion_actual, habitacion_actual, start_time = None, None, None
        for _, fila in subdf.iterrows():
            hab, pos, t = fila["habitacion_predicha"], fila["posicion_predicha"], fila["time"]
            if posicion_actual is None:
                posicion_actual, habitacion_actual, start_time = pos, hab, t
            elif (hab != habitacion_actual) or (pos != posicion_actual):
                fin_time = t
                duracion = (fin_time - start_time).total_seconds()
                if duracion > 5:
                    intervalos.append({
                        "Fecha": fecha,
                        "Habitacion": habitacion_actual,
                        "Posicion": posicion_actual,
                        "Duracion_segundos": duracion,
                    })
                posicion_actual, habitacion_actual, start_time = pos, hab, t
        if posicion_actual:
            duracion = (subdf.iloc[-1]["time"] - start_time).total_seconds()
            if duracion > 5:
                intervalos.append({
                    "Fecha": fecha,
                    "Habitacion": habitacion_actual,
                    "Posicion": posicion_actual,
                    "Duracion_segundos": duracion,
                })
    return pd.DataFrame(intervalos)

def generar_intervalos(path, dt_inicio, dt_fin):
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df = df[(df["time"] >= dt_inicio) & (df["time"] <= dt_fin)]

    # Validar datos válidos
    df = df[df["habitacion_predicha"] != "Duda"]
    df = df.sort_values("time").reset_index(drop=True)

    intervalos = []
    habitacion_actual, start_time = None, None

    for _, fila in df.iterrows():
        hab, t = fila["habitacion_predicha"], fila["time"]

        if habitacion_actual is None:
            # Iniciar primera habitación
            habitacion_actual, start_time = hab, t
        elif hab == habitacion_actual:
            # Seguimos en la misma lugar → actualizar hora de salida
            continue
        else:
            # Cambio de habitación → guardar el intervalo actual
            duracion = (t - start_time).total_seconds()
            if duracion > 5:
                intervalos.append({
                    "Inicio": start_time,
                    "Fin": t,
                    "Habitacion": habitacion_actual,
                    "Duracion_segundos": duracion,
                })
            # Reiniciar para nueva habitación
            habitacion_actual, start_time = hab, t

    # Guardar el último intervalo si existe
    if habitacion_actual:
        duracion = (df.iloc[-1]["time"] - start_time).total_seconds()
        if duracion > 5:
            intervalos.append({
                "Inicio": start_time,
                "Fin": df.iloc[-1]["time"],
                "Habitacion": habitacion_actual,
                "Duracion_segundos": duracion,
            })

    return pd.DataFrame(intervalos)