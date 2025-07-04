from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import numpy as np
from tensorflow.keras.models import load_model
import psycopg2
import joblib
from datetime import date
# Cargar modelo una vez al iniciar
modelo = load_model("modelo_bueno_Scaler.keras")
# Cargar el scaler
scaler = joblib.load("scaler.pkl")
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
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s OR correo = %s",
                    (user.username, user.correo))
        if cur.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Usuario o correo ya registrado")

        cur.execute("""
            INSERT INTO users (username, correo, password, nombre)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id
        """, (user.username, user.correo, user.password, user.username))
        user_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return {"message": "Usuario registrado correctamente", "user_id": user_id}
    except HTTPException:
        # deja pasar las HTTPException que lanzaste tú
        raise
    except Exception as e:
        # captura TODO lo demás y lo devuelve en el body
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")

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
    entrada_scaled = scaler.transform(entrada)
    
    # Realizar la predicción
    prediccion = modelo.predict(entrada_scaled)

    # Definir umbrales para cada etiqueta
    umbrales = [0.5, 0.3, 0.25, 0.5, 0.27, 0.55]

    # Aplicar umbrales para obtener predicción binaria
    pred_binaria = (prediccion > umbrales).astype(int)
    
    return {"prediccion": prediccion[0].tolist(),
            "prediccion_binaria": pred_binaria[0].tolist()}

class UserDataResponse(BaseModel):
    nombre: str
    edad: int
    dias_login: int
    imc: float
    ultima_fc_rutina: int | None
    ultima_fc_reposo: int | None


@app.get("/userData/{user_id}")
def get_user_data(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()

    # Datos del usuario
    cursor.execute("""
        SELECT nombre, edad, dias_login, imc 
        FROM users 
        WHERE user_id = %s
    """, (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

     # Obtener última FC en rutina
    cursor.execute("""
        SELECT fc_avg
        FROM fc_avg_rutina
        WHERE user_id = %s
        ORDER BY fecha DESC
        LIMIT 1
    """, (user_id,))
    rutina_row = cursor.fetchone()

    # Obtener última FC en reposo
    cursor.execute("""
        SELECT fc_rep
        FROM fc_avg_reposo
        WHERE user_id = %s
        ORDER BY fecha DESC
        LIMIT 1
    """, (user_id,))
    reposo_row = cursor.fetchone()

    cursor.close()

    return {
        "nombre":row[0],
        "edad":row[1],
        "dias_login":row[2],
        "imc":float(row[3]) if [3] is not None else 0.0,
        "ultima_fc_rutina":rutina_row[0] if rutina_row else None,
        "ultima_fc_reposo":reposo_row[0] if reposo_row else None
    }


class FCRutinaInput(BaseModel):
    user_id: int
    fc_avg: float

@app.post("/fc_rutina")
def registrar_fc_rutina(data: FCRutinaInput):
    conn = get_conn()
    cursor = conn.cursor()
    today = date.today()

    try:
        cursor.execute("""
            INSERT INTO fc_avg_rutina (user_id, fecha, fc_avg)
            VALUES (%s, %s, %s)
        """, (data.user_id, today, data.fc_avg))
        conn.commit()
        return {"mensaje": "Frecuencia promedio registrada"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {e}")

    finally:
        cursor.close()

class FCReposoInput(BaseModel):
    user_id: int
    fc_rep: float

@app.post("/fc_reposo")
def registrar_fc_reposo(data: FCReposoInput):
    conn = get_conn()
    cursor = conn.cursor()
    today = date.today()

    try:
        cursor.execute("""
            INSERT INTO fc_avg_reposo (user_id, fecha, fc_rep)
            VALUES (%s, %s, %s)
        """, (data.user_id, today, data.fc_rep))
        conn.commit()
        return {"mensaje": "Frecuencia en reposo registrada"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {e}")

    finally:
        cursor.close()

class InitialData(BaseModel):
    user_id: int
    user_height: float
    user_weight: float
    user_age: int

@app.post("/initialData")
def initial_data(user: InitialData):
    conn = get_conn()
    cursor = conn.cursor()

    # calcular imc con datos ingresados
    imc = user.user_weight / (user.user_height ** 2)
    cursor.execute("""
        INSERT INTO users (altura, peso, edad, imc, dias_login)
        VALUES (%s, %s, %s, %s, 0)
        ON CONFLICT (user_id) DO UPDATE SET
            altura = EXCLUDED.altura,
            peso = EXCLUDED.peso,
            edad = EXCLUDED.edad,
            imc = EXCLUDED.imc
    """, (user.user_height, user.user_weight, user.user_age, imc)) 

    conn.commit()
    conn.close()

    return {"mensaje": "Datos iniciales registrados correctamente"}

@app.get("/")
def saludo():
      print("hola")
      return {"mensaje": "Hola Mundo desde FastAPI en EC2"}
