# utils/helpers.py
from collections import Counter
import datetime
from PIL import Image, ImageDraw
import os
from matplotlib import pyplot as plt
import pandas as pd
import streamlit as st

MAPA_PATH = os.path.join(os.path.dirname(__file__), "../fotos/ParteDeAbajo.png")
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

transiciones = []
ultima_habitacion = None
ultima_posicion = None


CSV_PATH = "src/logs/predicciones_xgboost.csv"
ACTIONS_PATH = "src/logs/acciones_detectadas.csv"

VENTANA_SEG = 6         # últimos 6 s
UMBRAL_MAYORIA = 0.67   # 2/3 de los puntos
UMBRAL_CAMBIO = 4       # exigir 4 s de persistencia antes de “confirmar” el cambio

_ultima_confirmada = None          # (hab, pos)
_ts_ultimo_candidato = None        # cuando apareció el candidato
_candidato = None                  # (hab, pos)


def posicion_estable() -> tuple[str, str] | None:
    global _ultima_confirmada, _ts_ultimo_candidato, _candidato

    df = pd.read_csv(CSV_PATH)
    df["time"] = pd.to_datetime(df["time"], errors="coerce", dayfirst=True)

    if df.empty:
        return _ultima_confirmada

    tmax = df["time"].max()
    ventana = df[df["time"] >= tmax - pd.Timedelta(seconds=VENTANA_SEG)]
    if ventana.empty:
        return _ultima_confirmada

    ventana = ventana[
        (ventana["habitacion_predicha"] != "Duda") &
        (ventana["posicion_predicha"]   != "Duda")
    ]
    ventana = ventana[
        ventana.apply(lambda r: r["posicion_predicha"] in
                      VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []), axis=1)
    ]
    if ventana.empty:
        return _ultima_confirmada

    pares = list(zip(ventana["habitacion_predicha"], ventana["posicion_predicha"]))
    (hab,pos), freq = Counter(pares).most_common(1)[0]
    if freq / len(pares) < UMBRAL_MAYORIA:
        return _ultima_confirmada

    # Histeresis: confirmar cambio si persiste X s
    if _candidato != (hab,pos):
        _candidato = (hab,pos)
        _ts_ultimo_candidato = tmax
        return _ultima_confirmada

    if (tmax - _ts_ultimo_candidato).total_seconds() >= UMBRAL_CAMBIO:
        _ultima_confirmada = _candidato

    return _ultima_confirmada


def dibujar_esps(draw, fila):
    for esp, (x, y) in ESP_POSICIONES.items():
        if esp in fila:
            rssi = fila[esp]
            color = "green" if rssi >= -75 else "yellow" if rssi >= -95 else "red"
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)

def dibujar_transiciones(img):
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    now = datetime.datetime.now().timestamp()
    global transiciones
    for x1, y1, x2, y2, t in list(transiciones):
        elapsed = now - t
        if elapsed > 10:
            transiciones.remove((x1, y1, x2, y2, t))
            continue
        alpha = 255 if elapsed < 5 else int(255 * (1 - (elapsed - 5) / 5))
        od.line([(x1, y1), (x2, y2)], fill=(255, 0, 0, alpha), width=3)
    return Image.alpha_composite(img, overlay)

def dibujar_mapa(fila):
    global ultima_habitacion, ultima_posicion, transiciones
    img = Image.open(MAPA_PATH).convert("RGBA")
    d = ImageDraw.Draw(img)
    dibujar_esps(d, fila)
    nueva = posicion_estable()
    old_hab, old_pos = ultima_habitacion, ultima_posicion
    if nueva:
        ultima_habitacion, ultima_posicion = nueva
    coords = POSICIONES.get(f"{ultima_habitacion}_{ultima_posicion}", (0, 0)) if ultima_habitacion and ultima_posicion else (0, 0)
    if coords != (0, 0) and old_hab and old_pos:
        o = POSICIONES.get(f"{old_hab}_{old_pos}", (0, 0))
        if o != (0, 0) and o != coords:
            transiciones.append((*o, coords[0], coords[1], datetime.datetime.now().timestamp()))
    if coords != (0, 0):
        x, y = coords
        r = 14
        d.ellipse([x - r, y - r, x + r, y + r], fill="blue")
    return dibujar_transiciones(img)

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
