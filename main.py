import sys
import os
import subprocess
import importlib

def check_and_install_dependencies():
    """Verifica e instala dependencias automáticamente."""
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(req_file):
        print(f"Advertencia: No se encontró {req_file}")
        return

    try:
        # Intenta importar las librerías críticas para ver si existen
        import PyQt6
        import numpy
        import matplotlib
        import graphviz
    except ImportError as e:
        print(f"Dependencia faltante detectada ({e.name}). Instalando desde requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
            print("Dependencias instaladas exitosamente.")
            importlib.invalidate_caches()
        except subprocess.CalledProcessError as e:
            print(f"Error crítico al instalar dependencias: {e}")
            sys.exit(1)

if __name__ == "__main__":
    # 1. Verificar entorno antes de cargar nada
    check_and_install_dependencies()

    # 2. Importaciones diferidas (Lazy Import)
    # Esto evita el error "ModuleNotFoundError" antes de poder instalar
    try:
        from PyQt6.QtWidgets import QApplication
        from src.view.main_window import MainWindow
    except ImportError:
        # Si falló incluso después de intentar instalar, pedimos reinicio manual
        print("Error: No se pudieron cargar las librerías necesarias.")
        print("Por favor, ejecuta: pip install -r requirements.txt")
        sys.exit(1)

    def main():
        # Inicializar la aplicación Qt
        app = QApplication(sys.argv)
        
        # Aplicar un estilo (Fusion es limpio y funciona bien en Linux)
        app.setStyle("Fusion")
        
        # Crear y mostrar ventana
        window = MainWindow()
        window.show()
        
        # Loop principal
        sys.exit(app.exec())

    main()