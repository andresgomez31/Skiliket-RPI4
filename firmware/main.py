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
from gpiozero import LED, PWMOutputDevice, MotionSensor
import adafruit_ens160
import adafruit_ahtx0
from RPLCD.i2c import CharLCD
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.client import ClientOptions

# ==============================================================================
# --- 1. CONFIGURACIÓN Y UMBRALES ---
# ==============================================================================

# Cargar variables de entorno (.env)
load_dotenv()

# Credenciales Supabase (API REST)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
NODE_ID = 1  

# --- Configuración de Pines GPIO ---
# Semáforo de Ruido (Actuadores)
PIN_LED_VERDE = 22    # Ruido < 75 dB
PIN_LED_AMARILLO = 23 # Ruido 75 - 85 dB
PIN_LED_ROJO = 24     # Ruido > 85 dB

# Alarma Sonora
PIN_BUZZER = 25       # Alarma por CO2 (Pasivo/PWM)

# Sensor PIR (Entrada)
PIN_PIR = 17          # Movimiento

# --- Umbrales de Lógica ---
UMBRAL_RUIDO_BAJO = 75.0
UMBRAL_RUIDO_ALTO = 85.0
ALERTA_CO2_PPM = 500 # Nivel perjudicial ajustado

# --- Configuración LCD (RPLCD) ---
LCD_COLS = 16
LCD_ROWS = 2
LCD_ADDRESS = 0x27 
LCD_PORT = 1 

# --- Configuración Audio ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

# ==============================================================================
# --- 2. SILENCIADOR DE ERRORES ALSA ---
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
# --- 3. INICIALIZACIÓN DE HARDWARE ---
# ==============================================================================

print("\n--- INICIANDO SISTEMA SKILIKET (NODO 1 - SUPABASE API) ---")

# A. Cliente Supabase
supabase = None
try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ADVERTENCIA] Faltan SUPABASE_URL/KEY en .env (Modo Offline).")
    else:
        # Inicializamos el cliente web estándar
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public"))
        print("[OK] Cliente Supabase inicializado.")
except Exception as e:
    print(f"[ERROR] Supabase Init: {e}")

# B. Bus I2C
try:
    i2c = busio.I2C(board.SCL, board.SDA)
except ValueError:
    print("[ERROR FATAL] I2C no disponible.")
    exit(1)

# C. Sensores I2C
aht = None
ens = None
try:
    aht = adafruit_ahtx0.AHTx0(i2c)
    print("[OK] AHT20 listo.")
except: print("[ERROR] AHT20 no detectado.")

try:
    ens = adafruit_ens160.ENS160(i2c)
    ens.reset()
    time.sleep(0.5)
    ens.mode = adafruit_ens160.MODE_STANDARD
    print("[OK] ENS160 listo.")
except: print("[ERROR] ENS160 no detectado.")

# D. Pantalla LCD (RPLCD)
lcd = None
try:
    lcd = CharLCD(i2c_expander='PCF8574', address=LCD_ADDRESS, port=LCD_PORT, 
                  cols=LCD_COLS, rows=LCD_ROWS, dotsize=8)
    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string('Skiliket IoT')
    lcd.cursor_pos = (1, 0)
    lcd.write_string('Conectando...')
    print(f"[OK] LCD lista en {hex(LCD_ADDRESS)} (RPLCD).")
except Exception as e:
    print(f"[ERROR] LCD no detectada: {e}")

# E. Actuadores y Sensores GPIO
try:
    led_verde = LED(PIN_LED_VERDE)
    led_amarillo = LED(PIN_LED_AMARILLO)
    led_rojo = LED(PIN_LED_ROJO)
    buzzer = PWMOutputDevice(PIN_BUZZER, initial_value=0.0)
    pir = MotionSensor(PIN_PIR, queue_len=1)
    print(f"[OK] GPIO Configurado: LEDs(22-24), Buzzer(25), PIR({PIN_PIR}).")
except Exception as e:
    print(f"[ERROR] GPIO: {e}")

# F. Audio
audio = None
stream = None
try:
    with no_alsa_err():
        audio = pyaudio.PyAudio()
        dev_index = None
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if "USB" in info.get('name', '') or "PnP" in info.get('name', ''):
                dev_index = i
                print(f"[OK] Micrófono USB detectado: {info['name']}")
                break
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                            input_device_index=dev_index, frames_per_buffer=CHUNK)
        print("[OK] Audio activo.")
except Exception as e:
    print(f"[ERROR] Audio: {e}")

# ==============================================================================
# --- 4. LÓGICA DE CONTROL ---
# ==============================================================================

def calcular_decibeles(stream_audio):
    if not stream_audio: return 0.0
    try:
        data = stream_audio.read(CHUNK, exception_on_overflow=False)
        ints = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(ints.astype(np.float32)**2))
        if rms <= 0: return 0.0
        return round(20 * math.log10(rms) + 20, 1)
    except: return 0.0

