import os
import shutil
import json
import copy
from datetime import datetime

class ProjectManager:
    def __init__(self):
        self.current_project_path = None
        self.active_system_name = None 
        self.project_data = {}
        
        # Gestión de Configuración Global (Recientes)
        # Se guardará en la carpeta config/ o en la raíz
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.config_path = os.path.join(self.root_dir, "config", "global_config.json")
        self.recent_projects = []
        
        self.load_global_config()

    # =========================================================================
    # GESTIÓN DE CONFIGURACIÓN GLOBAL (RECIENTES)
    # =========================================================================
    
    def load_global_config(self):
        """Carga la lista de proyectos recientes desde el JSON global"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.recent_projects = data.get("recent_projects", [])
            except Exception:
                self.recent_projects = []
        else:
            self.recent_projects = []

    def save_global_config(self):
        """Guarda la configuración global"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {
            "recent_projects": self.recent_projects
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error guardando config global: {e}")

    def add_to_recent(self, path):
        """Añade un proyecto a la lista de recientes (Max 5)"""
        # Normalizar ruta
        path = os.path.normpath(path)
        
        # Eliminar si ya existe para moverlo al principio
        if path in self.recent_projects:
            self.recent_projects.remove(path)
            
        # Insertar al inicio
        self.recent_projects.insert(0, path)
        
        # Mantener solo los últimos 5
        if len(self.recent_projects) > 5:
            self.recent_projects = self.recent_projects[:5]
            
        self.save_global_config()

    def get_recent_projects(self):
        return self.recent_projects

    # =========================================================================
    # GESTIÓN DEL PROYECTO ACTUAL
    # =========================================================================

    def create_project(self, name, root_path):
        self.current_project_path = os.path.join(root_path, name)
        try:
            os.makedirs(os.path.join(self.current_project_path, "storage"), exist_ok=True)
            os.makedirs(os.path.join(self.current_project_path, "analysis"), exist_ok=True)
            
            self.project_data = {
                "name": name,
                "created_at": str(datetime.now()),
                "systems": {}, 
                "active_system": None,
                "global_states": {} 
            }
            
            self.create_system("Default_System")
            
            self.save_db()
            
            # AGREGAR A RECIENTES
            self.add_to_recent(self.current_project_path)
            
            return True, f"Proyecto creado en {self.current_project_path}"
        except Exception as e:
            return False, str(e)

    def load_project_from_path(self, full_path):
        db_path = os.path.join(full_path, "project_db.json")
        if not os.path.exists(db_path):
            return False, "No es un proyecto válido (falta project_db.json)."
        
        try:
            self.current_project_path = full_path
            with open(db_path, 'r') as f:
                self.project_data = json.load(f)
            
            active = self.project_data.get("active_system")
            systems = list(self.project_data.get("systems", {}).keys())
            
            if active and active in systems:
                self.active_system_name = active
            elif systems:
                self.active_system_name = systems[0]
            else:
                self.create_system("Default_System")
            
            # AGREGAR A RECIENTES
            self.add_to_recent(self.current_project_path)
                
            return True, "Proyecto cargado."
        except Exception as e:
            return False, f"Error JSON: {e}"

    def save_db(self):
        if self.current_project_path:
            self.project_data["active_system"] = self.active_system_name
            
            # Guardado atómico para evitar corrupción
            db_path = os.path.join(self.current_project_path, "project_db.json")
            tmp_path = db_path + ".tmp"
            
            try:
                with open(tmp_path, 'w') as f:
                    json.dump(self.project_data, f, indent=4)
                    
                # Si se escribió bien, reemplazamos el original
                # En Windows rename no es atómico si existe, pero aquí estamos en Linux
                if os.path.exists(db_path):
                    os.replace(tmp_path, db_path)
                else:
                    os.rename(tmp_path, db_path)
            except Exception as e:
                print(f"Error guardando DB: {e}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    # --- GESTIÓN DE SISTEMAS ---

    def create_system(self, sys_name):
        if sys_name in self.project_data.get("systems", {}):
            return False, "Ya existe."
        
        sys_path = os.path.join(self.current_project_path, "storage", sys_name)
        os.makedirs(sys_path, exist_ok=True)
        
        if "systems" not in self.project_data: self.project_data["systems"] = {}
        
        self.project_data["systems"][sys_name] = {
            "created": str(datetime.now()),
            "setup_state": {},
            "topology_state": {},
            "simulation_state": {},
            "analysis_state": {}
        }
        
        self.active_system_name = sys_name
        self.save_db()
        return True, sys_path

    def clone_system(self, new_name, source_name):
        if new_name in self.project_data["systems"]:
            return False, "Nombre existe."
        if source_name not in self.project_data["systems"]:
            return False, "Origen no existe."

        source_data = self.project_data["systems"][source_name]
        new_data = copy.deepcopy(source_data)
        new_data["created"] = str(datetime.now())
        
        # Resetear estados de simulación
        sim_state = new_data.get("simulation_state", {})
        if "tree_data" in sim_state:
            self._reset_tree_status(sim_state["tree_data"])
            
        self.project_data["systems"][new_name] = new_data
        
        src_path = os.path.join(self.current_project_path, "storage", source_name)
        dst_path = os.path.join(self.current_project_path, "storage", new_name)
        os.makedirs(dst_path, exist_ok=True)
        
        allowed = ['.mdp', '.itp', '.top', '.pdb'] 
        
        try:
            for item in os.listdir(src_path):
                if any(item.endswith(ext) for ext in allowed):
                    s = os.path.join(src_path, item)
                    d = os.path.join(dst_path, item)
                    if os.path.isfile(s):
                        shutil.copy2(s, d)
        except Exception as e:
            return False, f"Error copiando: {e}"

        self.active_system_name = new_name
        self.save_db()
        return True, "Clonado."

    def _reset_tree_status(self, nodes):
        for node in nodes:
            node['status'] = "Pendiente"
            if 'children' in node:
                self._reset_tree_status(node['children'])

    def delete_system(self, sys_name):
        if sys_name not in self.project_data.get("systems", {}):
            return False, "No existe."
            
        sys_path = os.path.join(self.current_project_path, "storage", sys_name)
        try:
            if os.path.exists(sys_path):
                shutil.rmtree(sys_path)
        except Exception as e:
            return False, str(e)
            
        del self.project_data["systems"][sys_name]
        
        if self.active_system_name == sys_name:
            keys = list(self.project_data["systems"].keys())
            if keys:
                self.active_system_name = keys[0]
            else:
                self.active_system_name = None
                self.create_system("Default_System")
        
        self.save_db()
        return True, "Eliminado."

    def get_active_system_path(self):
        if not self.current_project_path or not self.active_system_name: return None
        return os.path.join(self.current_project_path, "storage", self.active_system_name)

    def update_tab_state(self, tab, data):
        if self.active_system_name:
            self.project_data["systems"][self.active_system_name][f"{tab}_state"] = data
            self.save_db()

    def get_tab_state(self, tab):
        if self.active_system_name:
            return self.project_data["systems"][self.active_system_name].get(f"{tab}_state", {})
        return {}

    def update_global_state(self, key, data):
        if "global_states" not in self.project_data:
            self.project_data["global_states"] = {}
        self.project_data["global_states"][key] = data
        self.save_db()

    def get_global_state(self, key):
        return self.project_data.get("global_states", {}).get(key, {})
    
    def get_system_list(self):
        return list(self.project_data.get("systems", {}).keys())