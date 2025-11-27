import time
from gpiozero import PWMOutputDevice

# Configuración del Pin
BUZZER_PIN = 27

print(f"\n--- REPRODUCIENDO JOJO'S THEME (GIORNO'S THEME) EN GPIO {BUZZER_PIN} ---")

try:
    # Usamos PWMOutputDevice para generar frecuencias
    buzzer = PWMOutputDevice(BUZZER_PIN, initial_value=0.0)

    # Definición de frecuencias EXACTAS para la melodía
    NOTE_D5 = 587.33
    NOTE_E5 = 659.25
    NOTE_FS5 = 739.99  # Fa Sostenido 5
    NOTE_G5 = 783.99
    NOTE_A5 = 880.00
    NOTE_B5 = 987.77   # Si 5
    NOTE_D6 = 1174.66  # Re 6

    # Secuencia CORREGIDA (El famoso "Saxophone Drop")
    # Estructura: F# F# D6 B5 (Pausa) G A F# (Pausa) E F# E D E F#
    melody = [
        # Parte 1: El golpe fuerte
        (NOTE_FS5, 0.15), 
        (NOTE_FS5, 0.15), 
        (NOTE_D6, 0.40),  
        (NOTE_B5, 0.40),  
        (0, 0.10),        # Breve silencio dramático

        # Parte 2: La respuesta rápida
        (NOTE_G5, 0.15), 
        (NOTE_A5, 0.15),
        (NOTE_FS5, 0.40),
        (0, 0.10),        # Breve silencio dramático

        # Parte 3: El cierre rápido
        (NOTE_E5, 0.15),
        (NOTE_FS5, 0.15),
        (NOTE_E5, 0.15),
        (NOTE_D5, 0.15),
        (NOTE_E5, 0.15),
        (NOTE_FS5, 0.40),
    ]

    print("Kono Giorno Giovanna niwa yume ga aru... (Music Start!)")
    time.sleep(1)

    # Reproducir melodía
    for note, duration in melody:
        if note == 0:
            buzzer.value = 0.0  # Silencio
        else:
            buzzer.frequency = note
            buzzer.value = 0.5  # 50% volumen (Duty cycle)
        
        time.sleep(duration)
        
        # Staccato (corte breve entre notas para que no suenen pegadas)
        buzzer.value = 0.0
        time.sleep(0.02)

    print("\n[OK] Melodía finalizada.")

except KeyboardInterrupt:
    print("\nDetenido por usuario.")
    if 'buzzer' in locals():
        buzzer.value = 0.0
        buzzer.off()
except Exception as e:
    print(f"\n[ERROR] {e}")
