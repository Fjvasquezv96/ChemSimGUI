import os
import re

class MdpManager:
    def __init__(self, templates_dir):
        self.templates_dir = templates_dir
        # Debug: Imprimir dónde está buscando las plantillas
        print(f"DEBUG: MdpManager buscando plantillas en: {os.path.abspath(self.templates_dir)}")

    def get_template_content(self, template_name):
        """Lee el contenido de un archivo .mdp plantilla"""
        # Asegurar extensión
        if not template_name.endswith('.mdp'):
            filename = f"{template_name}.mdp"
        else:
            filename = template_name
            
        path = os.path.join(self.templates_dir, filename)
        
        if not os.path.exists(path):
            error_msg = f"; ERROR CRÍTICO: No se encontró la plantilla en:\n; {path}\n; Verifique que la carpeta 'src/assets/templates' exista y tenga los archivos minim.mdp, nvt.mdp, etc."
            print(error_msg)
            return error_msg
        
        try:
            with open(path, 'r') as f:
                return f.read()
        except Exception as e:
            return f"; Error leyendo plantilla: {str(e)}"

    def save_mdp(self, output_path, content):
        """Guarda el contenido editado en la carpeta del proyecto"""
        try:
            with open(output_path, 'w') as f:
                f.write(content)
            return True, f"Guardado en {os.path.basename(output_path)}"
        except Exception as e:
            return False, str(e)

    def update_parameters(self, content, params_dict):
        """Actualiza parámetros en el texto MDP conservando formato"""
        lines = content.split('\n')
        new_lines = []
        
        for line in lines:
            clean_line = line.split(';')[0].strip()
            # Ignorar líneas vacías o comentarios puros
            if not clean_line:
                new_lines.append(line)
                continue
                
            key_match = None
            for key in params_dict:
                # Regex: Busca 'key' al inicio, seguido de espacios o =
                # Ej: "dt =" o "dt=" o "dt "
                pattern = f"^{key}\\s*(=|\s)"
                if re.match(pattern, clean_line):
                    key_match = key
                    break
            
            if key_match:
                val = str(params_dict[key_match])
                # Mantener comentario original si existe
                comment = ""
                if ";" in line:
                    parts = line.split(';', 1)
                    if len(parts) > 1: comment = " ;" + parts[1]
                
                # Reconstruir línea alineada
                new_lines.append(f"{key_match:<25} = {val}{comment}")
            else:
                new_lines.append(line)
        
        return '\n'.join(new_lines)