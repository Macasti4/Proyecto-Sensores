"""
GUI de Visualizacion en Tiempo Real - Mapeo Espacial 2D por Fusion Multisensorial
MT7002 Sensores y Actuadores - Proyecto Final (Entrega 3)

Recibe por puerto serie una linea de texto por cada punto, con el formato:
    angulo,dist_us,dist_ir,dist_laser
ej:  90,45.30,46.10,44.95

Combina las tres lecturas mediante un PROMEDIO PONDERADO con pesos
predefinidos (ajustables desde la propia GUI) y dibuja la nube de puntos
resultante en un mapa polar en tiempo real, estilo "radar".

Dependencias (instalar con pip):
    pip install pyserial matplotlib

tkinter viene incluido con la instalacion estandar de Python en Windows y
Mac. En Linux puede requerir instalarlo aparte:
    sudo apt install python3-tk

Ejecutar:
    python gui_mapeo_fusion.py
"""

import csv
import math
import queue
import random
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import serial
import serial.tools.list_ports as list_ports


# ----------------------------------------------------------------------
# CONFIGURACION -- AJUSTAR SEGUN LOS RESULTADOS DE LA ENTREGA 1
# ----------------------------------------------------------------------
BAUDRATE_DEFAULT = 115200

# Pesos predefinidos para la fusion (no es obligatorio que sumen 1: se
# normalizan automaticamente). Ajustar segun la exactitud/precision de
# cada sensor obtenida en la caracterizacion de la Entrega 1.
PESOS_DEFAULT = {
    "us": 0.30,     # Ultrasonido (ej. HC-SR04)
    "ir": 0.30,     # Infrarrojo (triangulacion)
    "laser": 0.40,  # Laser ToF
}

# Rango efectivo de operacion del sistema (cm), segun especificacion del proyecto
RANGO_MIN_CM = 10.0
RANGO_MAX_CM = 200.0

# Si el angulo "retrocede" mas de esto respecto a la lectura anterior, se
# asume que comenzo una nueva vuelta y se limpia el mapa para redibujar
UMBRAL_NUEVA_VUELTA = 180.0

INTERVALO_REFRESCO_MS = 100  # cada cuanto se revisa la cola y se redibuja


# ----------------------------------------------------------------------
# LOGICA PURA (sin GUI) -- facil de probar de forma independiente
# ----------------------------------------------------------------------
def parse_line(line: str):
    """
    Convierte una linea recibida por serial en (angulo, d_us, d_ir, d_laser).
    Devuelve None si la linea no tiene el formato esperado (lineas
    incompletas, texto de depuracion del Arduino, etc. se ignoran).
    """
    try:
        partes = line.strip().split(",")
        if len(partes) != 4:
            return None
        angulo, d_us, d_ir, d_laser = (float(p) for p in partes)
        return angulo, d_us, d_ir, d_laser
    except (ValueError, AttributeError):
        return None


def distancia_valida(d: float) -> bool:
    """True si la lectura cae dentro del rango efectivo del sistema."""
    return RANGO_MIN_CM <= d <= RANGO_MAX_CM


def fusionar_distancias(d_us, d_ir, d_laser, pesos):
    """
    Promedio ponderado de las 3 lecturas. Las lecturas fuera del rango
    valido se excluyen y los pesos restantes se renormalizan entre si.
    Devuelve (distancia_fusionada, n_sensores_usados); si ninguna lectura
    es valida devuelve (None, 0).
    """
    lecturas = [("us", d_us), ("ir", d_ir), ("laser", d_laser)]
    validas = [(nombre, d) for nombre, d in lecturas if distancia_valida(d)]

    if not validas:
        return None, 0

    suma_pesos = sum(pesos[nombre] for nombre, _ in validas)
    if suma_pesos <= 0:
        fusion = sum(d for _, d in validas) / len(validas)
    else:
        fusion = sum(pesos[nombre] * d for nombre, d in validas) / suma_pesos

    return fusion, len(validas)


def normalizar_pesos(pesos: dict) -> dict:
    total = sum(pesos.values())
    if total <= 0:
        n = len(pesos)
        return {k: 1.0 / n for k in pesos}
    return {k: v / total for k, v in pesos.items()}


# ----------------------------------------------------------------------
# HILO DE LECTURA SERIAL
# ----------------------------------------------------------------------
class LectorSerial(threading.Thread):
    def __init__(self, puerto, baudrate, cola_salida, evento_parar):
        super().__init__(daemon=True)
        self.puerto = puerto
        self.baudrate = baudrate
        self.cola = cola_salida
        self.parar = evento_parar
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.puerto, self.baudrate, timeout=1)
        except serial.SerialException as e:
            self.cola.put(("error", str(e)))
            return

        time.sleep(2)  # tiempo para que el Arduino reinicie tras abrir el puerto

        while not self.parar.is_set():
            try:
                raw = self.ser.readline()
            except serial.SerialException as e:
                self.cola.put(("error", str(e)))
                break
            if not raw:
                continue
            try:
                linea = raw.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                continue
            datos = parse_line(linea)
            if datos is None:
                continue
            self.cola.put(("dato", datos))

        if self.ser and self.ser.is_open:
            self.ser.close()


