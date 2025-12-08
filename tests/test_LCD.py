import time
import board
import busio
import adafruit_character_lcd.character_lcd_i2c as character_lcd

# ==========================================
# CONFIGURACIÓN
# ==========================================
# Dirección I2C común: 0x27 o 0x3F.
# El escáner abajo nos dirá cuál es la correcta.
LCD_COLUMNS = 16
LCD_ROWS = 2

print("\n" + "="*40)
print("   PRUEBA DE DIAGNÓSTICO LCD 16x2")
print("="*40)

# 1. INICIALIZAR I2C
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    print("[PASO 1] Bus I2C iniciado correctamente.")
except ValueError:
    print("[ERROR FATAL] No se detectó el bus I2C. Revisa cables SDA/SCL.")
    exit()

# 2. ESCANEAR DISPOSITIVOS
print("[PASO 2] Escaneando direcciones I2C...")
while not i2c.try_lock():
    pass
try:
    devices = i2c.scan()
    direcciones_hex = [hex(device) for device in devices]
    print(f"   -> Dispositivos encontrados: {direcciones_hex}")
    
    if not devices:
        print("   [ALERTA] No se encontró NINGÚN dispositivo. Revisa cableado (VCC, GND, SDA, SCL).")
        exit()
        
    # Intentamos adivinar la dirección de la LCD (usualmente 0x27)
    lcd_address = 0x27
    if 0x27 in devices:
        lcd_address = 0x27
    elif 0x3f in devices:
        lcd_address = 0x3f
    elif len(devices) > 0:
        lcd_address = devices[0] # Usar el primero que encuentre si no es estándar
        print(f"   -> Usando dirección detectada: {hex(lcd_address)}")
    
finally:
    i2c.unlock()

# 3. INICIALIZAR PANTALLA
print(f"[PASO 3] Intentando encender LCD en {hex(lcd_address)}...")
try:
    lcd = character_lcd.Character_LCD_I2C(i2c, LCD_COLUMNS, LCD_ROWS, address=lcd_address)
    lcd.backlight = True
    lcd.clear()
    print("   -> Objeto LCD creado. Luz de fondo activada.")
except Exception as e:
    print(f"[ERROR] Fallo al crear objeto LCD: {e}")
    exit()

# 4. BUCLE DE PRUEBA VISUAL
print("\n[PASO 4] Ejecutando prueba visual...")
print("   -> Si la pantalla brilla pero NO ves texto: GIRA EL TORNILLO AZUL TRASERO.")
print("   -> Si la pantalla está negra: Revisa conexión a 5V.")

try:
    conteo = 0
    while True:
        # Forzar luz encendida
        lcd.backlight = True
        
        # Mensaje 1
        lcd.clear()
        lcd.message = f"TEST DE PANTALLA\nDireccion: {hex(lcd_address)}"
        time.sleep(3)
        
        # Mensaje 2 (Contador para ver si se congela)
        lcd.clear()
        lcd.message = f"Funcionando...\nConteo: {conteo}"
        conteo += 1
        time.sleep(2)
        
        # Efecto de parpadeo de luz (Para confirmar control)
        lcd.backlight = False
        time.sleep(0.5)
        lcd.backlight = True
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n[FIN] Prueba finalizada por usuario.")
    lcd.clear()
    lcd.backlight = False
