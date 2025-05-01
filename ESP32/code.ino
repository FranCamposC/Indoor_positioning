// Librerías necesarias
#include <WiFi.h>               // Biblioteca para conectarse a una red WiFi
#include <PubSubClient.h>       // Biblioteca para comunicarse con un broker MQTT
#include <BLEDevice.h>          // Biblioteca para usar funcionalidades BLE
#include <BLEAdvertisedDevice.h>
#include <time.h>               // Biblioteca para manejar tiempo y fecha

// **Configuración de WiFi**
const char* ssid = "POCO M6 PRO";            // Reemplaza con el nombre de tu red WiFi
const char* password = "francampos";    // Reemplaza con la contraseña de tu red WiFi

String esp32_id = "ESP32_1";  // ESTO TENGO  QUE CAMBIARLO DEPENDIENDO DE LA ESP !!!!!!!!!!!!!!!!!!


// **Configuración del broker MQTT**
const char* mqtt_server = "192.168.55.128";  // Reemplaza con la dirección de tu broker MQTT
const int mqtt_port = 1883;                             // Usualmente 1883 para MQTT sin SSL
const char* mqtt_user = "fran";                 // Reemplaza con tu usuario MQTT
const char* mqtt_password = "1234";          // Reemplaza con tu contraseña MQTT
const char* mqtt_topic = "receivers/1";              // Reemplaza con el tópico MQTT al que deseas publicar

// **Direcciones MAC de dispositivos BLE a filtrar**
const int numAddressesToFilter = 1;  // Número de direcciones en el array (ajusta según necesites)
const char* addresses_to_filter[numAddressesToFilter] = {
  "e34ce8b466a0" // Reemplaza con la MAC del primer dispositivo (sin dos puntos y en minúsculas 
  // Reemplaza con la MAC del segundo dispositivo (sin dos puntos y en minúsculas)
};

// **Variables globales**
WiFiClient espClient;                // Cliente WiFi
PubSubClient client(espClient);      // Cliente MQTT usando el cliente WiFi
bool timeSynchronized = false;       // Bandera para indicar si el tiempo ha sido sincronizado

// **Prototipos de funciones**
void publishMessage(String message);
String getTimeString();

// **Clase para manejar los dispositivos BLE detectados**
class MyAdvertisedDeviceCallbacks: public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertisedDevice) {
        // Obtener la dirección MAC del dispositivo detectado y formatearla
        String addr_str = advertisedDevice.getAddress().toString().c_str();
        addr_str.replace(":", "");       // Eliminar los dos puntos de la dirección MAC, esto no hace falta pero por si acaso
        addr_str.toLowerCase();          // Convertir a minúsculas para comparación

        // Verificar si la dirección MAC está en la lista de filtrado
        for (int i = 0; i < numAddressesToFilter; i++) {
            if (addr_str == addresses_to_filter[i]) {
                // **Dispositivo filtrado encontrado**

                // Obtener la hora actual
                String current_time_str = getTimeString();

                // Imprimir información en el monitor serial
                Serial.println(addr_str + " " + current_time_str + " RSSI: " + String(advertisedDevice.getRSSI()));

                // Crear el mensaje en formato JSON
                String message = "{\"address\":\"" + addr_str + "\", \"time\":\"" + current_time_str + "\", \"rssi\":" + String(advertisedDevice.getRSSI()) + "}";

                // Publicar el mensaje en el broker MQTT
                publishMessage(message);

                // Detener el escaneo BLE
                BLEDevice::getScan()->stop();
                break; // Salir del bucle una vez que se encontró un dispositivo
            }
        }
    }
};

// **Función para publicar un mensaje en MQTT**
void publishMessage(String message) {
    if (client.connected()) {
        String full_message = "{\"esp32_id\":\"" + esp32_id + "\", " + message.substring(1); //esta linea es para tener un identificador
        client.publish(mqtt_topic, full_message.c_str());   // Publicar el mensaje en el tópico especificado
        Serial.println("Mensaje publicado: " + full_message);
    } else {
        Serial.println("No conectado al broker MQTT.Comprobar si está encendido");
    }
}