# ----------------------------------------------------------------------
# HILO DE SIMULACION (para probar la GUI sin el hardware conectado)
# ----------------------------------------------------------------------
class SimuladorDatos(threading.Thread):
    """Genera datos sinteticos de un cuarto rectangular con ruido por
    sensor, util para probar la interfaz sin tener el Arduino a la mano."""

    def __init__(self, cola_salida, evento_parar, paso_grados=2):
        super().__init__(daemon=True)
        self.cola = cola_salida
        self.parar = evento_parar
        self.paso = paso_grados

    @staticmethod
    def _distancia_cuarto(angulo_deg, ancho=150, alto=100):
        rad = math.radians(angulo_deg)
        dx = (ancho / 2) / max(abs(math.cos(rad)), 1e-6)
        dy = (alto / 2) / max(abs(math.sin(rad)), 1e-6)
        return min(dx, dy)

    def run(self):
        angulo = 0.0
        while not self.parar.is_set():
            d_real = self._distancia_cuarto(angulo)
            d_real = max(RANGO_MIN_CM, min(RANGO_MAX_CM, d_real))
            d_us = d_real + random.gauss(0, 2.5)
            d_ir = d_real + random.gauss(0, 1.5)
            d_laser = d_real + random.gauss(0, 0.5)
            self.cola.put(("dato", (angulo, d_us, d_ir, d_laser)))
            angulo = (angulo + self.paso) % 360
            time.sleep(0.05)


