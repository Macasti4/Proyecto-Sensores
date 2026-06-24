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

try:
    from ctypes import windll
except ImportError:
    windll = None

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import serial
import serial.tools.list_ports as list_ports


# ---------------- Configuracion ----------------
BAUDRATE = 9600

# Escala inicial del mapa
RANGO_MAX_CM_DEFAULT = 175

# Stepper
PASOS_VUELTA = 200

# True si Arduino manda: paso,d_us,d_ir,d_laser
# False si Arduino manda: angulo,d_us,d_ir,d_laser
PRIMER_DATO_ES_PASO = True

# Tamaño de ventana del filtro de media móvil
VENTANA_MEDIA_MOVIL = 1


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Mapeo 2D - Fusión Multisensorial")
        self.root.geometry("1180x760")
        self.root.minsize(1050, 680)

        self.configurar_estilos()

        self.ser = None

        # Rango máximo configurable desde GUI
        self.rango_max_cm = RANGO_MAX_CM_DEFAULT

        # Datos de adquisición de la vuelta actual
        self.angulos_deg = []
        self.thetas = []

        self.us_filtrado = []
        self.ir_filtrado = []
        self.laser_filtrado = []
        self.fusion_filtrada = []

        self.angulo_anterior = None

        # Último punto actual para dibujar el rayo
        self.ultimo_theta = None
        self.ultimo_us = None
        self.ultimo_ir = None
        self.ultimo_laser = None
        self.ultimo_fusion = None

        # Mapa visual persistente
        # Este NO se borra al cambiar de vuelta.
        # Se va sobreescribiendo punto por punto.
        self.mapa_angulos_deg = [
            i * 360.0 / PASOS_VUELTA for i in range(PASOS_VUELTA)
        ]

        self.mapa_thetas = [
            math.radians(a) for a in self.mapa_angulos_deg
        ]

        self.mapa_us = [None] * PASOS_VUELTA
        self.mapa_ir = [None] * PASOS_VUELTA
        self.mapa_laser = [None] * PASOS_VUELTA
        self.mapa_fusion = [None] * PASOS_VUELTA

        # Memoria de vueltas
        self.vueltas = []
        self.mostrando_vuelta_guardada = False

        # Buffers del filtro de media móvil
        self.buffer_us = deque(maxlen=VENTANA_MEDIA_MOVIL)
        self.buffer_ir = deque(maxlen=VENTANA_MEDIA_MOVIL)
        self.buffer_laser = deque(maxlen=VENTANA_MEDIA_MOVIL)

        # ---------------- Layout principal ----------------
        self.root.configure(bg="#E5E7EB")

        contenedor = ttk.Frame(root, style="Main.TFrame", padding=12)
        contenedor.pack(fill=tk.BOTH, expand=True)

        panel = ttk.Frame(contenedor, style="Sidebar.TFrame", padding=14)
        panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        panel_grafico = ttk.Frame(contenedor, style="Chart.TFrame", padding=10)
        panel_grafico.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # ---------------- Título ----------------
        ttk.Label(
            panel,
            text="Mapeo 2D",
            style="Title.TLabel"
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            panel,
            text="Fusión multisensorial en tiempo real",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(0, 14))

        # ---------------- Conexión ----------------
        frame_conexion = ttk.LabelFrame(
            panel,
            text="Conexión",
            style="Card.TLabelframe",
            padding=10
        )
        frame_conexion.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            frame_conexion,
            text="Puerto serial",
            style="Body.TLabel"
        ).pack(anchor="w")

        fila_puerto = ttk.Frame(frame_conexion, style="CardInner.TFrame")
        fila_puerto.pack(fill=tk.X, pady=(5, 8))

        self.combo = ttk.Combobox(
            fila_puerto,
            width=16,
            state="readonly",
            values=self.obtener_puertos()
        )
        self.combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_refrescar = ttk.Button(
            fila_puerto,
            text="Refrescar",
            command=self.refrescar_puertos,
            style="Secondary.TButton"
        )
        self.btn_refrescar.pack(side=tk.LEFT, padx=(6, 0))

        if self.combo["values"]:
            self.combo.current(0)

        self.btn_conectar = ttk.Button(
            frame_conexion,
            text="Conectar",
            command=self.conectar,
            style="Accent.TButton"
        )
        self.btn_conectar.pack(fill=tk.X, pady=(0, 4))

        # ---------------- Mapa ----------------
        frame_mapa = ttk.LabelFrame(
            panel,
            text="Mapa",
            style="Card.TLabelframe",
            padding=10
        )
        frame_mapa.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            frame_mapa,
            text="Limpiar mapa",
            command=self.limpiar,
            style="Secondary.TButton"
        ).pack(fill=tk.X, pady=3)

        ttk.Button(
            frame_mapa,
            text="Guardar vuelta actual",
            command=self.guardar_vuelta_manual,
            style="Secondary.TButton"
        ).pack(fill=tk.X, pady=3)

        # ---------------- Rango configurable ----------------
        frame_rango = ttk.LabelFrame(
            panel,
            text="Escala del mapa",
            style="Card.TLabelframe",
            padding=10
        )
        frame_rango.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            frame_rango,
            text="Rango máximo [cm]",
            style="Body.TLabel"
        ).pack(anchor="w")

        self.var_rango_max = tk.StringVar(value=str(self.rango_max_cm))

        self.entry_rango = ttk.Entry(
            frame_rango,
            textvariable=self.var_rango_max
        )
        self.entry_rango.pack(fill=tk.X, pady=(5, 6))

        ttk.Button(
            frame_rango,
            text="Aplicar rango",
            command=self.aplicar_rango_max,
            style="Secondary.TButton"
        ).pack(fill=tk.X)

        # ---------------- Selector de señales ----------------
        frame_senales = ttk.LabelFrame(
            panel,
            text="Señales visibles",
            style="Card.TLabelframe",
            padding=10
        )
        frame_senales.pack(fill=tk.X, pady=(0, 10))

        self.var_us = tk.BooleanVar(value=True)
        self.var_ir = tk.BooleanVar(value=True)
        self.var_laser = tk.BooleanVar(value=True)
        self.var_fusion = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            frame_senales,
            text="Ultrasonido",
            variable=self.var_us,
            command=self.actualizar_grafico,
            style="Modern.TCheckbutton"
        ).pack(anchor="w", pady=1)

        ttk.Checkbutton(
            frame_senales,
            text="Infrarrojo",
            variable=self.var_ir,
            command=self.actualizar_grafico,
            style="Modern.TCheckbutton"
        ).pack(anchor="w", pady=1)

        ttk.Checkbutton(
            frame_senales,
            text="Láser ToF",
            variable=self.var_laser,
            command=self.actualizar_grafico,
            style="Modern.TCheckbutton"
        ).pack(anchor="w", pady=1)

        ttk.Checkbutton(
            frame_senales,
            text="Fusión",
            variable=self.var_fusion,
            command=self.actualizar_grafico,
            style="Modern.TCheckbutton"
        ).pack(anchor="w", pady=1)

        self.btn_toggle_senales = ttk.Button(
            frame_senales,
            text="Desactivar señales",
            command=self.toggle_senales,
            style="Secondary.TButton"
        )
        self.btn_toggle_senales.pack(fill=tk.X, pady=(8, 0))

        # ---------------- Vueltas guardadas ----------------
        frame_vueltas = ttk.LabelFrame(
            panel,
            text="Vueltas guardadas",
            style="Card.TLabelframe",
            padding=10
        )
        frame_vueltas.pack(fill=tk.X, pady=(0, 10))

        self.combo_vueltas = ttk.Combobox(
            frame_vueltas,
            width=18,
            state="readonly",
            values=[]
        )
        self.combo_vueltas.pack(fill=tk.X, pady=(0, 6))

        self.combo_vueltas.bind(
            "<<ComboboxSelected>>",
            self.seleccionar_vuelta_automaticamente
        )

        ttk.Button(
            frame_vueltas,
            text="Ver vuelta actual",
            command=self.mostrar_actual,
            style="Secondary.TButton"
        ).pack(fill=tk.X, pady=3)

        ttk.Button(
            frame_vueltas,
            text="Exportar vueltas CSV",
            command=self.exportar_csv,
            style="Secondary.TButton"
        ).pack(fill=tk.X, pady=3)

        # ---------------- Estado ----------------
        frame_estado = ttk.LabelFrame(
            panel,
            text="Estado",
            style="Card.TLabelframe",
            padding=10
        )
        frame_estado.pack(fill=tk.X, pady=(0, 10))

        self.lbl_estado = ttk.Label(
            frame_estado,
            text="Desconectado",
            style="Status.TLabel"
        )
        self.lbl_estado.pack(anchor="w", pady=2)

        self.lbl_info = ttk.Label(
            frame_estado,
            text=f"Media móvil: {VENTANA_MEDIA_MOVIL} muestras\nRango: 0-{self.rango_max_cm} cm",
            style="Body.TLabel"
        )
        self.lbl_info.pack(anchor="w", pady=6)

        self.lbl_fusion = ttk.Label(
            frame_estado,
            text="Fusión: -- cm",
            style="Fusion.TLabel"
        )
        self.lbl_fusion.pack(anchor="w", pady=2)

        # ---------------- Grafico polar ----------------
        self.fig = plt.Figure(figsize=(7, 7), facecolor="#F8FAFC")
        self.ax = self.fig.add_subplot(111, projection="polar")

        self.canvas = FigureCanvasTkAgg(self.fig, master=panel_grafico)
        self.canvas.get_tk_widget().pack(
            fill=tk.BOTH,
            expand=True
        )

        self.dibujar_actual()

    # ---------------- Estilos ----------------
    def configurar_estilos(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        color_bg = "#E5E7EB"
        color_card = "#F8FAFC"
        color_sidebar = "#F9FAFB"
        color_text = "#111827"
        color_muted = "#6B7280"
        color_accent = "#2563EB"
        color_accent_hover = "#1D4ED8"

        style.configure("Main.TFrame", background=color_bg)
        style.configure("Sidebar.TFrame", background=color_sidebar)
        style.configure("Chart.TFrame", background=color_card)
        style.configure("CardInner.TFrame", background=color_card)

        style.configure(
            "Title.TLabel",
            background=color_sidebar,
            foreground=color_text,
            font=("Segoe UI", 20, "bold")
        )

        style.configure(
            "Subtitle.TLabel",
            background=color_sidebar,
            foreground=color_muted,
            font=("Segoe UI", 9)
        )

        style.configure(
            "Body.TLabel",
            background=color_card,
            foreground=color_text,
            font=("Segoe UI", 9)
        )

        style.configure(
            "Status.TLabel",
            background=color_card,
            foreground=color_muted,
            font=("Segoe UI", 9, "bold")
        )

        style.configure(
            "Fusion.TLabel",
            background=color_card,
            foreground="#DC2626",
            font=("Segoe UI", 10, "bold")
        )

        style.configure(
            "Card.TLabelframe",
            background=color_card,
            foreground=color_text,
            borderwidth=1,
            relief="solid"
        )

        style.configure(
            "Card.TLabelframe.Label",
            background=color_sidebar,
            foreground=color_text,
            font=("Segoe UI", 10, "bold")
        )

        style.configure("TCombobox", padding=4, font=("Segoe UI", 9))
        style.configure("TEntry", padding=5, font=("Segoe UI", 9))

        style.configure(
            "Accent.TButton",
            background=color_accent,
            foreground="white",
            padding=7,
            font=("Segoe UI", 9, "bold"),
            borderwidth=0
        )

        style.map(
            "Accent.TButton",
            background=[
                ("active", color_accent_hover),
                ("pressed", "#1E40AF")
            ],
            foreground=[
                ("active", "white"),
                ("pressed", "white")
            ]
        )

        style.configure(
            "Secondary.TButton",
            background="#E5E7EB",
            foreground=color_text,
            padding=6,
            font=("Segoe UI", 9),
            borderwidth=0
        )

        style.map(
            "Secondary.TButton",
            background=[
                ("active", "#D1D5DB"),
                ("pressed", "#9CA3AF")
            ]
        )

        style.configure(
            "Modern.TCheckbutton",
            background=color_card,
            foreground=color_text,
            font=("Segoe UI", 9)
        )

        style.map(
            "Modern.TCheckbutton",
            background=[
                ("active", color_card)
            ]
        )

    # ---------------- Puertos ----------------
    def obtener_puertos(self):
        return [p.device for p in list_ports.comports()]

    def refrescar_puertos(self):
        puerto_actual = self.combo.get()
        puertos = self.obtener_puertos()

        self.combo["values"] = puertos

        if puerto_actual in puertos:
            self.combo.set(puerto_actual)
        elif puertos:
            self.combo.current(0)
        else:
            self.combo.set("")

        if self.ser is None:
            self.lbl_estado.config(
                text=f"{len(puertos)} puerto(s) detectado(s)"
            )

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

        if PRIMER_DATO_ES_PASO:
            angulo = dato_angulo * 360.0 / PASOS_VUELTA
        else:
            angulo = dato_angulo

        angulo = angulo % 360.0

        indice_mapa = int(round(angulo * PASOS_VUELTA / 360.0)) % PASOS_VUELTA

        if self.angulo_anterior is not None:
            if angulo < self.angulo_anterior - 180:
                self.guardar_vuelta_actual(automatica=True)

                self.limpiar_actual(
                    redibujar=False,
                    limpiar_mapa_visual=False
                )

        self.angulo_anterior = angulo

        d_us_f = self.media_movil(self.buffer_us, d_us)
        d_ir_f = self.media_movil(self.buffer_ir, d_ir)
        d_laser_f = self.media_movil(self.buffer_laser, d_laser)

        d_us_f = max(0, d_us_f)
        d_ir_f = max(0, d_ir_f)
        d_laser_f = max(0, d_laser_f)

        fusion = self.calcular_fusion(d_us_f, d_ir_f, d_laser_f)

        print(
            f"Ángulo: {angulo:.2f}°, "
            f"US: {d_us_f:.2f} cm, "
            f"IR: {d_ir_f:.2f} cm, "
            f"Láser: {d_laser_f:.2f} cm, "
            f"Fusión: {fusion:.2f} cm"
        )

        self.lbl_fusion.config(text=f"Fusión: {fusion:.2f} cm")

        self.angulos_deg.append(angulo)
        self.thetas.append(math.radians(angulo))

        self.us_filtrado.append(d_us_f)
        self.ir_filtrado.append(d_ir_f)
        self.laser_filtrado.append(d_laser_f)
        self.fusion_filtrada.append(fusion)

        # Último punto actual para el rayo
        self.ultimo_theta = math.radians(angulo)
        self.ultimo_us = d_us_f
        self.ultimo_ir = d_ir_f
        self.ultimo_laser = d_laser_f
        self.ultimo_fusion = fusion

        self.mapa_angulos_deg[indice_mapa] = angulo
        self.mapa_thetas[indice_mapa] = math.radians(angulo)

        self.mapa_us[indice_mapa] = d_us_f
        self.mapa_ir[indice_mapa] = d_ir_f
        self.mapa_laser[indice_mapa] = d_laser_f
        self.mapa_fusion[indice_mapa] = fusion

        if not self.mostrando_vuelta_guardada:
            self.dibujar_actual()

    # ---------------- Memoria de vueltas ----------------
    def guardar_vuelta_manual(self):
        guardada = self.guardar_vuelta_actual(automatica=False)

        if guardada:
            self.limpiar_actual(
                redibujar=True,
                limpiar_mapa_visual=False
            )

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

    def seleccionar_vuelta_automaticamente(self, event=None):
        idx = self.combo_vueltas.current()

        if idx < 0 or idx >= len(self.vueltas):
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

    # ---------------- Grafico polar ----------------
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

        self.ax.set_facecolor("#F8FAFC")

        # 0° hacia arriba y giro horario
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)

        self.ax.set_ylim(0, self.rango_max_cm)
        self.ax.set_rmax(self.rango_max_cm)

        self.ax.grid(color="#CBD5E1", linewidth=0.8, alpha=0.8)
        self.ax.tick_params(colors="#334155")

        self.ax.set_title(
            titulo,
            fontsize=13,
            fontweight="bold",
            color="#111827",
            pad=18
        )

    def dibujar_actual(self):
        self.configurar_grafico("Mapa polar - Vuelta actual")

        self.dibujar_senales(
            self.mapa_thetas,
            self.mapa_us,
            self.mapa_ir,
            self.mapa_laser,
            self.mapa_fusion
        )

        self.dibujar_rayo_actual()

    def dibujar_vuelta(self, vuelta):
        self.configurar_grafico(vuelta["nombre"])

        self.dibujar_senales(
            vuelta["thetas"],
            vuelta["us"],
            vuelta["ir"],
            vuelta["laser"],
            vuelta["fusion"]
        )

    def filtrar_puntos_validos(self, thetas, valores):
        thetas_validos = []
        valores_validos = []

        for theta, valor in zip(thetas, valores):
            if valor is not None:
                thetas_validos.append(theta)
                valores_validos.append(valor)

        return thetas_validos, valores_validos

    def dibujar_senales(self, thetas, us, ir, laser, fusion):
        hay_senales = False

        if thetas:
            if self.var_us.get():
                theta_us, datos_us = self.filtrar_puntos_validos(thetas, us)

                if datos_us:
                    self.ax.scatter(
                        theta_us,
                        datos_us,
                        s=14,
                        color="#2563EB",
                        label="Ultrasonido",
                        alpha=0.85
                    )
                    hay_senales = True

            if self.var_ir.get():
                theta_ir, datos_ir = self.filtrar_puntos_validos(thetas, ir)

                if datos_ir:
                    self.ax.scatter(
                        theta_ir,
                        datos_ir,
                        s=14,
                        color="#F97316",
                        label="Infrarrojo",
                        alpha=0.85
                    )
                    hay_senales = True

            if self.var_laser.get():
                theta_laser, datos_laser = self.filtrar_puntos_validos(thetas, laser)

                if datos_laser:
                    self.ax.scatter(
                        theta_laser,
                        datos_laser,
                        s=14,
                        color="#16A34A",
                        label="Láser ToF",
                        alpha=0.85
                    )
                    hay_senales = True

            if self.var_fusion.get():
                theta_fusion, datos_fusion = self.filtrar_puntos_validos(thetas, fusion)

                if datos_fusion:
                    self.ax.scatter(
                        theta_fusion,
                        datos_fusion,
                        s=20,
                        color="#DC2626",
                        label="Fusión",
                        alpha=0.95
                    )
                    hay_senales = True

            if hay_senales:
                self.ax.legend(
                    loc="upper right",
                    bbox_to_anchor=(1.30, 1.10),
                    frameon=True,
                    facecolor="#FFFFFF",
                    edgecolor="#CBD5E1"
                )

        self.canvas.draw_idle()

    def obtener_radio_para_rayo(self):
        if self.var_fusion.get() and self.ultimo_fusion is not None:
            return self.ultimo_fusion

        if self.var_laser.get() and self.ultimo_laser is not None:
            return self.ultimo_laser

        if self.var_ir.get() and self.ultimo_ir is not None:
            return self.ultimo_ir

        if self.var_us.get() and self.ultimo_us is not None:
            return self.ultimo_us

        if self.ultimo_fusion is not None:
            return self.ultimo_fusion

        return None

    def dibujar_rayo_actual(self):
        if self.ultimo_theta is None:
            return

        radio = self.obtener_radio_para_rayo()

        if radio is None:
            return

        self.ax.plot(
            [self.ultimo_theta, self.ultimo_theta],
            [0, radio],
            color="#111827",
            linewidth=2.0,
            linestyle="--",
            alpha=0.9,
            zorder=5
        )

        self.ax.scatter(
            [self.ultimo_theta],
            [radio],
            s=65,
            color="#111827",
            edgecolors="white",
            linewidths=1.0,
            zorder=6
        )

        self.canvas.draw_idle()

    # ---------------- Limpiar ----------------
    def limpiar(self):
        self.limpiar_actual(
            redibujar=True,
            limpiar_mapa_visual=True
        )

    def limpiar_actual(self, redibujar=True, limpiar_mapa_visual=True):
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

        self.ultimo_theta = None
        self.ultimo_us = None
        self.ultimo_ir = None
        self.ultimo_laser = None
        self.ultimo_fusion = None

        self.lbl_fusion.config(text="Fusión: -- cm")

        if limpiar_mapa_visual:
            self.mapa_us = [None] * PASOS_VUELTA
            self.mapa_ir = [None] * PASOS_VUELTA
            self.mapa_laser = [None] * PASOS_VUELTA
            self.mapa_fusion = [None] * PASOS_VUELTA

        if redibujar and not self.mostrando_vuelta_guardada:
            self.dibujar_actual()


if __name__ == "__main__":
    if windll is not None:
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    App(root)
    root.mainloop()