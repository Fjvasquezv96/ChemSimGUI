from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFormLayout, QGroupBox, QFileDialog)
from src.model.chemistry_tools import ChemistryTools

class SetupTab(QWidget):
    def __init__(self):
        super().__init__()
        self.chem_tools = ChemistryTools()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # --- SECCIÓN 1: Definición de Moléculas (Simplificado para demo) ---
        group_mol = QGroupBox("1. Composición del Sistema")
        form_mol = QFormLayout()
        
        self.input_pdb = QPushButton("Seleccionar PDB (Soluto/Solvente)")
        self.input_pdb.clicked.connect(self.select_pdb)
        self.lbl_pdb_path = QLabel("Ningún archivo seleccionado")
        
        self.input_mw = QLineEdit("18.015") # Defecto: Agua
        self.input_count = QLineEdit("1000")
        
        form_mol.addRow("Estructura:", self.input_pdb)
        form_mol.addRow("Ruta:", self.lbl_pdb_path)
        form_mol.addRow("Peso Molecular (g/mol):", self.input_mw)
        form_mol.addRow("Cantidad de Moléculas:", self.input_count)
        
        group_mol.setLayout(form_mol)
        layout.addWidget(group_mol)
        
        # --- SECCIÓN 2: Geometría de Caja ---
        group_box = QGroupBox("2. Geometría y Packmol")
        form_box = QFormLayout()
        
        self.input_density = QLineEdit("0.997") # Defecto: Agua a 25C
        self.btn_calc = QPushButton("Calcular Tamaño de Caja Automático")
        self.btn_calc.clicked.connect(self.calculate_box)
        
        self.lbl_result_box = QLabel("---")
        self.lbl_result_box.setStyleSheet("font-weight: bold; color: blue;")
        
        form_box.addRow("Densidad Objetivo (g/cm3):", self.input_density)
        form_box.addRow(self.btn_calc)
        form_box.addRow("Tamaño Calculado (Angstroms):", self.lbl_result_box)
        
        group_box.setLayout(form_box)
        layout.addWidget(group_box)
        
        # --- Botón Final ---
        self.btn_generate = QPushButton("Generar Input Packmol")
        # Aquí conectaremos con la lógica de escribir archivo más adelante
        layout.addWidget(self.btn_generate)
        
        layout.addStretch()
        self.setLayout(layout)

    def select_pdb(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDB", "", "PDB Files (*.pdb *.gro)")
        if fname:
            self.lbl_pdb_path.setText(fname)

    def calculate_box(self):
        try:
            # Recolectar datos de la GUI
            mw = float(self.input_mw.text())
            count = int(self.input_count.text())
            dens = float(self.input_density.text())
            
            # Crear lista de moléculas (en el futuro esto vendrá de una tabla)
            molecules = [{'mw': mw, 'count': count}]
            
            # Usar el modelo para calcular
            size = self.chem_tools.calculate_box_size(molecules, dens)
            
            self.lbl_result_box.setText(f"{size:.2f} Å (Cúbica)")
            
        except ValueError:
            self.lbl_result_box.setText("Error: Revise que los valores sean números")