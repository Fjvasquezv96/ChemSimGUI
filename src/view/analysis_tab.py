import os
import subprocess
import numpy as np

# Importaciones de Qt (PyQt6)
from PyQt6.QtWidgets import (
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QLabel, 
    QPushButton, 
    QComboBox, 
    QGroupBox, 
    QTableWidget, 
    QTableWidgetItem, 
    QHeaderView, 
    QMessageBox, 
    QSplitter, 
    QTabWidget, 
    QSpinBox, 
    QRadioButton, 
    QLineEdit, 
    QButtonGroup, 
    QStackedWidget, 
    QCheckBox,
    QDialog, 
    QTreeWidget, 
    QTreeWidgetItem, 
    QApplication, 
    QScrollArea,
    QDoubleSpinBox,
    QColorDialog,
    QFormLayout,
    QSizePolicy,
    QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor

# Importaciones del Modelo de Negocio
from src.model.analysis_parser import AnalysisParser
from src.model.molecule_graph import MoleculeGraphGenerator

# Importaciones de Matplotlib (Graficación)
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar


# =============================================================================
# CLASE WORKER: EJECUCIÓN EN SEGUNDO PLANO
# =============================================================================
class AnalysisWorker(QThread):
    """
    Hilo independiente para ejecutar tareas pesadas (GROMACS, TRAVIS)
    sin congelar la interfaz gráfica mientras se procesan los datos.
    """
    finished_signal = pyqtSignal(bool, str) # Señal que emite (Exito, Mensaje)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Ejecuta la función pasada como argumento en el hilo"""
        try:
            # Se asume que la función retorna una tupla (bool, str)
            success, msg = self.func(*self.args, **self.kwargs)
            self.finished_signal.emit(success, msg)
        except Exception as e:
            self.finished_signal.emit(False, f"Error inesperado en Worker: {str(e)}")


# =============================================================================
# CLASE DIÁLOGO: SELECCIÓN DE ÁTOMOS CON VISUALIZACIÓN
# =============================================================================
class AtomSelectionDialog(QDialog):
    """
    Ventana emergente que permite al usuario explorar la estructura molecular (.gro),
    generar diagramas 2D de las moléculas (usando Graphviz) para facilitar la identificación
    visual de los átomos, y seleccionar un residuo o átomo específico para crear un grupo.
    """
    def __init__(self, structure_map, gro_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Explorador Visual de Estructura Molecular")
        self.resize(1100, 750)
        
        # Estado interno
        self.selected_command = None
        self.gro_path = gro_path
        
        # Instancia del generador de grafos moleculares
        self.graph_gen = MoleculeGraphGenerator()
        
        # Directorio de cache para las imágenes generadas (evita re-generar)
        self.image_cache_dir = os.path.join(os.path.dirname(gro_path), "mol_images")
        os.makedirs(self.image_cache_dir, exist_ok=True)
        
        # Construir la interfaz del diálogo
        self.init_ui(structure_map)

    def init_ui(self, structure_map):
        layout = QVBoxLayout()
        
        # Splitter para dividir Árbol (Izq) y Visor (Der)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ------------------------------------------------------
        # PANEL IZQUIERDO: ÁRBOL DE JERARQUÍA
        # ------------------------------------------------------
        widget_left = QWidget()
        vbox_left = QVBoxLayout()
        
        lbl_instruct = QLabel("1. Navegue y seleccione un Residuo o Átomo:")
        lbl_instruct.setStyleSheet("font-weight: bold; color: #333;")
        vbox_left.addWidget(lbl_instruct)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Sistema / Estructura")
        self.tree.itemClicked.connect(self.on_item_clicked)
        vbox_left.addWidget(self.tree)
        
        widget_left.setLayout(vbox_left)
        
        # Llenar el árbol con los datos parseados del GRO
        for res_name, atoms in structure_map.items():
            # Nodo Padre: Residuo (Molécula)
            res_item = QTreeWidgetItem(self.tree)
            res_item.setText(0, f"Residuo: {res_name}")
            # Data oculta: comando para make_ndx
            res_item.setData(0, Qt.ItemDataRole.UserRole, f"r {res_name}")
            # Data oculta: nombre puro para generar imagen
            res_item.setData(0, Qt.ItemDataRole.UserRole + 1, res_name) 
            
            # Nodos Hijos: Átomos individuales
            for atom in sorted(atoms):
                atom_item = QTreeWidgetItem(res_item)
                atom_item.setText(0, f"Átomo: {atom}")
                # Data oculta: comando para seleccionar átomo específico
                atom_item.setData(0, Qt.ItemDataRole.UserRole, f"a {atom}")
                # Data oculta: referencia al residuo padre para la imagen
                atom_item.setData(0, Qt.ItemDataRole.UserRole + 1, res_name)
        
        # ------------------------------------------------------
        # PANEL DERECHO: VISOR DE IMAGEN
        # ------------------------------------------------------
        widget_right = QWidget()
        vbox_right = QVBoxLayout()
        
        lbl_vis = QLabel("2. Diagrama Estructural (Ayuda Visual):")
        lbl_vis.setStyleSheet("font-weight: bold; color: #333;")
        vbox_right.addWidget(lbl_vis)
        
        self.scroll_area = QScrollArea()
        self.lbl_image = QLabel("Seleccione un residuo a la izquierda para ver su estructura 2D.")
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        
        self.scroll_area.setWidget(self.lbl_image)
        self.scroll_area.setWidgetResizable(True)
        
        vbox_right.addWidget(self.scroll_area)
        widget_right.setLayout(vbox_right)
        
        # Agregar paneles al splitter
        splitter.addWidget(widget_left)
        splitter.addWidget(widget_right)
        splitter.setStretchFactor(1, 2) # Dar más espacio a la imagen (2/3)
        
        layout.addWidget(splitter)
        
        # ------------------------------------------------------
        # BOTONES DE ACCIÓN
        # ------------------------------------------------------
        btn_select = QPushButton("Confirmar Selección y Crear Grupo")
        btn_select.clicked.connect(self.accept_selection)
        btn_select.setStyleSheet("""
            QPushButton {
                font-weight: bold; 
                padding: 10px; 
                background-color: #007bff; 
                color: white; 
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #0056b3; }
        """)
        layout.addWidget(btn_select)
        
        self.setLayout(layout)

    def on_item_clicked(self, item, col):
        """Manejador: Genera o carga la imagen cuando se hace clic en un ítem"""
        # Recuperar nombre del residuo desde la data oculta
        res_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not res_name:
            return
        
        # Definir ruta de la imagen esperada
        img_path = os.path.join(self.image_cache_dir, f"{res_name}.png")
        
        # Si la imagen no existe en caché, generarla
        if not os.path.exists(img_path):
            self.lbl_image.setText(f"Generando diagrama para {res_name}...\n(Esto requiere graphviz instalado)")
            self.lbl_image.repaint()
            QApplication.processEvents() # Forzar actualización de UI para que no se congele
            
            # Llamada al modelo generador
            success, result = self.graph_gen.generate_image(self.gro_path, res_name, img_path)
            
            if not success:
                self.lbl_image.setText(f"Error generando imagen:\n{result}")
                return
                
        # Cargar y mostrar la imagen
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            # Escalar si es muy grande para que quepa mejor
            if pixmap.width() > 800:
                pixmap = pixmap.scaledToWidth(800, Qt.TransformationMode.SmoothTransformation)
            self.lbl_image.setPixmap(pixmap)
            self.lbl_image.setText("") # Borrar texto
        else:
            self.lbl_image.setText("Error cargando el archivo de imagen.")

    def accept_selection(self):
        """Valida y acepta la selección para cerrar el diálogo"""
        item = self.tree.currentItem()
        if not item:
            QMessageBox.warning(self, "Aviso", "Por favor, seleccione un elemento del árbol.")
            return
        
        # Guardar el comando (ej "a OW" o "r SOL")
        self.selected_command = item.data(0, Qt.ItemDataRole.UserRole)
        self.accept()


# =============================================================================
# CLASE PRINCIPAL: PESTAÑA DE ANÁLISIS
# =============================================================================
class AnalysisTab(QWidget):
    def __init__(self):
        super().__init__()
        
        # Instancia del parser de análisis
        self.parser = AnalysisParser()
        
        # Referencia al gestor de proyecto (se inyecta después)
        self.project_mgr = None
        
        # Worker para tareas asíncronas
        self.worker = None
        
        # Almacén de datos para la graficación avanzada
        # Diccionario { 'id_unico': {'label': str, 'filepath': str, 'x': np.array, 'y': np.array} }
        self.data_store = {} 
        
        # Inicializar la interfaz gráfica
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # ------------------------------------------------------
        # 1. SELECCIÓN DE SIMULACIÓN (GLOBAL)
        # ------------------------------------------------------
        group_sel = QGroupBox("1. Origen de Datos")
        hbox_sel = QHBoxLayout()
        
        self.combo_sims = QComboBox()
        self.combo_sims.setMinimumWidth(250)
        # Conectar cambio de simulación para actualizar listas
        self.combo_sims.currentIndexChanged.connect(self.on_sim_changed)
        
        hbox_sel.addWidget(QLabel("Simulación Actual:"))
        hbox_sel.addWidget(self.combo_sims)
        
        # Botón para refrescar manualmente
        btn_refresh = QPushButton("🔄 Refrescar Lista")
        btn_refresh.clicked.connect(self.refresh_simulation_list)
        hbox_sel.addWidget(btn_refresh)
        
        hbox_sel.addStretch()
        
        group_sel.setLayout(hbox_sel)
        layout.addWidget(group_sel)
        
        # ------------------------------------------------------
        # 2. PESTAÑAS PRINCIPALES DE FUNCIONALIDAD
        # ------------------------------------------------------
        self.tabs = QTabWidget()
        
        # Tab A: Cálculo Termodinámico
        self.tab_calc_thermo = QWidget()
        self.init_calc_thermo()
        self.tabs.addTab(self.tab_calc_thermo, "A. Termodinámica")
        
        # Tab B: Cálculo Estructural (RDF, PBC)
        self.tab_calc_struct = QWidget()
        self.init_calc_struct()
        self.tabs.addTab(self.tab_calc_struct, "B. Estructura (RDF)")
        
        # Tab C: Visualización Avanzada (Multipanel)
        self.tab_viz = QWidget()
        self.init_viz_advanced()
        self.tabs.addTab(self.tab_viz, "C. Visualización Avanzada")
        
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    # ------------------------------------------------------
    # UI PARTE A: CÁLCULO TERMODINÁMICA
    # ------------------------------------------------------
    def init_calc_thermo(self):
        layout = QVBoxLayout()
        
        lbl_info = QLabel("Extrae propiedades del archivo de energía (.edr) y las añade al graficador.")
        layout.addWidget(lbl_info)
        
        # Botones rápidos para propiedades comunes
        group_props = QGroupBox("Propiedades Comunes")
        hbox_btns = QHBoxLayout()
        
        props = ["Temperature", "Pressure", "Density", "Potential", "Total-Energy"]
        for prop in props:
            btn = QPushButton(prop)
            # Usar lambda para capturar el nombre de la propiedad
            btn.clicked.connect(lambda ch, pr=prop: self.run_energy(pr))
            hbox_btns.addWidget(btn)
        
        group_props.setLayout(hbox_btns)
        layout.addWidget(group_props)
        
        # Etiqueta de estado
        self.lbl_thermo_status = QLabel("Estado: Listo para calcular")
        self.lbl_thermo_status.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.lbl_thermo_status)
        
        layout.addStretch()
        self.tab_calc_thermo.setLayout(layout)

    # ------------------------------------------------------
    # UI PARTE B: CÁLCULO ESTRUCTURA (RDF & PBC)
    # ------------------------------------------------------
    def init_calc_struct(self):
        layout = QVBoxLayout()
        
        # --- SUBSECCIÓN: PBC (CORRECCIÓN DE TRAYECTORIA) ---
        group_pbc = QGroupBox("1. Corrección de Trayectoria (PBC)")
        vbox_pbc = QVBoxLayout()
        hbox_pbc = QHBoxLayout()
        
        # FIX: Usamos Combos en lugar de SpinBoxes para ser más amigables
        self.cb_pbc_center = QComboBox()
        self.cb_pbc_out = QComboBox()
        
        hbox_pbc.addWidget(QLabel("Centrar Grupo:"))
        hbox_pbc.addWidget(self.cb_pbc_center)
        hbox_pbc.addWidget(QLabel("Output Grupo:"))
        hbox_pbc.addWidget(self.cb_pbc_out)
        
        btn_trj = QPushButton("🛠️ Correr trjconv (Centrar)")
        btn_trj.clicked.connect(self.run_trjconv)
        hbox_pbc.addWidget(btn_trj)
        
        vbox_pbc.addLayout(hbox_pbc)
        group_pbc.setLayout(vbox_pbc)
        layout.addWidget(group_pbc)
        
        # --- SUBSECCIÓN: RDF (GROMACS Y TRAVIS) ---
        group_rdf = QGroupBox("2. Función de Distribución Radial (RDF)")
        vbox_rdf = QVBoxLayout()
        
        # Configuración General del Motor
        hbox_cfg = QHBoxLayout()
        self.rb_gmx = QRadioButton("GROMACS")
        self.rb_gmx.setChecked(True)
        self.rb_travis = QRadioButton("TRAVIS")
        
        bg = QButtonGroup(self)
        bg.addButton(self.rb_gmx)
        bg.addButton(self.rb_travis)
        self.rb_gmx.toggled.connect(self.update_rdf_ui)
        
        # Configuración de BIN (Resolución)
        self.sb_bin = QDoubleSpinBox()
        self.sb_bin.setRange(0.001, 1.0)
        self.sb_bin.setSingleStep(0.001)
        self.sb_bin.setValue(0.002)
        self.sb_bin.setDecimals(4)
        self.sb_bin.setSuffix(" nm")
        self.sb_bin.setToolTip("Ancho del bin. Menor valor = Mayor resolución.")
        
        # FIX: Añadido RMAX (Cut-off) solicitado por el usuario
        self.sb_rmax = QDoubleSpinBox()
        self.sb_rmax.setRange(0.1, 50.0)
        self.sb_rmax.setSingleStep(0.1)
        self.sb_rmax.setValue(1.5) # Default 1.5 nm (15 Angstroms)
        self.sb_rmax.setSuffix(" nm")
        self.sb_rmax.setToolTip("Distancia máxima de cálculo (-rmax)")
        
        hbox_cfg.addWidget(QLabel("Motor:"))
        hbox_cfg.addWidget(self.rb_gmx)
        hbox_cfg.addWidget(self.rb_travis)
        hbox_cfg.addSpacing(20)
        hbox_cfg.addWidget(QLabel("Resolución (Bin):"))
        hbox_cfg.addWidget(self.sb_bin)
        hbox_cfg.addWidget(QLabel("Cut-off (Max):"))
        hbox_cfg.addWidget(self.sb_rmax)
        
        vbox_rdf.addLayout(hbox_cfg)
        
        # Stack para inputs variables (GMX vs TRAVIS)
        self.stack_rdf = QStackedWidget()
        
        # --- PÁGINA 1: GROMACS INPUTS ---
        w_gmx = QWidget()
        v_gmx = QVBoxLayout()
        h_gmx_sel = QHBoxLayout()
        
        self.cb_ref = QComboBox()
        self.cb_sel = QComboBox()
        
        h_gmx_sel.addWidget(QLabel("Grupo Referencia:"))
        h_gmx_sel.addWidget(self.cb_ref)
        h_gmx_sel.addWidget(QLabel("Grupo Selección:"))
        h_gmx_sel.addWidget(self.cb_sel)
        
        h_gmx_tools = QHBoxLayout()
        btn_exp = QPushButton("🔍 Explorar Átomos y Crear Grupos")
        btn_exp.clicked.connect(self.open_explorer)
        
        self.chk_com = QCheckBox("Usar Centros de Masa")
        self.chk_com.setToolTip("Calcula RDF entre centros de masa moleculares (-selrpos mol_com)")
        
        h_gmx_tools.addWidget(btn_exp)
        h_gmx_tools.addWidget(self.chk_com)
        
        v_gmx.addLayout(h_gmx_sel)
        v_gmx.addLayout(h_gmx_tools)
        w_gmx.setLayout(v_gmx)
        self.stack_rdf.addWidget(w_gmx)
        
        # --- PÁGINA 2: TRAVIS INPUTS ---
        w_travis = QWidget()
        h_travis = QHBoxLayout()
        self.txt_m1 = QLineEdit()
        self.txt_m1.setPlaceholderText("Nombre Mol 1 (ej. CBD)")
        
        self.txt_m2 = QLineEdit()
        self.txt_m2.setPlaceholderText("Nombre Mol 2 (ej. SOL)")
        
        h_travis.addWidget(QLabel("Molécula 1:"))
        h_travis.addWidget(self.txt_m1)
        h_travis.addWidget(QLabel("Molécula 2:"))
        h_travis.addWidget(self.txt_m2)
        
        w_travis.setLayout(h_travis)
        self.stack_rdf.addWidget(w_travis)
        
        vbox_rdf.addWidget(self.stack_rdf)
        
        # Botón Calcular Principal
        btn_calc_rdf = QPushButton("📊 Calcular y Añadir a Gráficas")
        btn_calc_rdf.clicked.connect(self.run_rdf)
        btn_calc_rdf.setStyleSheet("font-weight: bold; color: green; padding: 8px; font-size: 13px;")
        vbox_rdf.addWidget(btn_calc_rdf)
        
        group_rdf.setLayout(vbox_rdf)
        layout.addWidget(group_rdf)
        
        layout.addStretch()
        self.tab_calc_struct.setLayout(layout)

    # ------------------------------------------------------
    # UI PARTE C: VISUALIZACIÓN AVANZADA (MULTIPANEL)
    # ------------------------------------------------------
    def init_viz_advanced(self):
        layout = QVBoxLayout()
        
        # 1. Configuración de la Figura
        group_cfg = QGroupBox("Configuración de Figura")
        hbox_cfg = QHBoxLayout()
        
        self.combo_layout = QComboBox()
        self.combo_layout.addItems(["1 Gráfico (Simple)", "2 Gráficos (1x2)", "4 Gráficos (2x2)"])
        self.combo_layout.currentIndexChanged.connect(self.update_plot_layout)
        
        self.sb_fontsize = QSpinBox()
        self.sb_fontsize.setRange(8, 30)
        self.sb_fontsize.setValue(12)
        
        self.sb_linewidth = QDoubleSpinBox()
        self.sb_linewidth.setRange(0.5, 5.0)
        self.sb_linewidth.setValue(1.5)
        
        btn_update_plot = QPushButton("🔄 Actualizar Gráfico")
        btn_update_plot.clicked.connect(self.update_plot_layout)
        
        btn_export = QPushButton("💾 Guardar Imagen")
        btn_export.clicked.connect(self.export_plot)
        
        hbox_cfg.addWidget(QLabel("Disposición:"))
        hbox_cfg.addWidget(self.combo_layout)
        hbox_cfg.addWidget(QLabel("Tamaño Fuente:"))
        hbox_cfg.addWidget(self.sb_fontsize)
        hbox_cfg.addWidget(QLabel("Grosor Línea:"))
        hbox_cfg.addWidget(self.sb_linewidth)
        hbox_cfg.addWidget(btn_update_plot)
        hbox_cfg.addWidget(btn_export)
        
        group_cfg.setLayout(hbox_cfg)
        layout.addWidget(group_cfg)
        
        # 2. Matriz de Asignación (Tabla)
        self.table_map = QTableWidget()
        self.table_map.setColumnCount(5)
        self.table_map.setHorizontalHeaderLabels(["Serie de Datos (Editable)", "Plot 1", "Plot 2", "Plot 3", "Plot 4"])
        self.table_map.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_map.setMaximumHeight(200)
        
        # Conectar cambio para redibujado automático y renombrado
        self.table_map.itemChanged.connect(self.on_table_item_changed)
        
        layout.addWidget(self.table_map)
        
        # Botón Eliminar
        btn_del_data = QPushButton("🗑️ Eliminar Serie Seleccionada")
        btn_del_data.setStyleSheet("color: red;")
        btn_del_data.clicked.connect(self.remove_data_series)
        layout.addWidget(btn_del_data)
        
        # 3. Canvas Matplotlib
        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        self.tab_viz.setLayout(layout)

    # ==========================================================
    # GESTIÓN DE DATOS (DATA STORE)
    # ==========================================================
    
    def add_data_to_store(self, label, x, y, filepath):
        """Guarda un set de datos calculado y lo añade a la tabla de visualización"""
        # Crear ID único
        data_id = f"{len(self.data_store)}_{label}"
        
        # Guardar en memoria (IMPORTANTE: Guardar filepath para persistencia)
        self.data_store[data_id] = {
            'label': label,
            'x': x,
            'y': y,
            'filepath': filepath 
        }
        
        # Añadir fila a la tabla (bloqueando señales para evitar redraw prematuro)
        self.table_map.blockSignals(True)
        row = self.table_map.rowCount()
        self.table_map.insertRow(row)
        
        # Nombre (Editable)
        item_name = QTableWidgetItem(label)
        # Guardamos el ID en el item para recuperarlo luego
        item_name.setData(Qt.ItemDataRole.UserRole, data_id)
        # Hacerlo editable
        item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table_map.setItem(row, 0, item_name)
        
        # Checkboxes (Columnas 1-4)
        for col in range(1, 5):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            
            # Por defecto, marcar en Plot 1
            if col == 1:
                chk.setCheckState(Qt.CheckState.Checked)
                
            self.table_map.setItem(row, col, chk)
            
        self.table_map.blockSignals(False)
        
        # Cambiar automáticamente a la pestaña de visualización y dibujar
        self.tabs.setCurrentIndex(2)
        self.update_plot_layout()

    def update_project_data(self, mgr):
        """Actualiza la referencia al proyecto y recarga lista de simulaciones"""
        self.project_mgr = mgr
        if not mgr or not mgr.current_project_path:
            return
            
        # Recargar lista
        self.refresh_simulation_list()

    def refresh_simulation_list(self):
        """Escanea el directorio del sistema activo en busca de archivos .tpr"""
        d = self.get_storage_path()
        if not d:
            return
            
        self.combo_sims.blockSignals(True)
        self.combo_sims.clear()
        
        if os.path.exists(d):
            files = os.listdir(d)
            # Listar archivos TPR (definen una simulación válida)
            tpr_files = [f for f in sorted(files) if f.endswith(".tpr")]
            
            if not tpr_files:
                self.combo_sims.addItem("No hay simulaciones (.tpr) encontradas")
                self.combo_sims.setEnabled(False)
            else:
                self.combo_sims.setEnabled(True)
                for f in tpr_files:
                    # Añadir nombre sin extensión
                    self.combo_sims.addItem(os.path.splitext(f)[0])
                    
        self.combo_sims.blockSignals(False)
        
        # Cargar grupos iniciales si hay simulaciones
        if self.combo_sims.isEnabled() and self.combo_sims.count() > 0:
            self.load_gmx_groups()

    def get_storage_path(self):
        """Obtiene la ruta del sistema activo"""
        if self.project_mgr:
            return self.project_mgr.get_active_system_path()
        return None

    def on_sim_changed(self):
        """Callback al cambiar simulación en el combo"""
        if self.rb_gmx.isChecked():
            self.load_gmx_groups()

    def update_rdf_ui(self):
        """Cambia la interfaz según el motor seleccionado"""
        if self.rb_gmx.isChecked():
            self.stack_rdf.setCurrentIndex(0)
            self.load_gmx_groups()
        else:
            self.stack_rdf.setCurrentIndex(1)

    def load_gmx_groups(self):
        """Carga los grupos del index.ndx en los combos (Para RDF y PBC)"""
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not d or not self.combo_sims.isEnabled():
            return
        
        # Ruta al TPR
        tpr_path = os.path.join(d, f"{sim}.tpr")
        if not os.path.exists(tpr_path):
            return

        # Llamar al parser para obtener grupos
        grps = self.parser.get_gromacs_groups(tpr_path, d)
        
        # Limpiar combos
        self.cb_ref.clear()
        self.cb_sel.clear()
        self.cb_pbc_center.clear()
        self.cb_pbc_out.clear()
        
        for n, i in grps.items():
            txt = f"{n} ({i})"
            # RDF Combos
            self.cb_ref.addItem(txt, i)
            self.cb_sel.addItem(txt, i)
            # PBC Combos
            self.cb_pbc_center.addItem(txt, i)
            self.cb_pbc_out.addItem(txt, i)

    def set_busy(self, busy):
        """Bloquea la interfaz mientras procesa"""
        self.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # ==========================================================
    # EJECUCIÓN DE CÁLCULOS
    # ==========================================================

    # --- 1. ENERGÍA ---
    def run_energy(self, prop):
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not d or not self.combo_sims.isEnabled():
            QMessageBox.warning(self, "Aviso", "Seleccione una simulación válida.")
            return
            
        edr = os.path.join(d, f"{sim}.edr")
        out = os.path.join(d, f"{sim}_{prop}.xvg")
        
        self.set_busy(True)
        self.lbl_thermo_status.setText(f"Calculando {prop}...")
        
        # Worker
        self.worker = AnalysisWorker(self.parser.run_gmx_energy, edr, out, [prop])
        self.worker.finished_signal.connect(lambda s, m: self.finish_calc(s, m, out, f"{prop} ({sim})"))
        self.worker.start()

    # --- 2. TRJCONV ---
    def run_trjconv(self):
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not d or not self.combo_sims.isEnabled():
            return
            
        tpr = os.path.join(d, f"{sim}.tpr")
        xtc = os.path.join(d, f"{sim}.xtc")
        out = os.path.join(d, f"{sim}_clean.xtc")
        
        if not os.path.exists(xtc):
            QMessageBox.warning(self, "Error", "No existe archivo de trayectoria (.xtc)")
            return
        
        # Obtener IDs de los combos PBC
        center_id = self.cb_pbc_center.currentData()
        out_id = self.cb_pbc_out.currentData()
        
        if center_id is None or out_id is None:
            QMessageBox.warning(self, "Aviso", "Grupos no cargados. Seleccione una simulación válida.")
            return
        
        self.set_busy(True)
        self.worker = AnalysisWorker(
            self.parser.run_trjconv, tpr, xtc, out, 
            center_id, out_id
        )
        self.worker.finished_signal.connect(lambda s, m: (self.set_busy(False), QMessageBox.information(self, "OK", "Trayectoria corregida.") if s else QMessageBox.critical(self, "Error", m)))
        self.worker.start()

    # --- 3. RDF ---
    def run_rdf(self):
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not d or not self.combo_sims.isEnabled():
            return
            
        tpr = os.path.join(d, f"{sim}.tpr")
        
        # Preferir trayectoria limpia
        xtc = os.path.join(d, f"{sim}_clean.xtc")
        if not os.path.exists(xtc):
            xtc = os.path.join(d, f"{sim}.xtc")
        
        self.set_busy(True)
        
        if self.rb_gmx.isChecked():
            # GROMACS
            out = os.path.join(d, f"{sim}_rdf_gmx.xvg")
            ref = self.cb_ref.currentData()
            sel = self.cb_sel.currentData()
            
            if ref is None: 
                self.set_busy(False)
                return
            
            # Pasar parámetros extendidos (Bin, Cutoff)
            self.worker = AnalysisWorker(
                self.parser.run_gmx_rdf, tpr, xtc, out, ref, sel, d, 
                self.chk_com.isChecked(), self.sb_bin.value(), self.sb_rmax.value()
            )
            
            label_base = f"RDF {self.cb_ref.currentText().split('(')[0]}-{self.cb_sel.currentText().split('(')[0]}"
            
        else:
            # TRAVIS
            out = os.path.join(d, f"{sim}_rdf_travis.csv")
            st = os.path.join(d, "system.gro")
            
            self.worker = AnalysisWorker(
                self.parser.run_travis_rdf, st, xtc, out, 
                self.tx_m1.text(), self.tx_m2.text()
            )
            label_base = f"RDF {self.tx_m1.text()}-{self.tx_m2.text()}"
        
        full_label = f"{label_base} ({sim})"
        self.worker.finished_signal.connect(lambda s, m: self.finish_calc(s, m, out, full_label))
        self.worker.start()

    def finish_calc(self, success, msg, out_file, label):
        """Callback genérico al terminar un cálculo"""
        self.set_busy(False)
        self.lbl_thermo_status.setText(f"Última acción: {label} - {'OK' if success else 'Error'}")
        
        if not success:
            QMessageBox.critical(self, "Error", msg)
            return
        
        # Leer datos y añadir a Store (guardando el filepath para persistencia)
        lbl, x, y_list = self.parser.get_data_from_file(out_file)
        
        if y_list:
            self.add_data_to_store(label, x, y_list[0], out_file)
        else:
            QMessageBox.warning(self, "Aviso", "El archivo de salida está vacío o tiene formato incorrecto.")

    def open_explorer(self):
        """Abre el diálogo de exploración de átomos"""
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not d: return
            
        gro = os.path.join(d, "system.gro")
        if not os.path.exists(gro):
            QMessageBox.warning(self, "Error", "Falta system.gro para leer estructura.")
            return
        
        struct = self.parser.scan_structure_atoms(gro)
        dlg = AtomSelectionDialog(struct, gro, self)
        
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_command:
            tpr = os.path.join(d, f"{sim}.tpr")
            
            self.set_busy(True)
            self.worker = AnalysisWorker(
                self.parser.add_custom_group, tpr, d, dlg.selected_command
            )
            
            # Al terminar, recargar los grupos del combobox
            self.worker.finished_signal.connect(
                lambda s, m: (self.set_busy(False), self.load_gmx_groups() if s else QMessageBox.critical(self, "Error", m))
            )
            self.worker.start()

    # ==========================================================
    # LÓGICA DE GRAFICACIÓN AVANZADA
    # ==========================================================
    def on_table_item_changed(self, item):
        """Callback cuando cambia un nombre o un checkbox"""
        # Si cambió la columna 0 (Nombre)
        if item.column() == 0:
            new_label = item.text()
            data_id = item.data(Qt.ItemDataRole.UserRole)
            if data_id and data_id in self.data_store:
                self.data_store[data_id]['label'] = new_label
        
        # Redibujar siempre que cambie algo
        self.update_plot_layout()
    
    def remove_data_series(self):
        """Elimina la fila seleccionada y libera memoria"""
        row = self.table_map.currentRow()
        if row >= 0:
            item = self.table_map.item(row, 0)
            did = item.data(Qt.ItemDataRole.UserRole)
            if did in self.data_store:
                del self.data_store[did]
            
            self.table_map.removeRow(row)
            self.update_plot_layout()

    def update_plot_layout(self):
        """Redibuja los gráficos según la configuración de la tabla"""
        self.figure.clear()
        
        # Configurar estilo global
        font_size = self.sb_fontsize.value()
        line_width = self.sb_linewidth.value()
        plt.rcParams.update({'font.size': font_size, 'lines.linewidth': line_width})
        
        layout_mode = self.combo_layout.currentIndex() # 0=1x1, 1=1x2, 2=2x2
        axes = []
        
        # Crear subplots según layout
        if layout_mode == 0:
            axes.append(self.figure.add_subplot(111))
        elif layout_mode == 1:
            axes.append(self.figure.add_subplot(121))
            axes.append(self.figure.add_subplot(122))
        elif layout_mode == 2:
            axes.append(self.figure.add_subplot(221))
            axes.append(self.figure.add_subplot(222))
            axes.append(self.figure.add_subplot(223))
            axes.append(self.figure.add_subplot(224))
            
        # Recorrer la tabla para ver qué dato va en qué plot
        row_count = self.table_map.rowCount()
        
        for r in range(row_count):
            # Recuperar ID del dato
            item_name = self.table_map.item(r, 0)
            data_id = item_name.data(Qt.ItemDataRole.UserRole)
            
            data = self.data_store.get(data_id)
            if not data:
                continue
            
            # Revisar columnas de checkboxes (Col 1 a 4)
            for c in range(1, 5):
                # Si el gráfico no existe en este layout, saltar
                plot_idx = c - 1
                if plot_idx >= len(axes):
                    break
                
                item_chk = self.table_map.item(r, c)
                if item_chk.checkState() == Qt.CheckState.Checked:
                    ax = axes[plot_idx]
                    ax.plot(data['x'], data['y'], label=data['label'])
                    
        # Decorar ejes
        for i, ax in enumerate(axes):
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.legend(fontsize=font_size-2)
            ax.set_title(f"Gráfico {i+1}", fontweight='bold')
            
            # Etiquetas genéricas (mejorable si guardamos metadatos de unidades)
            if i >= len(axes)-2:
                ax.set_xlabel("Eje X")
            ax.set_ylabel("Eje Y")

        self.figure.tight_layout()
        self.canvas.draw()
        
        # Auto-guardado
        self.auto_save_plot()

    def auto_save_plot(self):
        """Guarda imagen temporal"""
        if self.project_mgr and self.project_mgr.current_project_path:
            save_dir = os.path.join(self.project_mgr.current_project_path, "analysis", "autosave")
            os.makedirs(save_dir, exist_ok=True)
            try:
                self.figure.savefig(os.path.join(save_dir, "current_analysis.png"))
            except: pass

    def export_plot(self):
        """Guarda la imagen manualmente"""
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Imagen", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            try:
                self.figure.savefig(path, dpi=300)
                QMessageBox.information(self, "OK", f"Imagen guardada en:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ==========================================================
    # PERSISTENCIA (GUARDAR Y CARGAR ESTADO) - CRÍTICO
    # ==========================================================

    def get_state(self):
        """
        Retorna el estado actual de la pestaña.
        Guardamos la LISTA DE ARCHIVOS cargados (no los datos crudos).
        """
        loaded_files = []
        # Recorrer data_store (pero buscando el orden en la tabla)
        # Es mejor recorrer la tabla para guardar el orden y estado de checks
        
        for r in range(self.table_map.rowCount()):
            item_name = self.table_map.item(r, 0)
            data_id = item_name.data(Qt.ItemDataRole.UserRole)
            data = self.data_store.get(data_id)
            
            if data and data.get('filepath'):
                checks = []
                for c in range(1, 5):
                    checks.append(self.table_map.item(r, c).checkState() == Qt.CheckState.Checked)
                
                loaded_files.append({
                    'filepath': data['filepath'],
                    'label': data['label'], # El nombre que el usuario editó
                    'checks': checks
                })
        
        return {
            "layout_mode": self.combo_layout.currentIndex(),
            "loaded_files": loaded_files
        }

    def set_state(self, state):
        """Restaura el estado"""
        if not state:
            return
        
        # 1. Limpiar todo primero
        self.data_store = {}
        self.table_map.setRowCount(0)
        self.figure.clear()
        
        # 2. Restaurar Layout
        self.combo_layout.setCurrentIndex(state.get("layout_mode", 0))
        
        # 3. Recargar archivos y configuraciones
        files = state.get("loaded_files", [])
        
        for f_info in files:
            path = f_info.get('filepath')
            label = f_info.get('label')
            checks = f_info.get('checks', [])
            
            # Solo cargar si el archivo existe
            if path and os.path.exists(path):
                # Re-leer datos del disco
                lbl, x, y_list = self.parser.get_data_from_file(path)
                
                if y_list:
                    # Añadir a la store y tabla
                    self.add_data_to_store(label, x, y_list[0], path)
                    
                    # Restaurar checkboxes de esa fila (la última agregada)
                    row = self.table_map.rowCount() - 1
                    for i, is_checked in enumerate(checks):
                        col = i + 1
                        if col < 5:
                            self.table_map.item(row, col).setCheckState(
                                Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked
                            )
        
        # Actualizar gráfica final
        self.update_plot_layout()