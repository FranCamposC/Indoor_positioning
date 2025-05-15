#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import pandas as pd
import time
from datetime import datetime, timedelta
from collections import deque, Counter

# Rutas de archivos
INPUT_CSV = 'src/logs/predicciones_xgboost.csv'
ACTION_LOG = 'src/logs/acciones_detectadas.csv'

# Parámetros de estabilidad y actividad retrasada
WINDOW_SIZE = 5
MIN_STABLE_CONSECUTIVE = 3
MIN_TIME_STUDYING = 15  # segundos antes de considerar que inicia la actividad retrasada

DELAYED_ACTIVITIES = {
    'Escritorio': ('estudiando', 'Está estudiando', 'Deja de estudiar'),
    'Sofa': ('viendo la tele', 'Está viendo la tele', 'Deja de ver la tele'),
    'Mesa de juegos': ('jugando a juegos de mesa', 'Está jugando a juegos de mesa', 'Deja de jugar a juegos de mesa')
}

# Historial para ventanas deslizantes y control de timestamps
action_history = {
    'room_window': deque(maxlen=WINDOW_SIZE),
    'room_window_timestamps': deque(maxlen=WINDOW_SIZE),
    'position_window': deque(maxlen=WINDOW_SIZE),
    'position_window_timestamps': deque(maxlen=WINDOW_SIZE),
    'last_room': None,
    'last_position': None,
    'start_time': None,
    'current_activity': None,
    'current_activity_start_time': None,
    'just_ended_activity': False
}

# Para asegurar timestamps crecientes en el log
last_action_time_logged = None


