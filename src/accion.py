import os
import pandas as pd
import time
from datetime import datetime, timedelta
from collections import deque, Counter

# Rutas de los archivos CSV
INPUT_CSV = 'logs/predicciones_xgboost.csv'
ACTION_LOG = 'logs/acciones_detectadas.csv'

# Eliminar los archivos CSV si existen
if os.path.exists(INPUT_CSV):
    os.remove(INPUT_CSV)
    print(f"Archivo {INPUT_CSV} eliminado.")

if os.path.exists(ACTION_LOG):
    os.remove(ACTION_LOG)
    print(f"Archivo {ACTION_LOG} eliminado.")

# Parámetros del filtro
WINDOW_SIZE = 5  # Tamaño de la ventana deslizante
MIN_STABLE_CONSECUTIVE = 3  # Mínimo de veces consecutivas que debe aparecer el valor estable
MIN_TIME_STUDYING = 15  # Tiempo mínimo para iniciar actividad

# Diccionario de actividades retrasadas por posición
# posicion: (nombre_actividad, mensaje_inicio, mensaje_fin)
DELAYED_ACTIVITIES = {
    'Escritorio': ('estudiando', 'Está estudiando', 'Deja de estudiar'),
    'Sofa': ('viendo la tele', 'Está viendo la tele', 'Deja de ver la tele'),
    'Mesa de juegos': ('jugando a juegos de mesa', 'Está jugando a juegos de mesa', 'Deja de jugar a juegos de mesa')
}

# Estado interno
action_history = {
    'position_window': deque(maxlen=WINDOW_SIZE),
    'room_window': deque(maxlen=WINDOW_SIZE),
    'last_logged_room': None,
    'last_logged_position': None,
    'last_room': None,
    'last_position': None,
    'start_time': None,           # Hora desde que se mantiene la posición
    'current_activity': None,     # Actividad en curso
    'current_activity_start_time': None,
    'just_ended_activity': False  # Indica si acabamos de terminar una actividad
}

# Guardaremos la última hora a la que se registró una acción para evitar colisiones temporales
last_action_time_logged = None

def get_stable_value(window):
    if len(window) == WINDOW_SIZE:
        value_counts = Counter(window)
        most_common = value_counts.most_common(1)
        if most_common:
            return most_common[0][0]
    return None

def confirm_stability(value, window, min_consecutive):
    if value is None:
        return None
    if len(window) >= min_consecutive and all(w == value for w in list(window)[-min_consecutive:]):
        return value
    return None

def detect_actions(row):
    global action_history

    predicted_room = row['habitacion_predicha']
    predicted_position = row['posicion_predicha']
    timestamp = datetime.strptime(row['time'], '%d/%m/%Y %H:%M:%S')

    # Actualizar ventana de habitación
    if predicted_room != 'Duda':
        action_history['room_window'].append(predicted_room)
    stable_room = get_stable_value(action_history['room_window'])
    stable_room = confirm_stability(stable_room, action_history['room_window'], MIN_STABLE_CONSECUTIVE)

    # Actualizar ventana de posición
    if predicted_position != 'Duda':
        action_history['position_window'].append(predicted_position)
    else:
        # Si es Duda en posición, solo intentar cambio de habitación
        handle_room_change(stable_room, timestamp)
        return

    stable_position = get_stable_value(action_history['position_window'])
    stable_position = confirm_stability(stable_position, action_history['position_window'], MIN_STABLE_CONSECUTIVE)

    # Procesar sólo si tenemos valores estables
    if stable_room is None or stable_position is None:
        return

    handle_room_change(stable_room, timestamp)
    handle_position_change(stable_position, timestamp)
    detect_previous_actions(stable_position, timestamp)

def handle_room_change(stable_room, timestamp):
    global action_history
    if stable_room is not None and stable_room != action_history['last_room']:
        if action_history['last_room']:
            log_action(room_exit_message(action_history['last_room'], timestamp), "room")
        log_action(room_enter_message(stable_room, timestamp), "room")
        action_history['last_room'] = stable_room

def room_enter_message(room, timestamp):
    r = room.lower()
    if r == "dormitorio":
        return f"Entra en el {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "cocina":
        return f"Entra en la {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "baño":
        return f"Entra en el {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "salon":
        return f"Entra en el salón a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "exterior":
        return f"Entra en el exterior a las {timestamp.strftime('%H:%M:%S')}"

def room_exit_message(room, timestamp):
    r = room.lower()
    if r == "dormitorio":
        return f"Sale del {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "cocina":
        return f"Sale de la {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "baño":
        return f"Sale del {room} a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "salon":
        return f"Sale del salón a las {timestamp.strftime('%H:%M:%S')}"
    elif r == "exterior":
        return f"Sale del exterior a las {timestamp.strftime('%H:%M:%S')}"

