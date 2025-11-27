import time
import board
import busio
import os
import signal
import math
import numpy as np
import pyaudio
from ctypes import *
from contextlib import contextmanager
from gpiozero import PWMOutputDevice, MotionSensor
import adafruit_ens160
import adafruit_ahtx0
import adafruit_character_lcd.character_lcd_i2c as character_lcd # <-- LIBRERÍA LCD
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.client import ClientOptions

# ==============================================================================
# --- 1. CONFIGURACIÓN GENERAL ---
# ==============================================================================

# Cargar variables de entorno
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
NODE_ID = 1

# Configuración de Pines GPIO
BUZZER_PIN = 27
PIR_PIN = 22    # Sensor de Movimiento

# Configuración LCD (I2C)
LCD_COLUMNS = 16
LCD_ROWS = 2
LCD_ADDRESS = 0x27 # Dirección estándar (verifica si es 0x27 o 0x3F)

# Límites de Alerta
CO2_LIMIT_PPM = 1000
DB_LIMIT = 70.0  # Umbral de ruido (dB) para activar alarma

# Configuración de Audio (Micrófono USB)
CHUNK = 1024            # Muestras por bloque
FORMAT = pyaudio.paInt16 # Resolución de 16 bits
CHANNELS = 1            # Mono
RATE = 44100            # Frecuencia de muestreo (Hz)

# Mapa AQI
AQI_STATUS_MAP = {
    1: "Excelente", 2: "Bueno", 3: "Moderado", 4: "Pobre", 5: "Insano"
}

# ==============================================================================
# --- 2. MANEJADOR DE ERRORES DE AUDIO (SILENCIADOR) ---
# ==============================================================================
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def no_alsa_err():
    try:
        asound = cdll.LoadLibrary('libasound.so.2')
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)
    except:
        yield

# ==============================================================================
# --- 3. INICIALIZACIÓN ---
# ==============================================================================

# A. Supabase
try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Faltan las credenciales en el archivo .env")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public"))
    print("Conexión a Supabase establecida.")
except Exception as e:
    print(f"Error crítico Supabase: {e}")
    exit()

# B. Bus I2C
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    print("Bus I2C inicializado.")
except ValueError:
    print("Error: Bus I2C no disponible.")
    exit()

# C. Sensores I2C y Periféricos
aht = None
ens = None
lcd = None
buzzer = None
pir = None

# AHT20
try:
    aht = adafruit_ahtx0.AHTx0(i2c)
    print("[OK] AHT20 inicializado.")
except Exception as e:
    print(f"[ERROR] AHT20: {e}")

# ENS160
try:
    ens = adafruit_ens160.ENS160(i2c)
    ens.reset()
    time.sleep(0.5)
    ens.mode = adafruit_ens160.MODE_STANDARD
    print("[OK] ENS160 inicializado.")
except Exception as e:
    print(f"[ERROR] ENS160: {e}")

# LCD 16x2 (I2C)
try:
    lcd = character_lcd.Character_LCD_I2C(i2c, LCD_COLUMNS, LCD_ROWS, address=LCD_ADDRESS)
    lcd.backlight = True
    lcd.clear()
    lcd.message = "Skiliket IoT\nIniciando..."
    print(f"[OK] LCD inicializada en {hex(LCD_ADDRESS)}.")
except Exception as e:
    print(f"[ADVERTENCIA] LCD no detectada: {e}")

# Buzzer (GPIO 27) - PASIVO (PWM)
try:
    buzzer = PWMOutputDevice(BUZZER_PIN, initial_value=0.0)
    print(f"[OK] Buzzer Pasivo (PWM) en GPIO {BUZZER_PIN}.")
except Exception as e:
    print(f"[ERROR] Buzzer: {e}")

# Sensor PIR (GPIO 22)
try:
    pir = MotionSensor(PIR_PIN, queue_len=1)
    print(f"[OK] Sensor PIR inicializado en GPIO {PIR_PIN}.")
except Exception as e:
    print(f"[ERROR] Sensor PIR: {e}")

# D. Inicialización de Audio (PyAudio)
audio = None
stream = None

try:
    with no_alsa_err():
        audio = pyaudio.PyAudio()
        device_index = None
        print("-" * 30)
        print("Buscando micrófono USB...")
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            name = info.get('name', '')
            if "USB" in name or "PnP" in name or "PCM2902" in name:
                device_index = i
                print(f" -> ENCONTRADO: {name} (Index {i})")
                break

        if device_index is None:
            print("[ADVERTENCIA] No se detectó dispositivo USB.")

        stream = audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            input_device_index=device_index,
                            frames_per_buffer=CHUNK)
    print("[OK] Stream de audio iniciado.")

except Exception as e:
    print(f"[ERROR] Fallo al iniciar audio: {e}")

# ==============================================================================
# --- 4. FUNCIONES ---
# ==============================================================================

