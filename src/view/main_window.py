import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFileDialog, QMessageBox, 
                             QTabWidget, QFrame, QHBoxLayout, QComboBox, QInputDialog)
from PyQt6.QtCore import Qt
from src.model.project_manager import ProjectManager

from src.view.setup_tab import SetupTab 
from src.view.topology_tab import TopologyTab
from src.view.simulation_tab import SimulationTab 
from src.view.analysis_tab import AnalysisTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChemSimGUI - Gestor de Tesis")
        self.setGeometry(100, 100, 1100, 800)
        
        self.project_mgr = ProjectManager()

        main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        main_widget.setLayout(self.main_layout)
        self.setCentralWidget(main_widget)

        self.init_system_toolbar()
        
        self.tabs = QTabWidget()
        
        self.tab_home = QWidget(); self.setup_project_ui(); self.tabs.addTab(self.tab_home, "1. Proyecto")
        self.setup_tab = SetupTab(); self.tabs.addTab(self.setup_tab, "2. Setup")
        self.topo_tab = TopologyTab(); self.tabs.addTab(self.topo_tab, "3. Topología")
        self.sim_tab = SimulationTab(); self.tabs.addTab(self.sim_tab, "4. Simulación")
        self.analysis_tab = AnalysisTab(); self.tabs.addTab(self.analysis_tab, "5. Análisis")
        
        self.enable_tabs(False)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.main_layout.addWidget(self.tabs)

    def init_system_toolbar(self):
        self.system_bar = QFrame()
        self.system_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self.system_bar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #ddd;")
        
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(10, 5, 10, 5)
        
        h_layout.addWidget(QLabel("<b>Sistema Activo:</b>"))
        
        self.combo_systems = QComboBox()
        self.combo_systems.setMinimumWidth(200)
        self.combo_systems.currentIndexChanged.connect(self.on_system_changed)
        h_layout.addWidget(self.combo_systems)
        
        btn_new = QPushButton("➕ Nuevo")
        btn_new.clicked.connect(self.new_system_dialog)
        h_layout.addWidget(btn_new)
        
        btn_clone = QPushButton("content_copy Clonar")
        btn_clone.clicked.connect(self.clone_system_dialog)
        h_layout.addWidget(btn_clone)
        
        # BOTÓN ELIMINAR NUEVO
        btn_del = QPushButton("🗑️ Eliminar")
        btn_del.setStyleSheet("color: red; font-weight: bold;")
        btn_del.clicked.connect(self.delete_system_dialog)
        h_layout.addWidget(btn_del)
        
        h_layout.addStretch()
        self.lbl_path_info = QLabel("Ruta: Ninguna")
        self.lbl_path_info.setStyleSheet("color: gray; font-size: 10px;")
        h_layout.addWidget(self.lbl_path_info)
        
        self.system_bar.setLayout(h_layout)
        self.system_bar.setVisible(False) 
        
        self.main_layout.addWidget(self.system_bar)

    # --- GESTIÓN DE PROYECTO ---

    def setup_project_ui(self):
        l = QVBoxLayout(); l.setAlignment(Qt.AlignmentFlag.AlignTop)
        l.addWidget(QLabel("<h2>Gestión de Proyecto</h2>"))
        
        panel = QFrame(); panel.setFrameShape(QFrame.Shape.StyledPanel)
        pl = QVBoxLayout()
        pl.addWidget(QLabel("Nombre:")); self.input_name = QLineEdit("Tesis_01"); pl.addWidget(self.input_name)
        
        btn_create = QPushButton("Crear Nuevo"); btn_create.clicked.connect(self.create_handler); pl.addWidget(btn_create)
        btn_load = QPushButton("Cargar Existente"); btn_load.clicked.connect(self.load_handler); pl.addWidget(btn_load)
        
        panel.setLayout(pl); l.addWidget(panel)
        
        self.lbl_status = QLabel("Esperando..."); l.addWidget(self.lbl_status)
        self.tab_home.setLayout(l)

    def create_handler(self):
        name = self.input_name.text().strip()
        if not name: return
        path = QFileDialog.getExistingDirectory(self, "Dir")
        if path:
            success, msg = self.project_mgr.create_project(name, path)
            if success:
                self.project_loaded()
                QMessageBox.information(self, "OK", "Proyecto Creado")
            else:
                QMessageBox.critical(self, "Error", msg)

    def load_handler(self):
        path = QFileDialog.getExistingDirectory(self, "Dir")
        if path:
            success, msg = self.project_mgr.load_project_from_path(path)
            if success:
                self.project_loaded()
                QMessageBox.information(self, "OK", "Proyecto Cargado")
            else:
                QMessageBox.critical(self, "Error", msg)

    def project_loaded(self):
        self.enable_tabs(True)
        self.system_bar.setVisible(True)
        self.lbl_status.setText(f"Activo: {self.project_mgr.project_data['name']}")
        self.refresh_systems_combo()
        self.load_active_system_to_tabs()

    def refresh_systems_combo(self):
        self.combo_systems.blockSignals(True)
        self.combo_systems.clear()
        systems = self.project_mgr.get_system_list()
        self.combo_systems.addItems(systems)
        
        current = self.project_mgr.active_system_name
        idx = self.combo_systems.findText(current)
        if idx >= 0: self.combo_systems.setCurrentIndex(idx)
        self.combo_systems.blockSignals(False)

    # --- GESTIÓN DE SISTEMAS ---

    def on_system_changed(self):
        new_sys = self.combo_systems.currentText()
        if new_sys:
            self.project_mgr.active_system_name = new_sys
            self.project_mgr.save_db()
            self.load_active_system_to_tabs()

    def new_system_dialog(self):
        name, ok = QInputDialog.getText(self, "Nuevo Sistema", "Nombre (ej: 50_CBD):")
        if ok and name:
            success, msg = self.project_mgr.create_system(name)
            if success:
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()
            else:
                QMessageBox.warning(self, "Error", msg)

    def clone_system_dialog(self):
        name, ok = QInputDialog.getText(self, "Clonar Sistema", f"Clonar '{self.project_mgr.active_system_name}' como:")
        if ok and name:
            success, msg = self.project_mgr.clone_system(name, self.project_mgr.active_system_name)
            if success:
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()
                QMessageBox.information(self, "Clonado", "Sistema clonado.")
            else:
                QMessageBox.warning(self, "Error", msg)

    def delete_system_dialog(self):
        curr = self.project_mgr.active_system_name
        if not curr: return
        
        reply = QMessageBox.question(
            self, "Eliminar", 
            f"¿Está seguro de eliminar el sistema '{curr}'?\nEsta acción borrará todos sus archivos y NO se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.project_mgr.delete_system(curr)
            if success:
                QMessageBox.information(self, "Eliminado", msg)
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()
            else:
                QMessageBox.critical(self, "Error", msg)

    # --- PROPAGACIÓN DE DATOS A PESTAÑAS ---

    def load_active_system_to_tabs(self):
        """Carga la configuración del sistema activo en todas las pestañas"""
        sys_path = self.project_mgr.get_active_system_path()
        if not sys_path: return
        
        self.lbl_path_info.setText(f"Ruta Sistema: {sys_path}")
        
        self.setup_tab.update_project_data(self.project_mgr)
        self.setup_tab.set_state(self.project_mgr.get_tab_state("setup"))
        
        self.topo_tab.set_state(self.project_mgr.get_tab_state("topology"))
        mols = self.setup_tab.get_molecules_data()
        box = self.setup_tab.get_box_size_value()
        self.topo_tab.update_project_data(self.project_mgr, mols, box)
        
        self.sim_tab.update_project_data(self.project_mgr)
        self.sim_tab.set_state(self.project_mgr.get_tab_state("simulation"))
        
        self.analysis_tab.update_project_data(self.project_mgr)

    def on_tab_changed(self, index):
        self.save_all_states()
        if index == 2: # Topología
            mols = self.setup_tab.get_molecules_data()
            box = self.setup_tab.get_box_size_value()
            self.topo_tab.update_project_data(self.project_mgr, mols, box)
        
        if index == 3: self.sim_tab.update_project_data(self.project_mgr)
        if index == 4: self.analysis_tab.update_project_data(self.project_mgr)

    def save_all_states(self):
        if not self.project_mgr.active_system_name: return
        self.project_mgr.update_tab_state("setup", self.setup_tab.get_state())
        self.project_mgr.update_tab_state("topology", self.topo_tab.get_state())
        self.project_mgr.update_tab_state("simulation", self.sim_tab.get_state())

    def enable_tabs(self, enable):
        for i in range(1, 5): self.tabs.setTabEnabled(i, enable)
    
    def closeEvent(self, event):
        self.save_all_states()
        event.accept()