def initialize_log():
    """Inicializa el CSV de acciones borrando el anterior y escribiendo cabecera."""
    if os.path.exists(ACTION_LOG):
        os.remove(ACTION_LOG)
    with open(ACTION_LOG, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Fecha', 'Hora', 'Tipo', 'Descripción'])


def room_enter_message(room: str) -> str:
    r = room.lower()
    return {
        'dormitorio': 'Entra en el Dormitorio',
        'cocina':    'Entra en la Cocina',
        'baño':      'Entra en el Baño',
        'salon':     'Entra en el Salón',
        'exterior':  'Sale'
    }.get(r, f'Entra en {room}')


def room_exit_message(room: str) -> str:
    r = room.lower()
    return {
        'dormitorio': 'Sale del Dormitorio',
        'cocina':     'Sale de la Cocina',
        'baño':       'Sale del Baño',
        'salon':      'Sale del Salón',
        'exterior':   'Entra en casa'
    }.get(r, f'Sale de {room}')


def get_stable_value(window, window_ts):
    if len(window) < WINDOW_SIZE:
        return None, None
    val, _ = Counter(window).most_common(1)[0]
    # devolvemos la primera aparición de ese valor en la ventana
    for v, t in zip(window, window_ts):
        if v == val:
            return val, t
    return None, None


def confirm_stability(value, window, min_consec, window_ts):
    if value is None:
        return None, None
    tail = list(window)[-min_consec:]
    tail_ts = list(window_ts)[-min_consec:]
    if len(tail) == min_consec and all(v == value for v in tail):
        return value, tail_ts[0]
    return None, None


def log_action(descripcion: str, ts: datetime, action_type: str):
    """
    Escribe una fila en ACTION_LOG con columnas:
       Fecha (DD/MM/YYYY), Hora (HH:MM:SS), Tipo, Descripción
    Asegura que cada entrada tenga un timestamp mayor al anterior.
    """
    global last_action_time_logged

    # Si el timestamp no avanza, empujamos 1 segundo adelante
    if last_action_time_logged and ts <= last_action_time_logged:
        ts = last_action_time_logged + timedelta(seconds=1)
    last_action_time_logged = ts

    fecha = ts.strftime('%d/%m/%Y')
    hora = ts.strftime('%H:%M:%S')
    with open(ACTION_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([fecha, hora, action_type, descripcion])


def handle_transition(old_room, old_position, new_room, new_position, ts):
    """
    Gestiona la lógica de transiciones:
      1) Termina la posición anterior
      2) Sale de la habitación anterior
      3) Entra en la nueva habitación
      4) Inicia la nueva posición y posibles actividades retrasadas
    """
    global action_history

    # 1) Termina posición anterior si cambia
    if old_position and old_position != new_position:
        if action_history['current_activity']:
            end_current_activity(ts)
        if old_position == 'Cama':
            log_action('Se levanta de la cama', ts, 'position')
        else:
            if not action_history['just_ended_activity']:
                log_action(f'Termina en {old_position}', ts, 'position')
        action_history['just_ended_activity'] = False

    # 2) Salir de la habitación anterior
    if old_room and old_room != new_room:
        log_action(room_exit_message(old_room), ts, 'room')

    # 3) Entrar en la nueva habitación
    if new_room and old_room != new_room:
        log_action(room_enter_message(new_room), ts, 'room')
        action_history['last_room'] = new_room

    # 4) Iniciar nueva posición
    if new_position and old_position != new_position:
        log_action(f'Está en {new_position}', ts, 'position')
        action_history['last_position'] = new_position
        # Marcamos posible inicio de actividad retrasada
        if new_position in DELAYED_ACTIVITIES:
            action_history['start_time'] = ts
        else:
            action_history['start_time'] = None
        detect_previous_actions(new_position, ts)


def detect_previous_actions(current_position, ts):
    """
    Comprueba si ha pasado el tiempo mínimo para actividades retrasadas
    y genera los eventos de inicio/fin correspondientes.
    """
    global action_history
    if current_position in DELAYED_ACTIVITIES:
        name, start_msg, end_msg = DELAYED_ACTIVITIES[current_position]
        if action_history['start_time']:
            elapsed = (ts - action_history['start_time']).total_seconds()
            if elapsed >= MIN_TIME_STUDYING and not action_history['current_activity']:
                start_ts = action_history['start_time'] + timedelta(seconds=MIN_TIME_STUDYING)
                log_action(start_msg, start_ts, 'position')
                action_history['current_activity'] = name
                action_history['current_activity_start_time'] = start_ts
    else:
        if action_history['current_activity']:
            end_current_activity(ts)
        action_history['start_time'] = None


def end_current_activity(ts):
    """Finaliza la actividad retrasada en curso."""
    global action_history
    for pos, (name, start_msg, end_msg) in DELAYED_ACTIVITIES.items():
        if name == action_history['current_activity']:
            log_action(end_msg, ts, 'position')
            break
    action_history['current_activity'] = None
    action_history['current_activity_start_time'] = None
    action_history['just_ended_activity'] = True


def detect_actions(row):
    """
    Procesa una fila del CSV de predicciones:
      - Actualiza ventanas deslizantes
      - Detecta valores estables
      - Llama a handle_transition si hay cambio
    """
    global action_history
    predicted_room = row['habitacion_predicha']
    predicted_position = row['posicion_predicha']
    row_time = datetime.strptime(row['time'], '%d/%m/%Y %H:%M:%S')

    # Ventana de habitación
    if predicted_room != 'Duda':
        action_history['room_window'].append(predicted_room)
        action_history['room_window_timestamps'].append(row_time)
    room_val, room_ts = get_stable_value(
        action_history['room_window'],
        action_history['room_window_timestamps']
    )
    stable_room, stable_room_ts = confirm_stability(
        room_val,
        action_history['room_window'],
        MIN_STABLE_CONSECUTIVE,
        action_history['room_window_timestamps']
    )

    # Ventana de posición
    if predicted_position != 'Duda':
        action_history['position_window'].append(predicted_position)
        action_history['position_window_timestamps'].append(row_time)
    pos_val, pos_ts = get_stable_value(
        action_history['position_window'],
        action_history['position_window_timestamps']
    )
    stable_position, stable_position_ts = confirm_stability(
        pos_val,
        action_history['position_window'],
        MIN_STABLE_CONSECUTIVE,
        action_history['position_window_timestamps']
    )

    # Si no hay estabilidad, salimos
    if not stable_room or not stable_position:
        return

    old_room = action_history['last_room']
    old_position = action_history['last_position']

    # Si hay cambio estable, gestionamos transición
    if stable_room != old_room or stable_position != old_position:
        transition_ts = max(stable_room_ts, stable_position_ts)
        handle_transition(old_room, old_position, stable_room, stable_position, transition_ts)


def monitor_positions():
    """
    Bucle principal que:
      - Lee continuamente el CSV de predicciones
      - Procesa sólo las filas nuevas
      - Gestiona errores y tiempos de espera
    """
    last_processed = 0
    while True:
        try:
            if not os.path.isfile(INPUT_CSV) or os.stat(INPUT_CSV).st_size == 0:
                time.sleep(1)
                continue

            df = pd.read_csv(INPUT_CSV)
            if df.empty:
                time.sleep(1)
                continue

            new_rows = df.iloc[last_processed:]
            if new_rows.empty:
                time.sleep(1)
                continue

            for _, row in new_rows.iterrows():
                detect_actions(row)
            last_processed += len(new_rows)

        except Exception as e:
            print("Error al leer el archivo CSV:", e)
            time.sleep(1)


if __name__ == '__main__':
    initialize_log()
    monitor_positions()
