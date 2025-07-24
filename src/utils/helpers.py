# utils/helpers.py
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


def posicion_estable() -> tuple[str, str] | None:
    try:
        df = pd.read_csv(CSV_PATH)
        v = df.tail(3)
        if len(v) < 2:
            return None
        v = v[
            (v["habitacion_predicha"] != "Duda")
            & (v["posicion_predicha"] != "Duda")
        ]
        v = v[
            v.apply(
                lambda r: r["posicion_predicha"]
                in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []),
                axis=1,
            )
        ]
        if len(v) < 2:
            return None
        h = v["habitacion_predicha"].unique()
        p = v["posicion_predicha"].unique()
        return (h[0], p[0]) if len(h) == 1 and len(p) == 1 else None
    except Exception:
        return None

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
