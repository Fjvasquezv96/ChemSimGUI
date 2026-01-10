from PyQt6.QtCore import QThread, pyqtSignal
import subprocess
import os

class CommandWorker(QThread):
    log_signal = pyqtSignal(str)      
    finished_signal = pyqtSignal(bool, str) 

    def __init__(self, command_list, working_dir, input_file_path=None):
        super().__init__()
        self.command = command_list
        self.wd = working_dir
        self.input_file_path = input_file_path
        self.process = None

    def run(self):
        file_obj = None
        try:
            if self.input_file_path:
                try:
                    file_obj = open(self.input_file_path, 'r')
                except FileNotFoundError:
                    self.finished_signal.emit(False, f"Input no encontrado: {self.input_file_path}")
                    return

            self.log_signal.emit(f"CMD: {' '.join(self.command)}")
            
            # --- FIX: FORZAR SALIDA SIN BUFFER PARA VER EL AVANCE EN TIEMPO REAL ---
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            # -----------------------------------------------------------------------

            self.process = subprocess.Popen(
                self.command,
                cwd=self.wd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Unificar salida
                stdin=file_obj,
                text=True,    
                bufsize=1,     # Line buffered
                env=env        # Aplicar entorno
            )

            # Leer línea a línea
            while True:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None:
                    break
                if line:
                    self.log_signal.emit(line.strip())

            # Esperar a que el proceso muera realmente
            self.process.wait()
            rc = self.process.returncode
            
            if file_obj: file_obj.close()

            if rc == 0:
                self.finished_signal.emit(True, "Proceso finalizado correctamente.")
            elif rc == -15:
                self.finished_signal.emit(False, "Proceso detenido por el usuario.")
            else:
                self.finished_signal.emit(False, f"Error: Código de salida {rc}")

        except Exception as e:
            if file_obj: file_obj.close()
            self.finished_signal.emit(False, f"Error crítico: {str(e)}")

    def stop_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait() # Esperar a que muera antes de seguir