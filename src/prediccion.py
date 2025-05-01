import paho.mqtt.client as mqtt
import json
import pandas as pd
import threading
import joblib
from datetime import datetime
import os

# Configuración del broker MQTT
MQTT_BROKER = "192.168.0.190"
MQTT_PORT = 1883
MQTT_USER = "fran"
MQTT_PASSWORD = "1234"
MQTT_TOPIC = "receivers/#"

# Cargar los modelos
MODEL_HABITACION_PATH = 'logs/xgboost_habitacion_model.pkl'
ENCODER_HABITACION_PATH = 'logs/xgboost_label_encoder_habitacion.pkl'
MODEL_POSICION_PATH = 'logs/xgboost_posicion_model.pkl'
ENCODER_POSICION_PATH = 'logs/xgboost_label_encoder_posicion.pkl'

model_habitacion = joblib.load(MODEL_HABITACION_PATH)
label_encoder_habitacion = joblib.load(ENCODER_HABITACION_PATH)
model_posicion = joblib.load(MODEL_POSICION_PATH)
label_encoder_posicion = joblib.load(ENCODER_POSICION_PATH)

# Diccionario de posiciones posibles por habitación
posiciones_por_habitacion = {
    "Dormitorio": ["Cama", "Escritorio"],
    "Salon": ["Sofa", "Mesa de juegos"],
    "Cocina": ["Frigorifico", "Fregadero", "Vitroceramica"],
    "Baño": ["WC", "Lavabo"]
}

# Umbrales de confianza independientes
umbral_confianza_habitacion = 0.40
umbral_confianza_posicion = 0.00

# Archivo donde se guardarán las predicciones
OUTPUT_CSV = 'logs/predicciones_xgboost.csv'

# Estructuras de datos globales
current_row = None
row_lock = threading.RLock()
timeout_thread = None
TIMEOUT_SECONDS = 3
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

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado al broker MQTT")
        client.subscribe(MQTT_TOPIC)
    else:
        print("Error al conectar, código de error:", rc)

def on_message(client, userdata, msg):
    global current_row, timeout_thread

    try:
        data = json.loads(msg.payload.decode())
        esp32_id = esp32_ids.get(msg.topic)
        if not esp32_id:
            print(f"Tópico desconocido: {msg.topic}")
            return

        rssi = int(data.get('rssi', -150))  # Valor predeterminado para RSSI

        with row_lock:
            if current_row is None:
                current_row = {esp_id: -150 for esp_id in all_esp32_ids}
                current_row['time'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                print("Nueva fila creada")

                # Iniciar temporizador
                timeout_thread = threading.Timer(TIMEOUT_SECONDS, predict_position)
                timeout_thread.start()

            current_row[esp32_id] = rssi

            # Si se reciben todos los datos antes del timeout, forzar predicción
            if all(value != -150 for key, value in current_row.items() if key != 'time'):
                print("Todos los datos recibidos antes del timeout.")
                predict_position()

    except Exception as e:
        print("Error al procesar el mensaje:", e)

def predict_position():
    global current_row, timeout_thread

    with row_lock:
        if current_row is not None:
            df = pd.DataFrame([current_row])

            try:
                feature_columns = [col for col in df.columns if col.startswith('ESP32_')]
                X = df[feature_columns]

                # Predicción habitación con probabilidades
                prediction_habitacion_proba = model_habitacion.predict_proba(X)
                max_proba_hab = prediction_habitacion_proba.max(axis=1)[0]

                if max_proba_hab >= umbral_confianza_habitacion:
                    # Confianza suficiente en la habitación
                    prediction_habitacion = model_habitacion.predict(X)
                    predicted_habitacion_label = label_encoder_habitacion.inverse_transform(prediction_habitacion)[0]
                else:
                    # No hay suficiente confianza en la habitación
                    predicted_habitacion_label = "Duda"

                # Predicción posición con probabilidades
                prediction_posicion_proba = model_posicion.predict_proba(X)
                max_proba_pos = prediction_posicion_proba.max(axis=1)[0]

                if max_proba_pos >= umbral_confianza_posicion:
                    # Confianza suficiente en la posición
                    prediction_posicion = model_posicion.predict(X)
                    predicted_posicion_label = label_encoder_posicion.inverse_transform(prediction_posicion)[0]
                else:
                    # Confianza insuficiente en la posición
                    predicted_posicion_label = "Duda"

               #CAMBIO PARA QUE LA POSICIÓN SEA DUDA SI LA HABITACIÓN ES DUDA     
                # Fuerza la posición a "Duda" si la habitación es "Duda"
                if predicted_habitacion_label == "Duda":
                    predicted_posicion_label = "Duda"
                else:
                    # Si la habitación no es duda, verificamos coherencia
                    posiciones_validas = posiciones_por_habitacion.get(predicted_habitacion_label, [])
                    if predicted_posicion_label not in posiciones_validas and predicted_posicion_label != "Duda":
                        predicted_posicion_label = "Duda"

                # Añadir las predicciones al DataFrame
                df['habitacion_predicha'] = predicted_habitacion_label
                df['posicion_predicha'] = predicted_posicion_label

                # Mostrar las predicciones
                timestamp = df['time'].iloc[0]
                print(f"{timestamp} - Habitación predicha: {predicted_habitacion_label}, Posición predicha: {predicted_posicion_label}")

                # Guardar la fila en el archivo CSV
                if not os.path.isfile(OUTPUT_CSV):
                    df.to_csv(OUTPUT_CSV, index=False, mode='w')
                else:
                    df.to_csv(OUTPUT_CSV, index=False, mode='a', header=False)

            except Exception as e:
                print("Error al realizar la predicción:", e)

            current_row = None
            if timeout_thread is not None:
                timeout_thread.cancel()
                timeout_thread = None

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
except Exception as e:
    print(f"Error al conectar con el broker MQTT: {e}")
    exit(1)

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\nInterrupción del programa por el usuario. Cerrando conexión...")
    client.disconnect()