"""
Descubrimiento de recorridos con nodos START / END
DFG de frecuencias usando pm4py + Cytoscape (layout dagre estilo Disco)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, time
from io import BytesIO
import json, streamlit.components.v1 as components
from collections import Counter

from utils.helpers import CSV_PATH, VALID_POSITIONS_BY_ROOM
from utils.data_loader import generar_intervalos
import pm4py
from pm4py.algo.discovery.dfg import algorithm as dfg_factory

# ───────────────────────── Config inicial ─────────────────────────
st.set_page_config(page_title="Descubrimiento", page_icon="📊", layout="wide")
st.title("📊 Descubrimiento de recorridos (estilo Disco)")

# ───────────────────────── Helper fusión ──────────────────────────
def fusionar_intervalos(df_int: pd.DataFrame, etiqueta: str,
                        umbral: int, gap_merge: int = 8) -> pd.DataFrame:
    if df_int.empty:
        return df_int
    df = df_int[df_int['Duracion_segundos'] >= umbral].copy()
    if df.empty:
        return df

    df = df.sort_values('Inicio').reset_index(drop=True)

    # 1) fusionar consecutivos iguales
    df['grupo'] = (df[etiqueta] != df[etiqueta].shift()).cumsum()
    df = (df.groupby(['grupo', etiqueta], as_index=False)
            .agg(Inicio=('Inicio','min'), Fin=('Fin','max'))
            .drop(columns='grupo'))

    # 2) fusionar huecos pequeños entre bloques iguales
    res = []
    for _, row in df.iterrows():
        if not res:
            res.append(row)
            continue
        prev = res[-1]
        if (row[etiqueta] == prev[etiqueta] and
            (row['Inicio'] - prev['Fin']).total_seconds() <= gap_merge):
            res[-1]['Fin'] = row['Fin']
        else:
            res.append(row)

    out = pd.DataFrame(res)
    out['Duracion_segundos'] = (out['Fin'] - out['Inicio']).dt.total_seconds()
    return out

# ───────────────────────── Filtros usuario ────────────────────────
c1, c2 = st.columns(2)
with c1:
    fi = st.date_input("Fecha inicio")
with c2:
    ff = st.date_input("Fecha fin")

if fi > ff:
    st.warning("⚠️ La fecha de inicio no puede ser posterior a la de fin.")
    st.stop()

# ───────────────────────── Procesamiento ──────────────────────────
if st.button("Procesar y generar XES"):
    dt_i, dt_f = datetime.combine(fi, time.min), datetime.combine(ff, time.max)

    # 1️⃣  Cargar CSV y filtrado mínimo
    df = pd.read_csv(CSV_PATH)
    df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S",
                                errors="coerce")
    df = df.dropna(subset=["time"])
    df = df[(df["time"] >= dt_i) & (df["time"] <= dt_f)]
    df = df[(df["habitacion_predicha"] != "Duda") &
            (df["posicion_predicha"]   != "Duda")]
    df = df[df.apply(
        lambda r: r["posicion_predicha"]
        in VALID_POSITIONS_BY_ROOM.get(r["habitacion_predicha"], []), axis=1)]
    if df.empty:
        st.info("⚠️ No hay registros válidos en el rango seleccionado.")
        st.stop()

    # 2️⃣  Intervalos estables
    raw_hab = generar_intervalos(CSV_PATH, dt_i, dt_f)
    raw_hab = raw_hab[(raw_hab["Habitacion"] != "Duda") &
                      (raw_hab["Inicio"] >= dt_i) &
                      (raw_hab["Inicio"] <= dt_f)]
    df_hab = fusionar_intervalos(raw_hab, "Habitacion", 70)
    if df_hab.empty:
        st.info("No se encontraron intervalos estables.")
        st.stop()

    df_hab = df_hab.sort_values("Inicio").reset_index(drop=True)
    df_hab["case_id"] = df_hab["Inicio"].dt.date

    # 3️⃣  Log pm4py → DFG frecuencias
    log = pm4py.format_dataframe(
        df_hab.rename(columns={
            "case_id": "case:concept:name",
            "Habitacion": "concept:name",
            "Inicio": "time:timestamp"
        }),
        case_id="case:concept:name",
        activity_key="concept:name",
        timestamp_key="time:timestamp"
    )
    dfg_freq = dfg_factory.apply(log, variant=dfg_factory.Variants.FREQUENCY)

    # 4️⃣  Nodos START / END (conteo)
    first_acts = log.groupby("case:concept:name").first()["concept:name"]
    last_acts  = log.groupby("case:concept:name").last()["concept:name"]
    start_counts = first_acts.value_counts().to_dict()
    end_counts   = last_acts.value_counts().to_dict()

    # ───── Elementos Cytoscape ─────
    elements, nodes_seen = [], set()
    degree_counter = Counter()
    for (s, t), f in dfg_freq.items():
        degree_counter[s] += f
        degree_counter[t] += f
    for a, f in start_counts.items():
        degree_counter[a] += f
    for a, f in end_counts.items():
        degree_counter[a] += f

    max_freq   = max(list(dfg_freq.values()) + list(start_counts.values()) +
                     list(end_counts.values()))
    max_degree = max(degree_counter.values())

    # Nodos actividad
    for act, deg in degree_counter.items():
        if act not in nodes_seen:
            lbl = f"{act}\n{deg}"
            elements.append({"data": {"id": act, "label": lbl,
                                      "degree": deg},
                             "classes": "activity"})
            nodes_seen.add(act)

    # START / END
    elements += [
        {"data": {"id": "START"}, "classes": "start"},
        {"data": {"id": "END"},   "classes": "end"}
    ]

    # Aristas internas
    for (src, tgt), f in dfg_freq.items():
        elements.append({
            "data": {"id": f"{src}->{tgt}", "source": src, "target": tgt,
                     "label": str(f), "weight": f},
            "classes": "internal"
        })
    # START →
    for tgt, f in start_counts.items():
        elements.append({
            "data": {"id": f"START->{tgt}", "source": "START", "target": tgt,
                     "label": str(f), "weight": f},
            "classes": "terminal"
        })
    # → END
    for src, f in end_counts.items():
        elements.append({
            "data": {"id": f"{src}->END", "source": src, "target": "END",
                     "label": str(f), "weight": f},
            "classes": "terminal"
        })

    # ───── Estilos (parecido a Disco) ─────
    style_json = [
        # Actividades rectangulares color gradiente azul
        {"selector": ".activity",
         "style": {"shape": "round-rectangle",
                   "background-color": "#0d6efd",
                   "color": "#fff",
                   "text-outline-color": "#0d6efd",
                   "text-outline-width": 2,
                   "content": "data(label)",
                   "text-wrap": "wrap",
                   "text-valign": "center",
                   "font-size": "12px",
                   "width": f"mapData(degree,1,{max_degree}, 90, 220)",
                   "height": "label"}},
        # START / END
        {"selector": ".start",
         "style": {"shape": "triangle", "background-color": "#6ea94f",
                   "width": 45, "height": 45}},
        {"selector": ".end",
         "style": {"shape": "square", "background-color": "#795548",
                   "width": 45, "height": 45}},
        # Aristas internas grueso → frecuencia
        {"selector": ".internal",
         "style": {"curve-style": "bezier",
                   "target-arrow-shape": "triangle",
                   "line-color": "#555",
                   "target-arrow-color": "#555",
                   "width": f"mapData(weight,1,{max_freq},2,24)",
                   "label": "data(label)",
                   "font-size": "11px",
                   "text-background-color": "#fff",
                   "text-background-opacity": 1,
                   "text-background-padding": "2px"}},
        # Aristas START/END punteadas
        {"selector": ".terminal",
         "style": {"curve-style": "bezier",
                   "line-style": "dashed",
                   "target-arrow-shape": "triangle",
                   "line-color": "#bdbdbd",
                   "target-arrow-color": "#bdbdbd",
                   "width": f"mapData(weight,1,{max_freq},1,14)",
                   "label": "data(label)",
                   "font-size": "11px"}}
    ]

    # ───── HTML Cytoscape con layout dagre ─────
    cy_html = f"""
    <html>
      <head>
        <script src="https://unpkg.com/cytoscape@3/dist/cytoscape.min.js"></script>
        <script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
        <script src="https://unpkg.com/cytoscape-dagre@2.3.2/cytoscape-dagre.js"></script>
      </head>
      <body>
        <div id="cy" style="width:100%;height:750px;"></div>
        <script>
          cytoscape({{
            container: document.getElementById('cy'),
            elements: {json.dumps(elements)},
            style: {json.dumps(style_json)},
            layout: {{
              name: 'dagre',
              rankDir: 'LR',          // izquierda → derecha
              nodeSep: 60,
              edgeSep: 50,
              rankSep: 120,
              animate: false
            }}
          }});
        </script>
      </body>
    </html>
    """

    st.subheader("🌐 Directly-Follows Graph (layout dagre)")
    components.html(cy_html, height=780, scrolling=False)

    # ───── Tabla resumen ─────
    st.subheader("📄 Intervalos de habitación (fusionados)")
    st.dataframe(df_hab[["case_id","Habitacion","Inicio","Fin",
                         "Duracion_segundos"]], use_container_width=True)

    # ───── Descargar XES ─────
    def build_xes(df_int: pd.DataFrame) -> str:
        """
        Emite dos eventos por intervalo:
        - Inicio:  lifecycle:start
        - Fin:     lifecycle:complete
        Incluye Duracion_segundos como atributo (en el evento complete).
        """
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<log xes.version="1.0" xmlns="http://www.xes-standard.org/">']
        for cid, grp in df_int.groupby("case_id"):
            lines.append("  <trace>")
            lines.append(f'    <string key="concept:name" value="{cid}" />')
            for _, ev in grp.sort_values("Inicio").iterrows():
                act = ev["Habitacion"]
                ini = ev["Inicio"].isoformat()
                fin = ev["Fin"].isoformat()

                # start
                lines += [
                    "    <event>",
                    f'      <string key="concept:name" value="{act}" />',
                    f'      <string key="lifecycle:transition" value="start" />',
                    f'      <date   key="time:timestamp" value="{ini}" />',
                    "    </event>"
                ]
                # complete
                lines += [
                    "    <event>",
                    f'      <string key="concept:name" value="{act}" />',
                    f'      <string key="lifecycle:transition" value="complete" />',
                    f'      <date   key="time:timestamp" value="{fin}" />',
                    f'      <int    key="sojourn_seconds" value="{int(ev["Duracion_segundos"])}" />',
                    "    </event>"
                ]
            lines.append("  </trace>")
        lines.append("</log>")
        return "\n".join(lines)


    st.download_button("Descargar XES",
                       data=BytesIO(build_xes(df_hab).encode()),
                       file_name="historial_habitaciones.xes",
                       mime="application/xml",
                       use_container_width=True)

# ───────────────────── Navegación ─────────────────────
if st.button("Volver al menú"):
    st.switch_page("app.py")
