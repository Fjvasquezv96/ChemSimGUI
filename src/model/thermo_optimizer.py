import numpy as np
from scipy import optimize, ndimage

class ThermoOptimizer:
    """
    Módulo especializado en estadística y optimización termodinámica.
    Se encarga de:
    1. Analizar la estabilidad de los perfiles RDF (Radio de corte).
    2. Realizar regresiones globales para obtener energías de interacción.
    3. Preparar datos para diagnósticos visuales (Arrhenius).
    """

    def __init__(self):
        # Constante de gases ideal (J / mol K)
        self.R = 8.314462618

    # =========================================================================
    # 1. ANÁLISIS DE ESTABILIDAD (RADIO DE CORTE)
    # =========================================================================

    def analyze_stability_region(self, r_axis, curves_list, window_width=50):
        """
        Analiza múltiples curvas de parámetros (tau vs r) para encontrar la región
        más estable (menor varianza/pendiente) común a todas.

        Args:
            r_axis (np.array): Eje X (radios).
            curves_list (list of np.array): Lista de curvas de parámetros de diferentes sistemas.
            window_width (int): Tamaño de la ventana para el cálculo de desviación local.

        Returns:
            dict: {
                'stability_profile': array (Métrica de inestabilidad vs r),
                'suggested_r': float (Radio sugerido),
                'smoothed_curves': list (Curvas suavizadas para visualización)
            }
        """
        if not curves_list or len(r_axis) == 0:
            return None

        # Inicializar el perfil de inestabilidad acumulada con ceros
        # Debe tener el mismo tamaño que el eje r
        total_instability = np.zeros_like(r_axis, dtype=float)
        smoothed_curves = []

        for curve in curves_list:
            # 1. Suavizado (Moving Average) para eliminar ruido de alta frecuencia
            # Usamos filtro uniforme de scipy para robustez
            smooth = ndimage.uniform_filter1d(curve, size=int(window_width))
            smoothed_curves.append(smooth)

            # 2. Cálculo de la derivada local (Pendiente)
            # Un plateau ideal tiene pendiente 0.
            gradient = np.gradient(smooth, r_axis)

            # 3. Cálculo de la varianza local (Ruido en la zona)
            # Usamos la identidad Var(X) = E[X^2] - E[X]^2 para eficiencia y evitar errores de 'generic_filter1d'
            # smooth ya es E[X] (media móvil)
            mean_sq = ndimage.uniform_filter1d(curve**2, size=int(window_width))
            sq_mean = smooth**2
            variance = mean_sq - sq_mean
            
            # Corrección numérica para valores negativos muy pequeños (flotantes)
            variance[variance < 0] = 0
            local_std = np.sqrt(variance)

            # 4. Métrica de Inestabilidad para esta curva
            # Combinamos pendiente^2 + varianza local.
            # Queremos minimizar ambos (pendiente cero y poco ruido).
            # Normalizamos para que no pesen más los valores grandes.
            instability = (np.abs(gradient) ** 2) + local_std
            
            # Acumular al perfil global
            total_instability += instability

        # 5. Encontrar el mínimo global en un rango físico razonable
        # Ignoramos radios muy pequeños (< 0.5 nm) donde hay exclusión de volumen
        # y radios muy grandes donde el RDF ya es 1.
        
        valid_mask = (r_axis > 0.5) & (r_axis < r_axis[-1] * 0.9)
        
        if np.any(valid_mask):
            # Extraer subsección válida
            valid_indices = np.where(valid_mask)[0]
            valid_instability = total_instability[valid_indices]
            
            # Encontrar índice del mínimo en la subsección
            min_idx_local = np.argmin(valid_instability)
            
            # Convertir a índice global
            best_idx = int(valid_indices[min_idx_local])
            suggested_r = r_axis[best_idx]
        else:
            # Fallback si el rango es muy corto
            suggested_r = r_axis[len(r_axis)//2]

        return {
            'stability_profile': total_instability,
            'suggested_r': suggested_r,
            'smoothed_curves': smoothed_curves
        }

    # =========================================================================
    # 2. OPTIMIZACIÓN GLOBAL (REGRESIÓN TERMODINÁMICA)
    # =========================================================================

    def fit_interaction_energies(self, temperature_list, param_list, model_type, opt_method='theoretical', active_mask=None):
        """
        Encuentra los parámetros de interacción que minimizan el error.
        
        Args:
            opt_method (str): 'theoretical' (Delta G) o 'empirical' (A + B/T).
        """
        # Filtrar datos usando la máscara (si el usuario desactivó puntos)
        T_data = []
        P_data = []
        
        if active_mask is None:
            active_mask = [True] * len(temperature_list)

        for i, active in enumerate(active_mask):
            if active:
                T_data.append(temperature_list[i])
                P_data.append(param_list[i])

        # Convertir a numpy para velocidad
        T_arr = np.array(T_data)
        P_arr = np.array(P_data)

        if len(T_arr) == 0:
            return {'energy': 0.0, 'params': [0, 0], 'error': 0.0}

        # --- MODO TEÓRICO: 1 PARÁMETRO (DELTA G) ---
        if opt_method == 'theoretical':
            def nrtl_residuals(delta_g_guess):
                tau_calc = delta_g_guess / (self.R * T_arr)
                return P_arr - tau_calc

            def wilson_residuals(delta_g_guess):
                ln_lambda_obs = np.log(np.maximum(P_arr, 1e-10))
                ln_lambda_calc = -delta_g_guess / (self.R * T_arr)
                return ln_lambda_obs - ln_lambda_calc
            
            initial_guess = [1000.0]
            if model_type == 'nrtl': result = optimize.least_squares(nrtl_residuals, initial_guess)
            else: result = optimize.least_squares(wilson_residuals, initial_guess)

            return {'energy': result.x[0], 'params': [0, result.x[0]/self.R], 'error': np.sqrt(np.mean(result.fun**2))}

        # --- MODO EMPÍRICO (CLAUDE): 2 PARÁMETROS (A + B/T) ---
        else:
            # Modelo Linearizado: Y = A + B * X
            # Donde X = 1/T
            X_arr = 1.0 / T_arr
            
            Y_arr = None
            if model_type == 'nrtl':
                # tau = A + B/T
                Y_arr = P_arr
            else:
                # Wilson: ln(lambda) = A + B/T
                Y_arr = np.log(np.maximum(P_arr, 1e-10))
            
            # Regression Lineal Simple (No requiere optimizador iterativo, solución exacta)
            # A = Intercept, B = Slope
            slope, intercept = np.polyfit(X_arr, Y_arr, 1) # Note: polyfit returns [slope, intercept] for degree 1
            
            # polyfit retorna [highest_order, ... , lowest_order]
            # p(x) = slope * x + intercept
            # Y = B * (1/T) + A
            B = slope
            A = intercept
            
            # Calcular error
            Y_pred = A + B * X_arr
            rmsd = np.sqrt(np.mean((Y_arr - Y_pred)**2))
            
            return {
                'energy': 0.0, # No aplica concepto único de energía
                'params': [A, B], 
                'error': rmsd
            }

    # =========================================================================
    # 3. HELPER PARA GRÁFICAS DE DIAGNÓSTICO (ARRHENIUS)
    # =========================================================================

    def get_arrhenius_data(self, temperature_list, param_list):
        """
        Prepara coordenadas X, Y para graficar ln(Param) vs 1000/T.
        Útil para validar visualmente la calidad de la simulación.
        """
        x_axis = [] # 1000 / T
        y_axis = [] # ln(Param)

        for T, P in zip(temperature_list, param_list):
            if T > 0 and P > 0:
                x_axis.append(1000.0 / T)
                y_axis.append(np.log(P))
            else:
                # Manejo de datos inválidos (ej. param negativo o cero)
                x_axis.append(None)
                y_axis.append(None)
        
        return x_axis, y_axis