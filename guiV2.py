"""
GUI simple - Mapeo Espacial 2D por Fusion Multisensorial
MT7002 Sensores y Actuadores - Proyecto Final (Entrega 3)

Recibe por puerto serie una linea de texto por cada punto:
    angulo,dist_us,dist_ir,dist_laser
ej:  90,45.30,46.10,44.95

Combina las tres lecturas con un promedio ponderado de pesos predefinidos
y dibuja la nube de puntos resultante en un mapa polar en tiempo real.

Instalar:  pip install pyserial matplotlib
Ejecutar:  python gui_mapeo_simple.py
"""

import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import serial
import serial.tools.list_ports as list_ports

# ---------------- Configuracion ----------------
BAUDRATE = 115200

# Pesos predefinidos para la fusion (deben sumar 1).
# Ajustar segun los resultados de caracterizacion de la Entrega 1.
PESO_US = 0.30      # Ultrasonido
PESO_IR = 0.30      # Infrarrojo
PESO_LASER = 0.40   # Laser ToF

RANGO_MAX_CM = 200  # rango maximo de operacion del sistema (cm)

# ---------------- Variables globales ----------------
cola = queue.Queue()
evento_parar = threading.Event()
hilo = None
ser = None

thetas = []           # angulos acumulados de la vuelta actual (radianes)
radios = []            # distancias fusionadas acumuladas (cm)
angulo_anterior = None


# ---------------- Logica (funciones simples, sin clases) ----------------
def fusionar(d_us, d_ir, d_laser):
    """Promedio ponderado simple de las 3 lecturas."""
    return PESO_US * d_us + PESO_IR * d_ir + PESO_LASER * d_laser


def parse_linea(linea):
    """Convierte 'angulo,d_us,d_ir,d_laser' en una tupla de floats.
    Devuelve None si la linea no tiene el formato esperado."""
    try:
        partes = linea.strip().split(",")
        if len(partes) != 4:
            return None
        return tuple(float(p) for p in partes)
    except ValueError:
        return None


def leer_serial():
    """Funcion que corre en un hilo aparte: lee del puerto serie y mete
    cada dato valido en la cola para que la GUI lo procese."""
    while not evento_parar.is_set():
        try:
            linea = ser.readline().decode("utf-8", errors="ignore")
        except serial.SerialException:
            cola.put(("error", "Se perdio la conexion con el puerto"))
            return
        datos = parse_linea(linea)
        if datos:
            cola.put(("dato", datos))


# ---------------- Conexion ----------------
def conectar():
    global ser, hilo
    puerto = combo_puertos.get()
    if not puerto:
        messagebox.showwarning("Aviso", "Selecciona un puerto serial")
        return
    try:
        ser = serial.Serial(puerto, BAUDRATE, timeout=1)
    except serial.SerialException as e:
        messagebox.showerror("Error", str(e))
        return

    time.sleep(2)  # esperar a que el Arduino reinicie tras abrir el puerto
    evento_parar.clear()
    hilo = threading.Thread(target=leer_serial, daemon=True)
    hilo.start()

    btn_conectar.config(text="Desconectar", command=desconectar)
    lbl_estado.config(text=f"Conectado a {puerto}", foreground="green")


def desconectar():
    evento_parar.set()
    if ser and ser.is_open:
        ser.close()
    btn_conectar.config(text="Conectar", command=conectar)
    lbl_estado.config(text="Desconectado", foreground="red")


# ---------------- Grafico ----------------
def configurar_grafico():
    ax.clear()
    ax.set_theta_zero_location("N")   # 0 grados apunta hacia arriba
    ax.set_theta_direction(-1)        # sentido horario
    ax.set_rmax(RANGO_MAX_CM + 20)
    ax.set_title("Nube de puntos fusionada (cm)")


def redibujar():
    configurar_grafico()
    if thetas:
        ax.scatter(thetas, radios, s=12, c="tab:blue")
    canvas.draw_idle()


def procesar_cola():
    """Revisa la cola cada 100 ms, agrega los puntos nuevos y redibuja."""
    global angulo_anterior
    hubo_dato = False

    while not cola.empty():
        tipo, contenido = cola.get()
        if tipo == "error":
            messagebox.showerror("Error", contenido)
            desconectar()
            break

        angulo, d_us, d_ir, d_laser = contenido

        # Si el angulo "retrocede" significa que empezo una nueva vuelta
        if angulo_anterior is not None and angulo < angulo_anterior:
            thetas.clear()
            radios.clear()
        angulo_anterior = angulo

        thetas.append(math.radians(angulo))
        radios.append(fusionar(d_us, d_ir, d_laser))
        hubo_dato = True

    if hubo_dato:
        redibujar()
        lbl_info.config(text=f"Ultimo punto: {angulo:.0f} grados, {radios[-1]:.1f} cm")

    ventana.after(100, procesar_cola)


def al_cerrar():
    desconectar()
    ventana.destroy()


# ---------------- Interfaz ----------------
if __name__ == 'main':
    ventana = tk.Tk()
    ventana.title("Mapeo 2D - Fusion de sensores")
    ventana.geometry("950x650")
    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)

    panel = ttk.Frame(ventana, padding=10)
    panel.pack(side=tk.LEFT, fill=tk.Y)

    ttk.Label(panel, text="Puerto serial:").pack(anchor="w")
    combo_puertos = ttk.Combobox(panel, values=[p.device for p in list_ports.comports()])
    combo_puertos.pack(fill=tk.X, pady=5)

    btn_conectar = ttk.Button(panel, text="Conectar", command=conectar)
    btn_conectar.pack(fill=tk.X, pady=5)

    lbl_estado = ttk.Label(panel, text="Desconectado", foreground="red")
    lbl_estado.pack(pady=5)

    lbl_info = ttk.Label(panel, text="-")
    lbl_info.pack(pady=10)

    fig = plt.Figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="polar")
    canvas = FigureCanvasTkAgg(fig, master=ventana)
    canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    configurar_grafico()
    canvas.draw()
    ventana.after(100, procesar_cola)
    ventana.mainloop()