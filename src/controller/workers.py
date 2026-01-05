from PyQt6.QtCore import QThread, pyqtSignal
import subprocess

class CommandWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, command_list, working_dir, input_file_path=None):
        super().__init__()
        self.command = command_list
        self.wd = working_dir
        self.input_file_path = input_file_path
        self.process = None # Guardamos referencia al proceso

    def run(self):
        file_obj = None
        try:
            if self.input_file_path:
                try:
                    file_obj = open(self.input_file_path, 'r')
                except FileNotFoundError:
                    self.finished_signal.emit(False, f"Input no encontrado: {self.input_file_path}")
                    return

            self.log_signal.emit(f"EJECUTANDO: {' '.join(self.command)}")
            
            # Iniciamos el proceso guardando la referencia en self.process
            self.process = subprocess.Popen(
                self.command,
                cwd=self.wd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=file_obj,
                text=True,
                bufsize=1
            )

            # Leer salida
            if self.process.stdout:
                for line in self.process.stdout:
                    self.log_signal.emit(line.strip())
            
            # Esperar a que termine
            self.process.wait()
            
            if file_obj: file_obj.close()

            # Verificar si fue exitoso o matado
            if self.process.returncode == 0:
                self.finished_signal.emit(True, "Proceso finalizado con éxito.")
            elif self.process.returncode == -15 or self.process.returncode == -9:
                self.finished_signal.emit(False, "Proceso detenido por el usuario.")
            else:
                self.finished_signal.emit(False, f"Error: Código de salida {self.process.returncode}")

        except Exception as e:
            if file_obj: file_obj.close()
            self.finished_signal.emit(False, f"Error crítico: {str(e)}")

    def stop_process(self):
        """Mata el proceso actual si está corriendo"""
        if self.process and self.process.poll() is None:
            self.log_signal.emit("!!! DETENIENDO PROCESO ... !!!")
            self.process.terminate() # Señal SIGTERM (suave)
            # self.process.kill()    # Señal SIGKILL (fuerte) si fuera necesario