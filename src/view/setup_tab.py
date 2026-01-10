import os
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, 
    QGroupBox, QFileDialog, QMessageBox, QHBoxLayout, 
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QDoubleSpinBox, QCheckBox, QFormLayout
)
from src.model.chemistry_tools import ChemistryTools
from src.controller.workers import CommandWorker

class SetupTab(QWidget):
    def __init__(self):
        super().__init__()
        self.chem_tools = ChemistryTools()
        self.project_mgr = None
        self.worker = None
        
        # Bandera para evitar bucles de cálculo
        self.programmatic_update = False
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # ==========================================================
        # 1. COMPOSICIÓN DEL SISTEMA
        # ==========================================================
        group_mol = QGroupBox("1. Composición del Sistema")
        layout_mol = QVBoxLayout()
        
        self.table_comps = QTableWidget()
        self.table_comps.setColumnCount(5)
        self.table_comps.setHorizontalHeaderLabels([
            "Archivo PDB", "MW (g/mol)", "Cant.", "Densidad (kg/m3)", "Ruta Oculta"
        ])
        
        self.table_comps.setColumnHidden(4, True) 
        self.table_comps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_comps.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Conectar cambios para auto-cálculo
        self.table_comps.itemChanged.connect(self.on_table_data_changed)
        
        layout_mol.addWidget(self.table_comps)
        
        hbox_btns = QHBoxLayout()
        self.btn_add = QPushButton("➕ Agregar Componente")
        self.btn_add.clicked.connect(self.add_component_click)
        
        self.btn_remove = QPushButton("➖ Quitar Seleccionado")
        self.btn_remove.clicked.connect(self.remove_component)
        
        hbox_btns.addWidget(self.btn_add)
        hbox_btns.addWidget(self.btn_remove)
        
        layout_mol.addLayout(hbox_btns)
        group_mol.setLayout(layout_mol)
        layout.addWidget(group_mol)
        
        # ==========================================================
        # 2. DIMENSIONES
        # ==========================================================
        group_box = QGroupBox("2. Dimensiones de la Caja")
        form_box = QFormLayout()
        
        self.input_margin = QSpinBox()
        self.input_margin.setRange(0, 200)
        self.input_margin.setValue(10)
        self.input_margin.setSuffix(" % (Margen)")
        self.input_margin.setToolTip("Porcentaje extra al volumen para evitar choques iniciales")
        # Recalcular al cambiar margen
        self.input_margin.valueChanged.connect(self.calculate_box)
        
        self.btn_calc = QPushButton("Forzar Recálculo")
        self.btn_calc.clicked.connect(self.calculate_box)
        
        self.chk_manual = QCheckBox("Modo Manual")
        self.chk_manual.toggled.connect(self.toggle_manual_mode)
        
        self.spin_box_size = QDoubleSpinBox()
        self.spin_box_size.setRange(0.0, 10000.0)
        self.spin_box_size.setDecimals(3)
        self.spin_box_size.setSuffix(" Å")
        self.spin_box_size.setReadOnly(True)
        self.spin_box_size.setStyleSheet("font-weight: bold; color: blue;")
        
        form_box.addRow("Margen de Expansión:", self.input_margin)
        form_box.addRow("", self.btn_calc)
        form_box.addRow("", self.chk_manual)
        form_box.addRow("Lado de Caja (Cúbica):", self.spin_box_size)
        
        group_box.setLayout(form_box)
        layout.addWidget(group_box)
        
        # ==========================================================
        # 3. ACCIONES
        # ==========================================================
        
        self.btn_gen_input = QPushButton("1. Generar packmol.inp")
        self.btn_gen_input.clicked.connect(self.generate_input_file)
        self.btn_gen_input.setEnabled(False)
        
        hbox_run = QHBoxLayout()
        self.btn_run_packmol = QPushButton("2. ▶ Ejecutar Packmol")
        self.btn_run_packmol.clicked.connect(self.run_packmol_process)
        self.btn_run_packmol.setEnabled(False)
        self.btn_run_packmol.setStyleSheet("background-color: #d1e7dd; color: black; font-weight: bold;")
        
        self.btn_stop_packmol = QPushButton("⏹ Detener")
        self.btn_stop_packmol.clicked.connect(self.stop_packmol_process)
        self.btn_stop_packmol.setEnabled(False)
        self.btn_stop_packmol.setStyleSheet("background-color: #f8d7da; color: red;")
        
        self.btn_view_vmd = QPushButton("👁 Ver en VMD")
        self.btn_view_vmd.clicked.connect(self.open_vmd)
        self.btn_view_vmd.setEnabled(False)
        self.btn_view_vmd.setStyleSheet("background-color: #cff4fc; color: black;")
        
        hbox_run.addWidget(self.btn_run_packmol)
        hbox_run.addWidget(self.btn_stop_packmol)
        hbox_run.addWidget(self.btn_view_vmd)

        layout.addWidget(self.btn_gen_input)
        layout.addLayout(hbox_run)
        
        layout.addStretch()
        self.setLayout(layout)

    # ==========================================================
    # LÓGICA DE SISTEMA
    # ==========================================================

    def update_project_data(self, project_mgr):
        self.project_mgr = project_mgr
        if self.get_storage_path():
            self.btn_gen_input.setEnabled(True)

    def get_storage_path(self):
        if not self.project_mgr: return None
        return self.project_mgr.get_active_system_path()

    # ==========================================================
    # LÓGICA DE TABLA Y CÁLCULO (ROBUSTA)
    # ==========================================================

    def on_table_data_changed(self, item):
        """Detecta cambios manuales en la tabla y recalcula"""
        if self.programmatic_update: return
        
        # Solo recalculamos si cambiaron: MW(1), Cant(2), Dens(3)
        if item.column() in [1, 2, 3]:
            self.calculate_box()

    def add_component_click(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Seleccionar Componente", "", "PDB/GRO (*.pdb *.gro)")
        if fname:
            pdb_name = os.path.basename(fname)
            mw = str(self.chem_tools.get_mw_from_pdb(fname))
            self._insert_row_data(pdb_name, mw, "100", "1000.0", fname)

    def _insert_row_data(self, pdb, mw, count, dens, full_path):
        """Inserta fila de forma segura bloqueando señales"""
        # BLOQUEAR SEÑALES PARA EVITAR CRASH MIENTRAS SE LLENA LA FILA
        self.table_comps.blockSignals(True)
        
        row = self.table_comps.rowCount()
        self.table_comps.insertRow(row)
        
        self.table_comps.setItem(row, 0, QTableWidgetItem(str(pdb)))
        self.table_comps.setItem(row, 1, QTableWidgetItem(str(mw)))
        self.table_comps.setItem(row, 2, QTableWidgetItem(str(count)))
        self.table_comps.setItem(row, 3, QTableWidgetItem(str(dens)))
        self.table_comps.setItem(row, 4, QTableWidgetItem(str(full_path)))
        
        # DESBLOQUEAR SEÑALES
        self.table_comps.blockSignals(False)
        
        # Calcular una vez al final
        self.calculate_box()

    def remove_component(self):
        row = self.table_comps.currentRow()
        if row >= 0:
            self.table_comps.removeRow(row)
            self.calculate_box()

    def get_molecules_from_table(self):
        """Recopila datos de la tabla de forma segura (evita crash por None)"""
        molecules = []
        try:
            for row in range(self.table_comps.rowCount()):
                # Helper para obtener texto seguro
                def get_text(r, c):
                    item = self.table_comps.item(r, c)
                    return item.text() if item else ""

                pdb = get_text(row, 0)
                mw = get_text(row, 1)
                count = get_text(row, 2)
                dens = get_text(row, 3)
                path = get_text(row, 4)
                
                # Si falta algún dato crítico, saltamos la fila
                if not pdb or not mw or not count or not dens:
                    continue

                molecules.append({
                    'pdb': pdb,
                    'mw': float(mw),
                    'count': int(count),
                    'density_kg_m3': float(dens),
                    'full_path': path
                })
            return molecules
        except ValueError:
            return []

    def toggle_manual_mode(self, checked):
        self.spin_box_size.setReadOnly(not checked)
        self.btn_calc.setEnabled(True) # Siempre permitir forzar
        
        if checked:
            self.spin_box_size.setStyleSheet("background-color: white; color: black;")
        else:
            self.spin_box_size.setStyleSheet("font-weight: bold; color: blue;")
            self.calculate_box()

    def calculate_box(self):
        """Calcula el tamaño de la caja. A prueba de fallos."""
        # Si está en manual y no fue el botón quien llamó, no hacer nada
        if self.chk_manual.isChecked() and self.sender() != self.btn_calc:
            return

        molecules = self.get_molecules_from_table()
        if not molecules: return
        
        try:
            margin = self.input_margin.value()
            size = self.chem_tools.calculate_box_size_mixing_rule(molecules, margin)
            
            # Bloquear señal para evitar bucles infinitos con valueChanged
            self.spin_box_size.blockSignals(True)
            self.spin_box_size.setValue(size)
            self.spin_box_size.blockSignals(False)
            
        except ValueError:
            pass # Ignorar errores transitorios de cálculo

    # ==========================================================
    # GENERACIÓN Y EJECUCIÓN
    # ==========================================================

    def generate_input_file(self):
        storage_dir = self.get_storage_path()
        if not storage_dir:
            QMessageBox.warning(self, "Error", "No hay sistema activo.")
            return
            
        box_size = self.spin_box_size.value()
        if box_size <= 0:
            QMessageBox.warning(self, "Error", "Tamaño de caja inválido.")
            return

        molecules = self.get_molecules_from_table()
        if not molecules:
            QMessageBox.warning(self, "Error", "Tabla vacía.")
            return

        os.makedirs(storage_dir, exist_ok=True)

        for mol in molecules:
            dest = os.path.join(storage_dir, mol['pdb'])
            try: shutil.copy(mol['full_path'], dest)
            except Exception: pass

        inp_path = os.path.join(storage_dir, "packmol.inp")
        out_pdb = "system_init.pdb"
        
        success, msg = self.chem_tools.generate_packmol_input(inp_path, out_pdb, box_size, molecules)
        
        if success:
            QMessageBox.information(self, "Éxito", f"Input generado.\nLado: {box_size} Å")
            self.btn_run_packmol.setEnabled(True)
            self.btn_view_vmd.setEnabled(False) 
        else:
            QMessageBox.critical(self, "Error", msg)

    def run_packmol_process(self):
        storage_dir = self.get_storage_path()
        if not storage_dir: return
        inp_file = os.path.join(storage_dir, "packmol.inp")
        
        if not os.path.exists(inp_file): return
        
        self.worker = CommandWorker(["packmol"], storage_dir, input_file_path=inp_file)
        self.worker.log_signal.connect(lambda s: print(f"PKM: {s}"))
        self.worker.finished_signal.connect(self.on_packmol_finished)
        
        self.btn_run_packmol.setEnabled(False)
        self.btn_gen_input.setEnabled(False)
        self.btn_stop_packmol.setEnabled(True)
        self.btn_view_vmd.setEnabled(False)
        self.worker.start()

    def stop_packmol_process(self):
        if self.worker: self.worker.stop_process()

    def on_packmol_finished(self, success, msg):
        self.btn_run_packmol.setEnabled(True)
        self.btn_gen_input.setEnabled(True)
        self.btn_stop_packmol.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "Finalizado", "Estructura creada.")
            self.btn_view_vmd.setEnabled(True)
        else:
            QMessageBox.warning(self, "Aviso", msg)

    def open_vmd(self):
        d = self.get_storage_path()
        if d: 
            p = os.path.join(d, "system_init.pdb")
            if os.path.exists(p): 
                try: subprocess.Popen(["vmd", p])
                except: pass

    # Getters
    def get_box_size_value(self): return self.spin_box_size.value()
    def get_molecules_data(self): return self.get_molecules_from_table()
    
    # Persistencia
    def get_state(self):
        return {
            "molecules": self.get_molecules_from_table(),
            "margin": self.input_margin.value(),
            "manual_mode": self.chk_manual.isChecked(),
            "box_size": self.spin_box_size.value()
        }

    def set_state(self, state):
        if not state: return
        
        self.programmatic_update = True
        
        self.input_margin.setValue(state.get("margin", 10))
        self.chk_manual.setChecked(state.get("manual_mode", False))
        self.spin_box_size.setValue(state.get("box_size", 0.0))
        
        mols = state.get("molecules", [])
        self.table_comps.setRowCount(0)
        
        # Aquí usamos _insert_row_data que tiene blockSignals
        # para que no crashee al cargar masivamente
        for mol in mols:
            self._insert_row_data(
                mol.get('pdb', ''),
                mol.get('mw', 0),
                mol.get('count', 0),
                mol.get('density_kg_m3', 0),
                mol.get('full_path', '')
            )
            
        self.programmatic_update = False