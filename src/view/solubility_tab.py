import os
import re
import numpy as np

# Importaciones de Qt
from PyQt6.QtWidgets import (
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QLabel, 
    QPushButton, 
    QGroupBox, 
    QTableWidget, 
    QTableWidgetItem, 
    QHeaderView, 
    QMessageBox, 
    QSplitter, 
    QComboBox, 
    QSpinBox, 
    QDoubleSpinBox,
    QProgressBar, 
    QFrame, 
    QRadioButton, 
    QButtonGroup, 
    QTabWidget,
    QFormLayout, 
    QAbstractItemView, 
    QLineEdit,
    QCheckBox,
    QSizePolicy,
    QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Importaciones del Controlador
from src.controller.solubility_manager import SolubilityManager
# Importaciones del Modelo
from src.model.structure_analyzer import StructureAnalyzer

# Importaciones de Matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar


from src.view.validation_dialog import ValidationDialog

# =============================================================================
# CLASE WORKER: EJECUCIÓN BATCH (GENERADOR)
# =============================================================================
class BatchWorker(QThread):
    """
    Hilo especializado para ejecutar procesos largos que reportan progreso paso a paso.
    """
    progress_signal = pyqtSignal(str)     # Envía mensajes de log a la UI
    finished_signal = pyqtSignal(bool, str) # Envía resultado final

    def __init__(self, generator_func, *args, **kwargs):
        super().__init__()
        self.gen_func = generator_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # Iterar sobre el generador del manager para obtener actualizaciones en vivo
            for msg, status in self.gen_func(*self.args, **self.kwargs):
                self.progress_signal.emit(msg)
                if not status:
                    pass 
            
            self.finished_signal.emit(True, "Proceso por lotes completado.")
        except Exception as e:
            self.finished_signal.emit(False, f"Error crítico en BatchWorker: {str(e)}")


# =============================================================================
# CLASE PRINCIPAL: PESTAÑA SOLUBILIDAD
# =============================================================================
class SolubilityTab(QWidget):
    def __init__(self):
        super().__init__()
        
        # Referencias
        self.project_mgr = None
        self.manager = None 
        self.worker = None
        
        # Almacén de resultados calculados
        self.calculated_results = {} 
        
        # Inicializar interfaz
        self.init_ui()

    def init_ui(self):
        """Construye la interfaz gráfica organizada en pestañas"""
        layout = QVBoxLayout()
        
        # Contenedor de pestañas principales del flujo de trabajo
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

    # -------------------------------------------------------------------------
    # UI PARTE 1: CONFIGURACIÓN
    # -------------------------------------------------------------------------
    def init_ui_config(self):
        layout = QHBoxLayout()
        
        # --- COLUMNA IZQUIERDA: DEFINICIÓN DE SISTEMAS ---
        left_group = QGroupBox("Definición de Puntos Experimentales (Composición)")
        left_layout = QVBoxLayout()
        
        self.table_systems = QTableWidget()
        self.table_systems.setColumnCount(5)
        self.table_systems.setHorizontalHeaderLabels([
            "Sistema (Carpeta)", 
            "Fracción Molar (x1)", 
            "N Soluto", 
            "N Solvente",
            "¿Usar?"
        ])
        
        self.table_systems.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_systems.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_systems.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        left_layout.addWidget(self.table_systems)
        
        # Botones de gestión de tabla
        hbox_btns = QHBoxLayout()
        
        btn_add = QPushButton("➕ Agregar")
        btn_add.clicked.connect(self.add_system_row)
        
        btn_del = QPushButton("➖ Quitar")
        btn_del.clicked.connect(self.remove_system_row)
        
        btn_auto = QPushButton("🪄 Auto-Detectar")
        btn_auto.setToolTip("Intenta llenar la tabla basándose en los nombres de las carpetas (ej. CBD_0.1)")
        btn_auto.clicked.connect(self.auto_detect_systems)
        
        hbox_btns.addWidget(btn_add)
        hbox_btns.addWidget(btn_del)
        hbox_btns.addWidget(btn_auto)
        
        # Botón para leer topología automáticamente
        btn_read_top = QPushButton("🔢 Leer N de Topología")
        btn_read_top.setToolTip("Lee el archivo topol.top de cada sistema para llenar N Soluto y N Solvente automáticamente.")
        btn_read_top.clicked.connect(self.read_n_from_topology)
        btn_read_top.setStyleSheet("background-color: #e3f2fd; color: #0d47a1; font-weight: bold; padding: 5px;")
        
        left_layout.addLayout(hbox_btns)
        left_layout.addWidget(btn_read_top)
        
        left_group.setLayout(left_layout)
        layout.addWidget(left_group, stretch=55)
        
        # --- COLUMNA DERECHA: PARÁMETROS ---
        right_group = QGroupBox("Parámetros Físicos y Modelo")
        right_layout = QFormLayout()
        
        # Propiedades Físicas Soluto
        right_layout.addRow(QLabel("<b>Propiedades del Soluto:</b>"))
        
        self.sb_tm = QDoubleSpinBox()
        self.sb_tm.setRange(0, 5000)
        self.sb_tm.setValue(340.0)
        self.sb_tm.setSuffix(" K")
        
        self.sb_hfus = QDoubleSpinBox()
        self.sb_hfus.setRange(0, 100000)
        self.sb_hfus.setValue(25000)
        self.sb_hfus.setSuffix(" J/mol")
        
        self.sb_mw1 = QDoubleSpinBox()
        self.sb_mw1.setRange(0, 10000)
        self.sb_mw1.setValue(314.46)
        self.sb_mw1.setSuffix(" g/mol")
        
        self.sb_v1 = QDoubleSpinBox()
        self.sb_v1.setRange(0, 10000)
        self.sb_v1.setValue(300.0)
        self.sb_v1.setSuffix(" cm3/mol")
        
        right_layout.addRow("Temp. Fusión (Tm):", self.sb_tm)
        right_layout.addRow("Entalpía Fusión:", self.sb_hfus)
        right_layout.addRow("Peso Molecular:", self.sb_mw1)
        right_layout.addRow("Volumen Molar (V1):", self.sb_v1)
        
        # Propiedades Físicas Solvente
        right_layout.addRow(QLabel("<b>Propiedades del Solvente:</b>"))
        
        self.sb_mw2 = QDoubleSpinBox()
        self.sb_mw2.setRange(0, 10000)
        self.sb_mw2.setValue(72.15)
        self.sb_mw2.setSuffix(" g/mol")
        
        self.sb_v2 = QDoubleSpinBox()
        self.sb_v2.setRange(0, 10000)
        self.sb_v2.setValue(115.0)
        self.sb_v2.setSuffix(" cm3/mol")
        
        right_layout.addRow("Peso Molecular:", self.sb_mw2)
        right_layout.addRow("Volumen Molar (V2):", self.sb_v2)
        
        # Modelo Termodinámico
        right_layout.addRow(QLabel("<b>Modelo de Actividad:</b>"))
        
        self.combo_model = QComboBox()
        self.combo_model.addItems(["Wilson", "NRTL", "UNIQUAC"])
        # Conectar cambio de modelo a recálculo instantáneo
        self.combo_model.currentIndexChanged.connect(self.on_params_changed)
        
        right_layout.addRow("Modelo:", self.combo_model)
        
        # --- Parámetros Extra UNIQUAC ---
        self.group_uniquac = QFrame() # Frame ligero
        l_uni = QFormLayout()
        l_uni.setContentsMargins(0,0,0,0)
        
        # Soluto
        h_solu = QHBoxLayout()
        self.sb_r1 = QDoubleSpinBox(); self.sb_r1.setRange(0.1, 1000); self.sb_r1.setValue(1.0); self.sb_r1.setPrefix("r=")
        self.sb_q1 = QDoubleSpinBox(); self.sb_q1.setRange(0.1, 1000); self.sb_q1.setValue(1.0); self.sb_q1.setPrefix("q=")
        self.btn_calc_uni1 = QPushButton("⚡"); self.btn_calc_uni1.setToolTip("Calcular r y q desde estructura (.gro)")
        self.btn_calc_uni1.clicked.connect(lambda: self.estimate_uniquac_params(is_solute=True))
        h_solu.addWidget(self.sb_r1); h_solu.addWidget(self.sb_q1); h_solu.addWidget(self.btn_calc_uni1)
        l_uni.addRow("UNIQUAC Soluto:", h_solu)
        
        # Solvente
        h_solv = QHBoxLayout()
        self.sb_r2 = QDoubleSpinBox(); self.sb_r2.setRange(0.1, 1000); self.sb_r2.setValue(1.0); self.sb_r2.setPrefix("r=")
        self.sb_q2 = QDoubleSpinBox(); self.sb_q2.setRange(0.1, 1000); self.sb_q2.setValue(1.0); self.sb_q2.setPrefix("q=")
        self.btn_calc_uni2 = QPushButton("⚡"); self.btn_calc_uni2.setToolTip("Calcular r y q desde estructura (.gro)")
        self.btn_calc_uni2.clicked.connect(lambda: self.estimate_uniquac_params(is_solute=False))
        h_solv.addWidget(self.sb_r2); h_solv.addWidget(self.sb_q2); h_solv.addWidget(self.btn_calc_uni2)
        l_uni.addRow("UNIQUAC Solv:", h_solv)
        
        self.group_uniquac.setLayout(l_uni)
        right_layout.addRow(self.group_uniquac)
        
        # Estado inicial
        self.group_uniquac.setVisible(False)
        
        # Conectar cambio de V1/V2 a recálculo instantáneo (afecta Wilson)
        self.sb_v1.valueChanged.connect(self.on_params_changed)
        self.sb_v2.valueChanged.connect(self.on_params_changed)
        
        # Configuración GROMACS
        right_layout.addRow(QLabel("<b>Configuración GROMACS:</b>"))
        
        self.txt_step = QLineEdit("prod")
        self.txt_step.setPlaceholderText("Nombre paso producción (prefijo)")
        self.txt_step.setToolTip("Prefijo de los archivos .tpr (ej: prod, prod_298, etc)")
        right_layout.addRow("Prefijo Etapa:", self.txt_step)
        
        # Selectores de Grupo
        self.btn_load_groups = QPushButton("🔄 Cargar Grupos")
        self.btn_load_groups.setToolTip("Carga los grupos disponibles del primer sistema de la tabla.")
        self.btn_load_groups.clicked.connect(self.load_groups_from_system)
        
        self.btn_split = QPushButton("🛠️ Separar por Cantidad")
        self.btn_split.setToolTip("Crea grupos Custom_Solute/Solvent basados en N1/N2")
        self.btn_split.setStyleSheet("background-color: #fff3cd; color: #856404; font-weight: bold;")
        self.btn_split.clicked.connect(self.split_groups_by_count)
        
        hbox_g = QHBoxLayout()
        hbox_g.addWidget(self.btn_load_groups)
        hbox_g.addWidget(self.btn_split)
        right_layout.addRow(hbox_g)
        
        self.combo_grp1 = QComboBox()
        self.combo_grp1.setEditable(True)
        self.combo_grp1.setPlaceholderText("Seleccione Soluto")
        
        self.combo_grp2 = QComboBox()
        self.combo_grp2.setEditable(True)
        self.combo_grp2.setPlaceholderText("Seleccione Solvente")
        
        right_layout.addRow("Soluto:", self.combo_grp1)
        right_layout.addRow("Solvente:", self.combo_grp2)
        
        # Ejecución
        # CORRECCIÓN: Definir self.btn_calc_batch ANTES de añadirlo al layout
        self.btn_calc_batch = QPushButton("▶ CALCULAR PARÁMETROS")
        self.btn_calc_batch.setStyleSheet("background-color: #d4edda; font-weight: bold; color: green; height: 30px;")
        self.btn_calc_batch.clicked.connect(self.run_batch_calculation)
        right_layout.addRow(self.btn_calc_batch)
        
        # Definir barra de progreso y etiqueta de estado
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        right_layout.addRow(self.progress_bar)
        
        self.lbl_status = QLabel("Listo.")
        self.lbl_status.setStyleSheet("color: gray;")
        right_layout.addRow(self.lbl_status)
        
        right_group.setLayout(right_layout)
        layout.addWidget(right_group, stretch=45)
        
        self.tab_config.setLayout(layout)

    # -------------------------------------------------------------------------
    # UI PARTE 2: ANÁLISIS DE PARÁMETROS
    # -------------------------------------------------------------------------
    def init_ui_params(self):
        layout = QVBoxLayout()
        
        # Controles Superiores
        hbox_ctrl = QHBoxLayout()
        
        self.combo_sys_view = QComboBox()
        self.combo_sys_view.currentIndexChanged.connect(self.update_param_plot)
        
        hbox_ctrl.addWidget(QLabel("Ver Sistema:"))
        hbox_ctrl.addWidget(self.combo_sys_view)
        
        hbox_ctrl.addSpacing(20)
        
        hbox_ctrl.addWidget(QLabel("Radio de Corte (nm):"))
        self.sb_radius = QDoubleSpinBox()
        self.sb_radius.setRange(0.1, 5.0)
        self.sb_radius.setSingleStep(0.05)
        self.sb_radius.setValue(1.5) # Default 1.5 nm
        self.sb_radius.setSuffix(" nm")
        self.sb_radius.valueChanged.connect(self.update_param_values)
        
        hbox_ctrl.addWidget(self.sb_radius)
        
        # Botón de sugerencia automática
        btn_optimize_r = QPushButton("🔍 Sugerir Radio Óptimo")
        btn_optimize_r.setToolTip("Analiza la varianza de las curvas para encontrar la región más estable.")
        btn_optimize_r.clicked.connect(self.auto_find_stable_radius)
        hbox_ctrl.addWidget(btn_optimize_r)
        
        hbox_ctrl.addStretch()
        layout.addLayout(hbox_ctrl)
        
        # Gráfica Matplotlib
        self.fig_params = Figure(figsize=(8, 5))
        self.canvas_params = FigureCanvas(self.fig_params)
        self.toolbar_params = NavigationToolbar(self.canvas_params, self)
        
        layout.addWidget(self.toolbar_params)
        layout.addWidget(self.canvas_params)
        
        # Tabla de Resultados
        layout.addWidget(QLabel("<b>Parámetros Calculados al Radio Seleccionado:</b>"))
        
        self.table_params = QTableWidget()
        self.table_params.setColumnCount(6) # Extendida con Temp y Sim
        self.table_params.setHorizontalHeaderLabels([
            "Sistema", 
            "Simulación",
            "Temp (K)",
            "x1", 
            "P12", 
            "P21"
        ])
        self.table_params.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_params.setMaximumHeight(200)
        
        layout.addWidget(self.table_params)
        
        self.tab_params.setLayout(layout)

    # -------------------------------------------------------------------------
    # UI PARTE 3: PREDICCIÓN FINAL
    # -------------------------------------------------------------------------
    def init_ui_predict(self):
        layout = QVBoxLayout()
        
        # Control Superior
        hbox_ctrl = QHBoxLayout()
        
        self.chk_lowest = QCheckBox("Optimizar usando solo la concentración más baja (Recomendado)")
        self.chk_lowest.setChecked(True)
        self.chk_lowest.setToolTip("Descarta sistemas concentrados para evitar errores por aglomeración en el cálculo de energía.")
        
        btn_predict = QPushButton("📉 Optimizar y Generar Curva")
        btn_predict.clicked.connect(self.run_prediction)
        btn_predict.setStyleSheet("font-weight: bold; background-color: #cce5ff; padding: 8px;")
        
        hbox_ctrl.addWidget(self.chk_lowest)
        
        # Selector de Método de Optimización
        hbox_ctrl.addWidget(QLabel("Modelo Ajuste:"))
        self.combo_opt_method = QComboBox()
        self.combo_opt_method.addItems([
            "Teórico (Delta G)", 
            "Empírico (A + B/T) - Recomendado"
        ])
        self.combo_opt_method.setToolTip("Teórico: Asume entropía ideal. Empírico: Ajusta Entalpía y Entropía (Mejor para datos ruidosos).")
        hbox_ctrl.addWidget(self.combo_opt_method)
        
        # Rango de Temperatura
        hbox_ctrl.addWidget(QLabel("| Rango T (K):"))
        self.sb_t_min = QDoubleSpinBox()
        self.sb_t_min.setRange(100, 500); self.sb_t_min.setValue(250)
        self.sb_t_min.setToolTip("Temperatura mínima para la gráfica")
        
        self.sb_t_max = QDoubleSpinBox()
        self.sb_t_max.setRange(100, 500); self.sb_t_max.setValue(310)
        self.sb_t_max.setToolTip("Temperatura máxima para la gráfica")
        
        hbox_ctrl.addWidget(self.sb_t_min)
        hbox_ctrl.addWidget(QLabel("-"))
        hbox_ctrl.addWidget(self.sb_t_max)
        
        hbox_ctrl.addSpacing(10)
        
        # Botón Predicción (reutilizando variable btn_predict definida arriba)
        hbox_ctrl.addWidget(btn_predict)
        
        # Botón Validación (NUEVO)
        self.btn_validate = QPushButton("📊 Validar")
        self.btn_validate.setToolTip("Abrir tabla para validación de predicción vs experimental (copiar/pegar)")
        self.btn_validate.clicked.connect(self.open_validation_dialog)
        self.btn_validate.setEnabled(False) # Habilitado tras predicción exitosa
        hbox_ctrl.addWidget(self.btn_validate)

        hbox_ctrl.addStretch()
        
        # Eliminar posible re-declaración huérfana si existiera
        
        hbox_ctrl.addWidget(btn_predict)
        hbox_ctrl.addStretch()
        
        layout.addLayout(hbox_ctrl)
        
        # --- Gráficos Duales (Diagnóstico + Resultado) ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Gráfico Izquierdo: Diagnóstico (Arrhenius)
        self.fig_diag = Figure(figsize=(5, 6))
        self.cv_diag = FigureCanvas(self.fig_diag)
        self.tb_diag = NavigationToolbar(self.cv_diag, self)
        
        w_diag = QWidget()
        l_diag = QVBoxLayout()
        l_diag.addWidget(QLabel("<b>Diagnóstico (Arrhenius):</b>"))
        l_diag.addWidget(self.tb_diag)
        l_diag.addWidget(self.cv_diag)
        w_diag.setLayout(l_diag)
        
        # Gráfico Derecho: Resultado (Solubilidad)
        self.fig_sol = Figure(figsize=(5, 6))
        self.cv_sol = FigureCanvas(self.fig_sol)
        self.tb_sol = NavigationToolbar(self.cv_sol, self)
        
        w_sol = QWidget()
        l_sol = QVBoxLayout()
        l_sol.addWidget(QLabel("<b>Curva de Solubilidad (SLE):</b>"))
        l_sol.addWidget(self.tb_sol)
        l_sol.addWidget(self.cv_sol)
        w_sol.setLayout(l_sol)
        
        splitter.addWidget(w_diag)
        splitter.addWidget(w_sol)
        
        layout.addWidget(splitter)
        self.tab_predict.setLayout(layout)

    # =========================================================================
    # LÓGICA DE GESTIÓN DE DATOS
    # =========================================================================
    
    def estimate_uniquac_params(self, is_solute):
        """Usa StructureAnalyzer para estimar r y q desde un archivo GRO"""
        if self.table_systems.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Agregue sistemas a la tabla primero.")
            return

        # Tomar el primer sistema disponible
        sys_widget = self.table_systems.cellWidget(0, 0)
        sys_name = sys_widget.currentText()
        
        path = self.manager.get_system_path(sys_name)
        if not path:
            return
            
        # Buscar .gro
        candidates = [f for f in os.listdir(path) if f.endswith(".gro")]
        if not candidates:
            QMessageBox.warning(self, "Error", f"No hay archivos .gro en {path}")
            return
        
        # Priorizar equilibrados
        gro_file = os.path.join(path, candidates[0])
        for f in candidates:
            if "prod" in f or "npt" in f: 
                gro_file = os.path.join(path, f)
                break
        
        # Escanear residuos disponibles
        residues = set()
        try:
            with open(gro_file, 'r') as f:
                lines = f.readlines()
                for line in lines[2:min(500, len(lines)-1)]: # Scan rápido inicial
                     if len(line) > 10: residues.add(line[5:10].strip())
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        
        if not residues: return
        
        # Seleccionar residuo
        from PyQt6.QtWidgets import QInputDialog
        label = "Soluto" if is_solute else "Solvente"
        item, ok = QInputDialog.getItem(self, f"UNIQUAC {label}", 
                                      f"Seleccione el residuo que corresponde al {label}:", 
                                      sorted(list(residues)), 0, False)
        
        if ok and item:
            analyzer = StructureAnalyzer()
            r, q, details = analyzer.calculate_uniquac_params(gro_file, item)
            
            if is_solute:
                self.sb_r1.setValue(r); self.sb_q1.setValue(q)
            else:
                self.sb_r2.setValue(r); self.sb_q2.setValue(q)
                
            QMessageBox.information(self, "Reporte UNIFAC", 
                                  f"Estimación para '{item}':\n"
                                  f"R = {r}\nQ = {q}\n\n"
                                  f"Grupos:\n{details}\n\n"
                                  "Nota: Verifique si la detección de grupos es química y estructuralmente correcta.")

    def on_params_changed(self):
        """Recalcula P12/P21 si cambiamos de modelo o volúmenes molares (Hot Swap)"""
        # Toggle UI UNIQUAC
        is_uni = "UNIQUAC" in self.combo_model.currentText().upper()
        if hasattr(self, 'group_uniquac'):
            self.group_uniquac.setVisible(is_uni)
            
        if not self.calculated_results: return
        
        mod = self.combo_model.currentText().lower()
        v1 = self.sb_v1.value()
        v2 = self.sb_v2.value()
        
        # Invocamos al manager para recalcular usando omegas cacheados
        count = self.manager.recalculate_model_params(self.calculated_results, mod, v1, v2)
        
        if count > 0:
            self.lbl_status.setText(f"Modelo {mod.upper()} aplicado. {count} simulaciones actualizadas.")
            # Actualizar gráfica si hay una visible
            self.update_param_plot()
            # Actualizar valores de tabla
            self.update_param_values()

    def update_project_data(self, mgr):
        """Actualiza la referencia al proyecto"""
        self.project_mgr = mgr
        if self.project_mgr:
            self.manager = SolubilityManager(self.project_mgr)

    def add_system_row(self):
        """Añade una fila a la tabla de sistemas"""
        row = self.table_systems.rowCount()
        self.table_systems.insertRow(row)
        
        # Combo de sistemas disponibles en el proyecto
        cb_system = QComboBox()
        if self.project_mgr:
            systems = self.project_mgr.get_system_list()
            cb_system.addItems(sorted(systems))
        
        self.table_systems.setCellWidget(row, 0, cb_system)
        
        # Valores por defecto
        self.table_systems.setItem(row, 1, QTableWidgetItem("0.1")) # Fracción
        self.table_systems.setItem(row, 2, QTableWidgetItem("10"))  # N Soluto
        self.table_systems.setItem(row, 3, QTableWidgetItem("100")) # N Solvente
        
        # Checkbox Activo
        chk = QCheckBox()
        chk.setChecked(True)
        # Centrar Checkbox
        cell_widget = QWidget()
        lay = QHBoxLayout(cell_widget)
        lay.addWidget(chk)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(0,0,0,0)
        
        self.table_systems.setCellWidget(row, 4, cell_widget)

    def remove_system_row(self):
        """Elimina la fila seleccionada"""
        row = self.table_systems.currentRow()
        if row >= 0:
            self.table_systems.removeRow(row)

    def auto_detect_systems(self):
        """
        Intenta llenar la tabla automáticamente basándose en los nombres de las carpetas.
        """
        if not self.project_mgr:
            return
            
        self.table_systems.setRowCount(0)
        
        systems_list = self.project_mgr.get_system_list()
        
        for sys_name in systems_list:
            # Heurística: buscar un número flotante en el nombre (0.1, 0.5, etc)
            match = re.search(r"0\.\d+", sys_name)
            x_val = match.group(0) if match else "0.1"
            
            # Insertar Fila
            self.add_system_row()
            row = self.table_systems.rowCount() - 1
            
            # Seleccionar sistema en el combo
            cb = self.table_systems.cellWidget(row, 0)
            idx = cb.findText(sys_name)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            
            # Setear fracción
            self.table_systems.setItem(row, 1, QTableWidgetItem(x_val))

    def read_n_from_topology(self):
        """Lee topol.top de cada sistema y llena N1/N2"""
        if not self.project_mgr: return
        
        count = 0
        for r in range(self.table_systems.rowCount()):
            sys_name = self.table_systems.cellWidget(r, 0).currentText()
            path = os.path.join(self.project_mgr.current_project_path, "storage", sys_name, "topol.top")
            
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        lines = f.readlines()
                    
                    in_mols = False
                    mols_found = []
                    
                    for line in lines:
                        clean = line.strip()
                        if clean.startswith("[") and "molecules" in clean:
                            in_mols = True
                            continue
                        
                        if in_mols and clean and not clean.startswith(";"):
                            parts = clean.split()
                            if len(parts) >= 2:
                                try:
                                    mols_found.append( (parts[0], int(parts[1])) )
                                except: pass
                    
                    if len(mols_found) >= 2:
                        self.table_systems.setItem(r, 2, QTableWidgetItem(str(mols_found[0][1])))
                        self.table_systems.setItem(r, 3, QTableWidgetItem(str(mols_found[1][1])))
                        count += 1
                except Exception as e:
                    print(f"Error leyendo {sys_name}: {e}")
        
        QMessageBox.information(self, "Hecho", f"Se actualizaron {count} filas desde topol.top")

    # --- FEATURE: GRUPOS ---

    def load_groups_from_system(self):
        """Carga los grupos disponibles en los ComboBox"""
        if self.table_systems.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Agregue sistemas primero.")
            return
            
        sys_widget = self.table_systems.cellWidget(0, 0)
        sys_name = sys_widget.currentText()
        step = self.txt_step.text()
        
        self.lbl_status.setText(f"Escaneando grupos de {sys_name}...")
        QApplication.processEvents()
        
        # Llamada al manager
        groups = self.manager.get_available_groups(sys_name, step)
        
        if not groups:
            QMessageBox.warning(self, "Error", f"No se pudieron leer grupos de {sys_name}/{step}.tpr\nIntente 'Separar Grupos por Cantidad' si no hay grupos.")
            self.lbl_status.setText("Error leyendo grupos.")
            return
            
        self.combo_grp1.clear()
        self.combo_grp2.clear()
        
        # Llenar combos
        sorted_groups = sorted(groups.keys())
        self.combo_grp1.addItems(sorted_groups)
        self.combo_grp2.addItems(sorted_groups)
        
        # Defaults inteligentes
        for d in ["Custom_Solute", "CBD", "UNL", "MOL"]: 
            if self.combo_grp1.findText(d)>=0: 
                self.combo_grp1.setCurrentText(d); break
        for d in ["Custom_Solvent", "SOL", "Pentane"]: 
            if self.combo_grp2.findText(d)>=0: 
                self.combo_grp2.setCurrentText(d); break
        
        self.lbl_status.setText("Grupos cargados.")

    def split_groups_by_count(self):
        """Crea grupos Custom basados en conteo"""
        if self.table_systems.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Agregue sistemas primero.")
            return
            
        sys = self.table_systems.cellWidget(0, 0).currentText()
        try:
            n1 = int(self.table_systems.item(0, 2).text())
            n2 = int(self.table_systems.item(0, 3).text())
        except:
            QMessageBox.critical(self, "Error", "Valores N1/N2 inválidos")
            return
        
        self.lbl_status.setText("Creando grupos...")
        QApplication.processEvents()
        
        s, m = self.manager.force_creation_of_count_groups(sys, self.txt_step.text(), n1, n2)
        if s:
            QMessageBox.information(self, "Grupos Creados Exitosamente", 
                "Se han generado los grupos basados en cantidad:\n"
                "- 'Custom_Solute' (primeras N1 moléculas)\n"
                "- 'Custom_Solvent' (siguientes N2 moléculas)\n\n"
                "Se seleccionarán automáticamente ahora.")
            self.load_groups_from_system()
            
            # Forzar selección automática explícita
            idx1 = self.combo_grp1.findText("Custom_Solute")
            if idx1 >= 0: self.combo_grp1.setCurrentIndex(idx1)
            
            idx2 = self.combo_grp2.findText("Custom_Solvent")
            if idx2 >= 0: self.combo_grp2.setCurrentIndex(idx2)
        else:
            QMessageBox.critical(self, "Error", m)

    # =========================================================================
    # EJECUCIÓN (BATCH)
    # =========================================================================

    def run_batch_calculation(self):
        """Recopila datos de la tabla e inicia el proceso batch en segundo plano"""
        if self.table_systems.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "No hay sistemas en la tabla.")
            return
        
        # 1. Recopilar configuración de la tabla
        systems_config = []
        for r in range(self.table_systems.rowCount()):
            # Verificar si el checkbox está activo
            cell_w = self.table_systems.cellWidget(r, 4)
            # Buscar el QCheckBox dentro del layout
            chk = cell_w.findChild(QCheckBox) if cell_w else None
            
            if chk and not chk.isChecked():
                continue # Saltar sistema si no está marcado
            
            cb_system = self.table_systems.cellWidget(r, 0)
            name = cb_system.currentText()
            
            try:
                x1 = float(self.table_systems.item(r, 1).text())
                n1 = int(self.table_systems.item(r, 2).text())
                n2 = int(self.table_systems.item(r, 3).text())
            except ValueError:
                QMessageBox.critical(self, "Error", f"Valores numéricos inválidos en la fila {r+1}")
                return
            
            systems_config.append({
                'name': name, 
                'x_solute': x1, 
                'n_solute': n1, 
                'n_solvent': n2,
                'v1': self.sb_v1.value(), 
                'v2': self.sb_v2.value()
            })
            
        if not systems_config:
            QMessageBox.warning(self, "Aviso", "No hay sistemas seleccionados (Checkbox activo).")
            return
            
        # 2. Configurar Worker
        step_name = self.txt_step.text()
        
        # Usamos los textos de los combos cargados
        grp1 = self.combo_grp1.currentText()
        grp2 = self.combo_grp2.currentText()
        
        if not grp1 or not grp2:
             QMessageBox.warning(self, "Aviso", "Por favor cargue y seleccione los grupos antes de calcular.")
             return

        self.btn_calc_batch.setEnabled(False)
        self.progress_bar.setRange(0, 0) # Indeterminado
        
        # Instanciar BatchWorker con el generador del manager
        self.worker = BatchWorker(
            self.manager.run_batch_rdfs, 
            systems_config, step_name, grp1, grp2
        )
        
        # Conectar señales
        self.worker.progress_signal.connect(self.lbl_status.setText)
        self.worker.finished_signal.connect(lambda s, m: self.on_batch_finished(s, m, systems_config))
        
        self.worker.start()

    def on_batch_finished(self, success, msg, config):
        """Callback al terminar el cálculo de RDFs"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.btn_calc_batch.setEnabled(True)
        
        if not success:
            QMessageBox.critical(self, "Error en Batch", msg)
            # Aún así intentamos procesar lo que se haya logrado (si fue parcial)
        
        self.lbl_status.setText("Integrando RDFs y calculando parámetros...")
        QApplication.processEvents()
        
        model = self.combo_model.currentText().lower()
        mw1 = self.sb_mw1.value()
        mw2 = self.sb_mw2.value()
        step = self.txt_step.text()
        
        try:
            self.calculated_results = self.manager.calculate_params_profile(
                config, step, model, mw1, mw2
            )
            
            # Validar si hubo resultados
            if not self.calculated_results:
                QMessageBox.warning(self, "Datos Vacíos", 
                                    "El cálculo finalizó pero no se obtuvieron resultados válidos.\n"
                                    "Verifique los nombres de los grupos y que existan los archivos .tpr/.xtc.")
                self.lbl_status.setText("Fallo en cálculo matemático.")
                return

            QMessageBox.information(self, "Éxito", "Cálculos completados.\nRevise la pestaña 'Análisis de Parámetros'.")
            
            # Actualizar gráficos de parámetros
            self.update_param_plot_combo()
            self.update_param_plot()
            self.main_tabs.setCurrentIndex(1) # Ir a tab 2
            self.lbl_status.setText("Finalizado Correctamente.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error Matemático", str(e))
            self.lbl_status.setText("Error.")

    # =========================================================================
    # LÓGICA DE ANÁLISIS Y GRÁFICAS
    # =========================================================================

    def update_param_plot_combo(self):
        """Llena el combo de visualización con los sistemas procesados"""
        self.combo_sys_view.clear()
        self.combo_sys_view.addItems(sorted(self.calculated_results.keys()))

    def update_param_plot(self):
        """Dibuja la gráfica de convergencia de parámetros (Tau vs Radio)"""
        sys_name = self.combo_sys_view.currentText()
        if sys_name not in self.calculated_results:
            return
        
        data = self.calculated_results[sys_name]
        r = data['r']
        p12 = data['p12']
        p21 = data['p21']
        
        self.fig_params.clear()
        ax = self.fig_params.add_subplot(111)
        
        ax.plot(r, p12, label="Param 12", color='b', linewidth=2)
        ax.plot(r, p21, label="Param 21", color='red', linewidth=2)
        
        # Línea vertical del radio seleccionado
        cut = self.sb_radius.value()
        ax.axvline(x=cut, color='green', linestyle='--', label=f"Cutoff: {cut} nm")
        
        ax.set_title(f"Convergencia de Parámetros ({sys_name})")
        ax.set_xlabel("Radio de Integración (nm)")
        ax.set_ylabel("Valor Parámetro (Lambda/Tau)")
        ax.legend()
        ax.grid(True, linestyle='--', alpha=0.6)
        
        self.canvas_params.draw()
        
        # Actualizar tabla de valores puntuales
        self.update_param_values()

    def update_param_values(self):
        """Actualiza la tabla con los valores al radio de corte seleccionado"""
        cut = self.sb_radius.value()
        self.table_params.setRowCount(0)
        
        # Redibujar gráfica para mover la línea verde
        self.update_param_plot_combo_silent_redraw()
        
        for key, data in self.calculated_results.items():
            r = data['r']
            if len(r) == 0: continue
            
            # Encontrar índice más cercano al cutoff
            idx = (np.abs(r - cut)).argmin()
            
            val12 = data['p12'][idx]
            val21 = data['p21'][idx]
            x1 = data['x_solute']
            
            # Recuperar datos extra
            real_sys_name = data.get('system', key)
            sim_name = data.get('simulation', '-')
            temp_val = data.get('temperature', 0.0)
            
            row = self.table_params.rowCount()
            self.table_params.insertRow(row)
            
            # Columna 0: Sistema
            self.table_params.setItem(row, 0, QTableWidgetItem(real_sys_name))
            # Columna 1: Simulación
            self.table_params.setItem(row, 1, QTableWidgetItem(sim_name))
            # Columna 2: Temperatura
            self.table_params.setItem(row, 2, QTableWidgetItem(f"{temp_val:.2f}"))
            # Columna 3: Fracción x1
            self.table_params.setItem(row, 3, QTableWidgetItem(str(x1)))
            # Columna 4: Parámetro 12
            self.table_params.setItem(row, 4, QTableWidgetItem(f"{val12:.4f}"))
            # Columna 5: Parámetro 21
            self.table_params.setItem(row, 5, QTableWidgetItem(f"{val21:.4f}"))

    def update_param_plot_combo_silent_redraw(self):
        """Helper para redibujar solo la línea verde sin recargar todo el combo"""
        if self.fig_params.axes:
            ax = self.fig_params.axes[0]
            for line in ax.lines:
                if line.get_label().startswith("Cutoff"):
                    line.set_xdata([self.sb_radius.value()])
            self.canvas_params.draw()

    def auto_find_stable_radius(self):
        """Feature: Sugerencia de radio óptimo (Solo sistemas seleccionados)"""
        if not self.calculated_results: 
            QMessageBox.information(self, "Aviso", "Primero debe calcular los parámetros.")
            return

        # --- FILTRADO DE SISTEMAS ACTIVOS ---
        allowed_systems = set()
        for r in range(self.table_systems.rowCount()):
            cell_w = self.table_systems.cellWidget(r, 4)
            chk = cell_w.findChild(QCheckBox) if cell_w else None
            # Si no hay checkbox o está marcado, se considera activo
            if not chk or chk.isChecked():
                cb = self.table_systems.cellWidget(r, 0)
                if cb: allowed_systems.add(cb.currentText())

        # Filtrar datos de self.calculated_results
        active_results = {}
        for key, res in self.calculated_results.items():
            if res.get('system') in allowed_systems:
                active_results[key] = res
                
        if not active_results:
            QMessageBox.warning(self, "Aviso", "No hay sistemas seleccionados activos.")
            return

        try:
            res = self.manager.analyze_cutoff_stability(active_results)
            if res:
                s = res['suggested_r']
                self.sb_radius.setValue(s)
                QMessageBox.information(self, "Sugerencia", f"Radio sugerido: {s:.2f} nm\nBasado en {len(active_results)} simulaciones seleccionadas.")
            else:
                QMessageBox.warning(self, "Aviso", "No se encontró un radio estable claro.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al analizar estabilidad:\n{str(e)}")
    
    def open_validation_dialog(self):
        """Abre la ventana flotante de validación"""
        if not hasattr(self, 'last_prediction_state'): return
        
        # Recuperar parámetros del ajuste
        fit_state = self.last_prediction_state
        
        # Crear callback de predicción
        def predictor_callback(T):
            """Calcula Solubilidad (x) a una T específica usando parámetros ya ajustados"""
            fit12 = fit_state['fit12']
            fit21 = fit_state['fit21']
            mod = fit_state['model']
            method = fit_state['opt_method']
            
            # 1. Recuperar Energías (P12/P21) a la temperatura T
            R = 8.314
            p12 = 0.0
            p21 = 0.0
            
            # --- MISMA LÓGICA QUE EN solubility_manager.predict_with_global_optimization ---
            if method == 'empirical':
                A12, B12 = fit12['params']
                A21, B21 = fit21['params']
                
                v12 = A12 + B12 / T
                v21 = A21 + B21 / T
                
                if mod == 'nrtl':
                    p12 = v12
                    p21 = v21
                else: # wilson
                    p12 = np.exp(v12)
                    p21 = np.exp(v21)
            else:
                # Theoretical
                if mod == 'nrtl':
                    p12 = fit12['energy'] / (R * T)
                    p21 = fit21['energy'] / (R * T)
                else: 
                    # Wilson (Lambda = exp(-dg/RT))
                    p12 = np.exp(-fit12['energy'] / (R * T))
                    p21 = np.exp(-fit21['energy'] / (R * T))
            
            # 2. Solver SLE
            solver_params = {'p12': p12, 'p21': p21, 'alpha': 0.3}
            if fit_state.get('extra_params'):
                solver_params.update(fit_state['extra_params'])
                
            return self.manager.math_model.solve_sle_solubility(
                T, fit_state['tm'], fit_state['hfus'], mod, solver_params
            )
        
        # Obtener datos guardados si existen
        data = getattr(self, 'saved_validation_data', [])
        
        # Abrir Dialogo
        dlg = ValidationDialog(predictor_callback, initial_data=data, parent=self)
        dlg.exec() # Modal para asegurar consistencia
        
        # Al cerrar, guardar datos
        self.saved_validation_data = dlg.get_data()

    # =========================================================================
    # PREDICCIÓN FINAL
    # =========================================================================
    
    def run_prediction(self):
        """Calcula y grafica la curva de solubilidad final"""
        if not self.calculated_results:
            QMessageBox.warning(self, "Aviso", "No hay datos calculados.")
            return
        
        # --- FILTRADO DE SISTEMAS ACTIVOS ---
        allowed_systems = set()
        for r in range(self.table_systems.rowCount()):
            cell_w = self.table_systems.cellWidget(r, 4)
            chk = cell_w.findChild(QCheckBox) if cell_w else None
            # Si no hay checkbox o está marcado, se considera activo
            if not chk or chk.isChecked():
                cb = self.table_systems.cellWidget(r, 0)
                if cb: allowed_systems.add(cb.currentText())
        
        # Crear subconjunto de datos para la predicción
        active_results = {}
        for key, res in self.calculated_results.items():
            if res.get('system') in allowed_systems:
                active_results[key] = res
                
        if not active_results:
            QMessageBox.warning(self, "Aviso", "No hay sistemas activos seleccionados para generar la predicción.")
            return
        # ------------------------------------
        
        cut = self.sb_radius.value()
        tm = self.sb_tm.value()
        hfus = self.sb_hfus.value()
        mod = self.combo_model.currentText().lower()
        use_low = self.chk_lowest.isChecked()
        opt_method = "empirical" if "Empírico" in self.combo_opt_method.currentText() else "theoretical"
        
        # Rango de temperatura
        t_min, t_max = self.sb_t_min.value(), self.sb_t_max.value()
        
        # Extraer parámetros de UNIQUAC si es necesario
        extra_solver_params = {}
        if "uniquac" in mod:
            extra_solver_params['r1'] = self.sb_r1.value()
            extra_solver_params['q1'] = self.sb_q1.value()
            extra_solver_params['r2'] = self.sb_r2.value()
            extra_solver_params['q2'] = self.sb_q2.value()

        try:
            # Llamar al Solver Matemático usando SOLO LOS RESULTADOS ACTIVOS
            tr, xp, arr_data, fit_res = self.manager.predict_with_global_optimization(
                active_results, cut, tm, hfus, mod, use_low, opt_method, 
                t_range=(t_min, t_max), extra_params=extra_solver_params
            )
            
            # Guardamos el estado del ajuste para la ventana de validación
            self.last_prediction_state = {
                'fit12': fit_res['fit12'],
                'fit21': fit_res['fit21'],
                'tm': tm, 'hfus': hfus,
                'model': mod,
                'opt_method': opt_method,
                'extra_params': extra_solver_params
            }
            # Habilitar botón de validación si existe
            if hasattr(self, 'btn_validate'): self.btn_validate.setEnabled(True)
            
            if tr is None:
                QMessageBox.warning(self, "Error", "Datos insuficientes para regresión en los sistemas seleccionados.")
                return

            # Gráfica 1: Arrhenius (Diagnóstico)
            self.fig_diag.clear()
            ax1 = self.fig_diag.add_subplot(111)
            
            if arr_data and len(arr_data['x']) > 0:
                ax1.scatter(arr_data['x'], arr_data['y12'], c='b', label='Obs P12')
                ax1.scatter(arr_data['x'], arr_data['y21'], c='r', label='Obs P21')
                # Líneas de ajuste
                if 'fit_x' in arr_data:
                    ax1.plot(arr_data['fit_x'], arr_data['fit_y12'], 'b--', alpha=0.6)
                    ax1.plot(arr_data['fit_x'], arr_data['fit_y21'], 'r--', alpha=0.6)
            
            ax1.set_title("Diagnóstico (Arrhenius)")
            ax1.set_xlabel("1000/T (K⁻¹)")
            ax1.set_ylabel("ln(Parámetro)")
            ax1.grid(True)
            ax1.legend()
            self.cv_diag.draw()

            # Gráfica 2: Solubilidad
            self.fig_sol.clear()
            ax2 = self.fig_sol.add_subplot(111)
            
            ax2.plot(tr, xp, 'o-', color='purple', label=f"Predicción {mod.upper()}")
            
            ax2.set_title("Curva de Solubilidad Sólido-Líquido Predicha")
            ax2.set_xlabel("Temperatura (K)")
            ax2.set_ylabel("Fracción Molar Solubilidad ($x_{sat}$)")
            ax2.grid(True, linestyle='--', alpha=0.6)
            ax2.legend()
            
            self.cv_sol.draw()
            self.main_tabs.setCurrentIndex(2)
            
            QMessageBox.information(self, "Cálculo Exitoso", "Predicción Generada.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error en Predicción", str(e))

    # =========================================================================
    # PERSISTENCIA (GUARDAR Y CARGAR ESTADO)
    # =========================================================================

    def _serialize_results(self, results):
        """Asegura que los datos sean serializables a JSON (numpy -> list)"""
        if not results: return {}
        out = {}
        for k, v in results.items():
            out[k] = v.copy()
            # Incluimos omegas en la serialización
            for field in ['r', 'p12', 'p21', 'omega12', 'omega21']:
                if field in out[k] and isinstance(out[k][field], (np.ndarray, list)):
                    out[k][field] = np.array(out[k][field]).tolist()
        return out

    def _deserialize_results(self, data):
        """Restaura los datos desde JSON (list -> numpy)"""
        if not data: return {}
        out = {}
        for k, v in data.items():
            out[k] = v.copy()
            for field in ['r', 'p12', 'p21', 'omega12', 'omega21']:
                if field in out[k]:
                    out[k][field] = np.array(out[k][field])
        return out

    def get_state(self):
        """Guarda la configuración de la tabla y parámetros físicos"""
        systems = []
        for r in range(self.table_systems.rowCount()):
            cb = self.table_systems.cellWidget(r, 0)
            name = cb.currentText() if cb else ""
            
            # Obtener estado del checkbox
            cell_w = self.table_systems.cellWidget(r, 4)
            chk = cell_w.findChild(QCheckBox) if cell_w else None
            is_active = chk.isChecked() if chk else True

            systems.append({
                'name': name,
                'x1': self.table_systems.item(r, 1).text(),
                'n1': self.table_systems.item(r, 2).text(),
                'n2': self.table_systems.item(r, 3).text(),
                'active': is_active
            })
            
        return {
            "systems": systems,
            "tm": self.sb_tm.value(),
            "hfus": self.sb_hfus.value(),
            "mw1": self.sb_mw1.value(), "mw2": self.sb_mw2.value(),
            "v1": self.sb_v1.value(), "v2": self.sb_v2.value(),
            "model": self.combo_model.currentIndex(),
            "validation_data": getattr(self, 'saved_validation_data', []),
            "grp1": self.combo_grp1.currentText(),
            "grp2": self.combo_grp2.currentText(),
            "radius": self.sb_radius.value(),
            "calculated_results": self._serialize_results(self.calculated_results)
        }

    def set_state(self, state):
        """Restaura la configuración"""
        if not state: return
        
        # Restaurar Datos de Validación
        self.saved_validation_data = state.get('validation_data', [])
        
        self.sb_tm.setValue(state.get("tm", 340.0))
        self.sb_hfus.setValue(state.get("hfus", 25000))
        self.sb_mw1.setValue(state.get("mw1", 314.46))
        self.sb_mw2.setValue(state.get("mw2", 72.15))
        self.sb_v1.setValue(state.get("v1", 300.0))
        self.sb_v2.setValue(state.get("v2", 115.0))
        self.combo_model.setCurrentIndex(state.get("model", 0))
        self.combo_grp1.setEditText(state.get("grp1", ""))
        self.combo_grp2.setEditText(state.get("grp2", ""))
        self.sb_radius.setValue(state.get("radius", 1.0))
        
        # Restaurar resultados y actualizar gráficas
        raw_res = state.get("calculated_results", {})
        if raw_res:
            self.calculated_results = self._deserialize_results(raw_res)
            self.update_param_plot_combo()
            self.update_param_plot()
            # Ir a pestaña 2 si hay datos para mostrar que se cargaron
            if self.calculated_results:
                self.lbl_status.setText("Datos históricos restaurados.")
        
        self.table_systems.setRowCount(0)
        for s in state.get("systems", []):
            self.add_system_row()
            r = self.table_systems.rowCount() - 1
            cb = self.table_systems.cellWidget(r, 0)
            if cb: cb.setCurrentText(s.get("name", ""))
            self.table_systems.setItem(r, 1, QTableWidgetItem(s.get("x1")))
            self.table_systems.setItem(r, 2, QTableWidgetItem(s.get("n1")))
            self.table_systems.setItem(r, 3, QTableWidgetItem(s.get("n2")))
            
            # Restaurar checkbox
            active = s.get("active", True)
            cell_w = self.table_systems.cellWidget(r, 4)
            chk = cell_w.findChild(QCheckBox) if cell_w else None
            if chk: chk.setChecked(active)