// **Función para obtener la hora actual como cadena de caracteres**
String getTimeString() {
    time_t now;                     // Variable para almacenar el tiempo actual en segundos desde Epoch
    struct tm timeinfo;             // Estructura para almacenar la información de tiempo desglosada
    time(&now);                     // Obtener el tiempo actual
    localtime_r(&now, &timeinfo);   // Convertir el tiempo actual a hora local
    char buffer[30];                // Buffer para almacenar la cadena de tiempo formateada
    strftime(buffer, sizeof(buffer), "%d/%m/%Y %H:%M:%S", &timeinfo);  // Formatear la fecha y hora
    return String(buffer);          // Devolver la cadena de tiempo como objeto String
}

// **Función para conectarse al WiFi**
void setup_wifi() {
    delay(10);
    Serial.println();
    Serial.print("Conectando a ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);            // Configurar el modo WiFi como estación (cliente)
    WiFi.begin(ssid, password);     // Iniciar la conexión WiFi

    // Esperar hasta que el dispositivo se conecte al WiFi
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    // Conexión exitosa
    Serial.println("");
    Serial.println("WiFi conectado");
    Serial.println("Dirección IP: ");
    Serial.println(WiFi.localIP()); // Imprimir la dirección IP asignada
}

// **Función para configurar y sincronizar el tiempo mediante NTP**
void setup_time() {
    configTime(7200, 0, "pool.ntp.org", "time.nist.gov"); // Configurar NTP con servidores de tiempo
    Serial.println("Sincronizando tiempo...");
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {  // Intentar obtener la hora actual
        Serial.println("Error al obtener el tiempo");
        return;
    }
    Serial.println("Tiempo sincronizado");
    timeSynchronized = true;         // Indicar que el tiempo se ha sincronizado correctamente
}

// **Función para conectarse al broker MQTT**
void reconnect_mqtt() {
    while (!client.connected()) {
        Serial.print("Intentando conectar al broker MQTT...");
        // Intentar conectar al broker MQTT
        if (client.connect("ESP32Client", mqtt_user, mqtt_password)) {
            Serial.println("Conectado al broker MQTT");
            // Si necesitas suscribirte a tópicos, puedes hacerlo aquí
        } else {
            Serial.print("Error al conectar. Estado = ");
            Serial.print(client.state());
            Serial.println(" Intentando nuevamente en 5 segundos...");
            delay(5000);
        }
    }
}

// **Función de configuración inicial**
void setup() {
    Serial.begin(115200);        // Iniciar comunicación serial a 115200 baudios para depuración
    setup_wifi();                // Conectarse a la red WiFi
    client.setServer(mqtt_server, mqtt_port);   // Configurar el broker MQTT
    setup_time();                // Sincronizar el tiempo mediante NTP

    // Inicializar Bluetooth
    BLEDevice::init("");         // Inicializar el dispositivo BLE sin nombre
}

// **Función principal que se ejecuta continuamente**
void loop() {
    // Verificar la conexión al broker MQTT y reconectar si es necesario
    if (!client.connected()) {
        reconnect_mqtt();
    }
    client.loop();               // Mantener la conexión y procesar mensajes entrantes

    // Intentar sincronizar el tiempo si aún no se ha hecho
    if (!timeSynchronized) {
        setup_time();
    }

    // **Iniciar el escaneo BLE**
    BLEScan* pBLEScan = BLEDevice::getScan(); // Crear un nuevo objeto de escaneo BLE
    pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks(), false);  // Establecer la función de callback para dispositivos detectados
    pBLEScan->setActiveScan(true);        // Habilitar el escaneo activo para obtener más datos de los dispositivos
    pBLEScan->setInterval(100);           // Establecer el intervalo de escaneo (en milisegundos)
    pBLEScan->setWindow(99);              // Establecer la ventana de escaneo (debe ser menor o igual al intervalo)

    Serial.println("Iniciando escaneo...");
    BLEScanResults* foundDevices = pBLEScan->start(5, false); // Escanear durante 5 segundos
    Serial.println("Escaneo terminado.");

    // Esperar 2 segundos antes de iniciar el próximo escaneo
    delay(2000);
}
