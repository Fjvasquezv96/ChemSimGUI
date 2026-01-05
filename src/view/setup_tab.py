import os
import shutil
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                             QLineEdit, QFormLayout, QGroupBox, QFileDialog, 
                             QMessageBox, QHBoxLayout, QSpinBox)
from src.model.chemistry_tools import ChemistryTools
from src.controller.workers import CommandWorker

class SetupTab(QWidget):
    def __init__(self):
        super().__init__()
        self.chem_tools = ChemistryTools()
        self.current_project_path = None
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # --- SECCIÓN 1: Composición ---
        group_mol = QGroupBox("1. Composición del Sistema")
        form_mol = QFormLayout()
        
        self.input_pdb = QPushButton("Seleccionar PDB (Soluto/Solvente)")
        self.input_pdb.clicked.connect(self.select_pdb)
        self.lbl_pdb_path = QLabel("Ninguno")
        self.pdb_full_path = ""
        
        self.input_mw = QLineEdit("18.015")
        self.input_count = QLineEdit("1000")
        
        form_mol.addRow("Estructura:", self.input_pdb)
        form_mol.addRow("Ruta:", self.lbl_pdb_path)
        form_mol.addRow("Peso Molecular (g/mol):", self.input_mw)
        form_mol.addRow("Cantidad:", self.input_count)
        group_mol.setLayout(form_mol)
        layout.addWidget(group_mol)
        
        # --- SECCIÓN 2: Geometría y Configuración ---
        group_box = QGroupBox("2. Configuración de Caja")
        form_box = QFormLayout()
        
        # Cambio a kg/m3
        self.input_density = QLineEdit("997.0") # Agua a 25C aprox
        
        # Nuevo campo: Margen
        self.input_margin = QSpinBox()
        self.input_margin.setRange(0, 100) # De 0% a 100%
        self.input_margin.setValue(10)     # Default 10%
        self.input_margin.setSuffix(" %")
        
        self.btn_calc = QPushButton("Calcular Caja")
        self.btn_calc.clicked.connect(self.calculate_box)
        
        self.lbl_result_box = QLabel("---")
        self.lbl_result_box.setStyleSheet("font-weight: bold; color: blue; font-size: 14px;")
        
        form_box.addRow("Densidad (kg/m³):", self.input_density)
        form_box.addRow("Margen de expansión:", self.input_margin)
        form_box.addRow(self.btn_calc)
        form_box.addRow("Tamaño de Caja (Å):", self.lbl_result_box)
        group_box.setLayout(form_box)
        layout.addWidget(group_box)
        
        # --- BOTONES DE CONTROL ---
        self.btn_gen_input = QPushButton("Generar packmol.inp")
        self.btn_gen_input.clicked.connect(self.generate_input_file)
        self.btn_gen_input.setEnabled(False)
        
        # Layout horizontal para Ejecutar y Detener
        hbox_run = QHBoxLayout()
        
        self.btn_run_packmol = QPushButton("▶ Ejecutar Packmol")
        self.btn_run_packmol.clicked.connect(self.run_packmol_process)
        self.btn_run_packmol.setEnabled(False)
        self.btn_run_packmol.setStyleSheet("background-color: #d1e7dd; color: black; font-weight: bold;")
        
        self.btn_stop_packmol = QPushButton("⏹ Detener")
        self.btn_stop_packmol.clicked.connect(self.stop_packmol_process)
        self.btn_stop_packmol.setEnabled(False) # Se activa solo al correr
        self.btn_stop_packmol.setStyleSheet("background-color: #f8d7da; color: red;")
        
        hbox_run.addWidget(self.btn_run_packmol)
        hbox_run.addWidget(self.btn_stop_packmol)

        layout.addWidget(self.btn_gen_input)
        layout.addLayout(hbox_run)
        layout.addStretch()
        self.setLayout(layout)

    # --- LÓGICA ---

    def set_active_project(self, path):
        self.current_project_path = path
        self.btn_gen_input.setEnabled(True)

    def select_pdb(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDB", "", "PDB Files (*.pdb *.gro)")
        if fname:
            self.pdb_full_path = fname
            self.lbl_pdb_path.setText(os.path.basename(fname))

    def calculate_box(self):
        try:
            mw = float(self.input_mw.text())
            cnt = int(self.input_count.text())
            dens_kg_m3 = float(self.input_density.text())
            margin = self.input_margin.value()
            
            # Llamamos a la nueva función con kg/m3 y margen
            size = self.chem_tools.calculate_box_size(
                [{'mw': mw, 'count': cnt}], 
                dens_kg_m3,
                margin
            )
            self.lbl_result_box.setText(str(size))
        except ValueError:
            self.lbl_result_box.setText("Error Numérico")

    def generate_input_file(self):
        if not self.current_project_path: return

        try:
            box_size = float(self.lbl_result_box.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Calcule primero el tamaño de la caja.")
            return

        if not self.pdb_full_path:
            QMessageBox.warning(self, "Error", "Seleccione un PDB.")
            return

        storage_dir = os.path.join(self.current_project_path, "storage")
        os.makedirs(storage_dir, exist_ok=True)

        pdb_filename = os.path.basename(self.pdb_full_path)
        dest_pdb_path = os.path.join(storage_dir, pdb_filename)
        
        try:
            shutil.copy(self.pdb_full_path, dest_pdb_path)
        except Exception:
            pass # Si es el mismo archivo no pasa nada

        inp_path = os.path.join(storage_dir, "packmol.inp")
        out_pdb = "system_init.pdb"

        molecules = [{'pdb': pdb_filename, 'count': int(self.input_count.text())}]
        
        success, msg = self.chem_tools.generate_packmol_input(inp_path, out_pdb, box_size, molecules)
        
        if success:
            QMessageBox.information(self, "Éxito", f"Input generado.\nMargen aplicado: {self.input_margin.value()}%")
            self.btn_run_packmol.setEnabled(True)
        else:
            QMessageBox.critical(self, "Error", msg)

    def run_packmol_process(self):
        storage_dir = os.path.join(self.current_project_path, "storage")
        inp_file = os.path.join(storage_dir, "packmol.inp")
        
        if not os.path.exists(inp_file): return

        cmd = ["packmol"]
        self.worker = CommandWorker(cmd, storage_dir, input_file_path=inp_file)
        
        self.worker.log_signal.connect(lambda s: print(f"PKM: {s}"))
        self.worker.finished_signal.connect(self.on_packmol_finished)
        
        # Actualizar estado de botones
        self.btn_run_packmol.setEnabled(False)
        self.btn_gen_input.setEnabled(False)
        self.btn_stop_packmol.setEnabled(True) # Habilitar botón STOP
        
        self.worker.start()

    def stop_packmol_process(self):
        """Llamado al presionar Detener"""
        if self.worker and self.worker.isRunning():
            self.worker.stop_process()
            # La señal finished_signal se encargará de resetear los botones

    def on_packmol_finished(self, success, msg):
        # Restaurar botones
        self.btn_run_packmol.setEnabled(True)
        self.btn_gen_input.setEnabled(True)
        self.btn_stop_packmol.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "Finalizado", "Estructura creada correctamente.")
        else:
            QMessageBox.warning(self, "Proceso Interrumpido/Fallido", msg)