def calculate_db(audio_stream):
    if not audio_stream: return 0.0
    try:
        data = audio_stream.read(CHUNK, exception_on_overflow=False)
        ints = np.frombuffer(data, dtype=np.int16)
        floats = ints.astype(np.float32)
        rms = np.sqrt(np.mean(floats**2))
        if rms <= 0: return 0.0
        offset = 20
        decibels = 20 * math.log10(rms) + offset
        return round(max(0, decibels), 2)
    except Exception as e: return 0.0

def exit_handler(signum, frame):
    print("\nCerrando sistema...")
    if lcd:
        try:
            lcd.clear()
            lcd.backlight = False # Apagar luz al salir
        except: pass
    if buzzer:
        buzzer.value = 0.0
        buzzer.off()
    if stream:
        stream.stop_stream()
        stream.close()
    if audio:
        audio.terminate()
    exit(0)

signal.signal(signal.SIGINT, exit_handler)

def mostrar_ciclo_lcd(temp, hum, co2, db, mov, estado_buzzer):
    """Muestra información rotativa en la LCD"""
    if not lcd:
        time.sleep(5) # Si no hay LCD, esperamos 5 seg aquí
        return

    try:
        # Usamos ljust(16) para limpiar residuos de texto anterior sin borrar pantalla
        
        # PANTALLA 1: Clima Básico
        lcd.cursor_position(0, 0)
        line1 = f"T:{temp:.1f}C H:{hum:.0f}%".ljust(16)
        line2 = f"Ruido: {db} dB".ljust(16)
        lcd.message = f"{line1}\n{line2}"
        time.sleep(2.5) # Tiempo de visualización

        # PANTALLA 2: Calidad Aire y Estado
        lcd.cursor_position(0, 0)
        mov_str = "SI" if mov else "NO"
        # Mostramos alerta si el buzzer suena, sino el movimiento
        estado_extra = "ALERTA!" if "ACTIVADO" in estado_buzzer else f"Mov: {mov_str}"
        
        line1 = f"CO2: {int(co2)} ppm".ljust(16)
        line2 = f"{estado_extra}".ljust(16)
        lcd.message = f"{line1}\n{line2}"
        time.sleep(2.5) # Tiempo de visualización
        
    except Exception as e:
        print(f"[Error LCD] {e}")

# ==============================================================================
# --- 5. BUCLE PRINCIPAL ---
# ==============================================================================

print("\n--- Sistema IoT Iniciado ---")
print(f"Nodo: {NODE_ID} | Micrófono USB | PIR GPIO {PIR_PIN}")

if ens:
    print("Calentando sensor ENS160 (3 seg)...")
    time.sleep(3)

while True:
    try:
        # 1. Variables por defecto
        temp_c, hum_rel, eco2, tvoc, aqi = 0.0, 0.0, 0.0, 0, 0
        motion_detected = False

        # 2. Lectura Sensores
        if aht:
            try:
                temp_c = aht.temperature
                hum_rel = aht.relative_humidity
            except: pass

        if ens:
            try:
                if aht:
                    ens.temperature = temp_c
                    ens.humidity = hum_rel
                eco2 = ens.eCO2
                tvoc = ens.TVOC
                aqi = ens.AQI
            except: pass

        db_level = calculate_db(stream)

        if pir:
            motion_detected = pir.motion_detected

        # 6. Lógica de Alarma (Buzzer Pasivo)
        estado_buzzer = "Inactivo"
        if buzzer:
            alerta_co2 = eco2 > CO2_LIMIT_PPM
            alerta_ruido = db_level > DB_LIMIT

            if alerta_co2 or alerta_ruido:
                buzzer.frequency = 2000
                buzzer.value = 0.5
                estado_buzzer = "ACTIVADO"
            else:
                buzzer.value = 0.0

        # 7. Consola
        ts = time.strftime("%H:%M:%S")
        mov_txt = "SÍ" if motion_detected else "NO"
        print("-" * 50)
        print(f"[{ts}] Estado del Ambiente:")
        print(f"Temp: {temp_c:.1f}C | Humedad: {hum_rel:.1f}% | CO2: {eco2} ppm")
        print(f"Ruido: {db_level} dB | Movimiento: {mov_txt} | Alarma: {estado_buzzer}")

        # 8. Base de Datos
        data_payload = {
            "node": NODE_ID,
            "humidity": float(f"{hum_rel:.2f}"),
            "co2": float(eco2),
            # Descomentar cuando existan las columnas:
            # "temperature": float(f"{temp_c:.2f}"),
            # "noise": db_level,
            # "uv": 0.0,
            # "tvoc": int(tvoc),
            # "aqi": int(aqi),
            # "presence": bool(motion_detected)
        }

        try:
            supabase.table("measures").insert(data_payload).execute()
            print("Datos guardados en DB.")
        except Exception as e:
            print(f"Error DB: {e}")

        # 9. Ciclo Visual LCD (Reemplaza al sleep estático)
        # Esto hace que el bucle dure aprox 5 segundos (2.5s por pantalla x 2)
        mostrar_ciclo_lcd(temp_c, hum_rel, eco2, db_level, motion_detected, estado_buzzer)

    except KeyboardInterrupt:
        exit_handler(None, None)
    except Exception as e:
        print(f"Error bucle principal: {e}")
        time.sleep(5)
