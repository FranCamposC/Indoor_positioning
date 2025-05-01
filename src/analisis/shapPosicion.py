import os
import shap
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import ConfusionMatrixDisplay, roc_curve, auc
from sklearn.model_selection import train_test_split
import seaborn as sns
import joblib
import pandas as pd

# ----------------------------------------------------------------------------
# 1) Cargar el modelo y el LabelEncoder para 'Posicion'
#    Ajusta los paths a tus archivos .pkl
# ----------------------------------------------------------------------------
model_posicion_path = "logs/xgboost_posicion_model.pkl"
label_encoder_posicion_path = "logs/xgboost_label_encoder_posicion.pkl"

model = joblib.load(model_posicion_path)
label_encoder_posicion = joblib.load(label_encoder_posicion_path)

# ----------------------------------------------------------------------------
# 2) Cargar el CSV y filtrar datos
#    Ajusta la ruta si tu archivo se llama distinto
# ----------------------------------------------------------------------------
file_path = 'logs/parteDeAbajo.csv'
df = pd.read_csv(file_path)

# Columnas relevantes (RSSI)
features = [col for col in df.columns if col.startswith("ESP32")]

# Eliminar filas con valores faltantes en las columnas RSSI
df_filtered = df.dropna(subset=features)

# ----------------------------------------------------------------------------
# 3) Aplicar el LabelEncoder de Posicion que cargamos
#    IMPORTANTE: Aquí NO se hace fit_transform, sino sólo transform,
#    porque el encoder ya fue entrenado al crear 'xgboost_posicion_model.pkl'
# ----------------------------------------------------------------------------
# Asegúrate de que 'Posicion' en df_filtered es del mismo tipo/categorías 
# que el LabelEncoder conocía. Si no, tendrás que mapear manualmente.
posicion_original = df_filtered['Posicion'].values

# Convertimos los valores originales en sus índices encodificados
y_posicion = label_encoder_posicion.transform(posicion_original)

# ----------------------------------------------------------------------------
# 4) Preparar X e y para train/test
#    (Podríamos usar todo X_test sólo para SHAP, pero repetimos la lógica)
# ----------------------------------------------------------------------------
X = df_filtered[features]
# y_posicion es la variable objetivo ya transformada

# Dividir en conjunto de entrenamiento y prueba
X_train, X_test, y_train, y_test = train_test_split(
    X, y_posicion, test_size=0.4, random_state=42
)

# ----------------------------------------------------------------------------
# 5) Calcular valores SHAP sobre el conjunto de prueba
# ----------------------------------------------------------------------------
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

print(f"Dimensiones de X_test: {X_test.shape}")
print(f"Dimensiones de shap_values: {shap_values.shape}")

# ----------------------------------------------------------------------------
# 6) Crear carpeta para guardar nuestros gráficos de SHAP y métricas
# ----------------------------------------------------------------------------
output_dir = "logs/analysis_shap_posicion"
os.makedirs(output_dir, exist_ok=True)

# ----------------------------------------------------------------------------
# 7) IMPORTANCIA GLOBAL DE LAS CARACTERÍSTICAS (SHAP)
#    (Similar a tu script actual, pero centrado en 'posicion')
# ----------------------------------------------------------------------------
feature_importance = {}
# Para XGBoost multiclass, shap_values es un array [n_samples, n_features, n_classes]
# Sumamos los valores en todas las clases y tomamos la media del valor absoluto
for feature_index, feature_name in enumerate(features):
    # Extraer los SHAP values para esta característica a lo largo de todas las clases
    shap_values_feature = shap_values[:, feature_index, :]
    # Sumamos en axis=1 para colapsar las clases, y nos quedamos con la media
    feature_importance[feature_name] = np.mean(np.abs(shap_values_feature.sum(axis=1)))

# Ordenar características por importancia
sorted_importance = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
features_sorted, importances_sorted = zip(*sorted_importance)

# Crear gráfico de barras
plt.figure(figsize=(12, 6))
plt.bar(features_sorted, importances_sorted, color="skyblue")
plt.title("Importancia Global de las Características (SHAP) - Posicion")
plt.xlabel("Características (ESP32)")
plt.ylabel("Impacto Promedio de SHAP")
plt.xticks(rotation=45)
plt.tight_layout()

# Guardar gráfico
global_importance_path = os.path.join(output_dir, "global_feature_importance_posicion.png")
plt.savefig(global_importance_path)
plt.close()
print(f"Gráfico de importancia global (Posicion) guardado en: {global_importance_path}")

# ----------------------------------------------------------------------------
# 8) Matriz de confusión
# ----------------------------------------------------------------------------
print("Generando matriz de confusión para 'Posicion'...")

y_pred = model.predict(X_test)

# Definir 'class_names' antes de usarlo:
class_names = label_encoder_posicion.inverse_transform(
    range(len(label_encoder_posicion.classes_))
)

fig, ax = plt.subplots(figsize=(10, 8))  # Ajusta el tamaño según necesites
disp = ConfusionMatrixDisplay.from_predictions(
    y_test,
    y_pred,
    display_labels=class_names,
    cmap="Blues",
    ax=ax
)
# Rotar las etiquetas del eje X (predicted label):
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

plt.title("Matriz de Confusión para Posicion (clases originales)")
plt.tight_layout()

confusion_matrix_named_path = os.path.join(output_dir, "confusion_matrix_named_posicion.png")
plt.savefig(confusion_matrix_named_path)
plt.close()
print(f"Matriz de confusión guardada en: {confusion_matrix_named_path}")


# ----------------------------------------------------------------------------
# 9) Curva ROC y AUC (multiclase)
#    Dibujamos la curva ROC para cada clase vs. el resto
# ----------------------------------------------------------------------------
print("Generando curva ROC para 'Posicion'...")
y_prob = model.predict_proba(X_test)
plt.figure(figsize=(10, 6))
for i in range(len(label_encoder_posicion.classes_)):
    fpr, tpr, _ = roc_curve(y_test == i, y_prob[:, i])
    roc_auc = auc(fpr, tpr)
    plt.plot(fpr, tpr, label=f"Clase {class_names[i]} (AUC = {roc_auc:.2f})")

plt.title("Curva ROC - Posicion")
plt.xlabel("False Positive Rate")
plt.ylabel("True Positive Rate")
plt.legend()
roc_curve_path = os.path.join(output_dir, "roc_curve_posicion.png")
plt.savefig(roc_curve_path)
plt.close()
print(f"Curva ROC guardada en: {roc_curve_path}")

# ----------------------------------------------------------------------------
# 10) Distribución de errores
# ----------------------------------------------------------------------------
print("Generando distribución de errores de predicción para 'Posicion'...")
error_distribution = y_test - y_pred
sns.histplot(error_distribution, kde=True, color="purple")
plt.title("Distribución de Errores de Predicción (Posicion)")
plt.xlabel("Error (Valor Real - Predicción)")
plt.tight_layout()
error_distribution_path = os.path.join(output_dir, "error_distribution_posicion.png")
plt.savefig(error_distribution_path)
plt.close()
print(f"Distribución de errores guardada en: {error_distribution_path}")

print("\n--- Análisis SHAP de 'Posicion' completado con éxito ---")
