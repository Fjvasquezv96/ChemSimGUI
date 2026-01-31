
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QLabel, QHeaderView,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

class ValidationDialog(QDialog):
    """
    Diálogo flotante para validación detallada de solubilidad vs datos experimentales.
    Permite pegar desde Excel (Ctrl+V) y calcula error porcentual automáticamente.
    """
    def __init__(self, predictor_callback, initial_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validación de Predicción vs Experimental")
        self.resize(600, 400)
        
        self.predictor_callback = predictor_callback
        # Data format: [{'T': float, 'Exp': float}, ...]
        self.data_rows = initial_data if initial_data else []
        
        # Layout principal
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Instrucciones
        lbl_info = QLabel("Ingrese temperaturas y datos experimentales. Puede pegar desde Excel (Ctrl+V).")
        lbl_info.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(lbl_info)
        
        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["T (K)", "Predicción (x)", "Experimental (x)", "% Error"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        
        # Conectar cambios
        self.table.cellChanged.connect(self.on_cell_changed)
        
        layout.addWidget(self.table)
        
        # Botones
        hbox = QHBoxLayout()
        
        btn_add = QPushButton("➕ Agregar Fila")
        btn_add.clicked.connect(self.add_row)
        
        btn_clear = QPushButton("🗑️ Limpiar")
        btn_clear.clicked.connect(self.clear_table)
        
        btn_copy = QPushButton("📋 Copiar Tabla")
        btn_copy.clicked.connect(self.copy_to_clipboard)
        
        hbox.addWidget(btn_add)
        hbox.addWidget(btn_clear)
        hbox.addStretch()
        hbox.addWidget(btn_copy)
        
        layout.addLayout(hbox)
        
        # Atajo Ctrl+V
        self.shortcut_paste = QAction("Paste", self)
        self.shortcut_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.shortcut_paste.triggered.connect(self.paste_from_clipboard)
        self.addAction(self.shortcut_paste)
        
        # Cargar datos iniciales
        self.load_initial_data()

    def load_initial_data(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row_data in self.data_rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            
            # T
            t_val = row_data.get('T', 0)
            self.table.setItem(r, 0, QTableWidgetItem(str(t_val)))
            
            # Exp
            exp_val = row_data.get('Exp', '')
            self.table.setItem(r, 2, QTableWidgetItem(str(exp_val)))
            
            # Calcular (Pred y Error se llenan solos)
            self.calculate_row(r)
            
        if self.table.rowCount() == 0:
            self.add_row() # Al menos una fila vacía
            
        self.table.blockSignals(False)

    def add_row(self):
        self.table.insertRow(self.table.rowCount())

    def clear_table(self):
        self.table.setRowCount(0)
        self.add_row()
        self.data_rows = []

    def on_cell_changed(self, row, col):
        # Si cambia T (col 0) o Exp (col 2), recalcular
        if col == 0 or col == 2:
            self.calculate_row(row)
            self.save_data_state()

    def calculate_row(self, row):
        """Calcula Predicción y Error para una fila dada"""
        try:
            # Leer T
            item_t = self.table.item(row, 0)
            if not item_t or not item_t.text(): return
            
            t_val = float(item_t.text())
            
            # 1. Calcular Predicción
            pred_x = self.predictor_callback(t_val)
            pred_item = QTableWidgetItem(f"{pred_x:.6f}")
            pred_item.setFlags(item_t.flags() & ~Qt.ItemFlag.ItemIsEditable) # Read only
            # Color coding simple
            pred_item.setBackground(Qt.GlobalColor.white)
            
            self.table.blockSignals(True)
            self.table.setItem(row, 1, pred_item)
            self.table.blockSignals(False)
            
            # 2. Calcular Error (si hay Exp)
            item_exp = self.table.item(row, 2)
            if item_exp and item_exp.text():
                exp_val = float(item_exp.text())
                if exp_val != 0:
                    err = abs(pred_x - exp_val) / exp_val * 100.0
                    err_item = QTableWidgetItem(f"{err:.2f}%")
                    
                    # Color coding error
                    if err < 5: err_item.setForeground(Qt.GlobalColor.darkGreen)
                    elif err < 20: err_item.setForeground(Qt.GlobalColor.darkYellow)
                    else: err_item.setForeground(Qt.GlobalColor.red)
                    
                    self.table.blockSignals(True)
                    self.table.setItem(row, 3, err_item)
                    self.table.blockSignals(False)
        except ValueError:
            pass # Ignorar texto no numérico

    def save_data_state(self):
        """Guarda el estado actual en la lista interna para persistencia"""
        self.data_rows = []
        for r in range(self.table.rowCount()):
            try:
                t_item = self.table.item(r, 0)
                exp_item = self.table.item(r, 2)
                
                if t_item and t_item.text():
                    row_data = {'T': float(t_item.text())}
                    if exp_item and exp_item.text():
                        row_data['Exp'] = float(exp_item.text())
                    self.data_rows.append(row_data)
            except: pass

    def get_data(self):
        return self.data_rows

    def paste_from_clipboard(self):
        """Maneja Ctrl+V inteligente (acepta columnas de Excel)"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text: return
        
        rows = text.split('\n')
        # Identificar celda actual
        current_row = self.table.currentRow()
        if current_row < 0: current_row = 0
        current_col = self.table.columnCount() # Empezar nueva fila al final
        
        # Eliminar filas vacías del final de clipboard
        rows = [r for r in rows if r.strip()]
        
        self.table.blockSignals(True)
        for i, row_text in enumerate(rows):
            cols = row_text.split('\t')
            target_row = current_row + i
            
            if target_row >= self.table.rowCount():
                self.table.insertRow(target_row)
            
            # Lógica de pegado:
            # - Si hay 1 columna -> Pega en T (Col 0) si estamos en col 0
            # - Si hay 2 columnas -> Pega en T (Col 0) y Exp (Col 2)
            
            if len(cols) >= 1:
                # T
                self.table.setItem(target_row, 0, QTableWidgetItem(cols[0].strip()))
            
            if len(cols) >= 2:
                # Exp (ignoramos la col 1 que es predicho, asumimos que el usuario copia T y Exp de excel)
                self.table.setItem(target_row, 2, QTableWidgetItem(cols[1].strip()))
        
        self.table.blockSignals(False)
        
        # Recalcular todo
        for i in range(len(rows)):
            self.calculate_row(current_row + i)
            
        self.save_data_state()

    def copy_to_clipboard(self):
        """Copia la tabla entera al portapapeles formato Excel"""
        text = "T\tPred\tExp\tError\n"
        for r in range(self.table.rowCount()):
            row_txt = []
            for c in range(4):
                it = self.table.item(r, c)
                row_txt.append(it.text() if it else "")
            text += "\t".join(row_txt) + "\n"
        QApplication.clipboard().setText(text)
