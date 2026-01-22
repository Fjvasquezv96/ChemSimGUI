import os
import numpy as np
from src.model.analysis_parser import AnalysisParser
from src.model.thermo_solubility import ThermoMath

class SolubilityManager:
    """
    Controlador que orquesta el flujo de trabajo para el cálculo de solubilidad via SLE.
    Conecta los archivos físicos de GROMACS con el modelo matemático de Termodinámica.
    """
    def __init__(self, project_mgr):
        self.project_mgr = project_mgr
        self.parser = AnalysisParser()
        self.math_model = ThermoMath()

    def get_system_path(self, sys_name):
        """Devuelve la ruta absoluta a la carpeta storage de un sistema específico"""
        if not self.project_mgr or not self.project_mgr.current_project_path:
            return None
        return os.path.join(self.project_mgr.current_project_path, "storage", sys_name)

    # =========================================================================
    # 1. GENERACIÓN DE DATOS (BATCH RDF)
    # =========================================================================

    def run_batch_rdfs(self, systems_config, step_name, solute_group, solvent_group):
        """
        Genera las 3 RDFs necesarias (1-1, 2-2, 1-2) para cada sistema en la lista.
        
        Args:
            systems_config (list): Lista de dicts [{'name': 'SysA', ...}, ...]
            step_name (str): Nombre del paso de producción (ej: 'prod')
            solute_group (str): Nombre del grupo Soluto en index.ndx
            solvent_group (str): Nombre del grupo Solvente en index.ndx
            
        Returns:
            generator: Yields (progreso_str, exito_bool)
        """
        for sys_data in systems_config:
            sys_name = sys_data['name']
            path = self.get_system_path(sys_name)
            
            if not path or not os.path.exists(path):
                yield f"Error: No existe carpeta para {sys_name}", False
                continue

            # Archivos base
            tpr = os.path.join(path, f"{step_name}.tpr")
            xtc = os.path.join(path, f"{step_name}.xtc") # O clean
            if not os.path.exists(xtc):
                xtc = os.path.join(path, f"{step_name}_clean.xtc")
            
            if not os.path.exists(tpr) or not os.path.exists(xtc):
                yield f"Saltando {sys_name}: Faltan archivos .tpr/.xtc", False
                continue

            # Obtener IDs de grupos
            groups = self.parser.get_gromacs_groups(tpr, path)
            id_solute = groups.get(solute_group)
            id_solvent = groups.get(solvent_group)

            if id_solute is None or id_solvent is None:
                # Intentar crearlos si no existen
                yield f"Generando grupos para {sys_name}...", True
                if id_solute is None:
                    self.parser.add_custom_group(tpr, path, f"a {solute_group}" if len(solute_group)<4 else f"r {solute_group}")
                if id_solvent is None:
                    self.parser.add_custom_group(tpr, path, f"a {solvent_group}" if len(solvent_group)<4 else f"r {solvent_group}")
                
                # Recargar
                groups = self.parser.get_gromacs_groups(tpr, path)
                id_solute = groups.get(solute_group)
                id_solvent = groups.get(solvent_group)
            
            if id_solute is None or id_solvent is None:
                yield f"Error {sys_name}: No se pudieron identificar grupos {solute_group}/{solvent_group}", False
                continue

            # Carpeta de salida organizada
            out_dir = os.path.join(path, "solubility_data")
            os.makedirs(out_dir, exist_ok=True)

            # Definir las 3 parejas: 1-1, 2-2, 1-2
            pairs = [
                (id_solute, id_solute, "rdf_11.xvg"),
                (id_solvent, id_solvent, "rdf_22.xvg"),
                (id_solute, id_solvent, "rdf_12.xvg")
            ]

            for ref, sel, fname in pairs:
                out_xvg = os.path.join(out_dir, fname)
                # Ejecutar RDF con Centros de Masa (CRÍTICO para Yousefi method)
                # Bin width default 0.002 nm
                success, msg = self.parser.run_gmx_rdf(
                    tpr, xtc, out_xvg, ref, sel, path, 
                    use_com=True, bin_width=0.002, cutoff=2.5
                )
                if not success:
                    yield f"Error RDF {sys_name} ({fname}): {msg}", False
            
            yield f"RDFs calculadas para {sys_name}", True

    # =========================================================================
    # 2. EXTRACCIÓN DE DATOS FÍSICOS (Densidad y Volumen)
    # =========================================================================

    def get_system_volume_average(self, sys_name, step_name):
        """
        Ejecuta gmx energy para obtener el volumen promedio (nm^3).
        Necesario para calcular la densidad numérica exacta.
        """
        path = self.get_system_path(sys_name)
        edr = os.path.join(path, f"{step_name}.edr")
        out = os.path.join(path, "temp_vol.xvg")
        
        # Ejecutar energy solo para Volumen
        success, _ = self.parser.run_gmx_energy(edr, out, ["Volume"])
        if not success: return None
        
        # Leer y promediar
        _, _, y_list = self.parser.get_data_from_file(out)
        if y_list:
            vol_avg = np.mean(y_list[0]) # nm^3
            # Limpiar temporal
            try: os.remove(out)
            except: pass
            return vol_avg
        return None

    # =========================================================================
    # 3. CÁLCULO DE PARÁMETROS (INTEGRACIÓN)
    # =========================================================================

    def calculate_params_profile(self, systems_config, step_name, model_type, solute_mw, solvent_mw):
        """
        Calcula el perfil de parámetros de interacción vs Radio para todos los sistemas.
        
        Args:
            systems_config: Lista con metadatos (nombre, N_soluto, N_solvente).
            model_type: 'wilson', 'nrtl', 'uniquac'.
            
        Returns:
            Dict estructurado: { 
               'sys_name': {
                   'r': array, 
                   'param12': array, 
                   'param21': array,
                   'cn11': array, 'cn22': array, 'cn12': array
               } 
            }
        """
        results = {}
        
        for sys_data in systems_config:
            name = sys_data['name']
            N1 = int(sys_data['n_solute'])
            N2 = int(sys_data['n_solvent'])
            
            path = self.get_system_path(name)
            data_dir = os.path.join(path, "solubility_data")
            
            # 1. Obtener Volumen Promedio para Densidades
            vol_nm3 = self.get_system_volume_average(name, step_name)
            if not vol_nm3: 
                print(f"Error: No se pudo obtener volumen para {name}")
                continue
            
            # Densidades numéricas globales (Global Number Density)
            # rho = N / V
            rho1 = N1 / vol_nm3
            rho2 = N2 / vol_nm3
            
            # 2. Leer RDFs
            # get_data_from_file retorna (labels, x, [y])
            _, r, y11 = self.parser.get_data_from_file(os.path.join(data_dir, "rdf_11.xvg"))
            _, _, y22 = self.parser.get_data_from_file(os.path.join(data_dir, "rdf_22.xvg"))
            _, _, y12 = self.parser.get_data_from_file(os.path.join(data_dir, "rdf_12.xvg"))
            
            if not len(y11) or not len(y22) or not len(y12):
                print(f"Error: Faltan datos RDF en {name}")
                continue

            g11, g22, g12 = y11[0], y22[0], y12[0]
            
            # Asegurar que todos tengan la misma longitud (r)
            # A veces gmx corta si el radio es distinto. Truncamos al mínimo común.
            min_len = min(len(r), len(g11), len(g22), len(g12))
            r = r[:min_len]
            g11 = g11[:min_len]
            g22 = g22[:min_len]
            g12 = g12[:min_len]
            
            # 3. Calcular Números de Coordinación (Running Integration)
            # Pasamos la densidad de la especie "vecina" (j)
            n11 = self.math_model.calculate_coordination_number(r, g11, rho1)
            n22 = self.math_model.calculate_coordination_number(r, g22, rho2)
            
            # Para n12 (soluto alrededor de soluto? No, soluto-solvente)
            # n_ij: moléculas j alrededor de i. Usamos rho_j.
            n12 = self.math_model.calculate_coordination_number(r, g12, rho2)
            n21 = self.math_model.calculate_coordination_number(r, g12, rho1) # g12 = g21
            
            # 4. Calcular Omegas
            omega12 = self.math_model.calculate_local_composition_ratio(n12, n22)
            omega21 = self.math_model.calculate_local_composition_ratio(n21, n11)
            
            # 5. Calcular Parámetros de Energía según Modelo
            p12, p21 = None, None
            
            if model_type == 'wilson':
                # Necesitamos volúmenes molares.
                # Estimación simple: V ~ MW (muy burdo) o usar el input del usuario.
                # Aquí usamos MW como proxy si no hay dato, pero idealmente Vm.
                # El usuario provee Vm1 y Vm2 en la GUI.
                v1 = sys_data.get('v1', solute_mw) # Fallback a MW si no hay Vm
                v2 = sys_data.get('v2', solvent_mw)
                p12, p21 = self.math_model.get_wilson_params(omega12, omega21, v1, v2)
                
            elif model_type == 'nrtl':
                p12, p21 = self.math_model.get_nrtl_params(omega12, omega21)
                
            elif model_type == 'uniquac':
                # Requiere parámetros q (área).
                q1 = sys_data.get('q1', 1.0)
                q2 = sys_data.get('q2', 1.0)
                p12, p21 = self.math_model.get_uniquac_params(omega12, omega21, q1, q2)

            # Guardar resultados
            results[name] = {
                'r': r,
                'p12': p12,
                'p21': p21,
                'cn12': n12,
                'cn21': n21,
                'x_solute': sys_data['x_solute'] # Para graficar vs composición luego
            }
            
        return results

    # =========================================================================
    # 4. PREDICCIÓN FINAL
    # =========================================================================

    def predict_solubility_curve(self, temp_range, Tm, Hfus, model_type, params_at_sat):
        """
        Genera la curva x_sat vs T.
        params_at_sat: Los parámetros (tau12, tau21) optimizados o seleccionados.
        """
        x_pred = []
        for T in temp_range:
            # Asumimos que los parámetros son constantes con T (hipótesis fuerte)
            # O si son dependientes de T (como en Wilson), se ajustan aquí.
            # En el método de Yousefi, los parámetros Lambda de Wilson dependen de T implícitamente en el exponencial.
            # Pero el valor extraído del MD ya es el término de energía.
            
            # Llamamos al solver
            x = self.math_model.solve_sle_solubility(T, Tm, Hfus, model_type, params_at_sat)
            x_pred.append(x)
            
        return x_pred