# ----------------------------------------------------------------------
# APLICACION PRINCIPAL (GUI)
# ----------------------------------------------------------------------
class AppMapeo:
    def __init__(self, root):
        self.root = root
        self.root.title("Mapeo Espacial 2D - Fusion Multisensorial (MT7002)")
        self.root.geometry("1100x680")
        self.root.protocol("WM_DELETE_WINDOW", self.al_cerrar)

        self.cola = queue.Queue()
        self.evento_parar = threading.Event()
        self.hilo_lectura = None
        self.conectado = False

        self.pesos = dict(PESOS_DEFAULT)

        self.thetas = []
        self.radios = []
        self.colores = []
        self.angulo_anterior = None
        self.n_puntos_total = 0
        self.n_vueltas = 0
        self.historial_csv = []

        self._construir_widgets()
        self._configurar_grafico()
        self._actualizar_lista_puertos()
        self.root.after(INTERVALO_REFRESCO_MS, self._procesar_cola)

    # ---------------- construccion de la interfaz ----------------
    def _construir_widgets(self):
        panel = ttk.Frame(self.root, padding=10)
        panel.pack(side=tk.LEFT, fill=tk.Y)

        f_con = ttk.LabelFrame(panel, text="Conexion Serial", padding=10)
        f_con.pack(fill=tk.X, pady=5)

        ttk.Label(f_con, text="Puerto:").grid(row=0, column=0, sticky="w")
        self.combo_puertos = ttk.Combobox(f_con, width=14, state="readonly")
        self.combo_puertos.grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(f_con, text="Actualizar", width=10,
                   command=self._actualizar_lista_puertos).grid(row=0, column=2)

        ttk.Label(f_con, text="Baudrate:").grid(row=1, column=0, sticky="w")
        self.entry_baud = ttk.Entry(f_con, width=10)
        self.entry_baud.insert(0, str(BAUDRATE_DEFAULT))
        self.entry_baud.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        self.btn_conectar = ttk.Button(f_con, text="Conectar",
                                        command=self._alternar_conexion)
        self.btn_conectar.grid(row=2, column=0, columnspan=3, pady=(8, 2), sticky="we")

        self.btn_simular = ttk.Button(f_con, text="Modo simulacion (sin Arduino)",
                                       command=self._alternar_simulacion)
        self.btn_simular.grid(row=3, column=0, columnspan=3, pady=2, sticky="we")

        self.lbl_estado = ttk.Label(f_con, text="Desconectado", foreground="red")
        self.lbl_estado.grid(row=4, column=0, columnspan=3, pady=(6, 0))

        f_pesos = ttk.LabelFrame(panel, text="Pesos de Fusion", padding=10)
        f_pesos.pack(fill=tk.X, pady=5)

        self.vars_peso = {}
        etiquetas = {"us": "Ultrasonido", "ir": "Infrarrojo", "laser": "Laser ToF"}
        for i, clave in enumerate(["us", "ir", "laser"]):
            ttk.Label(f_pesos, text=f"{etiquetas[clave]}:").grid(row=i, column=0, sticky="w")
            var = tk.StringVar(value=str(self.pesos[clave]))
            self.vars_peso[clave] = var
            ttk.Entry(f_pesos, textvariable=var, width=8).grid(row=i, column=1, padx=5, pady=2)

        ttk.Button(f_pesos, text="Aplicar pesos",
                   command=self._aplicar_pesos).grid(row=3, column=0, columnspan=2, pady=(8, 2), sticky="we")
        ttk.Button(f_pesos, text="Restaurar predefinidos",
                   command=self._restaurar_pesos).grid(row=4, column=0, columnspan=2, sticky="we")

        self.lbl_pesos_norm = ttk.Label(f_pesos, text="", font=("TkDefaultFont", 8))
        self.lbl_pesos_norm.grid(row=5, column=0, columnspan=2, pady=(6, 0))
        self._mostrar_pesos_normalizados()

        f_mapa = ttk.LabelFrame(panel, text="Mapa", padding=10)
        f_mapa.pack(fill=tk.X, pady=5)
        ttk.Button(f_mapa, text="Limpiar mapa", command=self._limpiar_mapa).pack(fill=tk.X, pady=2)
        ttk.Button(f_mapa, text="Guardar CSV", command=self._guardar_csv).pack(fill=tk.X, pady=2)

        f_info = ttk.LabelFrame(panel, text="Ultima lectura", padding=10)
        f_info.pack(fill=tk.X, pady=5)
        self.lbl_ultima = ttk.Label(f_info, text="-", justify="left")
        self.lbl_ultima.pack(anchor="w")

        f_cont = ttk.LabelFrame(panel, text="Estadisticas", padding=10)
        f_cont.pack(fill=tk.X, pady=5)
        self.lbl_contadores = ttk.Label(f_cont, text="Puntos: 0   Vueltas: 0", justify="left")
        self.lbl_contadores.pack(anchor="w")

        self.fig = plt.Figure(figsize=(6.5, 6.5))
        self.ax = self.fig.add_subplot(111, projection="polar")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def _configurar_grafico(self):
        self.ax.clear()
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)
        self.ax.set_rmax(RANGO_MAX_CM + 20)
        self.ax.set_rticks([50, 100, 150, 200])
        self.ax.set_title("Nube de puntos - distancia fusionada (cm)", pad=20)
        self.canvas.draw_idle()

    # ---------------- conexion / desconexion ----------------
    def _actualizar_lista_puertos(self):
        puertos = [p.device for p in list_ports.comports()]
        self.combo_puertos["values"] = puertos
        if puertos and not self.combo_puertos.get():
            self.combo_puertos.set(puertos[0])

    def _alternar_conexion(self):
        if self.conectado:
            self._desconectar()
            return

        puerto = self.combo_puertos.get()
        if not puerto:
            messagebox.showwarning("Puerto no seleccionado",
                                    "Selecciona un puerto serial antes de conectar.")
            return
        try:
            baud = int(self.entry_baud.get())
        except ValueError:
            messagebox.showwarning("Baudrate invalido", "Ingresa un baudrate numerico.")
            return

        self.evento_parar.clear()
        self.hilo_lectura = LectorSerial(puerto, baud, self.cola, self.evento_parar)
        self.hilo_lectura.start()
        self.conectado = True
        self.btn_conectar.config(text="Desconectar")
        self.btn_simular.config(state="disabled")
        self.lbl_estado.config(text=f"Conectado a {puerto} @ {baud}", foreground="green")

    def _alternar_simulacion(self):
        if self.conectado:
            self._desconectar()

        self.evento_parar.clear()
        self.hilo_lectura = SimuladorDatos(self.cola, self.evento_parar)
        self.hilo_lectura.start()
        self.conectado = True
        self.btn_conectar.config(state="disabled")
        self.btn_simular.config(text="Detener simulacion", command=self._desconectar)
        self.lbl_estado.config(text="Simulacion activa", foreground="orange")

    def _desconectar(self):
        self.evento_parar.set()
        if self.hilo_lectura:
            self.hilo_lectura.join(timeout=2)
        self.conectado = False
        self.btn_conectar.config(text="Conectar", state="normal")
        self.btn_simular.config(text="Modo simulacion (sin Arduino)",
                                 state="normal", command=self._alternar_simulacion)
        self.lbl_estado.config(text="Desconectado", foreground="red")

    # ---------------- pesos ----------------
    def _aplicar_pesos(self):
        try:
            nuevos = {k: float(v.get()) for k, v in self.vars_peso.items()}
        except ValueError:
            messagebox.showwarning("Peso invalido", "Los pesos deben ser numeros.")
            return
        if any(v < 0 for v in nuevos.values()):
            messagebox.showwarning("Peso invalido", "Los pesos no pueden ser negativos.")
            return
        self.pesos = nuevos
        self._mostrar_pesos_normalizados()

    def _restaurar_pesos(self):
        self.pesos = dict(PESOS_DEFAULT)
        for k, v in self.pesos.items():
            self.vars_peso[k].set(str(v))
        self._mostrar_pesos_normalizados()

    def _mostrar_pesos_normalizados(self):
        norm = normalizar_pesos(self.pesos)
        texto = "Normalizados -> " + "  ".join(f"{k}:{v:.2f}" for k, v in norm.items())
        self.lbl_pesos_norm.config(text=texto)

    # ---------------- procesamiento de datos ----------------
    def _procesar_cola(self):
        hubo_dato_nuevo = False
        try:
            while True:
                tipo, contenido = self.cola.get_nowait()
                if tipo == "error":
                    messagebox.showerror("Error de conexion", contenido)
                    self._desconectar()
                    break
                angulo, d_us, d_ir, d_laser = contenido
                self._registrar_punto(angulo, d_us, d_ir, d_laser)
                hubo_dato_nuevo = True
        except queue.Empty:
            pass

        if hubo_dato_nuevo:
            self._redibujar()
            self._actualizar_labels()

        self.root.after(INTERVALO_REFRESCO_MS, self._procesar_cola)

    def _registrar_punto(self, angulo, d_us, d_ir, d_laser):
        if (self.angulo_anterior is not None and
                (self.angulo_anterior - angulo) > UMBRAL_NUEVA_VUELTA):
            self.thetas.clear()
            self.radios.clear()
            self.colores.clear()
            self.n_vueltas += 1
        self.angulo_anterior = angulo

        pesos_norm = normalizar_pesos(self.pesos)
        fusion, n_validos = fusionar_distancias(d_us, d_ir, d_laser, pesos_norm)

        self.historial_csv.append(
            (datetime.now().isoformat(), angulo, d_us, d_ir, d_laser, fusion)
        )
        self.n_puntos_total += 1
        self.ultima_lectura = (angulo, d_us, d_ir, d_laser, fusion, n_validos)

        if fusion is None:
            return

        self.thetas.append(math.radians(angulo))
        self.radios.append(fusion)
        self.colores.append("tab:blue" if n_validos == 3 else "tab:orange")

    def _redibujar(self):
        self._configurar_grafico()
        if self.thetas:
            self.ax.scatter(self.thetas, self.radios, s=12, c=self.colores, alpha=0.85)
        self.canvas.draw_idle()

    def _actualizar_labels(self):
        if hasattr(self, "ultima_lectura"):
            ang, us, ir, laser, fusion, n = self.ultima_lectura
            txt_fusion = f"{fusion:.1f} cm" if fusion is not None else "sin lectura valida"
            self.lbl_ultima.config(
                text=(f"Angulo: {ang:.0f} grados\n"
                      f"US: {us:.1f}  IR: {ir:.1f}  Laser: {laser:.1f}\n"
                      f"Fusion ({n} sensores): {txt_fusion}")
            )
        self.lbl_contadores.config(
            text=f"Puntos: {self.n_puntos_total}   Vueltas: {self.n_vueltas}"
        )

    # ---------------- mapa ----------------
    def _limpiar_mapa(self):
        self.thetas.clear()
        self.radios.clear()
        self.colores.clear()
        self.angulo_anterior = None
        self._redibujar()

    def _guardar_csv(self):
        if not self.historial_csv:
            messagebox.showinfo("Sin datos", "Todavia no hay datos para guardar.")
            return
        nombre_sugerido = f"mapeo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        ruta = filedialog.asksaveasfilename(defaultextension=".csv",
                                             initialfile=nombre_sugerido,
                                             filetypes=[("CSV", "*.csv")])
        if not ruta:
            return
        with open(ruta, "w", newline="") as f:
            escritor = csv.writer(f)
            escritor.writerow(["timestamp", "angulo_deg", "dist_us_cm",
                                "dist_ir_cm", "dist_laser_cm", "dist_fusionada_cm"])
            escritor.writerows(self.historial_csv)
        messagebox.showinfo("Guardado", f"Datos guardados en:\n{ruta}")

    # ---------------- cierre ----------------
    def al_cerrar(sexlf):
        self.evento_parar.set()
        if self.hilo_lectura:
            self.hilo_lectura.join(timeout=2)
        self.root.destroy()


def main():
    root = tk.Tk()
    AppMapeo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
