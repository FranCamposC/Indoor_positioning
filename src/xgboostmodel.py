import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
import joblib

# Cargar los datos desde el archivo CSV
file_path = 'src/logs/DatosparaEntrenar.csv'  # Cambia esta ruta a la ubicación de tu archivo
df = pd.read_csv(file_path)

# Seleccionar las columnas relevantes
features = [col for col in df.columns if col.startswith("ESP32")]
df_filtered = df.dropna(subset=features)  # Eliminar filas con valores faltantes en RSSI

# Codificar las etiquetas de 'Habitacion' y 'Posicion'
label_encoder_habitacion = LabelEncoder()
df_filtered['habitacion_encoded'] = label_encoder_habitacion.fit_transform(df_filtered['Habitacion'])

label_encoder_posicion = LabelEncoder()
df_filtered['posicion_encoded'] = label_encoder_posicion.fit_transform(df_filtered['Posicion'])

# Preparar características (X) y objetivos (y_habitacion y y_posicion)
X = df_filtered[features]
y_habitacion = df_filtered['habitacion_encoded']
y_posicion = df_filtered['posicion_encoded']

# Dividir en conjunto de entrenamiento y prueba con estratificación
X_train, X_test, y_habitacion_train, y_habitacion_test, y_posicion_train, y_posicion_test = train_test_split(
    X, y_habitacion, y_posicion, test_size=0.2, random_state=42, stratify=y_habitacion
)

# Marcar las filas usadas para entrenamiento y prueba en el DataFrame original
df_filtered['Set'] = 'Sin asignar'
df_filtered.loc[X_train.index, 'Set'] = 'Train'
df_filtered.loc[X_test.index, 'Set'] = 'Test'

# Guardar el DataFrame con las marcas de Train/Test
df_filtered.to_csv('src/logs/dataset_conjuntos.csv', index=False)

# Entrenar el modelo para 'Habitacion' con XGBoost
model_habitacion = XGBClassifier(
    n_estimators=300,        # Número de árboles en el modelo
    max_depth=4,             # Profundidad máxima de los árboles
    learning_rate=0.025,     # Tasa de aprendizaje
    subsample=0.8,           # Submuestreo para mejorar la generalización
    colsample_bytree=0.8,    # Submuestreo de características
    random_state=95,
    eval_metric='mlogloss'   # Evitar warning
)
model_habitacion.fit(X_train, y_habitacion_train)

# Evaluar el modelo para 'Habitacion'
accuracy_habitacion = model_habitacion.score(X_test, y_habitacion_test)
print(f"Precisión del modelo 'Habitacion' en el conjunto de prueba: {accuracy_habitacion * 100:.2f}%")

# Repetir la división para 'Posicion' con estratificación específica
X_train, X_test, y_habitacion_train, y_habitacion_test, y_posicion_train, y_posicion_test = train_test_split(
    X, y_habitacion, y_posicion, test_size=0.2, random_state=42, stratify=y_posicion
)

# Entrenar el modelo para 'Posicion' con XGBoost
model_posicion = XGBClassifier(
    n_estimators=600,        # Número de árboles en el modelo
    max_depth=6,             # Profundidad máxima de los árboles
    learning_rate=0.025,     # Tasa de aprendizaje
    subsample=0.8,           # Submuestreo para mejorar la generalización
    colsample_bytree=0.8,    # Submuestreo de características
    random_state=95,
    eval_metric='mlogloss'   # Evitar warning
)
model_posicion.fit(X_train, y_posicion_train)

# Evaluar el modelo para 'Posicion'
accuracy_posicion = model_posicion.score(X_test, y_posicion_test)
print(f"Precisión del modelo 'Posicion' en el conjunto de prueba: {accuracy_posicion * 100:.2f}%")

# Guardar los modelos y los LabelEncoders
joblib.dump(model_habitacion, 'src/logs/xgboost_habitacion_model.pkl')
joblib.dump(label_encoder_habitacion, 'src/logs/xgboost_label_encoder_habitacion.pkl')

joblib.dump(model_posicion, 'src/logs/xgboost_posicion_model.pkl')
joblib.dump(label_encoder_posicion, 'src/logs/xgboost_label_encoder_posicion.pkl')

print("Modelos entrenados y guardados correctamente.")
