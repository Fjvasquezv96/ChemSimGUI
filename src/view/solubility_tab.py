import os
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, 
    QMessageBox, QSplitter, QComboBox, QSpinBox, QDoubleSpinBox,
    QProgressBar, QFrame, QRadioButton, QButtonGroup, QTabWidget,
    QFormLayout, QAbstractItemView, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Controlador y Modelo
from src.controller.solubility_manager import SolubilityManager

# Matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

# ==========================================================
# WORKER: EJECUCIÓN BATCH (GENERADOR)
# ==========================================================
class BatchWorker(QThread):
    """
    Hilo para ejecutar procesos largos que reportan progreso paso a paso.
    Usa generadores (yield) del manager.
    """
    progress_signal = pyqtSignal(str) # Mensajes de log
    finished_signal = pyqtSignal(bool, str) # Resultado final

    def __init__(self, generator_func, *args, **kwargs):
        super().__init__()
        self.gen_func = generator_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # Iterar sobre el generador del manager
            for msg, status in self.gen_func(*self.args, **self.kwargs):
                self.progress_signal.emit(msg)
                if not status:
                    # Si un paso falla, no abortamos todo, pero avisamos
                    pass 
            
            self.finished_signal.emit(True, "Proceso completado.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

# ==========================================================
# CLASE PRINCIPAL: PESTAÑA SOLUBILIDAD
# ==========================================================
class SolubilityTab(QWidget):
    def __init__(self):
        super().__init__()
        
        self.project_mgr = None
        self.manager = None # Se instancia al recibir el project_mgr
        self.worker = None
        
        # Datos calculados (Cache)
        self.calculated_results = {} 
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # TABS PRINCIPALES DEL FLUJO DE TRABAJO
        self.main_tabs = QTabWidget()
        
        # 1. Configuración del Estudio
        self.tab_config = QWidget()
        self.init_ui_config()
        self.main_tabs.addTab(self.tab_config, "1. Configuración del Estudio")
        
        # 2. Análisis de Parámetros (Radio de Corte)
        self.tab_params = QWidget()
        self.init_ui_params()
        self.main_tabs.addTab(self.tab_params, "2. Análisis de Parámetros")
        
        # 3. Predicción Final
        self.tab_predict = QWidget()
        self.init_ui_predict()
        self.main_tabs.addTab(self.tab_predict, "3. Predicción de Solubilidad")
        
        layout.addWidget(self.main_tabs)
        self.setLayout(layout)

    # ------------------------------------------------------
    # UI: 1. CONFIGURACIÓN
    # ------------------------------------------------------
    def init_ui_config(self):
        layout = QHBoxLayout()
        
        # --- COLUMNA IZQ: DEFINICIÓN DE SISTEMAS ---
        left = QGroupBox("Definición de Puntos Experimentales (Composición)")
        l_left = QVBoxLayout()
        
        self.table_systems = QTableWidget()
        self.table_systems.setColumnCount(4)
        self.table_systems.setHorizontalHeaderLabels(["Sistema (Carpeta)", "Fracción Molar (x1)", "N Soluto", "N Solvente"])
        self.table_systems.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        l_left.addWidget(self.table_systems)
        
        h_btns = QHBoxLayout()
        btn_add = QPushButton("➕ Agregar Punto"); btn_add.clicked.connect(self.add_system_row)
        btn_del = QPushButton("➖ Quitar Punto"); btn_del.clicked.connect(self.remove_system_row)
        btn_auto = QPushButton("🪄 Auto-Detectar (Nombres)"); btn_auto.clicked.connect(self.auto_detect_systems)
        h_btns.addWidget(btn_add); h_btns.addWidget(btn_del); h_btns.addWidget(btn_auto)
        l_left.addLayout(h_btns)
        
        left.setLayout(l_left)
        layout.addWidget(left, stretch=60)
        
        # --- COLUMNA DER: CONSTANTES FÍSICAS ---
        right = QGroupBox("Parámetros Físicos y Modelo")
        l_right = QFormLayout()
        
        # Soluto
        l_right.addRow(QLabel("<b>Propiedades del Soluto (Sólido):</b>"))
        self.sb_tm = QDoubleSpinBox(); self.sb_tm.setRange(0, 5000); self.sb_tm.setValue(340.0); self.sb_tm.setSuffix(" K")
        self.sb_hfus = QDoubleSpinBox(); self.sb_hfus.setRange(0, 100000); self.sb_hfus.setValue(25000); self.sb_hfus.setSuffix(" J/mol")
        self.sb_mw1 = QDoubleSpinBox(); self.sb_mw1.setRange(0, 10000); self.sb_mw1.setValue(314.46); self.sb_mw1.setSuffix(" g/mol")
        self.sb_v1 = QDoubleSpinBox(); self.sb_v1.setRange(0, 10000); self.sb_v1.setValue(300.0); self.sb_v1.setSuffix(" cm3/mol")
        
        l_right.addRow("Temp. Fusión (Tm):", self.sb_tm)
        l_right.addRow("Entalpía Fusión:", self.sb_hfus)
        l_right.addRow("Peso Molecular:", self.sb_mw1)
        l_right.addRow("Volumen Molar (V1):", self.sb_v1)
        
        # Solvente
        l_right.addRow(QLabel("<b>Propiedades del Solvente:</b>"))
        self.sb_mw2 = QDoubleSpinBox(); self.sb_mw2.setRange(0, 10000); self.sb_mw2.setValue(72.15); self.sb_mw2.setSuffix(" g/mol")
        self.sb_v2 = QDoubleSpinBox(); self.sb_v2.setRange(0, 10000); self.sb_v2.setValue(115.0); self.sb_v2.setSuffix(" cm3/mol")
        l_right.addRow("Peso Molecular:", self.sb_mw2)
        l_right.addRow("Volumen Molar (V2):", self.sb_v2)
        
        # Modelo Termodinámico
        l_right.addRow(QLabel("<b>Modelo de Actividad:</b>"))
        self.combo_model = QComboBox(); self.combo_model.addItems(["Wilson", "NRTL"]) # UNIQUAC requiere mas params
        l_right.addRow("Modelo:", self.combo_model)
        
        # Config GROMACS
        l_right.addRow(QLabel("<b>Configuración GROMACS:</b>"))
        self.txt_step = QLineEdit("prod"); self.txt_step.setPlaceholderText("Nombre paso producción")
        self.txt_grp1 = QLineEdit("CBD"); self.txt_grp1.setPlaceholderText("Nombre Grupo Soluto")
        self.txt_grp2 = QLineEdit("Pentane"); self.txt_grp2.setPlaceholderText("Nombre Grupo Solvente")
        
        l_right.addRow("Nombre Etapa Prod:", self.txt_step)
        l_right.addRow("Grupo Soluto (ndx):", self.txt_grp1)
        l_right.addRow("Grupo Solvente (ndx):", self.txt_grp2)
        
        # Botón Ejecutar Batch
        self.btn_calc_batch = QPushButton("▶ Calcular RDFs y Parámetros")
        self.btn_calc_batch.setStyleSheet("background-color: #d4edda; font-weight: bold; padding: 10px; color: green;")
        self.btn_calc_batch.clicked.connect(self.run_batch_calculation)
        l_right.addRow(self.btn_calc_batch)
        
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(True)
        l_right.addRow(self.progress_bar)
        
        self.lbl_status = QLabel("Listo.")
        l_right.addRow(self.lbl_status)
        
        right.setLayout(l_right)
        layout.addWidget(right, stretch=40)
        self.tab_config.setLayout(layout)

    # ------------------------------------------------------
    # UI: 2. PARÁMETROS (RADIO DE CORTE)
    # ------------------------------------------------------
    def init_ui_params(self):
        layout = QVBoxLayout()
        
        # Controles
        h_ctrl = QHBoxLayout()
        self.combo_sys_view = QComboBox()
        self.combo_sys_view.currentIndexChanged.connect(self.update_param_plot)
        h_ctrl.addWidget(QLabel("Ver Sistema:"))
        h_ctrl.addWidget(self.combo_sys_view)
        
        h_ctrl.addWidget(QLabel("Radio de Corte (R):"))
        self.sb_radius = QDoubleSpinBox()
        self.sb_radius.setRange(0.1, 5.0); self.sb_radius.setSingleStep(0.05); self.sb_radius.setValue(1.0); self.sb_radius.setSuffix(" nm")
        self.sb_radius.valueChanged.connect(self.update_param_values)
        h_ctrl.addWidget(self.sb_radius)
        
        h_ctrl.addStretch()
        layout.addLayout(h_ctrl)
        
        # Gráfica
        self.fig_params = Figure(figsize=(8, 5))
        self.canvas_params = FigureCanvas(self.fig_params)
        self.toolbar_params = NavigationToolbar(self.canvas_params, self)
        layout.addWidget(self.toolbar_params)
        layout.addWidget(self.canvas_params)
        
        # Tabla de Resultados Calculados
        layout.addWidget(QLabel("<b>Parámetros Calculados al Radio Seleccionado:</b>"))
        self.table_params = QTableWidget()
        self.table_params.setColumnCount(4)
        self.table_params.setHorizontalHeaderLabels(["Sistema", "x1 (Soluto)", "Lambda 12 / Tau 12", "Lambda 21 / Tau 21"])
        self.table_params.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_params.setMaximumHeight(150)
        layout.addWidget(self.table_params)
        
        self.tab_params.setLayout(layout)

    # ------------------------------------------------------
    # UI: 3. PREDICCIÓN
    # ------------------------------------------------------
    def init_ui_predict(self):
        layout = QVBoxLayout()
        
        h_ctrl = QHBoxLayout()
        btn_predict = QPushButton("📈 Generar Curva de Solubilidad")
        btn_predict.clicked.connect(self.run_prediction)
        btn_predict.setStyleSheet("font-weight: bold; background-color: #cce5ff;")
        h_ctrl.addWidget(btn_predict)
        h_ctrl.addStretch()
        layout.addLayout(h_ctrl)
        
        self.fig_pred = Figure(figsize=(8, 6))
        self.canvas_pred = FigureCanvas(self.fig_pred)
        self.toolbar_pred = NavigationToolbar(self.canvas_pred, self)
        layout.addWidget(self.toolbar_pred)
        layout.addWidget(self.canvas_pred)
        
        self.tab_predict.setLayout(layout)

    # ==========================================================
    # LÓGICA DE GESTIÓN DE TABLA Y DATOS
    # ==========================================================
    
    def update_project_data(self, mgr):
        self.project_mgr = mgr
        if self.project_mgr:
            self.manager = SolubilityManager(self.project_mgr)

    def add_system_row(self):
        r = self.table_systems.rowCount(); self.table_systems.insertRow(r)
        
        # Combo de sistemas disponibles
        cb = QComboBox()
        if self.project_mgr:
            cb.addItems(self.project_mgr.get_system_list())
        self.table_systems.setCellWidget(r, 0, cb)
        
        self.table_systems.setItem(r, 1, QTableWidgetItem("0.1")) # x1
        self.table_systems.setItem(r, 2, QTableWidgetItem("10"))  # N1
        self.table_systems.setItem(r, 3, QTableWidgetItem("100")) # N2

    def remove_system_row(self):
        r = self.table_systems.currentRow()
        if r >= 0: self.table_systems.removeRow(r)

    def auto_detect_systems(self):
        """Intenta llenar la tabla basado en nombres de carpetas (ej 'CBD_0.1')"""
        if not self.project_mgr: return
        self.table_systems.setRowCount(0)
        
        systems = self.project_mgr.get_system_list()
        for sys_name in systems:
            # Heurística simple: buscar números flotantes en el nombre
            import re
            match = re.search(r"0\.\d+", sys_name)
            x_val = match.group(0) if match else "0.1"
            
            # Insertar
            self.add_system_row()
            row = self.table_systems.rowCount() - 1
            
            # Seleccionar en combo
            cb = self.table_systems.cellWidget(row, 0)
            idx = cb.findText(sys_name)
            if idx >= 0: cb.setCurrentIndex(idx)
            
            self.table_systems.setItem(row, 1, QTableWidgetItem(x_val))
            # N1 y N2 son difíciles de adivinar sin leer topol, dejamos defaults

    # ==========================================================
    # LÓGICA DE EJECUCIÓN (BATCH)
    # ==========================================================

    def run_batch_calculation(self):
        if self.table_systems.rowCount() == 0: return
        
        # 1. Recopilar configuración de la tabla
        systems_config = []
        for r in range(self.table_systems.rowCount()):
            cb = self.table_systems.cellWidget(r, 0)
            name = cb.currentText()
            x1 = float(self.table_systems.item(r, 1).text())
            n1 = int(self.table_systems.item(r, 2).text())
            n2 = int(self.table_systems.item(r, 3).text())
            
            systems_config.append({
                'name': name, 'x_solute': x1, 
                'n_solute': n1, 'n_solvent': n2,
                # Parámetros físicos
                'v1': self.sb_v1.value(), 'v2': self.sb_v2.value()
            })
            
        # 2. Configurar Worker
        step = self.txt_step.text()
        g1 = self.txt_grp1.text()
        g2 = self.txt_grp2.text()
        
        self.btn_calc_batch.setEnabled(False)
        self.progress_bar.setRange(0, 0) # Indeterminado
        
        # Primero ejecutamos la generación de RDFs (pesado)
        self.worker = BatchWorker(
            self.manager.run_batch_rdfs, 
            systems_config, step, g1, g2
        )
        self.worker.progress_signal.connect(self.lbl_status.setText)
        # Al terminar RDFs, calculamos parámetros matemáticos (rápido)
        self.worker.finished_signal.connect(lambda s, m: self.on_batch_finished(s, m, systems_config))
        self.worker.start()

    def on_batch_finished(self, success, msg, config):
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(100)
        self.btn_calc_batch.setEnabled(True)
        
        if not success:
            QMessageBox.critical(self, "Error", msg)
            return
            
        # 3. Calcular Parámetros Termodinámicos (Integración Numérica)
        model = self.combo_model.currentText().lower()
        mw1 = self.sb_mw1.value()
        mw2 = self.sb_mw2.value()
        step = self.txt_step.text()
        
        self.lbl_status.setText("Integrando RDFs...")
        try:
            self.calculated_results = self.manager.calculate_params_profile(
                config, step, model, mw1, mw2
            )
            QMessageBox.information(self, "Éxito", "Cálculos completados.\nRevise la pestaña 2.")
            
            # Actualizar gráficos de parámetros
            self.update_param_plot_combo()
            self.update_param_plot()
            self.main_tabs.setCurrentIndex(1) # Ir a tab 2
            
        except Exception as e:
            QMessageBox.critical(self, "Error Matemático", str(e))

    # ==========================================================
    # LÓGICA DE ANÁLISIS Y GRÁFICAS
    # ==========================================================

    def update_param_plot_combo(self):
        self.combo_sys_view.clear()
        self.combo_sys_view.addItems(sorted(self.calculated_results.keys()))

    def update_param_plot(self):
        sys_name = self.combo_sys_view.currentText()
        if sys_name not in self.calculated_results: return
        
        data = self.calculated_results[sys_name]
        r = data['r']
        p12 = data['p12']
        p21 = data['p21']
        
        self.fig_params.clear()
        ax = self.fig_params.add_subplot(111)
        
        ax.plot(r, p12, label="Param 12", color='blue')
        ax.plot(r, p21, label="Param 21", color='red')
        
        # Línea vertical del radio seleccionado
        cut = self.sb_radius.value()
        ax.axvline(x=cut, color='green', linestyle='--', label=f"Cutoff: {cut} nm")
        
        ax.set_title(f"Convergencia de Parámetros de Interacción ({sys_name})")
        ax.set_xlabel("Radio de Integración (nm)")
        ax.set_ylabel("Valor Parámetro (Lambda/Tau)")
        ax.legend()
        ax.grid(True)
        self.canvas_params.draw()
        
        self.update_param_values()

    def update_param_values(self):
        """Actualiza la tabla con los valores al radio de corte seleccionado"""
        cut = self.sb_radius.value()
        self.table_params.setRowCount(0)
        
        self.update_param_plot() # Refrescar línea vertical
        
        for sys_name, data in self.calculated_results.items():
            r = data['r']
            # Encontrar índice más cercano al cutoff
            idx = (np.abs(r - cut)).argmin()
            
            val12 = data['p12'][idx]
            val21 = data['p21'][idx]
            x1 = data['x_solute']
            
            row = self.table_params.rowCount()
            self.table_params.insertRow(row)
            self.table_params.setItem(row, 0, QTableWidgetItem(sys_name))
            self.table_params.setItem(row, 1, QTableWidgetItem(str(x1)))
            self.table_params.setItem(row, 2, QTableWidgetItem(f"{val12:.4f}"))
            self.table_params.setItem(row, 3, QTableWidgetItem(f"{val21:.4f}"))

    # ==========================================================
    # PREDICCIÓN FINAL
    # ==========================================================
    
    def run_prediction(self):
        if not self.calculated_results: return
        
        # Tomar parámetros PROMEDIO de todos los sistemas
        # (Mejora: Permitir regresión o selección manual)
        vals12 = []
        vals21 = []
        cut = self.sb_radius.value()
        
        for d in self.calculated_results.values():
            idx = (np.abs(d['r'] - cut)).argmin()
            vals12.append(d['p12'][idx])
            vals21.append(d['p21'][idx])
            
        # Parámetros finales para el modelo
        avg_p12 = np.mean(vals12)
        avg_p21 = np.mean(vals21)
        
        params = {'p12': avg_p12, 'p21': avg_p21, 'alpha': 0.3}
        
        # Generar curva T vs x
        tm = self.sb_tm.value()
        hfus = self.sb_hfus.value()
        model = self.combo_model.currentText().lower()
        
        # Rango T: Desde 0.5*Tm hasta Tm
        temp_range = np.linspace(tm * 0.5, tm * 0.99, 50)
        
        try:
            x_pred = self.manager.math_model.predict_solubility_curve(
                temp_range, tm, hfus, model, params
            )
            
            # Graficar
            self.fig_pred.clear()
            ax = self.fig_pred.add_subplot(111)
            
            # Graficar 1000/T vs ln(x) (Van't Hoff) o T vs x (Directo)
            # Usemos T vs x directo por claridad
            ax.plot(temp_range, x_pred, 'o-', color='purple', label=f"Predicción {model.upper()}")
            
            # Si hay puntos experimentales cargados (los sistemas base), graficarlos
            # Asumimos que los sistemas se corrieron a una T específica?
            # En esta implementación simple no sabemos la T de cada sistema,
            # pero podemos graficar el punto calculado a 298K si fuera el caso.
            
            ax.set_title("Curva de Solubilidad Sólido-Líquido Predicha")
            ax.set_xlabel("Temperatura (K)")
            ax.set_ylabel("Fracción Molar Solubilidad (x_sat)")
            ax.grid(True)
            ax.legend()
            self.canvas_pred.draw()
            
            self.main_tabs.setCurrentIndex(2)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def update_project_data(self, mgr):
        self.project_mgr = mgr
        if mgr:
            self.manager = SolubilityManager(mgr)