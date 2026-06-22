import serial
from datetime import datetime

ser = serial.Serial('COM4', 9600, timeout=1)

archivo = open("datos_serial.txt", "a", encoding="utf-8")

print("Guardando datos... Presiona Ctrl+C para detener.")

try:
    while True:
        if ser.in_waiting > 0:
            dato = ser.readline().decode("utf-8", errors="ignore").strip()

            if dato != "":
                tiempo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                linea = f"{tiempo} - {dato}"

                print(linea)
                archivo.write(linea + "\n")
                archivo.flush()

except KeyboardInterrupt:
    print("Lectura detenida por el usuario.")

finally:
    archivo.close()
    ser.close()