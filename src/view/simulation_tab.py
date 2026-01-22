import os
import re
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTextEdit, QGroupBox, 
    QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox, 
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QFormLayout, QLCDNumber, QProgressBar, QFrame, 
    QCheckBox, QDialog, QPlainTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QTime
from src.model.mdp_manager import MdpManager
from src.controller.workers import CommandWorker

# ==========================================================
# CLASE AUXILIAR: VISOR DE LOGS
# ==========================================================
class LogViewerDialog(QDialog):
    def __init__(self, log_content, title="Log de Simulación"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(700, 500)
        
        layout = QVBoxLayout()
        
        self.text_display = QPlainTextEdit()
        self.text_display.setPlainText(log_content)
        self.text_display.setReadOnly(True)
        self.text_display.setStyleSheet("font-family: monospace; font-size: 10pt; background-color: #f0f0f0;")
        
        layout.addWidget(self.text_display)
        
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        
        self.setLayout(layout)


# ==========================================================
# CLASE PRINCIPAL: PESTAÑA DE SIMULACIÓN
# ==========================================================
class SimulationTab(QWidget):
    def __init__(self):
        super().__init__()
        
        # ---------------------------------------------------------
        # CONFIGURACIÓN INICIAL
        # ---------------------------------------------------------
        
        # Rutas absolutas
        current_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.dirname(current_dir)
        templates_path = os.path.join(src_dir, "assets", "templates")
        
        # Gestores
        self.mdp_mgr = MdpManager(templates_path)
        self.project_mgr = None
        self.current_project_path = None
        
        # Worker para ejecución en segundo plano
        self.worker = None 
        
        # Estado del protocolo (Árbol)
        self.protocol_steps = []
        
        # Bandera para evitar bucles de actualización
        self.is_updating_ui = False
        
        # Variables para estimación de tiempo
        self.total_steps_target = 0
        self.start_time_wall = None
        
        # Modo de ejecución actual
        self.execution_mode = 'single'
        
        # Timer para el reloj de tiempo transcurrido
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        self.elapsed_seconds_counter = 0
        
        # Construir la UI
        self.init_ui()

    def init_ui(self):
        """Construye la interfaz gráfica completa"""
        layout = QVBoxLayout()
        
        # ============================================================
        # 1. ÁRBOL DE PROTOCOLO (RAMIFICACIÓN)
        # ============================================================
        group_proto = QGroupBox("1. Árbol de Simulación")
        layout_proto = QVBoxLayout()
        
        hbox_add = QHBoxLayout()
        
        # Selector de Tipo
        self.combo_type = QComboBox()
        self.combo_type.addItems(["minim", "nvt", "npt", "prod"])
        # Conectar cambio de tipo para sugerir nombre automáticamente
        self.combo_type.currentIndexChanged.connect(self.update_default_name)
        
        # Entrada de Nombre
        self.input_step_name = QLineEdit()
        self.input_step_name.setPlaceholderText("Nombre del paso")
        
        # Botones de Árbol
        btn_add_child = QPushButton("➕ Agregar Hijo")
        btn_add_child.setToolTip("Agrega un paso derivado del nodo seleccionado")
        btn_add_child.clicked.connect(self.add_step_child)
        
        btn_del = QPushButton("➖ Eliminar Rama")
        btn_del.setToolTip("Elimina el paso seleccionado y todos sus descendientes")
        btn_del.clicked.connect(self.remove_branch)
        
        # Layout de controles
        hbox_add.addWidget(QLabel("Tipo:"))
        hbox_add.addWidget(self.combo_type)
        hbox_add.addWidget(QLabel("Nombre:"))
        hbox_add.addWidget(self.input_step_name)
        hbox_add.addWidget(btn_add_child)
        hbox_add.addWidget(btn_del)
        
        # Árbol visual
        self.tree_steps = QTreeWidget()
        self.tree_steps.setHeaderLabels(["Nombre (ID)", "Tipo", "Estado"])
        self.tree_steps.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Conectar clic para cargar configuración
        self.tree_steps.itemClicked.connect(self.on_node_selected)
        
        layout_proto.addLayout(hbox_add)
        layout_proto.addWidget(self.tree_steps)
        
        group_proto.setLayout(layout_proto)
        layout.addWidget(group_proto)
        
        # ============================================================
        # 2. CONFIGURACIÓN (HORIZONTAL Y RESTRINGIDA)
        # ============================================================
        group_edit = QGroupBox("2. Configuración del Paso Seleccionado")
        layout_edit = QVBoxLayout()
        
        self.lbl_editing = QLabel("Seleccione un nodo del árbol para configurar...")
        self.lbl_editing.setStyleSheet("color: blue; font-weight: bold; font-size: 13px;")
        layout_edit.addWidget(self.lbl_editing)
        
        self.config_tabs = QTabWidget()
        
        # -- Tab A: Manual (Diseño Horizontal) --
        self.tab_manual = QWidget()
        self.init_manual_ui() 
        self.config_tabs.addTab(self.tab_manual, "Manual (Ajustes)")
        
        # -- Tab B: Experto (Código Fuente) --
        self.tab_expert = QWidget()
        layout_expert = QVBoxLayout()
        
        self.text_editor = QTextEdit()
        self.text_editor.setPlaceholderText("Aquí aparecerá el contenido del archivo .mdp...")
        self.text_editor.setStyleSheet("font-family: Monospace; font-size: 11px; background-color: #fcfcfc;")
        
        layout_expert.addWidget(self.text_editor)
        self.tab_expert.setLayout(layout_expert)
        self.config_tabs.addTab(self.tab_expert, "Experto (Código MDP)")
        
        layout_edit.addWidget(self.config_tabs)
        group_edit.setLayout(layout_edit)
        layout.addWidget(group_edit)
        
        # ============================================================
        # 3. MONITOR DE EJECUCIÓN (CON AUTO-RUN)
        # ============================================================
        group_run = QGroupBox("3. Motor de Ejecución")
        layout_run = QVBoxLayout()
        
        hbox_run = QHBoxLayout()
        
        # Botones de Control Manual
        self.btn_grompp = QPushButton("1. Compilar (grompp)")
        self.btn_grompp.clicked.connect(lambda: self.run_sequence(mode='single', compile_only=True))
        self.btn_grompp.setEnabled(False)
        self.btn_grompp.setMinimumHeight(40)
        
        self.btn_mdrun = QPushButton("2. Correr Paso (mdrun)")
        self.btn_mdrun.clicked.connect(lambda: self.run_sequence(mode='single', start_mdrun=True))
        self.btn_mdrun.setEnabled(False)
        self.btn_mdrun.setMinimumHeight(40)
        self.btn_mdrun.setStyleSheet("font-weight: bold; color: #006600;")
        
        self.btn_stop = QPushButton("⏹ Detener")
        self.btn_stop.clicked.connect(self.stop_simulation)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("color: red;")
        self.btn_stop.setMinimumHeight(40)
        
        self.btn_log = QPushButton("📄 Ver Log")
        self.btn_log.clicked.connect(self.show_log)
        self.btn_log.setMinimumHeight(40)
        
        hbox_run.addWidget(self.btn_grompp)
        hbox_run.addWidget(self.btn_mdrun)
        hbox_run.addWidget(self.btn_stop)
        hbox_run.addWidget(self.btn_log)
        
        # Botones de Automatización
        hbox_auto = QHBoxLayout()
        
        self.btn_run_branch = QPushButton("▶ Ejecutar Rama Actual (Cascada)")
        self.btn_run_branch.setToolTip("Ejecuta el paso actual y todos sus hijos secuencialmente")
        self.btn_run_branch.clicked.connect(lambda: self.run_sequence(mode='branch'))
        self.btn_run_branch.setStyleSheet("background-color: #e8f5e9; font-weight: bold;")
        
        self.btn_run_all = QPushButton("▶▶ Ejecutar TODO EL PROYECTO")
        self.btn_run_all.setToolTip("Ejecuta todas las ramas pendientes en orden")
        self.btn_run_all.clicked.connect(lambda: self.run_sequence(mode='all'))
        self.btn_run_all.setStyleSheet("background-color: #fff3cd; font-weight: bold;")
        
        hbox_auto.addWidget(self.btn_run_branch)
        hbox_auto.addWidget(self.btn_run_all)
        
        # --- INFO DE GROMACS ---
        self.lbl_gmx_info = QLabel("Estado: Esperando orden...")
        self.lbl_gmx_info.setStyleSheet("font-size: 12px; font-weight: bold; background: #e6e6e6; padding: 6px; border-radius: 4px;")
        self.lbl_gmx_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # --- INFO TIEMPO ---
        hbox_timer = QHBoxLayout()
        hbox_timer.addStretch()
        hbox_timer.addWidget(QLabel("Transcurrido:"))
        
        self.lbl_elapsed = QLabel("00:00:00")
        self.lbl_elapsed.setStyleSheet("font-weight: bold; color: blue; font-size: 14px;")
        
        hbox_timer.addWidget(self.lbl_elapsed)
        
        layout_run.addWidget(QLabel("<b>Control Manual:</b>"))
        layout_run.addLayout(hbox_run)
        layout_run.addWidget(QLabel("<b>Automatización:</b>"))
        layout_run.addLayout(hbox_auto)
        layout_run.addSpacing(10)
        layout_run.addWidget(self.lbl_gmx_info)
        layout_run.addLayout(hbox_timer)
        
        group_run.setLayout(layout_run)
        layout.addWidget(group_run)
        
        self.setLayout(layout)
        
        # Setear nombre inicial por defecto
        self.update_default_name()

    # ============================================================
    # INICIALIZACIÓN DE UI MANUAL (DISEÑO HORIZONTAL)
    # ============================================================
    def init_manual_ui(self):
        """Crea la interfaz de configuración dividida en 2 columnas"""
        h_layout = QHBoxLayout()
        
        # --- COLUMNA IZQUIERDA: PARÁMETROS DE CONTROL ---
        left_widget = QWidget()
        form_control = QFormLayout()
        
        self.spin_time_ns = QDoubleSpinBox()
        self.spin_time_ns.setRange(0, 10000)
        self.spin_time_ns.setSingleStep(0.1)
        self.spin_time_ns.setSuffix(" ns")
        self.spin_time_ns.setValue(5.0) # Default general
        # Conectar cambio para recalcular pasos
        self.spin_time_ns.valueChanged.connect(self.on_time_changed) 
        
        self.combo_integrator = QComboBox()
        self.combo_integrator.addItems(["md (Leap-frog)", "steep (Minimización)", "sd (Langevin)"])
        # Conectar cambio para actualizar texto
        self.combo_integrator.currentIndexChanged.connect(lambda: self.sync_gui_to_text())
        
        self.spin_dt = QDoubleSpinBox()
        self.spin_dt.setRange(0.0001, 0.010)
        self.spin_dt.setDecimals(4)
        self.spin_dt.setSuffix(" ps")
        self.spin_dt.setValue(0.002)
        # Conectar cambio para recalcular pasos
        self.spin_dt.valueChanged.connect(self.on_dt_changed) 
        
        self.lbl_steps_calc = QLabel("Pasos: 0 (Calculado)")
        self.lbl_steps_calc.setStyleSheet("color: gray; font-style: italic;")
        
        form_control.addRow(QLabel("<b>CONTROL:</b>"))
        form_control.addRow("Integrador:", self.combo_integrator)
        form_control.addRow("Paso (dt):", self.spin_dt)
        form_control.addRow("Duración:", self.spin_time_ns)
        form_control.addRow("", self.lbl_steps_calc)
        
        left_widget.setLayout(form_control)
        
        # --- COLUMNA DERECHA: FÍSICA (TEMP/PRES) ---
        right_widget = QWidget()
        vbox_right = QVBoxLayout()
        
        # Grupo Temperatura
        self.group_temp = QGroupBox("Temperatura")
        form_temp = QFormLayout()
        
        self.chk_global_temp = QCheckBox("Temp. de Operación (Global)")
        self.chk_global_temp.setToolTip("Si se activa, modificar la temperatura aquí actualizará TODOS los pasos de la rama (excepto minimizaciones).")
        self.chk_global_temp.setStyleSheet("color: #d35400; font-weight: bold;")
        
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0, 5000)
        self.spin_temp.setSuffix(" K")
        self.spin_temp.setValue(298.15) # Default
        self.spin_temp.valueChanged.connect(lambda: self.sync_gui_to_text())
        
        self.combo_tcoupl = QComboBox()
        self.combo_tcoupl.addItems(["V-rescale", "Nose-Hoover", "Berendsen", "no"])
        self.combo_tcoupl.currentIndexChanged.connect(lambda: self.sync_gui_to_text())
        
        # Botón para aplicar a la rama (Feature solicitado)
        btn_apply_branch_t = QPushButton("Aplicar T a toda esta Rama")
        btn_apply_branch_t.clicked.connect(self.apply_temp_to_branch)
        btn_apply_branch_t.setStyleSheet("background-color: #ffecd1; color: #d35400;")
        
        form_temp.addRow(self.chk_global_temp)
        form_temp.addRow("Ref T:", self.spin_temp)
        form_temp.addRow("Termostato:", self.combo_tcoupl)
        form_temp.addRow(btn_apply_branch_t)
        self.group_temp.setLayout(form_temp)
        
        # Grupo Presión
        self.group_press = QGroupBox("Presión")
        form_press = QFormLayout()
        
        self.spin_press = QDoubleSpinBox()
        self.spin_press.setRange(0, 2000)
        self.spin_press.setSuffix(" bar")
        self.spin_press.setValue(1.0) # Default
        self.spin_press.valueChanged.connect(lambda: self.sync_gui_to_text())
        
        self.combo_pcoupl = QComboBox()
        self.combo_pcoupl.addItems(["Parrinello-Rahman", "C-rescale", "Berendsen", "no"])
        self.combo_pcoupl.currentIndexChanged.connect(lambda: self.sync_gui_to_text())
        
        form_press.addRow("Ref P:", self.spin_press)
        form_press.addRow("Barostato:", self.combo_pcoupl)
        self.group_press.setLayout(form_press)
        
        vbox_right.addWidget(self.group_temp)
        vbox_right.addWidget(self.group_press)
        right_widget.setLayout(vbox_right)
        
        # Añadir al layout principal con Splitter visual
        h_layout.addWidget(left_widget)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        h_layout.addWidget(line)
        
        h_layout.addWidget(right_widget)
        
        self.tab_manual.setLayout(h_layout)

    # ============================================================
    # LÓGICA DE INTERFAZ DINÁMICA (RESTRICCIONES)
    # ============================================================
    def toggle_ui_elements(self, step_type):
        """Habilita/Deshabilita controles según el tipo de simulación"""
        
        # 1. Minimización
        if step_type == 'minim':
            self.spin_time_ns.setEnabled(False) 
            self.lbl_steps_calc.setText("Pasos definidos por nsteps/emtol")
            
            self.group_temp.setEnabled(False)
            self.chk_global_temp.setEnabled(False)
            self.group_press.setEnabled(False)
            
        # 2. NVT
        elif step_type == 'nvt':
            self.spin_time_ns.setEnabled(True)
            
            self.group_temp.setEnabled(True)
            self.chk_global_temp.setEnabled(True)
            self.group_press.setEnabled(False) # Bloquear presión
            
        # 3. NPT / Prod
        else:
            self.spin_time_ns.setEnabled(True)
            self.group_temp.setEnabled(True)
            self.chk_global_temp.setEnabled(True)
            self.group_press.setEnabled(True)

    def update_default_name(self):
        """Sugiere nombre basado en tipo"""
        idx = self.combo_type.currentIndex()
        if idx == 0:
            self.input_step_name.setText("minim")
        elif idx == 1:
            self.input_step_name.setText("gen") 
        elif idx == 2:
            self.input_step_name.setText("equil") 
        elif idx == 3:
            self.input_step_name.setText("prod") 

    # ============================================================
    # LÓGICA DE SINCRONIZACIÓN AUTOMÁTICA (GUI <-> TEXTO)
    # ============================================================
    
    def on_time_changed(self):
        """Calcula nsteps cuando cambia el tiempo en ns"""
        if self.is_updating_ui:
            return
        
        ns = self.spin_time_ns.value()
        dt_ps = self.spin_dt.value()
        
        if dt_ps <= 0:
            return
        
        # Calcular pasos: (ns * 1000) / dt
        nsteps = int((ns * 1000.0) / dt_ps)
        self.lbl_steps_calc.setText(f"Pasos: {nsteps}")
        
        # Actualizar texto inmediatamente
        self.sync_gui_to_text(nsteps_override=nsteps)

    def on_dt_changed(self):
        self.on_time_changed()

    def load_mdp_values_to_gui(self, content):
        """Lee el texto del archivo .mdp y actualiza los controles visuales"""
        self.is_updating_ui = True 
        try:
            match_dt = re.search(r"dt\s*=\s*([\d\.]+)", content)
            if match_dt:
                dt_val = float(match_dt.group(1))
                self.spin_dt.setValue(dt_val)

            match_steps = re.search(r"nsteps\s*=\s*(\d+)", content)
            if match_steps and 'dt_val' in locals():
                steps_val = int(match_steps.group(1))
                ns_val = (steps_val * dt_val) / 1000.0
                self.spin_time_ns.setValue(ns_val)
                self.lbl_steps_calc.setText(f"Pasos: {steps_val}")

            match_temp = re.search(r"ref_t\s*=\s*([\d\.]+)", content)
            if match_temp: self.spin_temp.setValue(float(match_temp.group(1)))

            match_pres = re.search(r"ref_p\s*=\s*([\d\.]+)", content)
            if match_pres: self.spin_press.setValue(float(match_pres.group(1)))

            match_int = re.search(r"integrator\s*=\s*(\w+)", content)
            if match_int:
                idx = self.combo_integrator.findText(match_int.group(1), Qt.MatchFlag.MatchStartsWith)
                if idx >= 0: self.combo_integrator.setCurrentIndex(idx)

            match_tc = re.search(r"tcoupl\s*=\s*([\w\-]+)", content)
            if match_tc:
                idx = self.combo_tcoupl.findText(match_tc.group(1))
                if idx >= 0: self.combo_tcoupl.setCurrentIndex(idx)
                
            match_pc = re.search(r"pcoupl\s*=\s*([\w\-]+)", content)
            if match_pc:
                idx = self.combo_pcoupl.findText(match_pc.group(1))
                if idx >= 0: self.combo_pcoupl.setCurrentIndex(idx)
                
        except Exception as e:
            print(f"Error parseando MDP a GUI: {e}")
        
        self.is_updating_ui = False

    def sync_gui_to_text(self, nsteps_override=None):
        """Toma valores de la GUI y actualiza el texto MDP"""
        if self.is_updating_ui:
            return
        
        current_item = self.tree_steps.currentItem()
        step_type = current_item.text(1) if current_item else "prod"
        
        params = {}
        
        # Parámetros Generales
        params['integrator'] = self.combo_integrator.currentText().split()[0]
        params['dt'] = self.spin_dt.value()
        
        if nsteps_override: params['nsteps'] = nsteps_override
        
        # Parámetros Condicionales
        if step_type != 'minim':
            params['ref_t'] = self.spin_temp.value()
            params['gen_temp'] = self.spin_temp.value()
            params['tcoupl'] = self.combo_tcoupl.currentText()
            
            if step_type in ['npt', 'prod']:
                params['ref_p'] = self.spin_press.value()
                params['pcoupl'] = self.combo_pcoupl.currentText()
            else:
                params['pcoupl'] = "no"
        else:
            params['pcoupl'] = "no"
            params['tcoupl'] = "no"
            params['gen_vel'] = "no"
        
        current_text = self.text_editor.toPlainText()
        new_text = self.mdp_mgr.update_parameters(current_text, params)
        
        self.is_updating_ui = True
        self.text_editor.setPlainText(new_text)
        self.is_updating_ui = False
        
        self.save_mdp_to_disk()

        # --- PROPAGACIÓN GLOBAL DE TEMPERATURA ---
        if self.chk_global_temp.isChecked() and step_type != 'minim':
            self.propagate_temperature(params['ref_t'])

    def propagate_temperature(self, temp_val):
        storage_dir = self.get_storage_path()
        if not storage_dir: return
        root = self.tree_steps.invisibleRootItem()
        self._recursive_temp_update(root, temp_val, storage_dir)

    def _recursive_temp_update(self, parent_item, temp_val, storage_dir):
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            name = item.text(0)
            stype = item.text(1)
            
            if stype != 'minim':
                path = os.path.join(storage_dir, f"{name}.mdp")
                if os.path.exists(path):
                    with open(path, 'r') as f: content = f.read()
                    params = {'ref_t': temp_val, 'gen_temp': temp_val}
                    new_c = self.mdp_mgr.update_parameters(content, params)
                    self.mdp_mgr.save_mdp(path, new_c)
            
            self._recursive_temp_update(item, temp_val, storage_dir)

    # ============================================================
    # GESTIÓN DEL ÁRBOL
    # ============================================================

    def on_node_selected(self, item, col):
        """Carga datos del nodo seleccionado en la tabla"""
        storage_dir = self.get_storage_path()
        if not storage_dir:
            return
        
        self.is_updating_ui = True 
        
        name = item.text(0)
        step_type = item.text(1)
        
        parent_name = item.parent().text(0) if item.parent() else "Sistema (Raíz)"
        self.lbl_editing.setText(f"Editando: {name} ({step_type}) | Padre: {parent_name}")
        
        self.toggle_ui_elements(step_type)
        
        mdp_path = os.path.join(storage_dir, f"{name}.mdp")
        file_exists = os.path.exists(mdp_path)
        
        if file_exists:
            with open(mdp_path, 'r') as f:
                content = f.read()
        else:
            content = self.mdp_mgr.get_template_content(step_type)
        
        self.text_editor.setPlainText(content)
        
        if file_exists:
            self.load_mdp_values_to_gui(content)
        else:
            # Defaults
            if step_type == 'minim':
                self.combo_integrator.setCurrentIndex(1)
            else:
                self.combo_integrator.setCurrentIndex(0)
                self.spin_temp.setValue(298.15)
                
                if step_type == 'nvt':
                    self.spin_time_ns.setValue(5.0)
                    self.combo_pcoupl.setCurrentIndex(3)
                elif step_type == 'npt':
                    self.spin_time_ns.setValue(10.0)
                    self.spin_press.setValue(1.0)
                    self.combo_pcoupl.setCurrentIndex(1)
                elif step_type == 'prod':
                    self.spin_time_ns.setValue(5.0)
                    self.spin_press.setValue(1.0)
                    self.combo_pcoupl.setCurrentIndex(0)
            
            self.is_updating_ui = False
            self.sync_gui_to_text()

        self.btn_grompp.setEnabled(True)
        self.btn_mdrun.setEnabled(False)
        self.is_updating_ui = False

    def add_step_child(self):
        """Añade un paso hijo"""
        current_item = self.tree_steps.currentItem()
        parent_item = current_item if current_item else self.tree_steps.invisibleRootItem()
        
        step_type = self.combo_type.currentText()
        name = self.input_step_name.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Error", "Escriba un nombre.")
            return
            
        if self.current_project_path:
             if os.path.exists(os.path.join(self.current_project_path, "storage", f"{name}.mdp")):
                QMessageBox.warning(self, "Error", "Nombre duplicado.")
                return

        item = QTreeWidgetItem(parent_item)
        item.setText(0, name)
        item.setText(1, step_type)
        item.setText(2, "Pendiente")
        
        if current_item:
            current_item.setExpanded(True)
            
        self.input_step_name.clear()
        
        self.tree_steps.setCurrentItem(item)
        self.on_node_selected(item, 0)
        
        next_type_idx = self.combo_type.currentIndex() + 1
        if next_type_idx < self.combo_type.count():
            self.combo_type.setCurrentIndex(next_type_idx)

    def remove_branch(self):
        item = self.tree_steps.currentItem()
        if not item: return
        reply = QMessageBox.question(self, "Eliminar", f"¿Eliminar '{item.text(0)}' y toda su rama?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            (item.parent() or self.tree_steps.invisibleRootItem()).removeChild(item)

    # ============================================================
    # PERSISTENCIA
    # ============================================================
    def update_project_data(self, project_mgr):
        self.project_mgr = project_mgr
        if project_mgr:
            self.current_project_path = project_mgr.get_active_system_path()
            # VALIDAR ESTADOS AL CARGAR (Recuperado)
            self.validate_all_statuses()

    def get_storage_path(self):
        if self.project_mgr:
            return self.project_mgr.get_active_system_path()
        return None

    def get_state(self):
        def serialize_item(item):
            node = {
                "name": item.text(0),
                "type": item.text(1),
                "status": item.text(2),
                "children": []
            }
            for i in range(item.childCount()):
                node["children"].append(serialize_item(item.child(i)))
            return node

        root = self.tree_steps.invisibleRootItem()
        tree_data = [serialize_item(root.child(i)) for i in range(root.childCount())]
        return {"tree_data": tree_data}

    def set_state(self, state):
        if not state: return
        self.tree_steps.clear()
        def deserialize_item(node_data, parent):
            item = QTreeWidgetItem(parent)
            item.setText(0, node_data["name"])
            item.setText(1, node_data["type"])
            st = node_data.get("status", "Pendiente")
            item.setText(2, st)
            
            self._set_status_color(item, st)
            
            for child_data in node_data.get("children", []):
                deserialize_item(child_data, item)
            item.setExpanded(True)

        for node in state.get("tree_data", []):
            deserialize_item(node, self.tree_steps)
            
        self.validate_all_statuses()

    def validate_all_statuses(self):
        """Verifica archivos físicos"""
        storage = self.get_storage_path()
        if not storage: return
        
        root = self.tree_steps.invisibleRootItem()
        self._recursive_validate(root, storage)

    def _recursive_validate(self, parent_item, storage):
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            name = item.text(0)
            
            gro_path = os.path.join(storage, f"{name}.gro")
            tpr_path = os.path.join(storage, f"{name}.tpr")
            
            status = "Pendiente"
            if os.path.exists(gro_path):
                status = "Completado"
            elif os.path.exists(tpr_path):
                status = "Listo (TPR)"
            
            item.setText(2, status)
            self._set_status_color(item, status)
            
            self._recursive_validate(item, storage)

    def _set_status_color(self, item, status):
        if status == 'Completado':
            item.setForeground(2, Qt.GlobalColor.green)
        elif status == 'Listo (TPR)':
            item.setForeground(2, Qt.GlobalColor.darkYellow)
        elif status == 'Error':
            item.setForeground(2, Qt.GlobalColor.red)
        else:
            item.setForeground(2, Qt.GlobalColor.black)

    def save_mdp_to_disk(self):
        item = self.tree_steps.currentItem()
        storage_dir = self.get_storage_path()
        if not item or not storage_dir:
            return
        path = os.path.join(storage_dir, f"{item.text(0)}.mdp")
        self.mdp_mgr.save_mdp(path, self.text_editor.toPlainText())

    def save_current_mdp(self):
        self.save_mdp_to_disk()
        QMessageBox.information(self, "OK", "Guardado")

    # ============================================================
    # EJECUCIÓN (MOTOR) - SAFETY CHECK INCLUDED
    # ============================================================
    
    def _cleanup_worker(self):
        """Limpieza segura de hilos"""
        if self.worker is not None:
            try:
                self.worker.finished_signal.disconnect()
            except TypeError:
                pass

            if self.worker.isRunning():
                self.worker.stop_process()
                self.worker.quit()
                self.worker.wait(1000)
            
            self.worker.deleteLater()
            self.worker = None

    def run_sequence(self, mode='single', compile_only=False, start_mdrun=False):
        """Método maestro de ejecución"""
        self.execution_mode = mode
        item = self.tree_steps.currentItem()
        
        if mode == 'all':
            item = self.find_next_pending_node(self.tree_steps.invisibleRootItem())
            if not item:
                QMessageBox.information(self, "Info", "No hay pasos pendientes.")
                return
            self.tree_steps.setCurrentItem(item)
            self.on_node_selected(item, 0)
        
        if not item: return

        if start_mdrun:
            self.run_mdrun()
        else:
            self.run_grompp()

    def get_chain_files(self, item):
        name = item.text(0)
        d = self.get_storage_path()
        if not d: return None
        
        parent = item.parent()
        input_gro = f"{parent.text(0)}.gro" if parent else "system.gro"
            
        if not os.path.exists(os.path.join(d, input_gro)):
            QMessageBox.warning(self, "Bloqueo", f"Falta input: {input_gro}")
            return None
        return f"{name}.mdp", input_gro, f"{name}.tpr"

    def run_grompp(self):
        self._cleanup_worker()

        item = self.tree_steps.currentItem()
        if not item: return
        
        self.save_mdp_to_disk()
        files = self.get_chain_files(item)
        if not files: return
        
        mdp, gro, tpr = files
        storage_dir = self.get_storage_path()
        
        cmd = ["gmx", "grompp", "-f", mdp, "-c", gro, "-p", "topol.top", "-o", tpr, "-maxwarn", "2"]
        
        self.worker = CommandWorker(cmd, storage_dir)
        self.worker.log_signal.connect(lambda s: print(f"GROMPP: {s}"))
        self.worker.finished_signal.connect(self.on_grompp_finished)
        
        self.btn_grompp.setEnabled(False)
        self.worker.start()

    def on_grompp_finished(self, success, msg):
        self.btn_grompp.setEnabled(True)
        if success:
            item = self.tree_steps.currentItem()
            item.setText(2, "Listo (TPR)")
            self._set_status_color(item, "Listo (TPR)")
            
            if self.execution_mode in ['branch', 'all']:
                self.run_mdrun()
            else:
                QMessageBox.information(self, "Éxito", "Compilación exitosa.")
                self.btn_mdrun.setEnabled(True)
        else:
            QMessageBox.critical(self, "Error", msg)

    def run_mdrun(self):
        self._cleanup_worker()

        item = self.tree_steps.currentItem()
        if not item: return
        
        n = item.text(0)
        d = self.get_storage_path()
        
        if not os.path.exists(os.path.join(d, f"{n}.tpr")):
             QMessageBox.warning(self, "Error", "Falta TPR.")
             return
        
        typ = item.text(1)
        if typ == 'minim': self.total_steps_target = 50000 
        else:
            ns = self.spin_time_ns.value(); dt = self.spin_dt.value()
            self.total_steps_target = int((ns * 1000) / dt) if dt > 0 else 100000
        
        cmd = ["gmx", "mdrun", "-v", "-deffnm", n]
        
        self.worker = CommandWorker(cmd, d)
        self.worker.log_signal.connect(self.parse_log_output)
        self.worker.finished_signal.connect(self.on_mdrun_finished)
        
        self.btn_grompp.setEnabled(False); self.btn_mdrun.setEnabled(False); self.btn_stop.setEnabled(True)
        item.setText(2, "Corriendo...")
        item.setForeground(2, Qt.GlobalColor.blue)
        self.lbl_gmx_info.setText("Iniciando...")
        
        self.elapsed_seconds_counter = 0; self.timer.start(1000)
        self.start_time_wall = datetime.datetime.now()
        
        self.worker.start()

    def stop_simulation(self):
        if self.worker:
            self.worker.stop_process()

    def on_mdrun_finished(self, success, msg):
        self.timer.stop()
        item = self.tree_steps.currentItem()
        
        self.btn_grompp.setEnabled(True); self.btn_mdrun.setEnabled(True); self.btn_stop.setEnabled(False)
        status = "Completado" if success else "Error"
        item.setText(2, status)
        self._set_status_color(item, status)
        
        if success:
            self.lbl_gmx_info.setText("FINALIZADO")
            
            next_node = None
            if self.execution_mode == 'branch':
                if item.childCount() > 0: next_node = item.child(0)
            elif self.execution_mode == 'all':
                next_node = self.find_next_pending_node(self.tree_steps.invisibleRootItem())

            if next_node:
                self.tree_steps.setCurrentItem(next_node)
                self.on_node_selected(next_node, 0)
                self.save_mdp_to_disk()
                QTimer.singleShot(1500, self.run_grompp)
                return 

            if self.execution_mode != 'single':
                QMessageBox.information(self, "Secuencia Terminada", "Se completaron las simulaciones.")
            else:
                QMessageBox.information(self, "Fin", "Simulación terminada.")
        else:
            QMessageBox.warning(self, "Error", msg)

    def find_next_pending_node(self, parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.text(2) not in ["Completado", "Error", "Corriendo..."]: return child
            res = self.find_next_pending_node(child)
            if res: return res
        return None

    # --- LOGS Y TIEMPO ---
    def show_log(self):
        item = self.tree_steps.currentItem()
        d = self.get_storage_path()
        if not item or not d: return
        log = os.path.join(d, f"{item.text(0)}.log")
        if os.path.exists(log):
            with open(log, 'r') as f: c = f.read()
            LogViewerDialog(c, f"Log {item.text(0)}").exec()
        else: QMessageBox.information(self, "Info", "No hay log.")

    def update_elapsed_time(self):
        self.elapsed_seconds_counter += 1
        self.lbl_elapsed.setText(str(datetime.timedelta(seconds=self.elapsed_seconds_counter)))

    def parse_log_output(self, text):
        l = text.strip()
        if "finish time" in l.lower(): 
            try: self.lbl_gmx_info.setText(f"Fin: {l.split(':',1)[1].strip()}")
            except: pass
        if "Rem:" in l: 
            try: self.lbl_gmx_info.setText(f"Faltan: {l.split('Rem:')[1].split('  ')[0]}")
            except: pass
        match = re.search(r"^\s*(\d+)\s+[\d\.]+", l)
        if match: 
            if "GMX" not in self.lbl_gmx_info.text():
                self.lbl_gmx_info.setText(f"Paso {match.group(1)}")

    # --- APLICAR T RAMA ---
    def apply_temp_to_branch(self):
        item = self.tree_steps.currentItem()
        if not item: return
        t = self.spin_temp.value()
        r = QMessageBox.question(self, "Aplicar", f"¿Aplicar {t}K a toda la rama?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            d = self.get_storage_path()
            if d: self._recursive_temp_update(item, t, d)
            QMessageBox.information(self, "OK", "Actualizado")

    def _recursive_temp_update(self, item, t, d):
        name = item.text(0); stype = item.text(1)
        if stype != 'minim':
            p = os.path.join(d, f"{name}.mdp")
            if os.path.exists(p):
                with open(p, 'r') as f: c = f.read()
                new_c = self.mdp_mgr.update_parameters(c, {'ref_t': t, 'gen_temp': t})
                self.mdp_mgr.save_mdp(p, new_c)
        for i in range(item.childCount()): self._recursive_temp_update(item.child(i), t, d)