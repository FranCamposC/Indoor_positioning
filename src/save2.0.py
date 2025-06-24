import os
import json
import threading
import pandas as pd
import paho.mqtt.client as mqtt

# --- 0. RUTAS ABSOLUTAS ---
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
LOGS_DIR    = os.path.join(BASE_DIR, 'logs')
CSV_FILE    = os.path.join(LOGS_DIR, 'datosparaEntrenar.csv')

# --- 1. CARGAR (O CREAR) CONFIGURACIÓN POR DEFECTO ---
default_cfg = {"total_readings_per_position": 300}
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(default_cfg, f, indent=2, ensure_ascii=False)
    print(f"Se creó {CONFIG_FILE} con {default_cfg}")

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

# --- 2. DECIDIR MODO DE FUNCIONAMIENTO ---
default_n = cfg.get("total_readings_per_position", 300)
resp = input(f"¿Usar configuración por defecto? ({default_n} lecturas/posición) [S/n]: ").strip().lower()
if resp in ('', 's', 'si', 'y', 'yes'):
    default_mode    = True
    total_readings  = default_n
else:
    default_mode    = False
    total_readings  = 0
    while total_readings < 1:
        try:
            total_readings = int(input("¿Cuántas lecturas por posición vas a recoger? "))
        except ValueError:
            print("Número entero, por favor.")

# --- 3. DEFINIR HABITACIONES Y POSICIONES ---
ROOM_OPTIONS = {
    1: 'Dormitorio',
    2: 'Cocina',
    3: 'Baño',
    4: 'Salón'
}
POSITION_OPTIONS = {
    'Dormitorio': ['Cama', 'Escritorio'],
    'Cocina':     ['Fregadero','Vitroceramica','Frigorifico'],
    'Baño':       ['Lavabo','WC'],
    'Salón':      ['Sofá','Mesa de juegos']
}

# --- 4. SECUENCIA AUTOMÁTICA (solo en default_mode) ---
if default_mode:
    sequence = []
    for _, room in ROOM_OPTIONS.items():
        for pos in POSITION_OPTIONS[room]:
            sequence.append((room, pos))
    seq_index = 0
    max_seq   = len(sequence)

# Variables globales de ubicación y conteo
current_room     = None
current_position = None
rows_written     = 0

def print_instruction():
    """Muestra la instrucción al usuario para la posición actual."""
    print("\n────────────────────────────────────")
    if default_mode:
        print(f"Posición {seq_index+1}/{max_seq}: {current_room} → {current_position}")
    else:
        print(f"Grabando para {current_room} → {current_position}")
    print(f"Mantente en '{current_position}' y mueve el reloj mientras recolectamos datos")
    print(f"({rows_written}/{total_readings})")
    print("────────────────────────────────────\n")

def ask_location_manual():
    """Modo manual: menus numerados para habitación y posición."""
    global current_room, current_position, rows_written
    print("\nSelecciona HABITACIÓN:")
    for k,v in ROOM_OPTIONS.items(): print(f"  {k}) {v}")
    c = 0
    while c not in ROOM_OPTIONS:
        try: c = int(input("Número de habitación: "))
        except: pass
    current_room = ROOM_OPTIONS[c]

    opts = POSITION_OPTIONS[current_room]
    print(f"\nSelecciona POSICIÓN en {current_room}:")
    for i,v in enumerate(opts,1): print(f"  {i}) {v}")
    c2 = 0
    while not (1<=c2<=len(opts)):
        try: c2 = int(input("Número de posición: "))
        except: pass
    current_position = opts[c2-1]

    rows_written = 0
    print_instruction()

def setup_next_default():
    """Avanza en la secuencia automática y pide confirmación."""
    global seq_index, current_room, current_position, rows_written
    seq_index += 1
    if seq_index >= max_seq:
        print("\n¡Secuencia completa! Todos los puntos han sido muestreados.")
        os._exit(0)
    # Esperamos a que el usuario se mueva a la siguiente posición
    input(f"\n--- {total_readings}/{total_readings} alcanzado. "
          f"Múevete a '{sequence[seq_index][1]}' en '{sequence[seq_index][0]}', y pulsa ENTER cuando estés listo.")
    current_room, current_position = sequence[seq_index]
    rows_written = 0
    print_instruction()

# --- 5. CALLBACKS y CSV ---
# Aseguramos carpeta y MQTT IDs
os.makedirs(LOGS_DIR, exist_ok=True)
esp32_ids = {f"receivers/{i}":f"ESP32_{i}" for i in range(1,11)}
all_esp32_ids = list(esp32_ids.values())

current_row    = None
row_lock       = threading.RLock()
timeout_thread = None
TIMEOUT_SECONDS=3.5

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print("Conectado al broker MQTT")
        client.subscribe("receivers/#")
    else:
        print("Error al conectar:", rc)

def on_message(client, userdata, msg):
    global current_row, timeout_thread
    try:
        data = json.loads(msg.payload.decode())
        esp  = esp32_ids.get(msg.topic)
        if not esp: return

        tstr = data.get('time')
        rssi = int(data.get('rssi',0))
        t_idx= pd.to_datetime(tstr,format='%d/%m/%Y %H:%M:%S')

        with row_lock:
            if current_row is None:
                current_row = {
                    'time':t_idx,
                    'Habitacion':current_room,
                    'Posicion':current_position
                }
                for e in all_esp32_ids: current_row[e]=None
                timeout_thread = threading.Timer(TIMEOUT_SECONDS, write_row_to_csv)
                timeout_thread.start()

            current_row[esp]=rssi
            if all(current_row[e] is not None for e in all_esp32_ids):
                write_row_to_csv()
    except Exception as e:
        print("Error al procesar mensaje:", e)

def write_row_to_csv():
    global current_row, timeout_thread, rows_written
    with row_lock:
        if current_row is None: return
        # Completar vacíos
        for e in all_esp32_ids:
            if current_row[e] is None:
                current_row[e] = -150
        # DataFrame y orden columnas
        df = pd.DataFrame([current_row]).set_index('time')
        cols = all_esp32_ids + ['Habitacion','Posicion']
        df = df[cols]
        # Escribimos con formato de fecha
        header = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE)==0
        df.to_csv(
            CSV_FILE, mode='a', header=header,
            date_format='%d/%m/%Y %H:%M:%S', index_label='time'
        )
        # Contador y feedback
        rows_written += 1
        print(f"[{rows_written}/{total_readings}] {current_room}/{current_position}")
        # Limpiar
        current_row = None
        if timeout_thread:
            timeout_thread.cancel()
            timeout_thread=None
        # ¿Fin del bloque?
        if rows_written >= total_readings:
            if default_mode:
                setup_next_default()
            else:
                ask_location_manual()

# --- 6. ARRANQUE ---
client = mqtt.Client()
client.username_pw_set("fran","1234")
client.on_connect = on_connect
client.on_message = on_message

# Primera ubicación
if default_mode:
    current_room, current_position = sequence[0]
    rows_written = 0
    print("\n--- MODO POR DEFECTO ACTIVADO ---")
    print(f"Harás {total_readings} lecturas en cada posición.\n")
    print_instruction()
else:
    ask_location_manual()

try:
    client.connect("192.168.0.190",1883,60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nInterrumpido. Cerrando...")
    client.disconnect()
