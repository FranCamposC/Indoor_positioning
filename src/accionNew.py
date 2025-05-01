import os
import pandas as pd
import time
from datetime import datetime, timedelta
from collections import deque, Counter

INPUT_CSV = 'logs/predicciones_xgboost.csv'
ACTION_LOG = 'logs/acciones_detectadas.csv'

if os.path.exists(INPUT_CSV):
    os.remove(INPUT_CSV)
    print(f"Archivo {INPUT_CSV} eliminado.")

if os.path.exists(ACTION_LOG):
    os.remove(ACTION_LOG)
    print(f"Archivo {ACTION_LOG} eliminado.")

WINDOW_SIZE = 5
MIN_STABLE_CONSECUTIVE = 3
MIN_TIME_STUDYING = 15

DELAYED_ACTIVITIES = {
    'Escritorio': ('estudiando', 'Está estudiando', 'Deja de estudiar'),
    'Sofa': ('viendo la tele', 'Está viendo la tele', 'Deja de ver la tele'),
    'Mesa de juegos': ('jugando a juegos de mesa', 'Está jugando a juegos de mesa', 'Deja de jugar a juegos de mesa')
}

action_history = {
    'room_window': deque(maxlen=WINDOW_SIZE),
    'room_window_timestamps': deque(maxlen=WINDOW_SIZE),
    'position_window': deque(maxlen=WINDOW_SIZE),
    'position_window_timestamps': deque(maxlen=WINDOW_SIZE),

    'last_room': None,
    'last_position': None,
    'last_logged_room': None,
    'last_logged_position': None,

    'start_time': None,           
    'current_activity': None,     
    'current_activity_start_time': None,
    'just_ended_activity': False
}

last_action_time_logged = None

def room_enter_message(room, ts):
    r = room.lower()
    if r == "dormitorio":
        return f"Entra en el Dormitorio a las {ts.strftime('%H:%M:%S')}"
    elif r == "cocina":
        return f"Entra en la Cocina a las {ts.strftime('%H:%M:%S')}"
    elif r == "baño":
        return f"Entra en el Baño a las {ts.strftime('%H:%M:%S')}"
    elif r == "salon":
        return f"Entra en el salón a las {ts.strftime('%H:%M:%S')}"
    elif r == "exterior":
        return f"Entra en el exterior a las {ts.strftime('%H:%M:%S')}"
    else:
        return f"Entra en {room} a las {ts.strftime('%H:%M:%S')}"

def room_exit_message(room, ts):
    r = room.lower()
    if r == "dormitorio":
        return f"Sale del Dormitorio a las {ts.strftime('%H:%M:%S')}"
    elif r == "cocina":
        return f"Sale de la Cocina a las {ts.strftime('%H:%M:%S')}"
    elif r == "baño":
        return f"Sale del Baño a las {ts.strftime('%H:%M:%S')}"
    elif r == "salon":
        return f"Sale del salón a las {ts.strftime('%H:%M:%S')}"
    elif r == "exterior":
        return f"Sale del exterior a las {ts.strftime('%H:%M:%S')}"
    else:
        return f"Sale de {room} a las {ts.strftime('%H:%M:%S')}"

def get_stable_value(window, window_ts):
    if len(window) < WINDOW_SIZE:
        return None, None
    value_counts = Counter(window)
    most_common_val, _ = value_counts.most_common(1)[0]
    # Marca de tiempo de la primera aparición de ese valor en la ventana
    for v, t in zip(window, window_ts):
        if v == most_common_val:
            return most_common_val, t
    return None, None

def confirm_stability(value, window, min_consecutive, window_ts):
    if value is None:
        return None, None
    tail_values = list(window)[-min_consecutive:]
    tail_times = list(window_ts)[-min_consecutive:]
    if len(tail_values) == min_consecutive and all(v == value for v in tail_values):
        return value, tail_times[0]  # Hora más antigua
    return None, None

def handle_transition(old_room, old_position, new_room, new_position, ts):
    """
    1) Terminar posición anterior (si había).
    2) Salir de la habitación anterior (si cambia).
    3) Entrar en la nueva habitación (si cambia).
    4) Iniciar nueva posición.
    """
    global action_history

    # 1) Terminar posición anterior
    if old_position and old_position != new_position:
        # Si había actividad en curso, la finalizamos
        if action_history['current_activity']:
            end_current_activity(ts)
        if old_position == "Cama":
            # Si era la cama, decimos "Se levanta de la cama"
            log_action(f"Se levanta de la cama a las {ts.strftime('%H:%M:%S')}", "position")
        else:
            # Para cualquier otra posición
            if not action_history['just_ended_activity']:
                log_action(f"Termina en el {old_position} a las {ts.strftime('%H:%M:%S')}", "position")
        # Reseteamos el flag
        action_history['just_ended_activity'] = False

    # 2) Salir de la habitación anterior
    if old_room and old_room != new_room:
        log_action(room_exit_message(old_room, ts), "room")

    # 3) Entrar en la nueva habitación
    if new_room and old_room != new_room:
        log_action(room_enter_message(new_room, ts), "room")
        action_history['last_room'] = new_room

    # 4) Iniciar la nueva posición (si cambió o no teníamos antes)
    if new_position and old_position != new_position:
        log_action(f"Está en el {new_position} a las {ts.strftime('%H:%M:%S')}", "position")
        action_history['last_position'] = new_position

        # Si la posición nueva admite actividad retrasada, reiniciamos 'start_time'
        if new_position in DELAYED_ACTIVITIES:
            action_history['start_time'] = ts
        else:
            action_history['start_time'] = None

        # Revisamos si hay alguna actividad que iniciar de inmediato (o al cabo de X seg)
        detect_previous_actions(new_position, ts)