def gestionar_actuadores(nivel_db, nivel_co2):
    """Controla LEDs por ruido y Buzzer por CO2"""
    # 1. Semáforo
    led_verde.off()
    led_amarillo.off()
    led_rojo.off()
    
    if nivel_db < UMBRAL_RUIDO_BAJO:
        led_verde.on()
    elif UMBRAL_RUIDO_BAJO <= nivel_db <= UMBRAL_RUIDO_ALTO:
        led_amarillo.on()
    else:
        led_rojo.on()
        
    # 2. Buzzer (Alarma CO2)
    status_buzzer = "Silencio"
    if nivel_co2 > ALERTA_CO2_PPM:
        buzzer.frequency = 3000
        buzzer.value = 0.5
        status_buzzer = "ALERTA CO2"
    else:
        buzzer.value = 0.0
        
    return status_buzzer

def actualizar_lcd(temp, hum, co2, tvoc, aqi, db, mov):
    if not lcd:
        time.sleep(4)
        return
    try:
        # PÁGINA 1
        lcd.cursor_pos = (0, 0)
        lcd.write_string(f"T:{temp:.1f}C H:{hum:.0f}%".ljust(16))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(f"Ruido: {db} dB".ljust(16))
        time.sleep(2)

        # PÁGINA 2
        lcd.cursor_pos = (0, 0)
        lcd.write_string(f"CO2: {int(co2)} ppm".ljust(16))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(f"TVOC:{int(tvoc)} AQI:{aqi}".ljust(16))
        time.sleep(2)
        
        # PÁGINA 3
        mov_str = "SI" if mov else "NO"
        estado_ruido = "OK" if db < 85 else "ALTO!"
        lcd.cursor_pos = (0, 0)
        lcd.write_string(f"Movimiento: {mov_str}".ljust(16))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(f"Nivel Ruido:{estado_ruido}".ljust(16))
        time.sleep(2)
    except Exception as e:
        print(f"[Error LCD] {e}")

def enviar_supabase_api(temp, hum, co2, ruido):
    """Envía datos usando la API REST de Supabase"""
    if not supabase: return

    try:
        payload = {
            "node": NODE_ID,
            "temperature": float(f"{temp:.2f}"),
            "humidity": float(f"{hum:.2f}"),
            "co2": float(co2),
            "noise": float(ruido),
            "uv": 0.0
        }
        # Insertar usando el cliente oficial
        supabase.table("measures").insert(payload).execute()
        
    except Exception as e:
        # Convertir error a string para detectar el código 42501
        err_str = str(e)
        if "42501" in err_str or "permission denied" in err_str:
            print("[ERROR RLS] Permiso denegado en Supabase.")
            print(" -> SOLUCIÓN: Ve a Supabase > Table Editor > measures > RLS y desactívalo.")
        else:
            print(f"[ERROR API] Fallo al enviar: {e}")

def exit_handler(signum, frame):
    print("\n[INFO] Apagando...")
    led_verde.off(); led_amarillo.off(); led_rojo.off()
    if buzzer: buzzer.value = 0.0; buzzer.off()
    if lcd: 
        lcd.clear()
        lcd.backlight_enabled = False
        lcd.close()
    if stream: stream.close()
    if audio: audio.terminate()
    exit(0)

signal.signal(signal.SIGINT, exit_handler)

# ==============================================================================
# --- 5. BUCLE PRINCIPAL ---
# ==============================================================================

print(f"Nodo: {NODE_ID} | Micrófono USB | PIR GPIO {PIN_PIR}")
if ens: time.sleep(2) 

while True:
    try:
        # 1. Lectura
        temp = aht.temperature if aht else 0.0
        hum = aht.relative_humidity if aht else 0.0
        if ens and aht:
            ens.temperature = temp
            ens.humidity = hum
        co2 = ens.eCO2 if ens else 0
        tvoc = ens.TVOC if ens else 0
        aqi = ens.AQI if ens else 0
        db = calcular_decibeles(stream)
        mov = pir.motion_detected if pir else False

        # 2. Control
        estado_buzzer = gestionar_actuadores(db, co2)

        # 3. Consola
        ts = time.strftime("%H:%M:%S")
        print("-" * 60)
        print(f"[{ts}] REPORTE DE SENSORES:")
        print(f"   Temperatura:                 {temp:.1f} C")
        print(f"   Humedad:                     {hum:.0f} %")
        print(f"   CO2 (Dióxido de Carbono):    {co2} ppm")
        print(f"   TVOC (Compuestos Orgánicos): {tvoc} ppb")
        print(f"   AQI (Índice Calidad Aire):   {aqi} (1-5)")
        print(f"   Ruido:                       {db} dB")
        print(f"   Movimiento:                  {'SI' if mov else 'NO'}")
        print(f"   Alarma:                      {estado_buzzer}")

        # 4. Envío a Nube (API)
        enviar_supabase_api(temp, hum, co2, db)

        # 5. Visualización Local
        actualizar_lcd(temp, hum, co2, tvoc, aqi, db, mov)

    except KeyboardInterrupt:
        exit_handler(None, None)
    except Exception as e:
        print(f"[ERROR BUCLE] {e}")
        time.sleep(5)
