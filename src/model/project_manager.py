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

    def create_project(self, name, root_path):
        self.current_project_path = os.path.join(root_path, name)
        try:
            os.makedirs(os.path.join(self.current_project_path, "storage"), exist_ok=True)
            
            self.project_data = {
                "name": name,
                "created_at": str(datetime.now()),
                "systems": {}, 
                "active_system": None
            }
            
            self.create_system("Default_System")
            self.save_db()
            return True, f"Proyecto creado en {self.current_project_path}"
        except Exception as e:
            return False, str(e)

    def load_project_from_path(self, full_path):
        db_path = os.path.join(full_path, "project_db.json")
        if not os.path.exists(db_path): return False, "No es un proyecto válido."
        
        try:
            self.current_project_path = full_path
            with open(db_path, 'r') as f: self.project_data = json.load(f)
            
            active = self.project_data.get("active_system")
            systems = list(self.project_data.get("systems", {}).keys())
            
            if active and active in systems: self.active_system_name = active
            elif systems: self.active_system_name = systems[0]
            else: self.create_system("Default_System")
                
            return True, "Proyecto cargado."
        except Exception as e: return False, f"Error JSON: {e}"

    def save_db(self):
        if self.current_project_path:
            self.project_data["active_system"] = self.active_system_name
            with open(os.path.join(self.current_project_path, "project_db.json"), 'w') as f:
                json.dump(self.project_data, f, indent=4)

    # --- GESTIÓN DE SISTEMAS ---

    def create_system(self, sys_name):
        if sys_name in self.project_data.get("systems", {}): return False, "Ya existe."
        
        sys_path = os.path.join(self.current_project_path, "storage", sys_name)
        os.makedirs(sys_path, exist_ok=True)
        
        if "systems" not in self.project_data: self.project_data["systems"] = {}
        
        self.project_data["systems"][sys_name] = {
            "created": str(datetime.now()),
            "setup_state": {},
            "topology_state": {},
            "simulation_state": {}
        }
        self.active_system_name = sys_name
        self.save_db()
        return True, sys_path

    def clone_system(self, new_name, source_name):
        """
        Clona configuración (MDP, ITP) pero NO resultados (GRO, TPR, XTC).
        Resetea el estado de las simulaciones a 'Pendiente'.
        """
        if new_name in self.project_data["systems"]: return False, "Nombre existe."
        if source_name not in self.project_data["systems"]: return False, "Origen no existe."

        # 1. Clonar datos del JSON
        source_data = self.project_data["systems"][source_name]
        new_data = copy.deepcopy(source_data)
        new_data["created"] = str(datetime.now())
        
        # 2. LIMPIEZA DE ESTADO (Issue #3)
        # Reseteamos recursivamente el árbol de simulación a "Pendiente"
        def reset_status_recursive(nodes):
            for node in nodes:
                node['status'] = "Pendiente"
                if 'children' in node:
                    reset_status_recursive(node['children'])
        
        sim_state = new_data.get("simulation_state", {})
        if "tree_data" in sim_state:
            reset_status_recursive(sim_state["tree_data"])
            
        self.project_data["systems"][new_name] = new_data
        
        # 3. Copiar Archivos Físicos (Filtrado - Issue #4)
        src_path = os.path.join(self.current_project_path, "storage", source_name)
        dst_path = os.path.join(self.current_project_path, "storage", new_name)
        os.makedirs(dst_path, exist_ok=True)
        
        # Extensiones permitidas (Configuración)
        # NO copiamos .gro (porque viene de Setup nuevo), ni .tpr, .xtc, .log
        # SÍ copiamos .mdp (parámetros), .itp (topologías), .top (estructura general), .pdb (referencias)
        allowed_ext = ['.mdp', '.itp', '.top', '.pdb'] 
        
        try:
            for item in os.listdir(src_path):
                if any(item.endswith(ext) for ext in allowed_ext):
                    # Excepción especial: system_init.pdb a veces se quiere conservar como referencia,
                    # pero system.gro NO, porque ese es el resultado de editconf.
                    s = os.path.join(src_path, item)
                    d = os.path.join(dst_path, item)
                    if os.path.isfile(s):
                        shutil.copy2(s, d)
        except Exception as e:
            return False, f"Error copiando: {e}"

        self.active_system_name = new_name
        self.save_db()
        return True, "Sistema clonado (Configuración copiada, Estados reseteados)."

    def delete_system(self, sys_name):
        if sys_name not in self.project_data.get("systems", {}): return False, "No existe."
        sys_path = os.path.join(self.current_project_path, "storage", sys_name)
        try:
            if os.path.exists(sys_path): shutil.rmtree(sys_path)
        except Exception as e: return False, str(e)
            
        del self.project_data["systems"][sys_name]
        
        if self.active_system_name == sys_name:
            keys = list(self.project_data["systems"].keys())
            if keys: self.active_system_name = keys[0]
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
    
    def get_system_list(self):
        return list(self.project_data.get("systems", {}).keys())