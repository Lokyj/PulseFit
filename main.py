from fastapi import FastAPI
from pydantic import BaseModel
import numpy as np
from tensorflow.keras.models import load_model

# Cargar modelo una vez al iniciar
modelo = load_model("modelo_bueno.keras")

# Crear instancia de FastAPI
app = FastAPI()

# Definir la estructura de los datos de entrada
class EntradaModelo(BaseModel):
    edad: float
    fc_reposo: float
    fc_promedio: float
    imc: float
    dias_entrenando: float

@app.post("/predecir")
def predecir(data: EntradaModelo):
    # Convertir datos a matriz y hacer predicción
    entrada = np.array([[data.edad, data.fc_reposo, data.fc_promedio, data.imc, data.dias_entrenando]])
    prediccion = modelo.predict(entrada)
    # Convertimos a lista de floats con redondeo
    return {"prediccion": prediccion[0].tolist()}

@app.get("/")
def saludo():
      print("hola")
      return {"mensaje": "Hola Mundo desde FastAPI en EC2"}