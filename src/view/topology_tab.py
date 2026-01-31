import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, 
    QGroupBox, QFormLayout, QFileDialog, QMessageBox, 
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QListWidget, QHBoxLayout, QCheckBox
)
from PyQt6.QtCore import Qt
from src.model.chemistry_tools import ChemistryTools
from src.model.analysis_parser import AnalysisParser
from src.controller.workers import CommandWorker

class TopologyTab(QWidget):
    def __init__(self):
        super().__init__()
        
        # Instancias de lógica
        self.chem_tools = ChemistryTools()
        self.parser = AnalysisParser()
        
        # Referencias al estado del proyecto
        self.project_mgr = None 
        self.current_project_path = None
        
        # Datos temporales
        self.molecules_data = [] 
        self.box_size_nm = 0.0
        
        # Inicializar interfaz
        self.init_ui()

    def init_ui(self):
        """Construye la interfaz gráfica"""
        layout = QVBoxLayout()
        
        # ==========================================================
        # SECCIÓN 1: ESTRUCTURA (AUTOMATIZACIÓN SYSTEM.GRO)
        # ==========================================================
        group_struc = QGroupBox("1. Estructura (system.gro)")
        layout_struc = QVBoxLayout()
        
        # Etiqueta de estado que reemplaza al botón manual
        # Informa al usuario lo que está pasando en background
        self.lbl_gro_status = QLabel("Estado: Esperando datos...")
        self.lbl_gro_status.setStyleSheet("color: gray; font-style: italic;")
        self.lbl_gro_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout_struc.addWidget(self.lbl_gro_status)
        
        group_struc.setLayout(layout_struc)
        layout.addWidget(group_struc)
        
        # ==========================================================
        # SECCIÓN 2: CONSTRUCTOR DE TOPOLOGÍA
        # ==========================================================
        group_top = QGroupBox("2. Constructor de Topología (topol.top)")
        layout_top = QVBoxLayout()
        
        # Selector de Campo de Fuerza
        form_ff = QFormLayout()
        self.combo_ff = QComboBox()
        self.combo_ff.addItems(["oplsaa.ff", "amber99sb.ff", "charmm36.ff", "gromos54a7.ff"])
        
        form_ff.addRow("Campo de Fuerza Base:", self.combo_ff)
        layout_top.addLayout(form_ff)
        
        # Opción de Sanitización (Auto-corrección)
        self.chk_sanitize = QCheckBox("🛠️ Auto-corregir ITPs (Extraer [atomtypes] y evitar colisiones)")
        self.chk_sanitize.setChecked(True)
        self.chk_sanitize.setToolTip("Separa los atomtypes en un archivo maestro y renombra átomos duplicados.")
        layout_top.addWidget(self.chk_sanitize)
        
        # Lista de Includes Globales
        layout_top.addWidget(QLabel("Includes Globales Manuales (ej: atomtypes extra):"))
        self.list_globals = QListWidget()
        self.list_globals.setMaximumHeight(60)
        layout_top.addWidget(self.list_globals)
        
        # Botones para Includes Globales
        hbox_glob = QHBoxLayout()
        btn_add_glob = QPushButton("Cargar Include (.itp)")
        btn_add_glob.clicked.connect(self.add_global_include)
        
        btn_del_glob = QPushButton("Borrar Seleccionado")
        btn_del_glob.clicked.connect(self.remove_global_include)
        
        hbox_glob.addWidget(btn_add_glob)
        hbox_glob.addWidget(btn_del_glob)
        layout_top.addLayout(hbox_glob)

        # Tabla de Asignación de Moléculas
        layout_top.addWidget(QLabel("Asignación de Topologías por Componente:"))
        self.table_mols = QTableWidget()
        self.table_mols.setColumnCount(3)
        self.table_mols.setHorizontalHeaderLabels([
            "Componente (Input)", 
            "Nombre [ moleculetype ]", 
            "Archivo .itp"
        ])
        self.table_mols.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout_top.addWidget(self.table_mols)
        
        # Opciones finales (Agua)
        self.chk_water = QCheckBox("Incluir Agua Estándar (spce/ions)")
        self.chk_water.setChecked(False) # Default false para control total
        layout_top.addWidget(self.chk_water)

        # Botón de Generación Final
        self.btn_gen_top = QPushButton("Generar topol.top")
        self.btn_gen_top.clicked.connect(self.generate_topology)
        self.btn_gen_top.setEnabled(False)
        self.btn_gen_top.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
        
        layout_top.addWidget(self.btn_gen_top)
        
        group_top.setLayout(layout_top)
        layout.addWidget(group_top)
        
        layout.addStretch()
        self.setLayout(layout)

    # ==========================================================
    # LÓGICA DE SISTEMA (RUTAS DINÁMICAS)
    # ==========================================================

    def get_storage_path(self):
        """Obtiene la ruta de almacenamiento del SISTEMA ACTIVO"""
        if self.project_mgr:
            return self.project_mgr.get_active_system_path()
        return None

    def update_project_data(self, project_mgr, molecules, box_size_angstrom=0.0):
        """
        Se llama automáticamente cuando el usuario entra a esta pestaña o cambia de sistema.
        Recibe los datos frescos de SetupTab.
        """
        self.project_mgr = project_mgr
        self.current_project_path = project_mgr.current_project_path
        
        self.molecules_data = molecules
        
        # Convertir Å a nm (GROMACS usa nm)
        self.box_size_nm = box_size_angstrom / 10.0
        
        # Habilitar interfaz
        self.btn_gen_top.setEnabled(True)
        
        # Refrescar la tabla con los datos nuevos
        self.refresh_table()

        # DISPARO AUTOMÁTICO DE EDITCONF
        self.run_editconf_auto()

    # ==========================================================
    # AUTOMATIZACIÓN DE ESTRUCTURA (EDITCONF)
    # ==========================================================

    def run_editconf_auto(self):
        """Ejecuta editconf en segundo plano para aplicar el tamaño de caja"""
        storage_dir = self.get_storage_path()
        if not storage_dir:
            return
            
        pdb_file = os.path.join(storage_dir, "system_init.pdb")
        
        if not os.path.exists(pdb_file):
            self.lbl_gro_status.setText("⚠️ Alerta: No se encontró system_init.pdb (Ejecute Packmol primero)")
            self.lbl_gro_status.setStyleSheet("color: orange; font-weight: bold;")
            return
            
        if self.box_size_nm <= 0:
            self.lbl_gro_status.setText("⚠️ Alerta: Tamaño de caja es 0 (Configure en Pestaña 2)")
            return

        # Actualizar UI para mostrar trabajo
        self.lbl_gro_status.setText("⏳ Generando system.gro con dimensiones actualizadas...")
        self.lbl_gro_status.setStyleSheet("color: blue;")

        # Comando con caja explícita (-box)
        val = str(self.box_size_nm)
        cmd = ["gmx", "editconf", "-f", "system_init.pdb", "-o", "system.gro", "-box", val, val, val]
        
        self.worker = CommandWorker(cmd, storage_dir)
        # Conectar señal de fin
        self.worker.finished_signal.connect(self.on_editconf_finished)
        self.worker.start()

    def on_editconf_finished(self, success, msg):
        """Callback al terminar editconf"""
        if success:
            self.lbl_gro_status.setText(f"✅ system.gro generado exitosamente (Caja: {self.box_size_nm} nm)")
            self.lbl_gro_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_gro_status.setText("❌ Error generando system.gro (Ver logs)")
            self.lbl_gro_status.setStyleSheet("color: red; font-weight: bold;")
            # Solo popup si falla crítico
            QMessageBox.warning(self, "Error GROMACS", f"Falló editconf:\n{msg}")

    # ==========================================================
    # GESTIÓN DE TABLA Y ARCHIVOS
    # ==========================================================

    def refresh_table(self):
        """Refresca la tabla de moléculas manteniendo asignaciones previas si existen"""
        self.table_mols.setRowCount(len(self.molecules_data))
        
        # Intentar recuperar mapeo guardado (si venimos de una carga de proyecto)
        # Este atributo se setea en set_state
        mapping = getattr(self, 'saved_itp_mapping', {})
        
        for i, mol in enumerate(self.molecules_data):
            # Col 0: Nombre PDB original
            self.table_mols.setItem(i, 0, QTableWidgetItem(mol['pdb']))
            
            # Col 1: Nombre sugerido (3 letras mayúsculas)
            # Ej: 'solute.pdb' -> 'SOLU'
            guess = os.path.splitext(mol['pdb'])[0][:4].upper()
            if "agua" in mol['pdb'].lower() or "water" in mol['pdb'].lower():
                guess = "SOL"
            self.table_mols.setItem(i, 1, QTableWidgetItem(guess))
            
            # Col 2: ITP (Botón)
            # Verificamos si ya teníamos un ITP asignado para este PDB
            prev_itp = mapping.get(mol['pdb'])
            
            btn = QPushButton()
            if prev_itp:
                # Si ya existía, mostramos el nombre en el botón
                btn.setText(prev_itp)
                btn.setStyleSheet("text-align: left; padding-left: 5px;")
            else:
                btn.setText("Cargar .itp")
            
            # Conectar botón pasando la fila específica con lambda
            btn.clicked.connect(lambda ch, r=i: self.select_itp_mol(r))
            
            self.table_mols.setCellWidget(i, 2, btn)

    def select_itp_mol(self, row):
        """Abre diálogo y copia el ITP a la carpeta del sistema"""
        f, _ = QFileDialog.getOpenFileName(self, "Seleccionar ITP", "", "GROMACS Top (*.itp)")
        if f:
            storage_dir = self.get_storage_path()
            if storage_dir:
                try:
                    # Copiar archivo al sistema activo
                    shutil.copy(f, os.path.join(storage_dir, os.path.basename(f)))
                except Exception as e:
                    print(f"Error copiando ITP: {e}")
            
            # Actualizar texto del botón en esa fila
            btn = self.table_mols.cellWidget(row, 2)
            if btn:
                btn.setText(os.path.basename(f))
                btn.setStyleSheet("text-align: left; padding-left: 5px; font-weight: bold;")

    def add_global_include(self):
        """Carga un include global (ej atomtypes.itp)"""
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar Includes", "", "ITP Files (*.itp)")
        storage_dir = self.get_storage_path()
        
        if files and storage_dir:
            for f in files:
                try:
                    shutil.copy(f, os.path.join(storage_dir, os.path.basename(f)))
                    self.list_globals.addItem(os.path.basename(f))
                except Exception as e:
                    print(f"Error copiando global: {e}")

    def remove_global_include(self):
        """Borra el include seleccionado de la lista"""
        row = self.list_globals.currentRow()
        if row >= 0:
            self.list_globals.takeItem(row)

    # ==========================================================
    # LÓGICA DE GENERACIÓN DE TOPOLOGÍA
    # ==========================================================

    def generate_topology(self):
        storage_dir = self.get_storage_path()
        if not storage_dir:
            return
            
        top_file = os.path.join(storage_dir, "topol.top")
        
        # 1. Recoger datos de la GUI
        raw_mol_itps = [] 
        final_mols_list = []
        
        # Mapa: índice de fila -> nombre de archivo ITP original
        # Esto sirve para luego mapear el nombre real de la molécula
        row_to_itp_map = {} 

        for i in range(self.table_mols.rowCount()):
            # Nombre de la molécula en GROMACS (Col 1)
            gmx_name = self.table_mols.item(i, 1).text()
            
            # Archivo ITP (Col 2 - Botón)
            btn = self.table_mols.cellWidget(i, 2)
            itp_filename = None
            if btn and btn.text() != "Cargar .itp":
                itp_filename = btn.text()
                raw_mol_itps.append(itp_filename)
                row_to_itp_map[i] = itp_filename
            
            count = self.molecules_data[i]['count']
            final_mols_list.append({
                'mol_name': gmx_name, 
                'count': count, 
                'has_itp': bool(itp_filename)
            })
        
        global_incs = [self.list_globals.item(i).text() for i in range(self.list_globals.count())]

        # 2. PROCESAMIENTO INTELIGENTE (SANITIZACIÓN)
        final_itps_to_include = raw_mol_itps
        itp_name_mapping = {orig: orig for orig in raw_mol_itps} # Mapa original -> final

        if self.chk_sanitize.isChecked() and raw_mol_itps:
            # Llamamos al sanitizador
            success, result = self.chem_tools.sanitize_itps(storage_dir, raw_mol_itps)
            
            if success:
                clean_itps = result 
                # Inyectar merged_atomtypes al inicio de globales si se creó
                if "merged_atomtypes.itp" not in global_incs:
                    global_incs.insert(0, "merged_atomtypes.itp")
                
                # Actualizar mapeo para saber qué archivo final corresponde a cada original
                for idx, original in enumerate(raw_mol_itps):
                    itp_name_mapping[original] = clean_itps[idx]
                    
                final_itps_to_include = clean_itps
                QMessageBox.information(self, "Sanitización", "Se han corregido los ITPs automáticamente para evitar colisiones.")
            else:
                QMessageBox.warning(self, "Error Sanitización", f"Falló el auto-corrector:\n{result}\nSe usarán archivos originales.")

        # 3. AUTO-CORRECCIÓN DE NOMBRES DE MOLÉCULA
        # Leemos el nombre real dentro del ITP (limpio u original) para evitar errores "No such moleculetype"
        # Esto soluciona el problema de que el usuario escriba "CO2" pero el ITP diga "CO2N"
        for i, mol_data in enumerate(final_mols_list):
            if mol_data['has_itp']:
                original_itp = row_to_itp_map.get(i)
                final_itp_name = itp_name_mapping.get(original_itp)
                
                if final_itp_name:
                    full_path = os.path.join(storage_dir, final_itp_name)
                    # Llamamos al helper que lee [ moleculetype ]
                    real_name = self.chem_tools.get_moleculetype_name_from_itp(full_path)
                    
                    if real_name:
                        mol_data['mol_name'] = real_name

        # 4. GENERAR ARCHIVO FINAL
        # Lista única de includes para no repetir imports
        unique_itps = sorted(list(set(final_itps_to_include)))
        
        success, msg = self.chem_tools.generate_topology_file(
            top_file,
            global_includes=global_incs,
            molecule_itps=unique_itps, 
            molecules_list=final_mols_list,
            forcefield=self.combo_ff.currentText(),
            include_water=self.chk_water.isChecked()
        )
        
        if success:
            top_msg = f"Topología generada correctamente:\n{top_file}"
            
            # 5. GENERAR ÍNDICE DE GRUPOS AUTOMÁTICAMENTE
            # Si tenemos al menos 2 componentes, asumimos Soluto = 1ero, Solvente = 2do
            # Esto facilita que las pestañas posteriores (RDF, Solubilidad) detecten grupos usables
            # sin obligar al usuario a usar "make_ndx" manual si todo se llama "UNL".
            
            # Buscamos system.gro
            gro_file = os.path.join(storage_dir, "system.gro")
            ndx_file = os.path.join(storage_dir, "index.ndx")
            
            if len(self.molecules_data) >= 2 and os.path.exists(gro_file):
                # Asumimos orden de tabla: Fila 0 = Soluto, Fila 1 = Solvente
                try:
                    n_solute = self.molecules_data[0]['count']
                    n_solvent = self.molecules_data[1]['count']
                    name_sol = "System_Solute"
                    name_slv = "System_Solvent"
                    
                    ok_ndx, msg_ndx = self.parser.generate_index_by_counts(
                        gro_file, ndx_file, 
                        n_solute, n_solvent,
                        name_sol, name_slv
                    )
                    if ok_ndx:
                        top_msg += f"\n\n[Auto-Index]: Se creó index.ndx con grupos '{name_sol}' y '{name_slv}'."
                except Exception as ex:
                    print(f"No se pudo generar index auto: {ex}")

            QMessageBox.information(self, "Éxito", top_msg)
        else:
            QMessageBox.critical(self, "Error", msg)

    # ==========================================================
    # PERSISTENCIA (GUARDAR Y CARGAR ESTADO)
    # ==========================================================

    def get_state(self):
        """Guarda estado para JSON"""
        # Guardar mapeo de qué ITP se asignó a qué molécula (por nombre de PDB)
        itp_mapping = {}
        for i in range(self.table_mols.rowCount()):
            # LEER DEL BOTÓN
            btn = self.table_mols.cellWidget(i, 2)
            if btn and btn.text() != "Cargar .itp":
                pdb_name = self.table_mols.item(i, 0).text()
                itp_mapping[pdb_name] = btn.text()
                
        return {
            "forcefield": self.combo_ff.currentIndex(),
            "sanitize": self.chk_sanitize.isChecked(),
            "include_water": self.chk_water.isChecked(),
            "global_includes": [self.list_globals.item(i).text() for i in range(self.list_globals.count())],
            "itp_mapping": itp_mapping
        }

    def set_state(self, state):
        """Restaura estado"""
        if not state: return
        
        self.combo_ff.setCurrentIndex(state.get("forcefield", 0))
        self.chk_sanitize.setChecked(state.get("sanitize", True))
        self.chk_water.setChecked(state.get("include_water", False))
        
        # Restaurar globales
        self.list_globals.clear()
        for g in state.get("global_includes", []):
            self.list_globals.addItem(g)
            
        # Guardar mapeo en variable temporal para usarlo en refresh_table cuando lleguen los datos
        self.saved_itp_mapping = state.get("itp_mapping", {})