def detect_previous_actions(current_position, ts):
    global action_history
    if current_position in DELAYED_ACTIVITIES:
        activity_name, activity_start_msg, _ = DELAYED_ACTIVITIES[current_position]
        if action_history['start_time'] is not None:
            elapsed_time = (ts - action_history['start_time']).total_seconds()
            if elapsed_time >= MIN_TIME_STUDYING and action_history['current_activity'] is None:
                start_activity_ts = action_history['start_time'] + timedelta(seconds=MIN_TIME_STUDYING)
                log_action(f"{activity_start_msg} desde {start_activity_ts.strftime('%H:%M:%S')}", "position")
                action_history['current_activity'] = activity_name
                action_history['current_activity_start_time'] = start_activity_ts
    else:
        # Si la nueva posición no admite actividad, y había una en curso, la terminamos
        if action_history['current_activity']:
            end_current_activity(ts)
        action_history['start_time'] = None

def end_current_activity(ts):
    global action_history
    for pos, (activity_name, _, activity_end_msg) in DELAYED_ACTIVITIES.items():
        if activity_name == action_history['current_activity']:
            log_action(f"{activity_end_msg} a las {ts.strftime('%H:%M:%S')}", "position")
            break
    action_history['current_activity'] = None
    action_history['current_activity_start_time'] = None
    action_history['just_ended_activity'] = True

def log_action(action, action_type):
    global action_history, last_action_time_logged

    # Ajustar tiempo para evitar "collisiones" en caso de que dos acciones 
    # salgan con la misma marca de tiempo
    current_action_time = None
    if " a las " in action:
        base, t_str = action.rsplit(" a las ", 1)
        try:
            current_action_time = datetime.strptime(t_str.strip(), "%H:%M:%S")
        except:
            current_action_time = None
    elif " desde " in action:
        base, t_str = action.rsplit(" desde ", 1)
        try:
            current_action_time = datetime.strptime(t_str.strip(), "%H:%M:%S")
        except:
            current_action_time = None

    if current_action_time is not None:
        if last_action_time_logged and current_action_time <= last_action_time_logged:
            while current_action_time <= last_action_time_logged:
                current_action_time += timedelta(seconds=5)

        if " a las " in action:
            base_text, _ = action.rsplit(" a las ", 1)
            action = f"{base_text} a las {current_action_time.strftime('%H:%M:%S')}"
        elif " desde " in action:
            base_text, _ = action.rsplit(" desde ", 1)
            action = f"{base_text} desde {current_action_time.strftime('%H:%M:%S')}"

        last_action_time_logged = current_action_time

    # Evitar duplicados
    if action_type == "room" and action_history['last_logged_room'] == action:
        return
    if action_type == "position" and action_history['last_logged_position'] == action:
        return

    print(f"Acción detectada: {action}")
    with open(ACTION_LOG, 'a') as f:
        f.write(action + "\n")

    if action_type == "room":
        action_history['last_logged_room'] = action
    else:
        action_history['last_logged_position'] = action

def detect_actions(row):
    """
    Lee las predicciones (room y position) y si hay cambio
    respecto a lo último estable, se llama a handle_transition(...)
    con el orden: 1) terminar pos anterior, 2) salir de old_room,
    3) entrar a new_room, 4) iniciar nueva posición.
    """
    global action_history

    predicted_room = row['habitacion_predicha']
    predicted_position = row['posicion_predicha']
    row_time = datetime.strptime(row['time'], '%d/%m/%Y %H:%M:%S')

    # Actualizar "room_window" y "position_window"
    if predicted_room != 'Duda':
        action_history['room_window'].append(predicted_room)
        action_history['room_window_timestamps'].append(row_time)

    room_raw, room_raw_ts = get_stable_value(
        action_history['room_window'], 
        action_history['room_window_timestamps']
    )
    stable_room, stable_room_ts = confirm_stability(
        room_raw,
        action_history['room_window'],
        MIN_STABLE_CONSECUTIVE,
        action_history['room_window_timestamps']
    )

    if predicted_position != 'Duda':
        action_history['position_window'].append(predicted_position)
        action_history['position_window_timestamps'].append(row_time)

    position_raw, position_raw_ts = get_stable_value(
        action_history['position_window'],
        action_history['position_window_timestamps']
    )
    stable_position, stable_position_ts = confirm_stability(
        position_raw,
        action_history['position_window'],
        MIN_STABLE_CONSECUTIVE,
        action_history['position_window_timestamps']
    )

    # Si aún no hay valores estables, no hacemos nada
    if not stable_room or not stable_position:
        return

    old_room = action_history['last_room']
    old_position = action_history['last_position']

    # Si algo cambió (de habitación o de posición), gestionamos la transición universal
    if (stable_room != old_room) or (stable_position != old_position):
        # Tomamos la marca de tiempo "más reciente" de las dos,
        # para no mezclar la hora de la habitación con la posición
        # (o bien podrías tomar la más antigua, según tu criterio).
        transition_ts = max(stable_room_ts, stable_position_ts)
        handle_transition(old_room, old_position, stable_room, stable_position, transition_ts)

def monitor_positions():
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

if __name__ == "__main__":
    monitor_positions()
