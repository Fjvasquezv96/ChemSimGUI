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
    QProgressDialog,
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


class FixGroupsDialog(QDialog):
    """
    Diálogo para forzar regeneración del index.ndx si está corrupto o desactualizado.
    Pide N1 y N2 al usuario.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regenerar Index (Reparar Grupos)")
        self.setFixedWidth(350)
        self.n1 = 0
        self.n2 = 0
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("⚠️ Use esto para reparar grupos Soluto/Solvente\nsi las gráficas RDF caen a 0 incorrectamente."))
        layout.addWidget(QLabel("Ingrese la cantidad exacta de moléculas:"))
        
        form = QFormLayout()
        self.sb_n1 = QSpinBox()
        self.sb_n1.setRange(1, 999999)
        self.sb_n2 = QSpinBox()
        self.sb_n2.setRange(1, 999999)
        
        form.addRow("Moléculas Soluto (N1):", self.sb_n1)
        form.addRow("Moléculas Solvente (N2):", self.sb_n2)
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        btn_ok = QPushButton("Regenerar index.ndx")
        btn_ok.clicked.connect(self.accept_data)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)
        
        self.setLayout(layout)
        
    def accept_data(self):
        self.n1 = self.sb_n1.value()
        self.n2 = self.sb_n2.value()
        self.accept()

# =============================================================================
# WORKER DEDICADO PARA PROCESAMIENTO POR LOTES (TRAYECTORIAS)
# =============================================================================
class BatchTrajectoryWorker(QThread):
    progress_signal = pyqtSignal(str, int) # Mensaje, Porcentaje
    finished_signal = pyqtSignal(int, list) # Success count, Lista de errores
    
    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self.is_running = True
        
    def stop(self):
        self.is_running = False
        
    def run(self):
        parser = AnalysisParser()
        errors = []
        success_count = 0
        total = len(self.tasks)
        
        for i, t in enumerate(self.tasks):
            if not self.is_running: break
            
            sys_name = t['sys_name']
            base_name = os.path.basename(t['out_path'])
            pct = int((i / total) * 100)
            
            self.progress_signal.emit(f"Procesando {sys_name}...\n>> {base_name}\n(Esto puede tardar dependiendo del tamaño)", pct)
            
            # Asegurar directorio
            try:
                os.makedirs(t['travis_dir'], exist_ok=True)
                
                # LLAMADA BLOQUEANTE A GROMACS
                ok, msg = parser.generate_pdb_trajectory(t['xtc'], t['tpr'], t['out_path'], "nojump")
                
                if ok:
                    success_count += 1
                else:
                    errors.append(f"{sys_name}: {msg}")
                    
            except Exception as e:
                errors.append(f"{sys_name}: Error inesperado {str(e)}")
        
        self.finished_signal.emit(success_count, errors)


class TrajectoryManagerDialog(QDialog):
    def __init__(self, project_mgr, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestor de Trayectorias GMX/Travis")
        self.resize(600, 400)
        self.project_mgr = project_mgr
        self.storage_path = None
        if self.project_mgr and self.project_mgr.current_project_path:
             self.storage_path = os.path.join(self.project_mgr.current_project_path, "storage")
        
        self.layout = QVBoxLayout()
        self.init_ui()
        self.setLayout(self.layout)
        self.scan_systems()

    def init_ui(self):
        lbl = QLabel("Este gestor permite pre-generar los archivos PDB/GRO 'unwrapped' que necesita Travis.\n"
                     "Esto evita regenerarlos cada vez y permite verificar que están correctos.")
        lbl.setWordWrap(True)
        self.layout.addWidget(lbl)
        
        # --- FILTROS Y HERRAMIENTAS DE SELECCIÓN ---
        hbox_filter = QHBoxLayout()
        
        self.chk_prod_only = QCheckBox("Mostrar solo 'prod...'")
        self.chk_prod_only.setToolTip("Si se marca, solo se mostrarán los archivos XTC que comiencen con 'prod'")
        self.chk_prod_only.setChecked(True)
        self.chk_prod_only.toggled.connect(self.scan_systems)
        hbox_filter.addWidget(self.chk_prod_only)
        
        hbox_filter.addSpacing(20)
        
        btn_all = QPushButton("Seleccionar Todo")
        btn_all.clicked.connect(self.select_all)
        hbox_filter.addWidget(btn_all)
        
        btn_sys = QPushButton("Seleccionar Sistema Actual")
        btn_sys.setToolTip("Marca todas las simulaciones que pertenezcan al mismo sistema de la fila seleccionada")
        btn_sys.clicked.connect(self.select_current_system)
        hbox_filter.addWidget(btn_sys)
        
        hbox_filter.addStretch()
        self.layout.addLayout(hbox_filter)
        # -------------------------------------------
        
        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Simulación (Sistema)", "XTC Original", "Estado Optimizado (GRO)", "Acción"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.layout.addWidget(self.table)
        
        # Botones de Acción Global
        hbox = QHBoxLayout()
        btn_scan = QPushButton("🔄 Re-Escanear")
        btn_scan.clicked.connect(self.scan_systems)
        hbox.addWidget(btn_scan)
        
        btn_process = QPushButton("⚙️ Procesar Seleccionados")
        btn_process.setStyleSheet("background-color: #007bff; color: white; font-weight: bold;")
        btn_process.clicked.connect(self.process_selected)
        hbox.addWidget(btn_process)
        
        self.layout.addLayout(hbox)

    def select_all(self):
        """Selecciona todos los items habilitados en la tabla"""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 3) # Columna checkboxes
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(Qt.CheckState.Checked)

    def select_current_system(self):
        """Selecciona todos los items del mismo sistema que el seleccionado actualmente"""
        cur = self.table.currentRow()
        if cur < 0:
            QMessageBox.information(self, "Aviso", "Seleccione primero una fila de referencia.")
            return
            
        # Obtenemos el nombre del sistema de la fila actual
        data = self.table.item(cur, 0).data(Qt.ItemDataRole.UserRole)
        target_sys = data.get('sys_name')
        
        for r in range(self.table.rowCount()):
            item_data = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if item_data.get('sys_name') == target_sys:
                chk_item = self.table.item(r, 3)
                if chk_item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    chk_item.setCheckState(Qt.CheckState.Checked)

    def scan_systems(self):
        self.table.setRowCount(0)
        if not self.storage_path or not os.path.exists(self.storage_path):
            return

        systems = sorted([d for d in os.listdir(self.storage_path) if os.path.isdir(os.path.join(self.storage_path, d))])
        
        # Filtro de nombre activado?
        filter_prod = self.chk_prod_only.isChecked()
        
        for sys_name in systems:
            sys_dir = os.path.join(self.storage_path, sys_name)
            
            # Buscar TODOS los archivos XTC en el directorio del sistema
            if not os.path.exists(sys_dir): continue
            
            xtc_files = [f for f in os.listdir(sys_dir) if f.endswith(".xtc")]
            
            if not xtc_files:
                continue

            for f_xtc in xtc_files:
                base_name = os.path.splitext(f_xtc)[0]
                
                # APLICAR FILTRO SI CORRESPONDE
                if filter_prod and not base_name.startswith("prod"):
                    continue
                
                xtc_path = os.path.join(sys_dir, f_xtc)
                
                # Buscamos tpr con el mismo nombre base (ej: prod.xtc -> prod.tpr)
                # O si no existe, quizas sys_name.tpr como fallback?
                tpr_path = os.path.join(sys_dir, f"{base_name}.tpr")
                if not os.path.exists(tpr_path):
                    # Fallback comun: nombre_del_sistema.tpr
                    tpr_path = os.path.join(sys_dir, f"{sys_name}.tpr")
                
                # Buscar carpeta travis
                travis_dir = os.path.join(sys_dir, "travis_work")
                
                # Nombre de salida esperado
                # Usamos el nombre del xtc para hacerlo único
                out_name = f"traj_unwrapped_{base_name}.gro"
                out_full = os.path.join(travis_dir, out_name)
                
                status_opt = "No generado"
                color_opt = "red"
                
                if os.path.exists(out_full):
                    size_mb = os.path.getsize(out_full) / (1024*1024)
                    status_opt = f"✅ Listo ({size_mb:.1f} MB)"
                    color_opt = "green"
                
                # Row
                r = self.table.rowCount()
                self.table.insertRow(r)
                
                # Col 0: Sistema > Simulacion
                label_sys = f"{sys_name} / {base_name}"
                item_sys = QTableWidgetItem(label_sys)
                self.table.setItem(r, 0, item_sys)
                
                # Col 1: Estado XTC/TPR
                status_xtc = "✅ OK" if os.path.exists(xtc_path) and os.path.exists(tpr_path) else "❌ Falta TPR"
                if not os.path.exists(xtc_path): status_xtc = "❌ Falta XTC"
                
                self.table.setItem(r, 1, QTableWidgetItem(status_xtc))
                
                # Col 2: Estado output
                item_stat = QTableWidgetItem(status_opt)
                item_stat.setForeground(QColor(color_opt))
                self.table.setItem(r, 2, item_stat)
                
                # Col 3: Checkbox
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Unchecked)
                if "OK" in status_xtc:
                     chk.setText("Generar")
                else:
                     chk.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(r, 3, chk)
                
                # Data
                item_sys.setData(Qt.ItemDataRole.UserRole, {
                    'sys_name': sys_name,
                    'xtc': xtc_path,
                    'tpr': tpr_path,
                    'travis_dir': travis_dir,
                    'out_path': out_full
                })

    def process_selected(self):
        tasks = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 3).checkState() == Qt.CheckState.Checked:
                data = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                tasks.append(data)
        
        if not tasks:
            QMessageBox.information(self, "Info", "Seleccione al menos una simulación.")
            return

        # Configurar diálogo de progreso modal
        self.progress_dlg = QProgressDialog("Iniciando...", "Cancelar", 0, 100, self)
        self.progress_dlg.setWindowTitle("Procesando Trayectorias")
        self.progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dlg.setMinimumDuration(0) # Aparecer inmediatamente
        self.progress_dlg.setValue(0)
        
        # Crear e iniciar Worker
        self.worker = BatchTrajectoryWorker(tasks)
        self.worker.progress_signal.connect(self.on_worker_progress)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.progress_dlg.canceled.connect(self.worker.stop)
        
        self.worker.start()

    def on_worker_progress(self, msg, pct):
        if self.progress_dlg:
            self.progress_dlg.setLabelText(msg)
            self.progress_dlg.setValue(pct)

    def on_worker_finished(self, success_count, errors):
        if self.progress_dlg:
            self.progress_dlg.setValue(100)
            self.progress_dlg.close()
            
        res_msg = f"Proceso finalizado.\nCompletados: {success_count}"
        if errors:
            res_msg += "\n\nSe encontraron errores:\n" + "\n".join(errors[:10])
            if len(errors) > 10: res_msg += "\n... (y más)"
        
        QMessageBox.information(self, "Fin del Proceso", res_msg)
        self.scan_systems()
        self.worker = None


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
        
        # COLA DE EJECUCIÓN
        self.queue_data = [] # Lista de diccionarios de tareas
        
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
    
    # METODO NUEVO
    def open_traj_manager(self):
        """Abre el diálogo de gestión de trayectorias"""
        dlg = TrajectoryManagerDialog(self.project_mgr, self)
        dlg.exec()

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

        btn_traj_mgr = QPushButton("📂 Gestor Travis (Pre-Process)")
        btn_traj_mgr.setToolTip("Abrir gestor para generar trayectorias PDB/GRO 'nojump' para Travis")
        btn_traj_mgr.clicked.connect(self.open_traj_manager)
        hbox_pbc.addWidget(btn_traj_mgr)
        
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
        
        # FIX: Botón Reparar Grupos
        btn_fix = QPushButton("🛠️ Reparar/Regenerar Grupos (Index)")
        btn_fix.clicked.connect(self.open_fix_groups_dialog)
        btn_fix.setStyleSheet("color: #d9534f; font-weight: bold;")
        
        self.chk_com = QCheckBox("Usar Centros de Masa")
        self.chk_com.setToolTip("Calcula RDF entre centros de masa moleculares (-selrpos mol_com)")
        
        h_gmx_tools.addWidget(btn_exp)
        h_gmx_tools.addWidget(btn_fix)
        h_gmx_tools.addWidget(self.chk_com)
        
        # Checkbox para ignorar trayectoria limpia (útil si trjconv falló)
        self.chk_force_raw = QCheckBox("Forzar XTC Original")
        self.chk_force_raw.setToolTip("Si se marca, usa el archivo .xtc original en lugar de buscar _clean.xtc")
        h_gmx_tools.addWidget(self.chk_force_raw)
        
        v_gmx.addLayout(h_gmx_sel)
        v_gmx.addLayout(h_gmx_tools)
        w_gmx.setLayout(v_gmx)
        self.stack_rdf.addWidget(w_gmx)
        
        # --- PÁGINA 2: TRAVIS INPUTS ---
        w_travis = QWidget()
        h_travis = QHBoxLayout()
        
        self.cb_travis_m1 = QComboBox()
        self.cb_travis_m2 = QComboBox()
        
        h_travis.addWidget(QLabel("Molécula 1:"))
        h_travis.addWidget(self.cb_travis_m1)
        h_travis.addWidget(QLabel("Molécula 2:"))
        h_travis.addWidget(self.cb_travis_m2)
        
        w_travis.setLayout(h_travis)
        self.stack_rdf.addWidget(w_travis)
        
        vbox_rdf.addWidget(self.stack_rdf)
        
        # Botones de Acción
        hbox_actions = QHBoxLayout()
        
        btn_run_now = QPushButton("▶️ Ejecutar Ahora")
        btn_run_now.clicked.connect(self.run_rdf)
        btn_run_now.setStyleSheet("font-weight: bold; color: #28a745; padding: 8px; font-size: 13px;")
        
        btn_add_queue = QPushButton("➕ Añadir a Cola")
        btn_add_queue.clicked.connect(self.add_rdf_to_queue) 
        btn_add_queue.setStyleSheet("font-weight: bold; color: #0056b3; padding: 8px; font-size: 13px;")
        
        hbox_actions.addWidget(btn_run_now)
        hbox_actions.addWidget(btn_add_queue)
        
        vbox_rdf.addLayout(hbox_actions)
        
        group_rdf.setLayout(vbox_rdf)
        layout.addWidget(group_rdf)
        
        # --- SECCIÓN DE COLA (NUEVO) ---
        group_queue = QGroupBox("Cola de Procesamiento (Lotes)")
        group_queue.setCheckable(True)
        group_queue.setChecked(True)
        vbox_queue = QVBoxLayout()
        
        self.table_queue = QTableWidget()
        self.table_queue.setColumnCount(4)
        self.table_queue.setHorizontalHeaderLabels(["Simulación", "Tipo", "Detalle", "Estado"])
        self.table_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_queue.setMaximumHeight(180)
        vbox_queue.addWidget(self.table_queue)
        
        hbox_q_actions = QHBoxLayout()
        btn_clear_q = QPushButton("Limpiar Cola")
        btn_clear_q.clicked.connect(self.clear_queue)
        
        btn_run_q = QPushButton("🚀 Ejecutar Cola (Optimizado)")
        btn_run_q.setToolTip("Agrupa cálculos compatibles para minimizar lecturas de disco.")
        btn_run_q.clicked.connect(self.run_queue_optimized)
        btn_run_q.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 6px;")
        
        hbox_q_actions.addWidget(btn_clear_q)
        hbox_q_actions.addWidget(btn_run_q)
        vbox_queue.addLayout(hbox_q_actions)
        
        group_queue.setLayout(vbox_queue)
        layout.addWidget(group_queue)
        
        layout.addStretch()
        self.tab_calc_struct.setLayout(layout)

    def open_traj_manager(self):
        """Abre el diálogo de gestión de trayectorias"""
        dlg = TrajectoryManagerDialog(self.project_mgr, self)
        dlg.exec()

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
        elif self.rb_travis.isChecked():
            self.load_travis_molecules()

    def update_rdf_ui(self):
        """Cambia la interfaz según el motor seleccionado"""
        if self.rb_gmx.isChecked():
            self.stack_rdf.setCurrentIndex(0)
            self.load_gmx_groups()
        else:
            self.stack_rdf.setCurrentIndex(1)
            self.load_travis_molecules()

    def load_travis_molecules(self):
        """Carga las moléculas detectadas en el .gro para Travis"""
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        if not sim or not d: return
        
        self.cb_travis_m1.clear()
        self.cb_travis_m2.clear()

        # Intentar leer desde el gro de la simulación o system.gro
        gro_file = os.path.join(d, f"{sim}.gro")
        if not os.path.exists(gro_file):
            gro_file = os.path.join(d, "system.gro")
            
        mols = self.parser.get_structure_molecules(gro_file)
        
        if not mols:
            self.cb_travis_m1.addItem("No detectadas", 1)
            self.cb_travis_m2.addItem("No detectadas", 2)
            return

        for i, m in enumerate(mols):
            # Travis ID = index + 1
            txt = f"{m} (ID: {i+1})"
            self.cb_travis_m1.addItem(txt, i+1)
            self.cb_travis_m2.addItem(txt, i+1)
            
        # Selección por defecto inteligente
        if len(mols) > 0: self.cb_travis_m1.setCurrentIndex(0)
        if len(mols) > 1: self.cb_travis_m2.setCurrentIndex(1)
        else: self.cb_travis_m2.setCurrentIndex(0)

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
        # NO deshabilitar todo el widget porque congela la UI visualmente
        # Solo deshabilitar inputs críticos y poner cursor de espera
        self.btn_run_q = self.findChild(QPushButton, "btn_run_q") # Buscar dinamicamente si no esta en scope
        
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            if hasattr(self, 'group_queue'): self.group_queue.setEnabled(False) # Si existe
            # Si no encontramos el group_queue, deshabilitar la tabla
            self.table_queue.setEnabled(False)
        else:
            QApplication.restoreOverrideCursor()
            if hasattr(self, 'group_queue'): self.group_queue.setEnabled(True)
            self.table_queue.setEnabled(True)

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

        # Advertencia si el output no es todo el sistema
        # Suponemos que si el nombre no contiene "System", puede ser peligroso para RDF posterior
        out_text = self.cb_pbc_out.currentText()
        if "System" not in out_text and out_id != 0:
            resp = QMessageBox.question(
                self, "Advertencia de Compatibilidad",
                f"Ha seleccionado '{out_text}' como grupo de salida.\n"
                "Esto generará una trayectoria reducida (menos átomos).\n"
                "Si luego ejecuta RDF usando el TPR original (sistema completo), GROMACS fallará por 'Atom mismatch'.\n\n"
                "¿Desea continuar de todas formas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.No:
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
        
        # Preferir trayectoria limpia salvo que se force la original
        xtc = os.path.join(d, f"{sim}_clean.xtc")
        if self.chk_force_raw.isChecked() or not os.path.exists(xtc):
            xtc = os.path.join(d, f"{sim}.xtc")
            
        # Verificar integridad mínima
        if os.path.exists(xtc) and os.path.getsize(xtc) == 0:
            QMessageBox.warning(self, "Error", f"El archivo de trayectoria {os.path.basename(xtc)} está vacío.")
            return

        self.set_busy(True)
        
        if self.rb_gmx.isChecked():
            # GROMACS
            out = os.path.join(d, f"{sim}_rdf_gmx.xvg")
            ref_idx = self.cb_ref.currentData()
            
            if ref_idx is None: 
                self.set_busy(False)
                return

            # Obtener nombres reales de los grupos (eliminando el ID visual)
            # Formato en combo: "Nombre (ID)"
            ref_name = self.cb_ref.currentText().rsplit(' (', 1)[0]
            sel_name = self.cb_sel.currentText().rsplit(' (', 1)[0]
            
            # --- VALIDACIÓN DE CUTOFF vs BOX SIZE ---
            rmax = self.sb_rmax.value()
            
            # Intentar leer dimensiones de la simulación actual (ej: prod.gro), sino system.gro
            gro_file = os.path.join(d, f"{sim}.gro")
            if not os.path.exists(gro_file):
                gro_file = os.path.join(d, "system.gro")
                
            min_box = self.parser.get_box_dimensions(gro_file)
            
            if min_box:
                limit = min_box / 2.0
                if rmax > limit:
                    msg = f"El cut-off solicitado ({rmax} nm) es mayor que la mitad de la caja ({limit:.2f} nm).\n\n" \
                          "Esto causará datos anómalos (ceros) a distancias largas debido a PBC (Minimum Image Convention).\n" \
                          f"Se recomienda usar un valor menor a {limit:.2f} nm.\n\n" \
                          "¿Desea continuar de todos modos?"
                    resp = QMessageBox.warning(self, "Advertencia de PBC", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if resp == QMessageBox.StandardButton.No:
                        self.set_busy(False)
                        return
            # ----------------------------------------
            
            # Pasar parámetros extendidos (Bin, Cutoff)
            # Usamos ref_name y sel_name en lugar de índices para mayor seguridad con make_ndx
            self.worker = AnalysisWorker(
                self.parser.run_gmx_rdf, tpr, xtc, out, ref_name, sel_name, d, 
                self.chk_com.isChecked(), self.sb_bin.value(), rmax
            )
            
            label_base = f"RDF {ref_name}-{sel_name}"
            
        else:
            # TRAVIS (Experimental)
            gro_file = os.path.join(d, f"{sim}.gro")
            if not os.path.exists(gro_file):
                gro_file = os.path.join(d, "system.gro")
            
            # Obtener IDs directamente de los ComboBoxes (Data tiene el ID Int)
            ref_id = self.cb_travis_m1.currentData()
            sel_id = self.cb_travis_m2.currentData()
            
            if ref_id is None: ref_id = 1
            if sel_id is None: sel_id = 2
            
            # Nombres para la etiqueta (sin el ID)
            ref_name = self.cb_travis_m1.currentText().split(" (ID:")[0]
            sel_name = self.cb_travis_m2.currentText().split(" (ID:")[0]

            out = os.path.join(d, "travis_results.csv") 
            # FIX: Pasar también el TPR file (necesario para el unwrap en run_travis_rdf actualizado)
            tpr_file = os.path.join(d, f"{sim}.tpr")
            
            self.worker = AnalysisWorker(
                self.parser.run_travis_rdf, gro_file, xtc, tpr_file,
                ref_id, sel_id, ref_name, sel_name, 
                self.sb_rmax.value(), self.sb_bin.value()
            )
            label_base = f"Travis RDF ({ref_name}-{sel_name})"

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
        
        # FIX: Travis genera archivos con nombres autogenerados (ej: rdf_mol1_mol2.csv)
        # Si ejecutamos Travis, debemos buscar el CSV más nuevo en la carpeta
        final_file = out_file
        if "Travis" in label:
            d = os.path.dirname(out_file)
            try:
                # Buscar CSVs que empiecen con rdf_ y ordenar por fecha
                csvs = [os.path.join(d, f) for f in os.listdir(d) 
                        if f.startswith("rdf_") and f.endswith(".csv")]
                if csvs:
                    final_file = max(csvs, key=os.path.getmtime)
            except:
                pass

        # Leer datos y añadir a Store (guardando el filepath para persistencia)
        lbl, x, y_list = self.parser.get_data_from_file(final_file)
        
        if y_list:
            self.add_data_to_store(label, x, y_list[0], final_file)
        else:
            QMessageBox.warning(self, "Aviso", f"El archivo de salida ({os.path.basename(final_file)}) está vacío o tiene formato incorrecto.")

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

    def open_fix_groups_dialog(self):
        """Abre dialogo para regenerar index.ndx usando generate_index_by_counts"""
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        if not sim or not d: return
        
        # Verificar si existe system.gro (necesario para contar átomos)
        gro_file = os.path.join(d, "system.gro")
        if not os.path.exists(gro_file):
            QMessageBox.warning(self, "Error", "Falta 'system.gro' en la carpeta.")
            return
            
        dlg = FixGroupsDialog(self)
        
        # Intentar Auto-Detección desde topol.top
        top_file = os.path.join(d, "topol.top")
        if os.path.exists(top_file):
            try:
                # Parseo rudimentario de [ molecules ]
                # Formato: Compound    #mols
                mols_found = []
                in_mols = False
                with open(top_file, 'r') as f:
                    for line in f:
                        clean = line.split(';')[0].strip()
                        if not clean: continue
                        if clean.startswith('[') and 'molecules' in clean:
                            in_mols = True
                            continue
                        if in_mols and not clean.startswith('['):
                            parts = clean.split()
                            if len(parts) >= 2 and parts[1].isdigit():
                                mols_found.append(int(parts[1]))
                
                if len(mols_found) >= 2:
                    dlg.sb_n1.setValue(mols_found[0]) # N1 (Soluto)
                    dlg.sb_n2.setValue(mols_found[1]) # N2 (Solvente)
                    dlg.setWindowTitle("Regenerar Index (Auto-Detectado)")
            except:
                pass # Fallback a 0/0
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            n1 = dlg.n1
            n2 = dlg.n2
            
            self.set_busy(True)
            ndx_file = os.path.join(d, "index.ndx")
            
            # Usamos un worker para no congelar, aunque es rápido
            # La función devuelve (success, msg)
            def fix_task():
                return self.parser.generate_index_by_counts(
                    gro_file, ndx_file, n1, n2,
                    name_solute="System_Solute_Fixed", 
                    name_solvent="System_Solvent_Fixed"
                )

            self.worker = AnalysisWorker(fix_task)
            self.worker.finished_signal.connect(self._on_fix_finished)
            self.worker.start()
            
    def _on_fix_finished(self, success, msg):
        self.set_busy(False)
        if success:
            QMessageBox.information(self, "Éxito", "Grupos regenerados correctamente.\nSeleccione 'System_Solute_Fixed' y 'System_Solvent_Fixed'.")
            self.load_gmx_groups()
            
            # Auto-seleccionar si existen
            idx1 = self.cb_ref.findText("System_Solute_Fixed", Qt.MatchFlag.MatchContains)
            if idx1 >= 0: self.cb_ref.setCurrentIndex(idx1)
            
            idx2 = self.cb_sel.findText("System_Solvent_Fixed", Qt.MatchFlag.MatchContains)
            if idx2 >= 0: self.cb_sel.setCurrentIndex(idx2)
        else:
            QMessageBox.critical(self, "Error", msg)

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

    # ==========================================================
    # LOGICA DE COLA (OPTIMIZADA)
    # ==========================================================

    def add_rdf_to_queue(self):
        """Valida y añade una tarea de RDF a la cola"""
        sim = self.combo_sims.currentText()
        d = self.get_storage_path()
        
        if not sim or not self.combo_sims.isEnabled():
            QMessageBox.warning(self, "Aviso", "Seleccione una simulación válida.")
            return

        ref_id = self.cb_ref.currentData()
        sel_id = self.cb_sel.currentData()
        
        if ref_id is None or sel_id is None:
            QMessageBox.warning(self, "Aviso", "Seleccione Grupos Validos.")
            return
            
        ref_name = self.cb_ref.currentText().split('(')[0].strip()
        sel_name = self.cb_sel.currentText().split('(')[0].strip()

        # Determinar tipo
        task_type = 'rdf_gmx' if self.rb_gmx.isChecked() else 'rdf_travis'

        # Crear objeto tarea
        task = {
            'type': task_type,
            'sim': sim,
            'path': d,
            'status': 'pending',
            # Parámetros Clave para Agrupación
            'ref_id': ref_id,  
            'ref_name': ref_name,
            # Parámetro Variable
            'sel_id': sel_id,
            'sel_name': sel_name,
            # Configuración
            'com': self.chk_com.isChecked(),
            'bin': self.sb_bin.value(),
            'rmax': self.sb_rmax.value()
        }
        
        self.queue_data.append(task)
        self._update_queue_table()

    def clear_queue(self):
        self.queue_data = []
        self._update_queue_table()

    def _update_queue_table(self):
        self.table_queue.setRowCount(0)
        for t in self.queue_data:
            row = self.table_queue.rowCount()
            self.table_queue.insertRow(row)
            self.table_queue.setItem(row, 0, QTableWidgetItem(t['sim']))
            self.table_queue.setItem(row, 1, QTableWidgetItem(t['type']))
            
            det = f"{t['ref_name']} - {t['sel_name']}"
            self.table_queue.setItem(row, 2, QTableWidgetItem(det))
            
            st = t['status']
            item_st = QTableWidgetItem(st)
            if st == 'done': item_st.setForeground(QColor('green'))
            elif 'error' in st: item_st.setForeground(QColor('red'))
            self.table_queue.setItem(row, 3, item_st)

    def run_queue_optimized(self):
        """
        Ejecuta la cola agrupando tareas compatibles.
        Estrategia: Agrupar por (Simulación, Ref_ID, Parametros).
        Las selecciones variables se juntan en una sola llamada.
        """
        if not self.queue_data: return
        
        # 1. Agrupar tareas
        grouped_jobs = {} # Key: (type, sim, ref_id, params...) -> List of tasks indices
        
        pending_count = 0
        for i, task in enumerate(self.queue_data):
            if task['status'] == 'done': continue
            pending_count += 1
            
            # Parametros base
            t_sim = task['sim']
            t_ref = task['ref_id']
            t_rmax = task['rmax']
            t_bin = task['bin']
            
            if task['type'] == 'rdf_gmx':
                # GMX depende de Use COM
                key = ('rdf_gmx', t_sim, t_ref, t_rmax, t_bin, task['com'])
            elif task['type'] == 'rdf_travis':
                # Travis no usa COM en interfaz simple (por ahora)
                key = ('rdf_travis', t_sim, t_ref, t_rmax, t_bin, None)
            else:
                key = ('unknown', t_sim, t_ref, i) # Fallback
            
            if key not in grouped_jobs:
                grouped_jobs[key] = []
            
            grouped_jobs[key].append(i) 
            
        if pending_count == 0:
            QMessageBox.information(self, "Info", "No hay tareas pendientes.")
            return

        self.set_busy(True)
        self.current_batch_jobs = list(grouped_jobs.items())
        self.current_job_index = 0
        
        self.lbl_thermo_status.setText(f"Iniciando lotes optimizados: {len(self.current_batch_jobs)} bloques...")
        self._process_next_batch_job()

    def _process_next_batch_job(self):
        """Procesa el siguiente grupo de tareas optimizado"""
        if self.current_job_index >= len(self.current_batch_jobs):
            self.set_busy(False)
            self._update_queue_table()
            QMessageBox.information(self, "Cola Finalizada", "Todos los análisis terminaron. Revise la pestaña Visualización Avanzada.")
            self.tabs.setCurrentIndex(2) # Switch to Viz Tab
            return
            
        key, task_indices = self.current_batch_jobs[self.current_job_index]
        job_type = key[0]
        
        if job_type == 'rdf_gmx':
            self._process_gmx_batch(key, task_indices)
        elif job_type == 'rdf_travis':
            self._process_travis_batch(key, task_indices)
        else:
            print("Unknown job type")
            self.current_job_index += 1
            self._process_next_batch_job()

    def _process_gmx_batch(self, key, task_indices):
        _, sim_name, ref_id, rmax, bin_w, use_com = key
        
        # Recuperar nombres 
        first_task = self.queue_data[task_indices[0]]
        ref_name = first_task['ref_name']
        d = first_task['path']

        # Obtener lista de NOMBRES de selección para este grupo
        sel_names = [self.queue_data[idx]['sel_name'] for idx in task_indices]
            
        # Preparar archivos
        tpr = os.path.join(d, f"{sim_name}.tpr")
        xtc = os.path.join(d, f"{sim_name}_clean.xtc")
        if not os.path.exists(xtc): xtc = os.path.join(d, f"{sim_name}.xtc")
        
        # Nombre de salida único para el batch
        import time
        ts = int(time.time())
        out_file = os.path.join(d, f"{sim_name}_rdf_gmx_batch_{self.current_job_index}_{ts}.xvg")
        
        self.lbl_thermo_status.setText(f"Batch GMX {self.current_job_index + 1}: {ref_name} vs {len(sel_names)} grupos...")
        
        self.worker = AnalysisWorker(
            self.parser.run_gmx_rdf_multi, 
            tpr, xtc, out_file, ref_name, sel_names, d, 
            use_com, bin_w, rmax
        )
        
        self.worker.finished_signal.connect(
            lambda s, m: self._on_gmx_batch_finished(s, m, out_file, task_indices)
        )
        self.worker.start()

    def _process_travis_batch(self, key, task_indices):
        _, sim_name, ref_id, rmax, bin_w, _ = key
        
        first_task = self.queue_data[task_indices[0]]
        ref_name = first_task['ref_name']
        d = first_task['path']
        
        # Preparar lista de tareas para el parser
        travis_tasks = []
        for idx in task_indices:
            t = self.queue_data[idx]
            travis_tasks.append({
                'obs_id': t['sel_id'], # ID Numerico
                'obs_name': t['sel_name'],
                'rmax': rmax,
                'bins': bin_w
            })
            
        tpr = os.path.join(d, f"{sim_name}.tpr")
        xtc = os.path.join(d, f"{sim_name}_clean.xtc")
        if not os.path.exists(xtc): xtc = os.path.join(d, f"{sim_name}.xtc")
        
        self.lbl_thermo_status.setText(f"Batch TRAVIS {self.current_job_index + 1}: {ref_name} vs {len(travis_tasks)} grupos...")
        
        # Travis corre en terminal externo y bloquea (pero necesitamos que no bloquee la GUI)
        # Como AnalysisWorker corre en thread, está bien.
        
        self.worker = AnalysisWorker(
            self.parser.run_travis_batch,
            d, xtc, tpr, ref_id, ref_name, travis_tasks
        )
        
        self.worker.finished_signal.connect(
            lambda s, m: self._on_travis_batch_finished(s, m, task_indices)
        )
        self.worker.start()

    def _on_gmx_batch_finished(self, success, msg, out_file, task_indices):
        """Maneja el resultado de GMX"""
        if success:
            lbls, x, ys = self.parser.get_data_from_file(out_file)
            
            if len(ys) == len(task_indices):
                for i, idx in enumerate(task_indices):
                    task = self.queue_data[idx]
                    y_data = ys[i]
                    label = f"RDF(GMX): {task['ref_name']} - {task['sel_name']} [{task['sim']}]"
                    self.add_data_to_store(label, x, y_data, out_file)
                    self.queue_data[idx]['status'] = 'done'
            else:
                 # Mismatch logic simplificada
                 print(f"Mismatch GMX: {len(ys)} vs {len(task_indices)}")
                 for idx in task_indices: self.queue_data[idx]['status'] = 'error (cols)'
        else:
            for idx in task_indices: self.queue_data[idx]['status'] = 'error'
            print(msg)
        
        self.current_job_index += 1
        self._process_next_batch_job()

    def _on_travis_batch_finished(self, success, msg, task_indices):
        """Maneja el resultado de Travis (MSG contiene paths nuevos)"""
        if success:
            # El mensaje trae "Se generaron X archivos...\nPath1\nPath2..."
            # Pero run_travis_batch no nos devuelve el mapeo exacto 1 a 1 ordenado de forma garantizada 
            # si los nombres de archivo dependen de lo que detectó travis.
            
            # Sin embargo, AnalysisParser movió los archivos a RDF_System_Ref-Sel.csv
            # Intentemos buscar archivos recientes que coincidan con lo esperado.
            
            # Marcar todo como hecho por ahora
            # Lo ideal sería leer los CSV resultantes.
            
            # AnalysisParser.run_travis_batch devuelve success y un log.
            # No devuelve los datos X, Y. Hay que leerlos de disco.
            
            # Intento de carga automática:
            # Buscamos en 'msg' las rutas? El msg es string.
            # Mejor escaneamos carpeta 'd' buscando RDF_{sim}... que coincidan con ref/sel
            
            first_task = self.queue_data[task_indices[0]]
            d = first_task['path']
            
            # Vamos uno por uno intentando cargar su resultado esperado
            # AnalysisParser generó: f"RDF_{sys_id}_{safe_ref}-{safe_sel}.csv"
            
            # Reconstruyamos sys_id (aproximado, o buscamos wildcard)
            # sys_id depende del path. Es dificil reconstruirlo exacto aquí sin duplica logica.
            # Pero podemos buscar por "RDF_*_{ref}-{sel}.csv"
            
            import glob
            
            for idx in task_indices:
                task = self.queue_data[idx]
                s_ref = task['ref_name'].replace(" ", "_").replace("(", "").replace(")", "")
                s_sel = task['sel_name'].replace(" ", "_").replace("(", "").replace(")", "")
                
                # Pattern
                pattern = os.path.join(d, f"RDF_*_{s_ref}-{s_sel}.csv")
                matches = glob.glob(pattern)
                
                if matches:
                    # Cargar el más nuevo
                    latest = max(matches, key=os.path.getmtime)
                    label = f"RDF(Travis): {task['ref_name']} - {task['sel_name']} [{task['sim']}]"
                    
                    try:
                        l, x, ys = self.parser.get_data_from_file(latest)
                        if ys:
                            self.add_data_to_store(label, x, ys[0], latest)
                            self.queue_data[idx]['status'] = 'done'
                        else:
                            self.queue_data[idx]['status'] = 'empty'
                    except:
                         self.queue_data[idx]['status'] = 'error read'
                else:
                    self.queue_data[idx]['status'] = 'not found'

        else:
            for idx in task_indices:
                self.queue_data[idx]['status'] = 'error'
        
        self.current_job_index += 1
        self._process_next_batch_job()

