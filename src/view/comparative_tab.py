import os
import shutil
import datetime
from PyQt6.QtWidgets import (
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QLabel, 
    QPushButton, 
    QGroupBox, 
    QTableWidget, 
    QTableWidgetItem, 
    QHeaderView, 
    QMessageBox, 
    QSplitter, 
    QComboBox, 
    QSpinBox, 
    QDoubleSpinBox,
    QFileDialog, 
    QFrame, 
    QColorDialog, 
    QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# Modelo
from src.model.analysis_parser import AnalysisParser

# Matplotlib integration
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

class ComparativeTab(QWidget):
    def __init__(self):
        super().__init__()
        
        # Instancia del parser para leer archivos .xvg/.csv
        self.parser = AnalysisParser()
        
        # Referencia al gestor de proyectos
        self.project_mgr = None
        
        # Almacén de datos en memoria para graficación rápida
        # Estructura: { 'id_unico': {'label': str, 'x': np.array, 'y': np.array, 'color': hex, 'filepath': str} }
        self.data_store = {}
        
        # Paleta de colores para asignar automáticamente a nuevas series
        self.colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
        ]
        
        # Inicializar la interfaz gráfica
        self.init_ui()

    def init_ui(self):
        """Construye la interfaz gráfica dividida en dos paneles"""
        # Layout principal horizontal (Splitter)
        main_layout = QHBoxLayout()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ==========================================================
        # PANEL IZQUIERDO: CONTROLES Y LISTA (30%)
        # ==========================================================
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        
        # --- 1. SELECTOR JERÁRQUICO (CASCADA) ---
        group_sel = QGroupBox("1. Selección de Datos (Cascada)")
        vbox_sel = QVBoxLayout()
        
        # Nivel 1: Sistema
        hbox_sys = QHBoxLayout()
        self.combo_systems = QComboBox()
        self.combo_systems.currentIndexChanged.connect(self.on_system_changed)
        
        hbox_sys.addWidget(QLabel("Sistema:"))
        hbox_sys.addWidget(self.combo_systems)
        
        # Nivel 2: Etapa (Simulación)
        hbox_step = QHBoxLayout()
        self.combo_steps = QComboBox()
        self.combo_steps.currentIndexChanged.connect(self.on_step_changed)
        
        hbox_step.addWidget(QLabel("Etapa:"))
        hbox_step.addWidget(self.combo_steps)
        
        # Nivel 3: Propiedad (Archivo)
        hbox_prop = QHBoxLayout()
        self.combo_props = QComboBox()
        
        hbox_prop.addWidget(QLabel("Dato:"))
        hbox_prop.addWidget(self.combo_props)
        
        # Botón de Acción
        btn_add = QPushButton("⬇ Añadir a Comparación")
        btn_add.clicked.connect(self.add_data_series)
        btn_add.setStyleSheet("font-weight: bold; color: green; padding: 5px;")
        
        vbox_sel.addLayout(hbox_sys)
        vbox_sel.addLayout(hbox_step)
        vbox_sel.addLayout(hbox_prop)
        vbox_sel.addWidget(btn_add)
        
        group_sel.setLayout(vbox_sel)
        left_layout.addWidget(group_sel)
        
        # --- 2. TABLA DE SERIES (MATRIZ DE ASIGNACIÓN) ---
        group_list = QGroupBox("2. Series Cargadas")
        vbox_list = QVBoxLayout()
        
        self.table_series = QTableWidget()
        self.table_series.setColumnCount(5)
        self.table_series.setHorizontalHeaderLabels(["Etiqueta (Editable)", "Color", "P1", "P2", "P3/4"])
        
        # Ajustes de estilo de tabla
        self.table_series.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_series.setColumnWidth(1, 40) # Color pequeño
        self.table_series.setColumnWidth(2, 25) # Checkbox P1
        self.table_series.setColumnWidth(3, 25) # Checkbox P2
        self.table_series.setColumnWidth(4, 35) # Checkbox P3/4
        
        # Conexiones de la tabla
        self.table_series.itemChanged.connect(self.on_table_changed)
        self.table_series.cellClicked.connect(self.on_table_clicked)
        
        vbox_list.addWidget(self.table_series)
        
        # Botones de gestión de tabla
        hbox_tbl = QHBoxLayout()
        btn_remove = QPushButton("🗑️ Quitar")
        btn_remove.clicked.connect(self.remove_series)
        
        btn_clear = QPushButton("Limpiar Todo")
        btn_clear.clicked.connect(self.clear_all)
        
        hbox_tbl.addWidget(btn_remove)
        hbox_tbl.addWidget(btn_clear)
        vbox_list.addLayout(hbox_tbl)
        
        group_list.setLayout(vbox_list)
        left_layout.addWidget(group_list)
        
        # --- 3. CONFIGURACIÓN VISUAL ---
        group_cfg = QGroupBox("Configuración Gráfica")
        form_cfg = QVBoxLayout()
        
        hbox_layout_sel = QHBoxLayout()
        self.combo_layout = QComboBox()
        self.combo_layout.addItems(["1 Gráfico (Simple)", "2 Gráficos (Horizontal)", "4 Gráficos (2x2)"])
        self.combo_layout.currentIndexChanged.connect(self.update_plot)
        
        hbox_layout_sel.addWidget(QLabel("Layout:"))
        hbox_layout_sel.addWidget(self.combo_layout)
        
        hbox_font = QHBoxLayout()
        self.sb_fontsize = QSpinBox()
        self.sb_fontsize.setRange(8, 30)
        self.sb_fontsize.setValue(10)
        
        self.sb_linewidth = QDoubleSpinBox()
        self.sb_linewidth.setRange(0.5, 5.0)
        self.sb_linewidth.setValue(1.5)
        
        hbox_font.addWidget(QLabel("Fuente:"))
        hbox_font.addWidget(self.sb_fontsize)
        hbox_font.addWidget(QLabel("Grosor:"))
        hbox_font.addWidget(self.sb_linewidth)
        
        btn_update = QPushButton("🔄 Actualizar Gráfico")
        btn_update.clicked.connect(self.update_plot)
        
        form_cfg.addLayout(hbox_layout_sel)
        form_cfg.addLayout(hbox_font)
        form_cfg.addWidget(btn_update)
        
        group_cfg.setLayout(form_cfg)
        left_layout.addWidget(group_cfg)
        
        left_widget.setLayout(left_layout)
        
        # ==========================================================
        # PANEL DERECHO: GRÁFICAS (MATPLOTLIB) (70%)
        # ==========================================================
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        
        self.figure = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Botón de Exportación
        btn_export = QPushButton("💾 Guardar Imagen (PNG/PDF)")
        btn_export.clicked.connect(self.export_plot)
        
        hbox_tools = QHBoxLayout()
        hbox_tools.addWidget(self.toolbar)
        hbox_tools.addWidget(btn_export)
        
        right_layout.addLayout(hbox_tools)
        right_layout.addWidget(self.canvas)
        
        right_widget.setLayout(right_layout)
        
        # Añadir widgets al Splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        # Configurar proporciones (30% izq, 70% der)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    # ==========================================================
    # LÓGICA DE DATOS: SELECTOR JERÁRQUICO
    # ==========================================================

    def update_project_data(self, mgr):
        """Recibe el manager y actualiza la lista de sistemas disponibles"""
        self.project_mgr = mgr
        if not mgr or not mgr.current_project_path:
            return
        
        # Llenar Combo 1: Sistemas
        self.combo_systems.blockSignals(True)
        self.combo_systems.clear()
        
        # Obtener carpetas en storage/
        storage_root = os.path.join(mgr.current_project_path, "storage")
        if os.path.exists(storage_root):
            # Listar solo directorios
            systems = [d for d in os.listdir(storage_root) if os.path.isdir(os.path.join(storage_root, d))]
            self.combo_systems.addItems(sorted(systems))
            
        self.combo_systems.blockSignals(False)
        
        # Disparar actualización en cascada para llenar el siguiente combo
        self.on_system_changed()

    def on_system_changed(self):
        """Al cambiar el sistema, buscar etapas (archivos .tpr)"""
        sys_name = self.combo_systems.currentText()
        if not sys_name or not self.project_mgr:
            return
        
        sys_path = os.path.join(self.project_mgr.current_project_path, "storage", sys_name)
        
        self.combo_steps.blockSignals(True)
        self.combo_steps.clear()
        
        if os.path.exists(sys_path):
            files = os.listdir(sys_path)
            # Buscamos .tpr como indicador de etapas válidas
            steps = [os.path.splitext(f)[0] for f in files if f.endswith(".tpr")]
            self.combo_steps.addItems(sorted(steps))
            
        self.combo_steps.blockSignals(False)
        
        # Disparar actualización del siguiente nivel
        self.on_step_changed()

    def on_step_changed(self):
        """Al cambiar etapa, buscar archivos de datos (.xvg, .csv)"""
        sys_name = self.combo_systems.currentText()
        step_name = self.combo_steps.currentText()
        
        if not sys_name or not step_name: 
            self.combo_props.clear()
            return
            
        sys_path = os.path.join(self.project_mgr.current_project_path, "storage", sys_name)
        
        self.combo_props.blockSignals(True)
        self.combo_props.clear()
        
        if os.path.exists(sys_path):
            files = os.listdir(sys_path)
            
            # Buscamos archivos que empiecen con el nombre del paso
            props = []
            for f in files:
                if f.startswith(step_name) and (f.endswith(".xvg") or f.endswith(".csv")):
                    # Limpiar nombre para mostrar solo la propiedad en la UI
                    # ej: nvt_Temperature.xvg -> Temperature
                    clean_prop = f.replace(step_name + "_", "").replace(".xvg", "").replace(".csv", "")
                    
                    # Guardar tupla: (Nombre Visual, Nombre Archivo Real)
                    props.append((clean_prop, f))
            
            # Añadir al combo ordenados
            for visual, filename in sorted(props):
                self.combo_props.addItem(visual, filename)
                
        self.combo_props.blockSignals(False)

    # ==========================================================
    # LÓGICA DE CARGA Y GESTIÓN DE TABLA
    # ==========================================================

    def add_data_series(self):
        """Carga el archivo seleccionado en los combos y lo añade a la tabla"""
        sys_name = self.combo_systems.currentText()
        step_name = self.combo_steps.currentText()
        filename = self.combo_props.currentData() # Recupera el filename guardado en el combo
        
        if not filename:
            QMessageBox.warning(self, "Aviso", "Seleccione un dato válido.")
            return

        # Construir ruta completa al archivo
        full_path = os.path.join(self.project_mgr.current_project_path, "storage", sys_name, filename)
        
        # Usar el parser para leer los datos numéricos
        labels, x, y_list = self.parser.get_data_from_file(full_path)
        
        if not y_list:
            QMessageBox.warning(self, "Error", f"No se pudieron leer datos de:\n{filename}")
            return

        # Crear ID único para almacenamiento interno
        data_id = f"{sys_name}_{filename}_{len(self.data_store)}"
        
        # Etiqueta automática para la leyenda: "Sistema - Etapa - Propiedad"
        prop_name = self.combo_props.currentText()
        label_auto = f"{sys_name} ({prop_name})"
        
        # Asignar color rotativo de la paleta
        color_idx = len(self.data_store) % len(self.colors)
        color = self.colors[color_idx]
        
        # Guardar en el almacén de datos (Memoria)
        self.data_store[data_id] = {
            'label': label_auto,
            'x': x,
            'y': y_list[0], # Tomamos la primera columna Y por defecto
            'color': color,
            'xlabel': labels[0],
            'ylabel': labels[1],
            'filepath': full_path # Guardamos ruta para persistencia
        }
        
        # Añadir fila visual a la tabla
        self.add_row_to_table(data_id, label_auto, color)
        
        # Actualizar gráfica inmediatamente
        self.update_plot()

    def add_row_to_table(self, data_id, label, color_hex):
        """Helper para insertar una fila en la QTableWidget"""
        self.table_series.blockSignals(True)
        row = self.table_series.rowCount()
        self.table_series.insertRow(row)
        
        # Col 0: Nombre Editable
        item_name = QTableWidgetItem(label)
        item_name.setData(Qt.ItemDataRole.UserRole, data_id) # Guardamos la ID oculta
        item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table_series.setItem(row, 0, item_name)
        
        # Col 1: Color (Celda coloreada)
        item_color = QTableWidgetItem("")
        item_color.setBackground(QColor(color_hex))
        item_color.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table_series.setItem(row, 1, item_color)
        
        # Col 2, 3, 4: Checkboxes para asignar a Subplots
        for c in range(2, 5):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            
            # Por defecto, marcar en Plot 1 (Columna 2)
            if c == 2:
                chk.setCheckState(Qt.CheckState.Checked)
            else:
                chk.setCheckState(Qt.CheckState.Unchecked)
            
            self.table_series.setItem(row, c, chk)
            
        self.table_series.blockSignals(False)

    def on_table_changed(self, item):
        """Detecta cambios de nombre (Col 0) o checkboxes (Col 2-4)"""
        row = item.row()
        col = item.column()
        
        # Recuperar ID del dato
        name_item = self.table_series.item(row, 0)
        data_id = name_item.data(Qt.ItemDataRole.UserRole)
        
        if not data_id or data_id not in self.data_store:
            return
        
        # Si cambió el nombre (Col 0)
        if col == 0:
            self.data_store[data_id]['label'] = item.text()
            self.update_plot()
            
        # Si cambiaron los checkboxes, redibujamos
        elif col >= 2:
            self.update_plot()

    def on_table_clicked(self, row, col):
        """Maneja clic en la celda de color para abrir diálogo"""
        if col == 1:
            name_item = self.table_series.item(row, 0)
            data_id = name_item.data(Qt.ItemDataRole.UserRole)
            
            current_hex = self.data_store[data_id]['color']
            color = QColorDialog.getColor(QColor(current_hex), self, "Seleccionar Color")
            
            if color.isValid():
                self.data_store[data_id]['color'] = color.name()
                # Actualizar celda visual
                self.table_series.item(row, 1).setBackground(color)
                # Redibujar gráfica
                self.update_plot()

    def remove_series(self):
        """Elimina la serie seleccionada de la tabla y memoria"""
        row = self.table_series.currentRow()
        if row >= 0:
            name_item = self.table_series.item(row, 0)
            data_id = name_item.data(Qt.ItemDataRole.UserRole)
            
            if data_id in self.data_store:
                del self.data_store[data_id]
            
            self.table_series.removeRow(row)
            self.update_plot()

    def clear_all(self):
        """Limpia todo"""
        self.data_store = {}
        self.table_series.setRowCount(0)
        self.update_plot()

    # ==========================================================
    # LÓGICA DE GRAFICACIÓN (MATPLOTLIB)
    # ==========================================================
    
    def update_plot(self):
        """Redibuja los gráficos según la configuración de la tabla"""
        self.figure.clear()
        
        # Configurar estilos globales
        fs = self.sb_fontsize.value()
        lw = self.sb_linewidth.value()
        plt.rcParams.update({'font.size': fs, 'lines.linewidth': lw})
        
        # Configurar Layout (Subplots)
        layout_mode = self.combo_layout.currentIndex() # 0=1x1, 1=1x2, 2=2x2
        axes = []
        
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
        row_count = self.table_series.rowCount()
        
        for r in range(row_count):
            # Recuperar ID del dato
            key_item = self.table_series.item(r, 0)
            data_id = key_item.data(Qt.ItemDataRole.UserRole)
            
            data = self.data_store.get(data_id)
            if not data:
                continue
            
            # Revisar columnas de checkboxes (Col 2, 3, 4 mapean a plots 0, 1, 2, 3)
            # Nota: Col 2 = Plot 0. Col 3 = Plot 1. Col 4 = Plot 2 y 3 (simplificación)
            
            for i, ax in enumerate(axes):
                # Lógica de mapeo de columnas:
                # Si hay 1 gráfico: Col 2 lo controla.
                # Si hay 2 gráficos: Col 2->Plot1, Col 3->Plot2.
                # Si hay 4 gráficos: Col 4 lo manda a Plot 3 y 4 (para no saturar tabla).
                
                col_idx = i + 2
                
                # Ajuste para matrices de 4x4 (usamos la col 4 para los extra)
                if col_idx > 4: 
                    col_idx = 4
                
                if col_idx < self.table_series.columnCount():
                    chk = self.table_series.item(r, col_idx)
                    if chk.checkState() == Qt.CheckState.Checked:
                        ax.plot(
                            data['x'], 
                            data['y'], 
                            label=data['label'], 
                            color=data['color']
                        )
                        # Poner etiquetas si es el primero
                        if not ax.get_xlabel(): ax.set_xlabel(data['xlabel'])
                        if not ax.get_ylabel(): ax.set_ylabel(data['ylabel'])

        # Finalizar ejes
        for i, ax in enumerate(axes):
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.legend(fontsize=fs-2)
            ax.set_title(f"Gráfico Comparativo {i+1}", fontweight='bold')

        self.figure.tight_layout()
        self.canvas.draw()
        
        # Auto-guardado temporal
        if self.project_mgr and self.project_mgr.current_project_path:
            p = os.path.join(self.project_mgr.current_project_path, "analysis", "last_comparison.png")
            try:
                self.figure.savefig(p)
            except:
                pass

    def export_plot(self):
        """Exportar imagen manualmente"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Imagen", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if path:
            try:
                self.figure.savefig(path, dpi=300)
                QMessageBox.information(self, "OK", f"Imagen guardada en:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ==========================================================
    # PERSISTENCIA (GUARDAR Y CARGAR ESTADO)
    # ==========================================================

    def get_state(self):
        """
        Retorna el estado actual de la pestaña.
        Guardamos la LISTA DE ARCHIVOS cargados (path) y su configuración visual.
        """
        loaded_files = []
        
        for r in range(self.table_series.rowCount()):
            item_name = self.table_series.item(r, 0)
            data_id = item_name.data(Qt.ItemDataRole.UserRole)
            data = self.data_store.get(data_id)
            
            if data and data.get('filepath'):
                # Guardar estado de checkboxes
                checks = []
                for c in range(2, 5):
                    is_checked = (self.table_series.item(r, c).checkState() == Qt.CheckState.Checked)
                    checks.append(is_checked)
                
                loaded_files.append({
                    'filepath': data['filepath'],
                    'label': data['label'], # El nombre editado por usuario
                    'color': data['color'],
                    'checks': checks
                })
        
        return {
            "layout_mode": self.combo_layout.currentIndex(),
            "font_size": self.sb_fontsize.value(),
            "loaded_files": loaded_files
        }

    def set_state(self, state):
        """Restaura el estado"""
        if not state:
            return
        
        # 1. Limpiar todo
        self.clear_all()
        
        # 2. Restaurar Configuración Global
        self.combo_layout.setCurrentIndex(state.get("layout_mode", 0))
        self.sb_fontsize.setValue(state.get("font_size", 10))
        
        # 3. Recargar archivos y configuraciones
        files_info = state.get("loaded_files", [])
        
        for f_info in files_info:
            path = f_info.get('filepath')
            label = f_info.get('label')
            color = f_info.get('color')
            checks = f_info.get('checks', [])
            
            # Solo cargar si el archivo físico aún existe
            if path and os.path.exists(path):
                # Re-leer datos del disco
                lbl, x, y_list = self.parser.get_data_from_file(path)
                
                if y_list:
                    # Recrear ID
                    # Usamos add_data_to_store_manual para poder inyectar label y color guardados
                    self._restore_single_series(label, x, y_list[0], path, color, checks, lbl)
        
        self.update_plot()

    def _restore_single_series(self, label, x, y, filepath, color, checks, labels):
        """Helper interno para restaurar una serie con propiedades específicas"""
        data_id = f"restored_{len(self.data_store)}"
        
        self.data_store[data_id] = {
            'label': label,
            'x': x,
            'y': y,
            'color': color,
            'filepath': filepath,
            'xlabel': labels[0],
            'ylabel': labels[1]
        }
        
        self.table_series.blockSignals(True)
        row = self.table_series.rowCount()
        self.table_series.insertRow(row)
        
        # Nombre
        item_name = QTableWidgetItem(label)
        item_name.setData(Qt.ItemDataRole.UserRole, data_id)
        item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table_series.setItem(row, 0, item_name)
        
        # Color
        item_col = QTableWidgetItem("")
        item_col.setBackground(QColor(color))
        item_col.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table_series.setItem(row, 1, item_col)
        
        # Checkboxes
        for i, is_checked in enumerate(checks):
            col_idx = i + 2
            if col_idx < 5:
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                self.table_series.setItem(row, col_idx, chk)
                
        self.table_series.blockSignals(False)