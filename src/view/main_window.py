import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFileDialog, QMessageBox, 
                             QTabWidget, QFrame)
from PyQt6.QtCore import Qt
from src.model.project_manager import ProjectManager
from src.view.setup_tab import SetupTab 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChemSimGUI - Gestor de Tesis")
        self.setGeometry(100, 100, 900, 650)
        
        # Instanciar el gestor lógico
        self.project_mgr = ProjectManager()

        # Widget central con pestañas
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # --- INICIALIZACIÓN DE PESTAÑAS ---
        
        # 1. Crear la pestaña de INICIO (Proyecto)
        self.tab_home = QWidget()
        self.setup_project_ui() # Llamamos a la función que dibuja los botones
        self.tabs.addTab(self.tab_home, "1. Inicio / Proyecto")
        
        # 2. Crear la pestaña de CONFIGURACIÓN (Importada de setup_tab.py)
        self.setup_tab = SetupTab() 
        self.tabs.addTab(self.setup_tab, "2. Configuración del Sistema")
        
        # Deshabilitamos la pestaña 2 hasta que se cree un proyecto
        self.tabs.setTabEnabled(1, False) 

    def setup_project_ui(self):
        """Diseño visual de la pestaña Inicio"""
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Título
        title = QLabel("Bienvenido al Gestor de Simulaciones")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # --- PANEL DE CREACIÓN ---
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 10px;")
        panel_layout = QVBoxLayout()
        
        # Paso 1: Nombre
        panel_layout.addWidget(QLabel("Paso 1: Defina el nombre del nuevo proyecto"))
        self.input_name = QLineEdit("Mi_Tesis_Simulacion_01")
        self.input_name.setStyleSheet("padding: 5px; font-size: 14px;")
        panel_layout.addWidget(self.input_name)
        
        panel_layout.addSpacing(10) # Espacio vacío
        
        # Paso 2: Botón
        panel_layout.addWidget(QLabel("Paso 2: Seleccione dónde guardar la carpeta"))
        self.btn_create = QPushButton("📂 Seleccionar Ruta y Crear Proyecto")
        self.btn_create.setMinimumHeight(40)
        self.btn_create.setStyleSheet("background-color: #007bff; color: white; font-weight: bold;")
        self.btn_create.clicked.connect(self.create_project_handler)
        panel_layout.addWidget(self.btn_create)
        
        panel.setLayout(panel_layout)
        layout.addWidget(panel)
        
        # --- ESTADO ---
        layout.addSpacing(20)
        self.lbl_status = QLabel("Estado: Esperando creación de proyecto...")
        self.lbl_status.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.lbl_status)
        
        self.lbl_path_info = QLabel("")
        layout.addWidget(self.lbl_path_info)
        
        self.tab_home.setLayout(layout)

    def create_project_handler(self):
        """Lógica al presionar el botón azul"""
        # 1. Validar que haya nombre
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Por favor escriba un nombre para el proyecto.")
            return

        # 2. Abrir selector de carpetas
        # Nota: El usuario elige la carpeta PADRE (ej. Escritorio)
        root_path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Raíz donde se guardará el proyecto")
        
        if root_path:
            # 3. Llamar al manager para crear las carpetas físicas
            success, msg = self.project_mgr.create_project(name, root_path)
            
            if success:
                # Actualizar interfaz visual
                self.lbl_status.setText(f"✅ PROYECTO ACTIVO: {name}")
                self.lbl_status.setStyleSheet("color: green; font-weight: bold; font-size: 14px;")
                
                full_path = self.project_mgr.current_project_path
                self.lbl_path_info.setText(f"Ruta: {full_path}")
                
                # Desbloquear la pestaña 2 y avisarle la ruta
                self.tabs.setTabEnabled(1, True)
                self.setup_tab.set_active_project(full_path)
                
                QMessageBox.information(self, "Proyecto Creado", 
                                      f"Se ha creado la carpeta:\n{full_path}\n\nAhora puede pasar a la pestaña 'Configuración'.")
            else:
                self.lbl_status.setText(f"❌ Error: {msg}")
                self.lbl_status.setStyleSheet("color: red;")