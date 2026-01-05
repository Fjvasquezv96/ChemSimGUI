import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFileDialog, QMessageBox, QTabWidget)
from src.model.project_manager import ProjectManager
# IMPORTANTE: Importamos la nueva pestaña
from src.view.setup_tab import SetupTab 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulador Tesis Ing. Química")
        self.setGeometry(100, 100, 900, 600)
        
        self.project_mgr = ProjectManager()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Inicializar Pestañas
        self.setup_project_tab()
        
        # AQUI USAMOS LA NUEVA CLASE
        self.setup_tab = SetupTab() 
        self.tabs.addTab(self.setup_tab, "Configuración del Sistema")

    def setup_project_tab(self):
        """Pestaña 1: Gestión de Proyecto"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<h2>Gestión de Proyecto</h2>"))
        layout.addWidget(QLabel("Nombre del Proyecto:"))
        
        self.input_name = QLineEdit("Nuevo_Proyecto")
        layout.addWidget(self.input_name)
        
        btn_create = QPushButton("Crear / Seleccionar Directorio")
        btn_create.clicked.connect(self.create_project_handler)
        layout.addWidget(btn_create)
        
        self.lbl_status = QLabel("Estado: Esperando...")
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        self.tabs.addTab(tab, "Inicio")

    def create_project_handler(self):
        root_path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Raíz")
        if root_path:
            name = self.input_name.text()
            success, msg = self.project_mgr.create_project(name, root_path)
            if success:
                self.lbl_status.setText(f"Activo: {msg}")
                self.lbl_status.setStyleSheet("color: green")
                QMessageBox.information(self, "Éxito", msg)
            else:
                self.lbl_status.setText(f"Error: {msg}")