"""
GUI para visualizar en tiempo real datos de Arduino por serial
Mapeo Espacial 2D - MT7002 Proyecto Final

Formato esperado:
    paso,d_us,d_ir,d_laser

Ejemplo:
    50,45.30,46.10,44.95

Si Arduino ya manda ángulo en vez de paso, cambiar:
    PRIMER_DATO_ES_PASO = False
"""

import math
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import deque

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import serial
import serial.tools.list_ports as list_ports


# ---------------- Configuracion ----------------
BAUDRATE = 9600

# Escala inicial del mapa
RANGO_MAX_CM_DEFAULT = 300

# Stepper
PASOS_VUELTA = 200

# True si Arduino manda: paso,d_us,d_ir,d_laser
# False si Arduino manda: angulo,d_us,d_ir,d_laser
PRIMER_DATO_ES_PASO = True

# Tamaño de ventana del filtro de media móvil
VENTANA_MEDIA_MOVIL = 4


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Mapeo 2D - Sensores Superpuestos")

        self.ser = None

        # Rango máximo configurable desde GUI
        self.rango_max_cm = RANGO_MAX_CM_DEFAULT

        # Datos de la vuelta actual
        self.angulos_deg = []
        self.thetas = []

        self.us_filtrado = []
        self.ir_filtrado = []
        self.laser_filtrado = []
        self.fusion_filtrada = []

        self.angulo_anterior = None

        # Memoria de vueltas
        self.vueltas = []
        self.mostrando_vuelta_guardada = False

        # Buffers del filtro de media móvil
        self.buffer_us = deque(maxlen=VENTANA_MEDIA_MOVIL)
        self.buffer_ir = deque(maxlen=VENTANA_MEDIA_MOVIL)
        self.buffer_laser = deque(maxlen=VENTANA_MEDIA_MOVIL)

        # ---------------- Panel de control ----------------
        panel = ttk.Frame(root, padding=10)
        panel.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(panel, text="Puerto:").pack(anchor="w")

        self.combo = ttk.Combobox(
            panel,
            width=18,
            state="readonly",
            values=[p.device for p in list_ports.comports()]
        )
        self.combo.pack(pady=5)

        if self.combo["values"]:
            self.combo.current(0)

        self.btn_conectar = ttk.Button(
            panel,
            text="Conectar",
            command=self.conectar
        )
        self.btn_conectar.pack(pady=5, fill=tk.X)

        ttk.Button(
            panel,
            text="Limpiar vuelta actual",
            command=self.limpiar
        ).pack(pady=5, fill=tk.X)

        ttk.Button(
            panel,
            text="Guardar vuelta actual",
            command=self.guardar_vuelta_manual
        ).pack(pady=5, fill=tk.X)

        ttk.Separator(panel, orient="horizontal").pack(fill=tk.X, pady=10)

        # ---------------- Rango configurable ----------------
        ttk.Label(panel, text="Rango máximo cm:").pack(anchor="w")

        self.var_rango_max = tk.StringVar(value=str(self.rango_max_cm))

        self.entry_rango = ttk.Entry(
            panel,
            textvariable=self.var_rango_max,
            width=18
        )
        self.entry_rango.pack(pady=5, fill=tk.X)

        ttk.Button(
            panel,
            text="Aplicar rango",
            command=self.aplicar_rango_max
        ).pack(pady=5, fill=tk.X)

        ttk.Separator(panel, orient="horizontal").pack(fill=tk.X, pady=10)

        # ---------------- Selector de señales ----------------
        ttk.Label(panel, text="Señales a graficar:").pack(anchor="w")

        self.var_us = tk.BooleanVar(value=True)
        self.var_ir = tk.BooleanVar(value=True)
        self.var_laser = tk.BooleanVar(value=True)
        self.var_fusion = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            panel,
            text="Ultrasonido",
            variable=self.var_us,
            command=self.actualizar_grafico
        ).pack(anchor="w")

        ttk.Checkbutton(
            panel,
            text="Infrarrojo",
            variable=self.var_ir,
            command=self.actualizar_grafico
        ).pack(anchor="w")

        ttk.Checkbutton(
            panel,
            text="Láser ToF",
            variable=self.var_laser,
            command=self.actualizar_grafico
        ).pack(anchor="w")

        ttk.Checkbutton(
            panel,
            text="Fusión",
            variable=self.var_fusion,
            command=self.actualizar_grafico
        ).pack(anchor="w")

        self.btn_toggle_senales = ttk.Button(
            panel,
            text="Desactivar señales",
            command=self.toggle_senales
        )
        self.btn_toggle_senales.pack(pady=5, fill=tk.X)

        ttk.Separator(panel, orient="horizontal").pack(fill=tk.X, pady=10)

        ttk.Label(panel, text="Vueltas guardadas:").pack(anchor="w")

        self.combo_vueltas = ttk.Combobox(
            panel,
            width=18,
            state="readonly",
            values=[]
        )
        self.combo_vueltas.pack(pady=5)

        ttk.Button(
            panel,
            text="Ver vuelta guardada",
            command=self.mostrar_vuelta_guardada
        ).pack(pady=5, fill=tk.X)

        ttk.Button(
            panel,
            text="Ver vuelta actual",
            command=self.mostrar_actual
        ).pack(pady=5, fill=tk.X)

        ttk.Button(
            panel,
            text="Exportar vueltas CSV",
            command=self.exportar_csv
        ).pack(pady=5, fill=tk.X)

        self.lbl_estado = ttk.Label(panel, text="Desconectado")
        self.lbl_estado.pack(pady=10)

        self.lbl_info = ttk.Label(
            panel,
            text=f"Media móvil: {VENTANA_MEDIA_MOVIL} muestras\nRango: 0-{self.rango_max_cm} cm"
        )
        self.lbl_info.pack(pady=10)

        self.lbl_fusion = ttk.Label(panel, text="Fusión: -- cm")
        self.lbl_fusion.pack(pady=10)

        # ---------------- Grafico polar ----------------
        self.fig = plt.Figure(figsize=(7, 7))
        self.ax = self.fig.add_subplot(111, projection="polar")

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(
            side=tk.RIGHT,
            fill=tk.BOTH,
            expand=True
        )

        self.dibujar_actual()

    # ---------------- Rango máximo ----------------
    def aplicar_rango_max(self):
        try:
            nuevo_rango = float(self.var_rango_max.get())
        except ValueError:
            messagebox.showwarning(
                "Valor inválido",
                "El rango máximo debe ser un número."
            )
            return

        if nuevo_rango <= 0:
            messagebox.showwarning(
                "Valor inválido",
                "El rango máximo debe ser mayor que 0."
            )
            return

        self.rango_max_cm = nuevo_rango

        self.lbl_info.config(
            text=f"Media móvil: {VENTANA_MEDIA_MOVIL} muestras\nRango: 0-{self.rango_max_cm:.1f} cm"
        )

        self.actualizar_grafico()

    # ---------------- Conexion ----------------
    def conectar(self):
        if self.ser:
            self.ser.close()
            self.ser = None
            self.btn_conectar.config(text="Conectar")
            self.lbl_estado.config(text="Desconectado")
            return

        puerto = self.combo.get()

        if not puerto:
            messagebox.showwarning("Aviso", "Selecciona un puerto.")
            return

        try:
            self.ser = serial.Serial(puerto, BAUDRATE, timeout=1)
        except serial.SerialException as e:
            messagebox.showerror("Error", str(e))
            return

        self.btn_conectar.config(text="Desconectar")
        self.lbl_estado.config(text=f"Conectado a {puerto}")

        self.leer_serial()

    def leer_serial(self):
        if self.ser is None:
            return

        try:
            while self.ser.in_waiting:
                linea = self.ser.readline().decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                self.procesar_linea(linea)

        except serial.SerialException:
            self.lbl_estado.config(text="Error de lectura serial")

        self.root.after(50, self.leer_serial)

    # ---------------- Filtro ----------------
    def media_movil(self, buffer, nuevo_valor):
        buffer.append(nuevo_valor)
        return sum(buffer) / len(buffer)

    # ---------------- Fusion ----------------
    def calcular_fusion(self, d_us, d_ir, d_laser):
        if d_laser <= 30:
            peso_us = 0.0
            peso_ir = 0.3
            peso_laser = 0.7
        else:
            peso_us = 0.0
            peso_ir = 0.0
            peso_laser = 1.0

        fusion = (
            peso_us * d_us +
            peso_ir * d_ir +
            peso_laser * d_laser
        )

        return max(0, fusion)

    # ---------------- Procesamiento de datos ----------------
    def procesar_linea(self, linea):
        partes = linea.split(",")

        if len(partes) != 4:
            return

        try:
            dato_angulo, d_us, d_ir, d_laser = (float(p) for p in partes)
        except ValueError:
            return

        # Convertir paso a ángulo si es necesario
        if PRIMER_DATO_ES_PASO:
            angulo = dato_angulo * 360.0 / PASOS_VUELTA
        else:
            angulo = dato_angulo

        angulo = angulo % 360.0

        # Detecta nueva vuelta
        if self.angulo_anterior is not None:
            if angulo < self.angulo_anterior - 180:
                self.guardar_vuelta_actual(automatica=True)
                self.limpiar_actual(redibujar=False)

        self.angulo_anterior = angulo

        # Media móvil para cada sensor
        d_us_f = self.media_movil(self.buffer_us, d_us)
        d_ir_f = self.media_movil(self.buffer_ir, d_ir)
        d_laser_f = self.media_movil(self.buffer_laser, d_laser)

        # Evitar valores negativos
        d_us_f = max(0, d_us_f)
        d_ir_f = max(0, d_ir_f)
        d_laser_f = max(0, d_laser_f)

        # Fusión usando señales filtradas
        fusion = self.calcular_fusion(d_us_f, d_ir_f, d_laser_f)

        # Imprimir fusión en consola
        print(
            f"Ángulo: {angulo:.2f}°, "
            f"US: {d_us_f:.2f} cm, "
            f"IR: {d_ir_f:.2f} cm, "
            f"Láser: {d_laser_f:.2f} cm, "
            f"Fusión: {fusion:.2f} cm"
        )

        # Mostrar fusión en la interfaz
        self.lbl_fusion.config(text=f"Fusión: {fusion:.2f} cm")

        # Guardar datos de vuelta actual
        self.angulos_deg.append(angulo)
        self.thetas.append(math.radians(angulo))

        self.us_filtrado.append(d_us_f)
        self.ir_filtrado.append(d_ir_f)
        self.laser_filtrado.append(d_laser_f)
        self.fusion_filtrada.append(fusion)

        # Solo redibuja en vivo si no estás revisando una vuelta guardada
        if not self.mostrando_vuelta_guardada:
            self.dibujar_actual()

    # ---------------- Memoria de vueltas ----------------
    def guardar_vuelta_manual(self):
        guardada = self.guardar_vuelta_actual(automatica=False)

        if guardada:
            self.limpiar_actual(redibujar=True)
            messagebox.showinfo(
                "Vuelta guardada",
                "La vuelta actual fue guardada en memoria."
            )
        else:
            messagebox.showwarning(
                "Aviso",
                "No hay suficientes puntos para guardar la vuelta."
            )

    def guardar_vuelta_actual(self, automatica=False):
        if len(self.thetas) < 2:
            return False

        numero = len(self.vueltas) + 1

        vuelta = {
            "nombre": f"Vuelta {numero} - {len(self.thetas)} puntos",
            "angulos_deg": list(self.angulos_deg),
            "thetas": list(self.thetas),
            "us": list(self.us_filtrado),
            "ir": list(self.ir_filtrado),
            "laser": list(self.laser_filtrado),
            "fusion": list(self.fusion_filtrada)
        }

        self.vueltas.append(vuelta)
        self.actualizar_combo_vueltas()

        if automatica:
            self.lbl_estado.config(
                text=f"Vuelta {numero} guardada automáticamente"
            )

        return True

    def actualizar_combo_vueltas(self):
        nombres = [v["nombre"] for v in self.vueltas]
        self.combo_vueltas["values"] = nombres

        if nombres:
            self.combo_vueltas.current(len(nombres) - 1)

    def mostrar_vuelta_guardada(self):
        idx = self.combo_vueltas.current()

        if idx < 0 or idx >= len(self.vueltas):
            messagebox.showwarning(
                "Aviso",
                "Selecciona una vuelta guardada."
            )
            return

        self.mostrando_vuelta_guardada = True
        self.dibujar_vuelta(self.vueltas[idx])

    def mostrar_actual(self):
        self.mostrando_vuelta_guardada = False
        self.dibujar_actual()

    # ---------------- Exportar CSV ----------------
    def exportar_csv(self):
        if not self.vueltas:
            messagebox.showwarning(
                "Aviso",
                "No hay vueltas guardadas para exportar."
            )
            return

        ruta = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")],
            title="Guardar vueltas como CSV"
        )

        if not ruta:
            return

        try:
            with open(ruta, mode="w", newline="", encoding="utf-8") as archivo:
                writer = csv.writer(archivo)

                writer.writerow([
                    "vuelta",
                    "punto",
                    "angulo_deg",
                    "ultrasonido_cm",
                    "infrarrojo_cm",
                    "laser_cm",
                    "fusion_cm"
                ])

                for i, vuelta in enumerate(self.vueltas, start=1):
                    for j in range(len(vuelta["angulos_deg"])):
                        writer.writerow([
                            i,
                            j,
                            vuelta["angulos_deg"][j],
                            vuelta["us"][j],
                            vuelta["ir"][j],
                            vuelta["laser"][j],
                            vuelta["fusion"][j]
                        ])

            messagebox.showinfo(
                "Exportado",
                f"Vueltas exportadas correctamente:\n{ruta}"
            )

        except OSError as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Grafico ----------------
    def actualizar_grafico(self):
        if self.mostrando_vuelta_guardada:
            idx = self.combo_vueltas.current()

            if idx >= 0 and idx < len(self.vueltas):
                self.dibujar_vuelta(self.vueltas[idx])
            else:
                self.dibujar_actual()
        else:
            self.dibujar_actual()

    def toggle_senales(self):
        alguna_activa = (
            self.var_us.get() or
            self.var_ir.get() or
            self.var_laser.get() or
            self.var_fusion.get()
        )

        nuevo_estado = not alguna_activa

        self.var_us.set(nuevo_estado)
        self.var_ir.set(nuevo_estado)
        self.var_laser.set(nuevo_estado)
        self.var_fusion.set(nuevo_estado)

        if nuevo_estado:
            self.btn_toggle_senales.config(text="Desactivar señales")
        else:
            self.btn_toggle_senales.config(text="Activar señales")

        self.actualizar_grafico()

    def configurar_grafico(self, titulo):
        self.ax.clear()

        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)

        # Escala fija configurable desde GUI
        self.ax.set_ylim(0, self.rango_max_cm)
        self.ax.set_rmax(self.rango_max_cm)

        self.ax.set_title(titulo)

    def dibujar_actual(self):
        self.configurar_grafico("Mapa polar - Vuelta actual")

        self.dibujar_senales(
            self.thetas,
            self.us_filtrado,
            self.ir_filtrado,
            self.laser_filtrado,
            self.fusion_filtrada
        )

    def dibujar_vuelta(self, vuelta):
        self.configurar_grafico(vuelta["nombre"])

        self.dibujar_senales(
            vuelta["thetas"],
            vuelta["us"],
            vuelta["ir"],
            vuelta["laser"],
            vuelta["fusion"]
        )

    def dibujar_senales(self, thetas, us, ir, laser, fusion):
        hay_senales = False

        if thetas:
            if self.var_us.get():
                self.ax.plot(
                    thetas,
                    us,
                    linewidth=1.2,
                    color="tab:blue",
                    label="Ultrasonido"
                )
                hay_senales = True

            if self.var_ir.get():
                self.ax.plot(
                    thetas,
                    ir,
                    linewidth=1.2,
                    color="tab:orange",
                    label="Infrarrojo"
                )
                hay_senales = True

            if self.var_laser.get():
                self.ax.plot(
                    thetas,
                    laser,
                    linewidth=1.2,
                    color="tab:green",
                    label="Láser ToF"
                )
                hay_senales = True

            if self.var_fusion.get():
                self.ax.plot(
                    thetas,
                    fusion,
                    linewidth=2.0,
                    color="tab:red",
                    label="Fusión"
                )
                hay_senales = True

            if hay_senales:
                self.ax.legend(
                    loc="upper right",
                    bbox_to_anchor=(1.30, 1.10)
                )

        self.canvas.draw_idle()

    # ---------------- Limpiar ----------------
    def limpiar(self):
        self.limpiar_actual(redibujar=True)

    def limpiar_actual(self, redibujar=True):
        self.angulos_deg.clear()
        self.thetas.clear()

        self.us_filtrado.clear()
        self.ir_filtrado.clear()
        self.laser_filtrado.clear()
        self.fusion_filtrada.clear()

        self.buffer_us.clear()
        self.buffer_ir.clear()
        self.buffer_laser.clear()

        self.angulo_anterior = None

        self.lbl_fusion.config(text="Fusión: -- cm")

        if redibujar and not self.mostrando_vuelta_guardada:
            self.dibujar_actual()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()