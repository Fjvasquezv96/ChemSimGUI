import os
import re
import numpy as np

# Importación de la capa de Modelo
from src.model.analysis_parser import AnalysisParser
from src.model.thermo_solubility import ThermoMath
from src.model.thermo_optimizer import ThermoOptimizer

class SolubilityManager:
    """
    Controlador central para el flujo de trabajo de solubilidad (SLE).
    
    Responsabilidades:
    1. Gestionar rutas de archivos en el proyecto.
    2. Orquestar la generación de datos (RDFs) usando GROMACS.
    3. Extraer datos físicos (Densidad, Temperatura) de los logs/edr.
    4. Calcular parámetros de interacción (Wilson/NRTL) integrando RDFs.
    5. Realizar regresiones globales (Arrhenius) para predecir solubilidad.
    """
    
    def __init__(self, project_mgr):
        self.project_mgr = project_mgr
        
        # Instancias de los modelos
        self.parser = AnalysisParser()
        self.math_model = ThermoMath()
        self.optimizer = ThermoOptimizer() # Nuevo módulo de optimización estadística

    # =========================================================================
    # HELPERS DE RUTAS Y SISTEMA
    # =========================================================================

    def get_system_path(self, sys_name):
        """Devuelve la ruta absoluta a la carpeta storage de un sistema específico"""
        if not self.project_mgr or not self.project_mgr.current_project_path:
            return None
        return os.path.join(self.project_mgr.current_project_path, "storage", sys_name)

    def get_available_groups(self, system_name, step_name):
        """
        Lee los grupos disponibles de un sistema específico para llenar los ComboBoxes.
        Intenta buscar cualquier TPR que coincida con el paso para leer el índice.
        """
        path = self.get_system_path(system_name)
        if not path or not os.path.exists(path):
            return {}
        
        # Intentamos encontrar un TPR válido con el prefijo
        tpr_path = None
        try:
            for f in os.listdir(path):
                if f.startswith(step_name) and f.endswith(".tpr"):
                    tpr_path = os.path.join(path, f)
                    break
        except Exception:
            pass
            
        if not tpr_path:
            # Fallback: intentar nombre exacto
            tpr_path = os.path.join(path, f"{step_name}.tpr")
        
        # El parser se encarga de ejecutar gmx make_ndx y leer el resultado
        return self.parser.get_gromacs_groups(tpr_path, path)

    # =========================================================================
    # LÓGICA DE GRUPOS PERSONALIZADOS (SOLUCIÓN UNL / CONTEO)
    # =========================================================================

    def force_creation_of_count_groups(self, sys_name, step_name, n_solute, n_solvent):
        """
        Genera explícitamente el index.ndx separando átomos por CANTIDAD (N1, N2).
        Esto soluciona el problema cuando todas las moléculas se llaman 'UNL'.
        """
        path = self.get_system_path(sys_name)
        if not path:
            return False, "Ruta no encontrada"

        # Intentar buscar el GRO de referencia para contar átomos
        # 1. system.gro (Salida inicial)
        gro_ref = os.path.join(path, "system.gro")
        
        # 2. Si no existe, buscar algun output de la simulación
        if not os.path.exists(gro_ref):
            # Buscar cualquier .gro que empiece con el paso
            try:
                candidates = [f for f in os.listdir(path) if f.startswith(step_name) and f.endswith(".gro")]
                if candidates:
                    gro_ref = os.path.join(path, candidates[0])
            except:
                pass
        
        if not os.path.exists(gro_ref):
            return False, f"No se encontró archivo de estructura (.gro) en {sys_name}"

        # El archivo índice destino
        ndx_file = os.path.join(path, "index.ndx")

        # Llamar al parser para generar por conteo
        # Usamos nombres fijos claros: Custom_Solute y Custom_Solvent
        success, msg = self.parser.generate_index_by_counts(
            gro_ref, 
            ndx_file, 
            n_solute, 
            n_solvent, 
            name_solute="Custom_Solute", 
            name_solvent="Custom_Solvent"
        )
        
        return success, msg

    def _resolve_group_id(self, tpr, path, group_name):
        """
        Intenta encontrar el ID de un grupo. Si no existe, intenta crearlo.
        Estrategia defensiva: Buscar -> Crear Residuo -> Buscar -> Crear Átomo -> Buscar.
        """
        # 1. Buscar en grupos existentes
        groups = self.parser.get_gromacs_groups(tpr, path)
        if group_name in groups:
            return groups[group_name]
        
        # 2. Si no existe, intentar crear por Nombre de Residuo (r Name)
        self.parser.add_custom_group(tpr, path, f"r {group_name}")
        
        # 3. Recargar y verificar
        groups = self.parser.get_gromacs_groups(tpr, path)
        if group_name in groups:
            return groups[group_name]
            
        # 4. Si falla, intentar por Nombre de Átomo (a Name)
        self.parser.add_custom_group(tpr, path, f"a {group_name}")
        
        # 5. Último intento de verificación
        groups = self.parser.get_gromacs_groups(tpr, path)
        if group_name in groups:
            return groups[group_name]
            
        return None

    # =========================================================================
    # 1. GENERACIÓN DE DATOS (BATCH RDF - ESCANEO DE TEMPERATURAS)
    # =========================================================================

    def run_batch_rdfs(self, systems_config, step_prefix, solute_group, solvent_group):
        """
        Genera las 3 RDFs necesarias para cada simulación encontrada.
        Soporta múltiples temperaturas escaneando el prefijo.
        
        Yields: (Mensaje, Estado)
        """
        for sys_data in systems_config:
            sys_name = sys_data['name']
            path = self.get_system_path(sys_name)
            
            yield f"Escaneando sistema: {sys_name}...", True
            
            if not path or not os.path.exists(path):
                yield f"Error: No existe carpeta para {sys_name}", False
                continue

            # --- ESCANEO DE ARCHIVOS TPR POR PREFIJO ---
            # Esto permite encontrar prod.tpr, prod_300.tpr, prod_310.tpr automáticamente
            try:
                tpr_files = [f for f in os.listdir(path) if f.startswith(step_prefix) and f.endswith(".tpr")]
            except Exception as e:
                yield f"Error leyendo directorio: {e}", False
                continue
            
            if not tpr_files:
                yield f"No se encontraron simulaciones con prefijo '{step_prefix}' en {sys_name}", False
                continue

            # --- PREPARACIÓN DE ÍNDICE (Una vez por sistema si es Custom) ---
            if solute_group == "Custom_Solute" or solvent_group == "Custom_Solvent":
                # Usamos system.gro como referencia base
                gro_ref = os.path.join(path, "system.gro")
                # Si no existe, usamos el primer .gro que encontremos
                if not os.path.exists(gro_ref):
                    try:
                        gros = [f for f in os.listdir(path) if f.startswith(step_prefix) and f.endswith(".gro")]
                        if gros: gro_ref = os.path.join(path, gros[0])
                    except: pass
                
                if os.path.exists(gro_ref):
                    try:
                        self.parser.generate_index_by_counts(
                            gro_ref, 
                            os.path.join(path, "index.ndx"), 
                            int(sys_data['n_solute']), 
                            int(sys_data['n_solvent']),
                            "Custom_Solute", "Custom_Solvent"
                        )
                    except: pass # Si falla, intentaremos resolver IDs más adelante

            # --- PROCESAR CADA SIMULACIÓN ---
            for tpr_file in tpr_files:
                # Nombre base de esta simulación específica (ej: prod_300)
                sim_base = os.path.splitext(tpr_file)[0]
                
                tpr_path = os.path.join(path, tpr_file)
                
                # Buscar trayectoria correspondiente
                # Prioridad: 1. clean.xtc, 2. .xtc
                xtc_path = os.path.join(path, f"{sim_base}_clean.xtc")
                if not os.path.exists(xtc_path):
                    xtc_path = os.path.join(path, f"{sim_base}.xtc")
                
                if not os.path.exists(xtc_path):
                    yield f"Saltando {sim_base}: Falta trayectoria .xtc", False
                    continue

                yield f"Calculando RDFs para {sys_name} / {sim_base}...", True

                # Resolver IDs para esta simulación específica
                id_solute = self._resolve_group_id(tpr_path, path, solute_group)
                id_solvent = self._resolve_group_id(tpr_path, path, solvent_group)
                
                if id_solute is None or id_solvent is None:
                    yield f"Error en {sim_base}: No se encuentran grupos {solute_group}/{solvent_group}", False
                    continue

                # Carpeta de salida
                out_dir = os.path.join(path, "solubility_data")
                os.makedirs(out_dir, exist_ok=True)

                # Definir pares: 11 (Sol-Sol), 22 (Slv-Slv), 12 (Sol-Slv)
                # Usamos sufijo único para no sobrescribir entre temperaturas
                suffix = f"_{sim_base}"
                pairs = [
                    (id_solute, id_solute, f"rdf_11{suffix}.xvg"),
                    (id_solvent, id_solvent, f"rdf_22{suffix}.xvg"),
                    (id_solute, id_solvent, f"rdf_12{suffix}.xvg")
                ]

                success_count = 0
                for ref, sel, fname in pairs:
                    out_xvg = os.path.join(out_dir, fname)
                    
                    # Ejecutar RDF:
                    # - Centro de Masa (use_com=True)
                    # - Bin 0.002 nm
                    # - Cutoff 3.0 nm (para asegurar cola larga)
                    success, msg = self.parser.run_gmx_rdf(
                        tpr_path, xtc_path, out_xvg, ref, sel, path, 
                        use_com=True, bin_width=0.002, cutoff=3.0
                    )
                    
                    if success:
                        success_count += 1
                    else:
                        yield f"Fallo RDF {fname}: {msg}", False
                
                if success_count == 3:
                    # yield f"OK: {sim_base}", True # Opcional, para no saturar log
                    pass

            yield f"Sistema {sys_name} procesado.", True

    # =========================================================================
    # 2. EXTRACCIÓN DE DATOS FÍSICOS (DENSIDAD Y TEMPERATURA REAL)
    # =========================================================================

    def get_physical_data(self, path, base_name):
        """
        Lee el archivo .edr para obtener Volumen y Temperatura promedio.
        Retorna: (vol_avg, temp_avg)
        """
        edr = os.path.join(path, f"{base_name}.edr")
        if not os.path.exists(edr):
            return None, None
        
        # Archivos temporales
        out_vol = os.path.join(path, f"tmp_vol_{base_name}.xvg")
        out_tem = os.path.join(path, f"tmp_tem_{base_name}.xvg")
        
        # Extraer Volumen
        self.parser.run_gmx_energy(edr, out_vol, ["Volume"])
        # Extraer Temperatura
        self.parser.run_gmx_energy(edr, out_tem, ["Temperature"])
        
        vol_avg = None
        temp_avg = None
        
        # Leer Volumen
        _, _, yv = self.parser.get_data_from_file(out_vol)
        if yv and len(yv) > 0:
            vol_avg = np.mean(yv[0])
            
        # Leer Temperatura con validación de sanidad
        lbls_t, _, yt = self.parser.get_data_from_file(out_tem)
        if yt and len(yt) > 0:
            val = np.mean(yt[0])
            
            # Validación: gmx energy a veces falla o selecciona la propiedad incorrecta.
            # 1. Comprobar la etiqueta del eje Y si existe
            label_ok = True
            if len(lbls_t) > 1 and lbls_t[1]:
                yl = lbls_t[1].lower()
                # Si dice explícitamente Pressure, Density, Virial, etc. rechazamos
                if "pressure" in yl or "density" in yl or "virial" in yl:
                    label_ok = False
            
            # 2. Comprobar rango físico (10K - 10000K)
            # Valores como 0.7 suelen ser presión (bar) o densidad normalizada, no temperatura en K.
            range_ok = (10.0 < val < 10000.0)
            
            if label_ok and range_ok:
                temp_avg = val
            
        # Limpieza
        try:
            if os.path.exists(out_vol): os.remove(out_vol)
            if os.path.exists(out_tem): os.remove(out_tem)
        except:
            pass
            
        return vol_avg, temp_avg

    # =========================================================================
    # 3. CÁLCULO DE PARÁMETROS (INTEGRACIÓN)
    # =========================================================================

    def calculate_params_profile(self, systems_config, step_prefix, model_type, solute_mw, solvent_mw):
        """
        Escanea todos los sistemas y todas las simulaciones dentro de ellos.
        Integra las RDFs y calcula los perfiles de parámetros.
        
        Returns:
            Dict con claves únicas 'Sistema::Simulacion'.
        """
        results = {}
        
        for sys_data in systems_config:
            sys_name = sys_data['name']
            path = self.get_system_path(sys_name)
            data_dir = os.path.join(path, "solubility_data")
            
            if not os.path.exists(data_dir):
                continue
                
            # Buscar archivos RDF generados (que tienen sufijo de simulacion)
            # Buscamos rdf_12_{SIMULACION}.xvg
            try:
                files = os.listdir(data_dir)
            except:
                continue
                
            rdf12_files = [f for f in files if f.startswith("rdf_12_") and f.endswith(".xvg")]
            
            for f in rdf12_files:
                # Extraer nombre base de la simulación
                # Formato esperado: rdf_12_prod_298.xvg -> prod_298
                sim_base_name = f.replace("rdf_12_", "").replace(".xvg", "")
                
                # Verificar si coincide con el prefijo solicitado
                if not sim_base_name.startswith(step_prefix):
                    continue
                
                # Verificar pares completos
                f11 = os.path.join(data_dir, f"rdf_11_{sim_base_name}.xvg")
                f22 = os.path.join(data_dir, f"rdf_22_{sim_base_name}.xvg")
                f12 = os.path.join(data_dir, f)
                
                if not (os.path.exists(f11) and os.path.exists(f22)):
                    continue
                
                # Obtener Datos Físicos Reales
                vol_real, temp_real = self.get_physical_data(path, sim_base_name)
                
                # Fallbacks si falla lectura de energía
                if not vol_real: 
                    # Estimación densidad ~1
                    try:
                        n1 = int(sys_data['n_solute'])
                        n2 = int(sys_data['n_solvent'])
                        mass_g = (n1*solute_mw + n2*solvent_mw)/6.022e23
                        vol_real = mass_g * 1e21
                    except:
                        continue
                        
                if not temp_real:
                    # Intento de recuperación heurística: extraer T del nombre de simulación
                    # Ej: prod_298, npt_300 -> 298.0, 300.0
                    match = re.search(r'[-_](\d{3})', sim_base_name)
                    if match:
                        try:
                            t_guess = float(match.group(1))
                            # Validar que sea una temperatura razonable (100K - 1000K)
                            if 100 <= t_guess <= 1000:
                                temp_real = t_guess
                        except:
                            pass

                    # Fallback final si no se pudo recuperar
                    if not temp_real:
                        temp_real = 298.15
                
                # Densidades numéricas
                try:
                    n1 = int(sys_data['n_solute'])
                    n2 = int(sys_data['n_solvent'])
                    rho1 = n1 / vol_real
                    rho2 = n2 / vol_real
                except:
                    continue
                
                # Leer RDFs
                _, r, y11 = self.parser.get_data_from_file(f11)
                _, _, y22 = self.parser.get_data_from_file(f22)
                _, _, y12 = self.parser.get_data_from_file(f12)
                
                if not len(y11) or not len(y22) or not len(y12):
                    continue

                g11 = y11[0]
                g22 = y22[0]
                g12 = y12[0]
                
                # Truncar longitudes
                min_len = min(len(r), len(g11), len(g22), len(g12))
                r = r[:min_len]
                g11 = g11[:min_len]; g22 = g22[:min_len]; g12 = g12[:min_len]
                
                # Integración CN
                n11 = self.math_model.calculate_coordination_number(r, g11, rho1)
                n22 = self.math_model.calculate_coordination_number(r, g22, rho2)
                n12 = self.math_model.calculate_coordination_number(r, g12, rho2)
                n21 = self.math_model.calculate_coordination_number(r, g12, rho1)
                
                # Omegas
                omega12 = self.math_model.calculate_local_composition_ratio(n12, n22)
                omega21 = self.math_model.calculate_local_composition_ratio(n21, n11)
                
                # Modelos
                p12, p21 = None, None
                if model_type == 'wilson':
                    v1 = sys_data.get('v1', solute_mw)
                    v2 = sys_data.get('v2', solvent_mw)
                    p12, p21 = self.math_model.get_wilson_params(omega12, omega21, v1, v2)
                elif model_type == 'nrtl':
                    p12, p21 = self.math_model.get_nrtl_params(omega12, omega21)
                
                # Clave única compuesta
                unique_key = f"{sys_name}::{sim_base_name}"
                
                results[unique_key] = {
                    'system': sys_name,
                    'simulation': sim_base_name,
                    'r': r, 
                    'omega12': omega12, # Cacheamos omegas
                    'omega21': omega21, # Cacheamos omegas
                    'p12': p12, 'p21': p21,
                    'x_solute': sys_data['x_solute'],
                    'temperature': temp_real
                }
                
        return results

    def recalculate_model_params(self, current_results, model_type, v1=None, v2=None):
        """
        Recalcula P12 y P21 usando los omegas cacheados sin releer archivos.
        """
        updated_count = 0
        for key, data in current_results.items():
            if 'omega12' not in data or 'omega21' not in data:
                continue
                
            o12 = data['omega12']
            o21 = data['omega21']
            
            p12, p21 = None, None
            if model_type == 'wilson':
                # v1 y v2 son obligatorios para Wilson
                # Si no se pasan, intentamos usar defaults (aunque deberian pasarse desde la UI)
                _v1 = v1 if v1 else 300.0
                _v2 = v2 if v2 else 100.0
                p12, p21 = self.math_model.get_wilson_params(o12, o21, _v1, _v2)
            elif model_type == 'nrtl':
                p12, p21 = self.math_model.get_nrtl_params(o12, o21)
            
            data['p12'] = p12
            data['p21'] = p21
            updated_count += 1
            
        return updated_count

    # =========================================================================
    # 4. OPTIMIZACIÓN Y ANÁLISIS DE ESTABILIDAD
    # =========================================================================

    def analyze_cutoff_stability(self, calculated_data):
        """Wrapper para el optimizador de estabilidad"""
        curves = []
        r_axis = None
        
        for d in calculated_data.values():
            if len(d['r']) > 0:
                if r_axis is None: r_axis = d['r']
                min_l = min(len(r_axis), len(d['p12']))
                curves.append(d['p12'][:min_l])
                r_axis = r_axis[:min_l]
        
        if not curves: return None
        return self.optimizer.analyze_stability_region(r_axis, curves)

    # =========================================================================
    # 5. PREDICCIÓN CON REGRESIÓN GLOBAL
    # =========================================================================

    def predict_with_global_optimization(self, calculated_data, radius_cut, tm, hfus, model, use_lowest_x_only, opt_method='theoretical', t_range=None, extra_params=None):
        """
        Realiza la regresión global para obtener Delta G (o A+B/T) y luego predice la curva.
        """
        if extra_params is None: extra_params = {}
        # 1. Extraer puntos al radio de corte
        valid_points = []
        for key, d in calculated_data.items():
            if len(d['r']) == 0: continue
            
            # Interpolación o índice cercano
            idx = (np.abs(d['r'] - radius_cut)).argmin()
            
            valid_points.append({
                'T': d['temperature'],
                'x': float(d['x_solute']),
                'p12': d['p12'][idx],
                'p21': d['p21'][idx]
            })
            
        if not valid_points: return None, None, None
        
        # 2. Agrupar por Temperatura
        grouped_T = {}
        for p in valid_points:
            t_round = round(p['T'], 1)
            if t_round not in grouped_T: grouped_T[t_round] = []
            grouped_T[t_round].append(p)
            
        # 3. Preparar datos para Regresión y Arrhenius
        arrhenius_data = {'x': [], 'y12': [], 'y21': [], 'labels': []}
        
        temp_list = []
        p12_list = []
        p21_list = []
        
        for t_val, points in grouped_T.items():
            # Filtro Lowest X
            if use_lowest_x_only:
                selected = sorted(points, key=lambda k: k['x'])[0]
                points_use = [selected]
            else:
                points_use = points
            
            # Promedio local para esta T
            avg_p12 = np.mean([x['p12'] for x in points_use])
            avg_p21 = np.mean([x['p21'] for x in points_use])
            
            if avg_p12 > 0 and avg_p21 > 0:
                temp_list.append(t_val)
                p12_list.append(avg_p12)
                p21_list.append(avg_p21)
                
                # Datos gráfico
                arrhenius_data['x'].append(1000.0 / t_val)
                arrhenius_data['y12'].append(np.log(avg_p12))
                arrhenius_data['y21'].append(np.log(avg_p21))
                arrhenius_data['labels'].append(f"{t_val}K")

        # 4. Ajuste Global usando el Optimizador
        # Nota: fit_interaction_energies ya maneja el modo (Theoretical vs Empirical)
        fit12 = self.optimizer.fit_interaction_energies(temp_list, p12_list, model, opt_method=opt_method)
        fit21 = self.optimizer.fit_interaction_energies(temp_list, p21_list, model, opt_method=opt_method)
        
        if not fit12 or not fit21: return None, None, None
        
        # Datos de líneas de ajuste para gráfico (Arrhenius)
        if arrhenius_data['x']:
            min_x, max_x = min(arrhenius_data['x']), max(arrhenius_data['x'])
            fit_x_axis = np.array([min_x, max_x])
            
            # Función local para calcular líneas de ajuste visuales
            def get_ln_p_fitted(x_val, fit_res, method):
                T_calc = 1000.0 / x_val
                R = 8.314
                
                if method == 'empirical':
                    # Modelo Ajustado: tau = A + B/T
                    A, B = fit_res['params']
                    val = A + B / T_calc
                    
                    if model == 'nrtl':
                        # NRTL tau devuelve directo. Para plot arrhenius graficamos ln(tau)
                        return np.log(val) if val > 0 else -10
                    else:
                        # Wilson Params son Lambda. Modelo ajustado ln(lambda) = A + B/T
                        # Devolvemos val directo (que ya es ln)
                        return val
                
                else: # Theoretical
                    energy = fit_res['energy']
                    if model == 'nrtl':
                        p_val = energy / (R * T_calc)
                        # Evitar log(0)
                        return np.log(p_val) if p_val > 0 else -10
                    else: 
                        # Wilson Lambda = exp(-dg/RT) -> ln = -dg/RT
                        return -energy / (R * T_calc)

            arrhenius_data['fit_x'] = fit_x_axis
            arrhenius_data['fit_y12'] = [get_ln_p_fitted(x, fit12, opt_method) for x in fit_x_axis]
            arrhenius_data['fit_y21'] = [get_ln_p_fitted(x, fit21, opt_method) for x in fit_x_axis]

        # 5. Generar Curva de Predicción Final (Sólido-Líquido)
        if t_range:
            t_min, t_max = t_range
            tr = np.linspace(t_min, t_max, 50)
        else:
            # Default fallback
            tr = np.linspace(tm * 0.7, tm * 0.99, 50)

        xr = []
        
        # Función local para evaluar parámetro a cualquier T
        def eval_param_at_T(fit_res, T_sol, method):
            R = 8.314
            if method == 'empirical':
                A, B = fit_res['params']
                val = A + B / T_sol
                if model == 'wilson': return np.exp(val) # Wilson
                else: return val # NRTL
            else:
                dg = fit_res['energy']
                if model == 'wilson': return np.exp(-dg / (R * T_sol))
                else: return dg / (R * T_sol)
        
        for T in tr:
            p12_T = eval_param_at_T(fit12, T, opt_method)
            p21_T = eval_param_at_T(fit21, T, opt_method)
            
            # Construir dict de params
            solver_params = {'p12': p12_T, 'p21': p21_T, 'alpha': 0.3}
            if extra_params: solver_params.update(extra_params)
            
            x = self.math_model.solve_sle_solubility(
                T, tm, hfus, model, solver_params
            )
            xr.append(x)
            
        return tr, xr, arrhenius_data, {'fit12': fit12, 'fit21': fit21}

    def predict_solubility_curve(self, t, tm, h, mod, p):
        # Wrapper legacy
        return self.math_model.predict_solubility_curve(t, tm, h, mod, p)