# 📡 Sistema de Localización Indoor con Inferencia de Acciones y Alertas

Este proyecto implementa un sistema de localización en interiores basado en dispositivos ESP32 y tecnología Bluetooth Low Energy (BLE), complementado con algoritmos de machine learning para la predicción de posición e inferencias de acciones basadas en reglas. Además, incluye un sistema de alertas configurables para el seguimiento en tiempo real del comportamiento del usuario.

---

## 🎯 Objetivos

- Capturar datos de señales BLE mediante dispositivos ESP32 y smartwatch.
- Predecir la posición del usuario en tiempo real con un modelo de ML (XGBoost).
- Inferir acciones del usuario basadas en su comportamiento posicional.
- Detectar y generar alertas personalizadas en situaciones concretas.
- Proporcionar una interfaz gráfica intuitiva para la visualización.

---

## ⚙️ Tecnologías utilizadas

- **Hardware:** ESP32, smartwatch BLE.
- **Red de comunicación:** MQTT para transmisión de datos.
- **Machine Learning:** XGBoost.
- **Backend:** Python.
- **Motor de reglas:** Esper (Complex Event Processing).
- **Frontend:** HTML/CSS/JS (visualización de posición e inferencias).
- **Documentación:** LaTeX.
- **Control de versiones:** GitHub.

---
## ⚠️ Alertas soportadas

- El usuario permanece demasiado tiempo en una misma ubicación.
- El usuario no se encuentra donde debería a una hora determinada.
- No se detecta señal del smartwatch por parte de los ESP32.

Las alertas se configuran a través de una interfaz accesible e intuitiva.

---

## 📊 Métricas esperadas

- **Precisión de predicción:** ≥ 85% en datos de validación.
- **Frecuencia de lectura:** 1 dato cada 3 segundos por dispositivo.
- **Instalación sencilla:** sin conocimientos técnicos avanzados.
- **Coste del sistema:** ≤ 200€ por unidad instalada.

---

## 🧪 Casos de uso

- Supervisión de personas mayores o dependientes.

---

## 👨‍💻 Autores

- **Francisco Antonio Campos Campos** (autor del proyecto)
- **Directores:** María Teresa Gómez López y Ángel Jesús Varela Vaca

---

## 📄 Licencia

Este proyecto está bajo la licencia [MIT](LICENSE). Puedes usar, modificar y dis
