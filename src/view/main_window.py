import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFileDialog, QMessageBox, 
                             QTabWidget, QFrame, QHBoxLayout, QComboBox, QInputDialog,
                             QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt
from src.model.project_manager import ProjectManager

from src.view.setup_tab import SetupTab 
from src.view.topology_tab import TopologyTab
from src.view.simulation_tab import SimulationTab 
from src.view.analysis_tab import AnalysisTab
from src.view.comparative_tab import ComparativeTab
from src.view.solubility_tab import SolubilityTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChemSimGUI - Gestor de Tesis en Ingeniería Química")
        self.setGeometry(100, 100, 1200, 850)
        
        self.project_mgr = ProjectManager()

        main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        main_widget.setLayout(self.main_layout)
        self.setCentralWidget(main_widget)

        # Barra Superior
        self.init_system_toolbar()
        
        # Pestañas
        self.tabs = QTabWidget()
        
        self.tab_home = QWidget(); self.setup_project_ui(); self.tabs.addTab(self.tab_home, "1. Proyecto")
        self.setup_tab = SetupTab(); self.tabs.addTab(self.setup_tab, "2. Setup")
        self.topo_tab = TopologyTab(); self.tabs.addTab(self.topo_tab, "3. Topología")
        self.sim_tab = SimulationTab(); self.tabs.addTab(self.sim_tab, "4. Simulación")
        self.analysis_tab = AnalysisTab(); self.tabs.addTab(self.analysis_tab, "5. Análisis")
        self.comp_tab = ComparativeTab(); self.tabs.addTab(self.comp_tab, "6. Comparativa")
        self.sol_tab = SolubilityTab()
        self.tabs.addTab(self.sol_tab, "7. Solubilidad (SLE)")
        self.enable_tabs(False)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.main_layout.addWidget(self.tabs)

        # Cargar lista de recientes al inicio
        self.refresh_recent_list()

    def init_system_toolbar(self):
        self.system_bar = QFrame()
        self.system_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self.system_bar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #ddd;")
        
        h = QHBoxLayout(); h.setContentsMargins(10, 5, 10, 5)
        h.addWidget(QLabel("<b>Sistema Activo:</b>"))
        
        self.combo_systems = QComboBox()
        self.combo_systems.setMinimumWidth(200)
        self.combo_systems.currentIndexChanged.connect(self.on_system_changed)
        h.addWidget(self.combo_systems)
        
        btn_new = QPushButton("➕ Nuevo")
        btn_new.clicked.connect(self.new_system_dialog)
        h.addWidget(btn_new)
        
        btn_clone = QPushButton("⎘ Clonar")
        btn_clone.clicked.connect(self.clone_system_dialog)
        h.addWidget(btn_clone)
        
        btn_del = QPushButton("🗑️ Eliminar")
        btn_del.setStyleSheet("color: red;")
        btn_del.clicked.connect(self.delete_system_dialog)
        h.addWidget(btn_del)
        
        h.addStretch()
        self.lbl_path_info = QLabel("Ruta: -")
        h.addWidget(self.lbl_path_info)
        
        self.system_bar.setLayout(h)
        self.system_bar.setVisible(False) 
        self.main_layout.addWidget(self.system_bar)

    # --- PESTAÑA INICIO (RECIENTES) ---

    def setup_project_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        layout.addWidget(QLabel("<h2>Bienvenido al Gestor de Simulaciones</h2>"))
        
        # Panel Principal
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setStyleSheet("background-color: #f0f0f0; border-radius: 8px; padding: 20px;")
        pl = QVBoxLayout()
        
        pl.addWidget(QLabel("<b>Crear Nuevo Proyecto:</b>"))
        self.input_name = QLineEdit("Tesis_Simulacion_01")
        pl.addWidget(self.input_name)
        
        btn_create = QPushButton("📂 Seleccionar Ruta y Crear")
        btn_create.setMinimumHeight(40)
        btn_create.setStyleSheet("background-color: #007bff; color: white; font-weight: bold;")
        btn_create.clicked.connect(self.create_handler)
        pl.addWidget(btn_create)
        
        pl.addSpacing(15)
        
        btn_load = QPushButton("📂 Cargar Proyecto desde Disco")
        btn_load.setMinimumHeight(40)
        btn_load.clicked.connect(self.load_handler)
        pl.addWidget(btn_load)
        
        panel.setLayout(pl)
        layout.addWidget(panel)
        
        # --- LISTA DE RECIENTES ---
        layout.addSpacing(20)
        layout.addWidget(QLabel("<b>Proyectos Recientes:</b>"))
        
        self.list_recent = QListWidget()
        self.list_recent.setMaximumHeight(150)
        self.list_recent.itemDoubleClicked.connect(self.on_recent_clicked)
        self.list_recent.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        layout.addWidget(self.list_recent)
        
        self.lbl_status = QLabel("Estado: Esperando...")
        self.lbl_status.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.lbl_status)
        
        self.tab_home.setLayout(layout)

    def refresh_recent_list(self):
        """Llena la lista de recientes desde el manager"""
        self.list_recent.clear()
        recents = self.project_mgr.get_recent_projects()
        
        if not recents:
            self.list_recent.addItem("No hay proyectos recientes.")
            self.list_recent.setEnabled(False)
        else:
            self.list_recent.setEnabled(True)
            for path in recents:
                name = os.path.basename(path)
                item = QListWidgetItem(f"{name}  ({path})")
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.list_recent.addItem(item)

    def on_recent_clicked(self, item):
        """Manejador al hacer doble clic en un reciente"""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            success, msg = self.project_mgr.load_project_from_path(path)
            if success:
                self.project_loaded()
            else:
                QMessageBox.critical(self, "Error", msg)
        else:
            QMessageBox.warning(self, "Error", "La carpeta del proyecto ya no existe.")

    def create_handler(self):
        name = self.input_name.text().strip()
        if not name: return
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Raíz")
        if path:
            success, msg = self.project_mgr.create_project(name, path)
            if success:
                self.project_loaded()
                QMessageBox.information(self, "Éxito", "Proyecto creado.")
            else:
                QMessageBox.critical(self, "Error", msg)

    def load_handler(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Proyecto")
        if path:
            success, msg = self.project_mgr.load_project_from_path(path)
            if success:
                self.project_loaded()
            else:
                QMessageBox.critical(self, "Error", msg)

    def project_loaded(self):
        self.enable_tabs(True)
        self.system_bar.setVisible(True)
        self.lbl_status.setText(f"Activo: {self.project_mgr.project_data['name']}")
        
        self.refresh_systems_combo()
        self.refresh_recent_list() # Actualizar la lista al cargar uno
        self.load_active_system_to_tabs()
        
        # Cargar estado global
        self.comp_tab.set_state(self.project_mgr.get_global_state("comparative"))
        self.sol_tab.set_state(self.project_mgr.get_global_state("solubility"))

    def refresh_systems_combo(self):
        self.combo_systems.blockSignals(True)
        self.combo_systems.clear()
        self.combo_systems.addItems(self.project_mgr.get_system_list())
        
        current = self.project_mgr.active_system_name
        idx = self.combo_systems.findText(current) if current else 0
        if idx >= 0: self.combo_systems.setCurrentIndex(idx)
        self.combo_systems.blockSignals(False)

    def on_system_changed(self):
        sys_name = self.combo_systems.currentText()
        if sys_name:
            self.project_mgr.active_system_name = sys_name
            self.project_mgr.save_db()
            self.load_active_system_to_tabs()

    def new_system_dialog(self):
        name, ok = QInputDialog.getText(self, "Nuevo", "Nombre del Sistema:")
        if ok and name.strip():
            if self.project_mgr.create_system(name.strip()):
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()
                QMessageBox.information(self, "Éxito", "Sistema creado.")

    def clone_system_dialog(self):
        curr = self.project_mgr.active_system_name
        if not curr: return
        name, ok = QInputDialog.getText(self, "Clonar", f"Clonar '{curr}' como:")
        if ok and name.strip():
            if self.project_mgr.clone_system(name.strip(), curr):
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()
                QMessageBox.information(self, "Éxito", "Sistema clonado.")

    def delete_system_dialog(self):
        curr = self.project_mgr.active_system_name
        if not curr: return
        r = QMessageBox.question(self, "Borrar", f"¿Eliminar '{curr}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            if self.project_mgr.delete_system(curr):
                self.refresh_systems_combo()
                self.load_active_system_to_tabs()

    def load_active_system_to_tabs(self):
        path = self.project_mgr.get_active_system_path()
        if not path:
            self.lbl_path_info.setText("Ruta: N/A")
            return
        
        self.lbl_path_info.setText(f"Ruta: {path}")
        
        self.setup_tab.update_project_data(self.project_mgr)
        self.setup_tab.set_state(self.project_mgr.get_tab_state("setup"))
        
        self.topo_tab.set_state(self.project_mgr.get_tab_state("topology"))
        self.topo_tab.update_project_data(self.project_mgr, self.setup_tab.get_molecules_data(), self.setup_tab.get_box_size_value())
        
        self.sim_tab.update_project_data(self.project_mgr)
        self.sim_tab.set_state(self.project_mgr.get_tab_state("simulation"))
        
        self.analysis_tab.update_project_data(self.project_mgr)
        self.analysis_tab.set_state(self.project_mgr.get_tab_state("analysis"))
        
        self.comp_tab.update_project_data(self.project_mgr)
        self.sol_tab.update_project_data(self.project_mgr)

    def on_tab_changed(self, index):
        self.save_all_states()
        
        if index == 2:
            self.topo_tab.update_project_data(self.project_mgr, self.setup_tab.get_molecules_data(), self.setup_tab.get_box_size_value())
        elif index == 3: self.sim_tab.update_project_data(self.project_mgr)
        elif index == 4: self.analysis_tab.update_project_data(self.project_mgr)
        elif index == 5: self.comp_tab.update_project_data(self.project_mgr)
        elif index == 6: self.sol_tab.update_project_data(self.project_mgr)

    def save_all_states(self):
        if not self.project_mgr.active_system_name: return
        self.project_mgr.update_tab_state("setup", self.setup_tab.get_state())
        self.project_mgr.update_tab_state("topology", self.topo_tab.get_state())
        self.project_mgr.update_tab_state("simulation", self.sim_tab.get_state())
        self.project_mgr.update_tab_state("analysis", self.analysis_tab.get_state())
        self.project_mgr.update_global_state("comparative", self.comp_tab.get_state())
        self.project_mgr.update_global_state("solubility", self.sol_tab.get_state())
        self.project_mgr.save_db()

    def enable_tabs(self, enable):
        for i in range(1, 7): self.tabs.setTabEnabled(i, enable)
    
    def closeEvent(self, event):
        self.save_all_states()
        event.accept()