def handle_position_change(stable_position, timestamp):
    global action_history
    prev_position = action_history['last_position']

    # Si hay actividad en curso y cambiamos de posición, finalizamos la actividad primero
    if action_history['current_activity'] and stable_position != prev_position:
        end_current_activity(timestamp)

    if stable_position is not None and stable_position != prev_position:
        # Acciones de salida/inicio inmediata

        # Si acabamos de terminar una actividad, no decir "Termina en el {prev_position}" 
        # si esa posición era la misma donde se hacía la actividad.
        if prev_position == 'Cama':
            log_action(f"Se levanta de la cama a las {timestamp.strftime('%H:%M:%S')}", "position")
        else:
            # Si no es cama y no acabamos de terminar una actividad en esa posición
            # registramos "Termina en el {prev_position}"
            if prev_position and prev_position not in ['Cama']:
                # Solo si no acabamos de terminar la actividad en ese mismo movimiento
                if not action_history['just_ended_activity']:
                    log_action(f"Termina en el {prev_position} a las {timestamp.strftime('%H:%M:%S')}", "position")

        log_action(f"Está en el {stable_position} a las {timestamp.strftime('%H:%M:%S')}", "position")
        action_history['last_position'] = stable_position

        # Si es una posición con actividad retrasada, iniciamos conteo
        if stable_position in DELAYED_ACTIVITIES:
            action_history['start_time'] = timestamp
        else:
            action_history['start_time'] = None

        # Una vez registrada la nueva posición, si just_ended_activity estaba en True, la ponemos en False
        action_history['just_ended_activity'] = False

def detect_previous_actions(confirmed_position, timestamp):
    global action_history

    if confirmed_position in DELAYED_ACTIVITIES:
        activity_name, activity_start_msg, activity_end_msg = DELAYED_ACTIVITIES[confirmed_position]
        if action_history['start_time'] is not None:
            elapsed_time = (timestamp - action_history['start_time']).total_seconds()
            if elapsed_time >= MIN_TIME_STUDYING and action_history['current_activity'] is None:
                # Momento en el que se cumplen los 15s
                activity_start_time = action_history['start_time'] + timedelta(seconds=MIN_TIME_STUDYING)
                log_action(f"{activity_start_msg} desde {activity_start_time.strftime('%H:%M:%S')}", "position")
                action_history['current_activity'] = activity_name
                action_history['current_activity_start_time'] = activity_start_time
    else:
        # Si no hay actividad retrasada en esta posición, finalizar si había una actividad
        if action_history['current_activity']:
            end_current_activity(timestamp)
        action_history['start_time'] = None

def end_current_activity(timestamp):
    global action_history
    for pos, activity_tuple in DELAYED_ACTIVITIES.items():
        if activity_tuple[0] == action_history['current_activity']:
            log_action(f"{activity_tuple[2]} a las {timestamp.strftime('%H:%M:%S')}", "position")
            break
    action_history['current_activity'] = None
    action_history['current_activity_start_time'] = None
    action_history['just_ended_activity'] = True

def log_action(action, action_type):
    global action_history, last_action_time_logged

    # Extraemos la hora del texto, si existe " a las "
    current_action_time = None
    if " a las " in action:
        base_text, time_str = action.rsplit(" a las ", 1)
        try:
            current_action_time = datetime.strptime(time_str.strip(), "%H:%M:%S")
        except:
            current_action_time = None
    elif " desde " in action:
        # Caso "Está estudiando desde XX:XX:XX" o similar
        base_text, time_str = action.rsplit(" desde ", 1)
        try:
            current_action_time = datetime.strptime(time_str.strip(), "%H:%M:%S")
        except:
            current_action_time = None

    # Ajustar tiempo para evitar colisiones temporales
    if current_action_time is not None:
        if last_action_time_logged is not None and (current_action_time <= last_action_time_logged):
            while current_action_time <= last_action_time_logged:
                current_action_time += timedelta(seconds=5)
        # Reconstruir el mensaje
        if " a las " in action:
            base_text, _ = action.rsplit(" a las ", 1)
            action = f"{base_text} a las {current_action_time.strftime('%H:%M:%S')}"
        elif " desde " in action:
            base_text, _ = action.rsplit(" desde ", 1)
            action = f"{base_text} desde {current_action_time.strftime('%H:%M:%S')}"

        last_action_time_logged = current_action_time

    # Evitar registro duplicado
    if action_type == "room" and action_history['last_logged_room'] == action:
        return
    if action_type == "position" and action_history['last_logged_position'] == action:
        return

    print(f"Acción detectada: {action}")
    with open(ACTION_LOG, 'a') as file:
        file.write(f"{action}\n")

    # Actualizar última acción registrada
    if action_type == "room":
        action_history['last_logged_room'] = action
    elif action_type == "position":
        action_history['last_logged_position'] = action

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
