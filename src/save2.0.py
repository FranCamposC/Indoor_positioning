import paho.mqtt.client as mqtt
import json
import pandas as pd
import os
import threading
import time

# Configuración del broker MQTT
MQTT_BROKER = "192.168.0.190" 
MQTT_PORT = 1883
MQTT_USER = "fran"
MQTT_PASSWORD = "1234"
MQTT_TOPIC = "receivers/#"  # Usar # para suscribirse a múltiples tópicos

# Nombre del archivo CSV en la carpeta 'logs'
LOGS_DIR = 'src/logs'
CSV_FILE = os.path.join(LOGS_DIR, 'datosparaEntrenar.csv')

# Crear la carpeta 'logs' si no existe
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Estructuras de datos globales
current_row = None  # Fila pendiente
row_lock = threading.RLock()
timeout_thread = None
TIMEOUT_SECONDS = 3.5 # Tiempo de espera para completar la fila
esp32_ids = {
    'receivers/1': 'ESP32_1',
    'receivers/2': 'ESP32_2',
    'receivers/3': 'ESP32_3',
    'receivers/4': 'ESP32_4',
    'receivers/5': 'ESP32_5',
    'receivers/6': 'ESP32_6',
    'receivers/7': 'ESP32_7',
    'receivers/8': 'ESP32_8',
    'receivers/9': 'ESP32_9',
    'receivers/10': 'ESP32_10'
}

all_esp32_ids = list(esp32_ids.values())

# Función que se llama cuando se establece la conexión con el broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado al broker MQTT")
        client.subscribe(MQTT_TOPIC)
    else:
        print("Error al conectar, código de error:", rc)

# Función que se llama cuando se recibe un mensaje
def on_message(client, userdata, msg):
    global current_row, timeout_thread

    try:
        data = json.loads(msg.payload.decode())
        print("Mensaje recibido:", data)

        esp32_id = esp32_ids.get(msg.topic)
        if not esp32_id:
            print(f"Tópico desconocido: {msg.topic}")
            return

        timestamp_str = data.get('time')
        rssi = int(data.get('rssi', 0))

        if timestamp_str and esp32_id:
            # Convertir el tiempo a objeto datetime
            time_index = pd.to_datetime(timestamp_str, format='%d/%m/%Y %H:%M:%S')

            with row_lock:
                if current_row is None:
                    # Crear una nueva fila pendiente con todas las claves de los ESP32
                    current_row = {'time': time_index}
                    for esp_id in all_esp32_ids:
                        current_row[esp_id] = None
                    print(f"Fila pendiente creada: {current_row}")

                    # Iniciar temporizador para cerrar la fila después de TIMEOUT_SECONDS
                    timeout_thread = threading.Timer(TIMEOUT_SECONDS, write_row_to_csv)
                    timeout_thread.start()

                # Actualizar la fila pendiente con los datos recibidos
                current_row[esp32_id] = rssi
                print(f"Fila pendiente actualizada: {current_row}")

                # Verificar si todos los ESP32 han enviado datos
                if all(current_row[esp_id] is not None for esp_id in all_esp32_ids):
                    print("Todos los datos recibidos antes del timeout. Escribiendo fila en CSV.")
                    write_row_to_csv()

    except Exception as e:
        print("Error al procesar el mensaje:", e)

# Función para escribir la fila pendiente en el CSV
def write_row_to_csv():
    global current_row, timeout_thread

    with row_lock:
        if current_row is not None:
            # Reemplazar None por -150
            for esp_id in all_esp32_ids:
                if current_row[esp_id] is None:
                    current_row[esp_id] = -150

            df_row = pd.DataFrame([current_row])
            df_row.set_index('time', inplace=True)

            write_header = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0

            df_row.to_csv(CSV_FILE, mode='a', header=write_header)
            print(f"Fila escrita en CSV: {df_row}")

            current_row = None

            # Cancelar el temporizador si está activo
            if timeout_thread is not None:
                timeout_thread.cancel()
                timeout_thread = None

# Configuración del cliente MQTT
client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message

# Conexión al broker
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
except Exception as e:
    print(f"Error al conectar con el broker MQTT: {e}")
    exit(1)

# Iniciar el bucle del cliente MQTT
try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\nInterrupción del programa por el usuario. Guardando datos y cerrando conexión...")
    client.disconnect()
