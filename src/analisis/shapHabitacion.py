import os
import shap
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import ConfusionMatrixDisplay, roc_curve, auc
import seaborn as sns

# Carga del modelo previamente entrenado
model = joblib.load("logs/xgboost_habitacion_model.pkl")

# Cargar los datos desde el archivo CSV
file_path = 'logs/parteDeAbajo.csv'  # Ajusta la ruta según corresponda
df = pd.read_csv(file_path)

# Seleccionar las columnas relevantes
features = [col for col in df.columns if col.startswith("ESP32")]
df_filtered = df.dropna(subset=features)  # Eliminar filas con valores faltantes en RSSI

# Codificar las etiquetas
label_encoder_habitacion = LabelEncoder()
df_filtered['habitacion_encoded'] = label_encoder_habitacion.fit_transform(df_filtered['Habitacion'])

# Preparar características (X) y objetivos (y_habitacion)
X = df_filtered[features]
y_habitacion = df_filtered['habitacion_encoded']

# Dividir en conjunto de entrenamiento y prueba (usando un conjunto de prueba mayor)
X_train, X_test, y_train, y_test = train_test_split(
    X, y_habitacion, test_size=0.4, random_state=42
)

# Generar valores explicativos SHAP
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# Verificar dimensiones de SHAP y X_test
print(f"Dimensiones de X_test: {X_test.shape}")
print(f"Dimensiones de shap_values: {shap_values.shape}")

# Crear carpeta para guardar gráficos
output_dir = "logs/analysis_shap"
os.makedirs(output_dir, exist_ok=True)

# ----------------------------------------------------------------------
# Mantenemos la importancia global de las características (SHAP),
# pero eliminamos el loop que creaba gráficos para cada ESP.
# ----------------------------------------------------------------------

# Calcular importancia global de cada ESP
feature_importance = {}
for feature_index, feature_name in enumerate(features):
    shap_values_feature = shap_values[:, feature_index, :].sum(axis=1)
    feature_importance[feature_name] = np.mean(np.abs(shap_values_feature))

# Ordenar características por importancia
sorted_importance = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
features_sorted, importances_sorted = zip(*sorted_importance)

# Crear gráfico de barras para importancia global
plt.figure(figsize=(12, 6))
plt.bar(features_sorted, importances_sorted, color="skyblue")
plt.title("Importancia Global de las Características (SHAP)")
plt.xlabel("Características (ESP32)")
plt.ylabel("Impacto Promedio de SHAP")
plt.xticks(rotation=45)
plt.tight_layout()

# Guardar el gráfico de importancia global
global_importance_path = os.path.join(output_dir, "global_feature_importance.png")
plt.savefig(global_importance_path)
plt.close()
print(f"Gráfico de importancia global guardado en: {global_importance_path}")

# ----------------------------------------------------------------------
# Matriz de confusión con nombres de clases
# ----------------------------------------------------------------------
print("Generando matriz de confusión...")
y_pred = model.predict(X_test)
class_names = label_encoder_habitacion.inverse_transform(
    range(len(label_encoder_habitacion.classes_))
)
ConfusionMatrixDisplay.from_predictions(
    y_test, y_pred, display_labels=class_names, cmap="Blues"
)
plt.title("Matriz de Confusión con Nombres de Clases")
plt.tight_layout()
confusion_matrix_named_path = os.path.join(output_dir, "confusion_matrix_named.png")
plt.savefig(confusion_matrix_named_path)
plt.close()
print(f"Matriz de confusión con nombres guardada en: {confusion_matrix_named_path}")

# ----------------------------------------------------------------------
# Curva ROC y AUC
# ----------------------------------------------------------------------
print("Generando curva ROC...")
y_prob = model.predict_proba(X_test)
plt.figure(figsize=(10, 6))
for i in range(len(label_encoder_habitacion.classes_)):
    fpr, tpr, _ = roc_curve(y_test == i, y_prob[:, i])
    roc_auc = auc(fpr, tpr)
    plt.plot(fpr, tpr, label=f'Clase {class_names[i]} (AUC = {roc_auc:.2f})')
plt.title("Curva ROC")
plt.xlabel("False Positive Rate")
plt.ylabel("True Positive Rate")
plt.legend()
roc_curve_path = os.path.join(output_dir, "roc_curve.png")
plt.savefig(roc_curve_path)
plt.close()
print(f"Curva ROC guardada en: {roc_curve_path}")

# ----------------------------------------------------------------------
# Distribución de errores de predicción
# ----------------------------------------------------------------------
print("Generando distribución de errores de predicción...")
error_distribution = y_test - y_pred
sns.histplot(error_distribution, kde=True, color="purple")
plt.title("Distribución de Errores de Predicción")
plt.xlabel("Error (Valor Real - Predicción)")
plt.tight_layout()
error_distribution_path = os.path.join(output_dir, "error_distribution.png")
plt.savefig(error_distribution_path)
plt.close()
print(f"Distribución de errores guardada en: {error_distribution_path}")
