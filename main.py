from fastapi import FastAPI
from pydantic import BaseModel, EmailStr
import numpy as np
from tensorflow.keras.models import load_model
import psycopg2
# Cargar modelo una vez al iniciar
modelo = load_model("modelo_bueno.keras")

# Crear instancia de FastAPI
app = FastAPI()

# Configuración directa (sin .env)
DB_URL = "postgresql://PulseFitDB_owner:npg_inNlcuI7y4YC@ep-delicate-hat-a4aar8aa-pooler.us-east-1.aws.neon.tech/PulseFitDB?sslmode=require"

# Conexión a la base
def get_conn():
    return psycopg2.connect(DB_URL)

# Esquemas
class RegisterUser(BaseModel):
    correo: EmailStr
    username: str
    password: str

class LoginUser(BaseModel):
    username: str
    password: str

# Registro
@app.post("/register")
def register(user: RegisterUser):
    conn = get_conn()
    cur = conn.cursor()

    # Verificar si ya existe username o correo
    cur.execute("SELECT * FROM users WHERE username = %s OR correo = %s", (user.username, user.correo))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Usuario o correo ya registrado")

    # Insertar nuevo usuario
    cur.execute("""
        INSERT INTO users (username, correo, password, nombre)
        VALUES (%s, %s, %s, %s)
        RETURNING user_id
    """, (user.username, user.correo, user.password, user.username))
    user_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return {"message": "Usuario registrado correctamente", "user_id": user_id}

# Login
@app.post("/login")
def login(user: LoginUser):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT user_id, password FROM users WHERE username = %s", (user.username,))
    result = cur.fetchone()
    conn.close()

    if not result or result[1] != user.password:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return {"message": "Login exitoso", "user_id": result[0]}

# Definir la estructura de los datos de entrada
class EntradaModelo(BaseModel):
    edad: int
    fc_reposo: float
    fc_promedio: float
    imc: float
    dias_entrenando: int

@app.post("/predecir")
def predecir(data: EntradaModelo):
    # Convertir datos a matriz y hacer predicción
    entrada = np.array([[data.edad, data.fc_reposo, data.fc_promedio, data.imc, data.dias_entrenando]])
    prediccion = modelo.predict(entrada)
    umbrales = [0.1, 0.005, 0.005, 0.005, 0.005, 0.4]

    # Aplicar umbrales para obtener predicción binaria
    pred_binaria = (prediccion > umbrales).astype(int)
    # Convertimos a lista de floats con redondeo
    return {"prediccion": prediccion[0].tolist(),
            "prediccion_binaria": pred_binaria[0].tolist()}

@app.get("/")
def saludo():
      print("hola")
      return {"mensaje": "Hola Mundo desde FastAPI en EC2"}