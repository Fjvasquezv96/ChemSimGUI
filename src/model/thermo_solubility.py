import numpy as np
from scipy import integrate, optimize

class ThermoMath:
    """
    Motor matemático para cálculos de Equilibrio Sólido-Líquido (SLE)
    basados en Dinámica Molecular.
    
    Contiene:
    1. Integración numérica de RDFs.
    2. Conversión de propiedades micro (RDF) a macro (Wilson/NRTL).
    3. Solvers de ecuaciones no lineales para solubilidad.
    """
    
    # Constante de gases ideal (J / mol K)
    R = 8.314462618

    def __init__(self):
        pass

    # =========================================================================
    # 1. INTEGRACIÓN DE RDF (Dinámica Molecular -> Propiedades Estructurales)
    # =========================================================================

    def calculate_coordination_number(self, r_nm, g_r, number_density_j):
        """
        Calcula el Número de Coordinación acumulado n(r).
        Eq: n_ij(R) = 4 * pi * rho_j * integral(0->R) of (r^2 * g_ij(r) dr)
        
        Args:
            r_nm (np.array): Eje X del RDF (distancia en nm).
            g_r (np.array): Eje Y del RDF (adimensional).
            number_density_j (float): Densidad numérica de la especie J (molecules/nm^3).
        
        Returns:
            np.array: Array del mismo tamaño que r_nm con el CN acumulado.
        """
        # Integrando: 4 * pi * r^2 * g(r)
        # Nota: r_nm está en nm, rho en 1/nm^3
        integrand = 4 * np.pi * (r_nm ** 2) * g_r
        
        # Integración numérica acumulativa (Regla del trapecio)
        cumulative_integral = integrate.cumulative_trapezoid(integrand, r_nm, initial=0)
        
        cn_profile = number_density_j * cumulative_integral
        return cn_profile

    def calculate_local_composition_ratio(self, n_ij, n_jj):
        """
        Calcula el ratio de composición local (Omega_ij).
        Omega_ij = n_ij / n_jj
        Ref: Yousefi Seyf & Haghtalab (2017).
        """
        # Evitar división por cero
        with np.errstate(divide='ignore', invalid='ignore'):
            omega = n_ij / n_jj
            # Si n_jj es 0, omega es 0 (o infinito, pero para modelos de actividad 0 es más seguro inicial)
            omega[n_jj == 0] = 0.0
            # Reemplazar infinitos si ocurren
            omega = np.nan_to_num(omega, posinf=0.0, neginf=0.0)
            
        return omega

    # =========================================================================
    # 2. CONVERSIÓN A PARÁMETROS DE MODELOS (Micro -> Macro)
    # =========================================================================

    def get_wilson_params(self, omega_12, omega_21, v1, v2):
        """
        Convierte Omega (del MD) a Lambda (Wilson).
        Lambda_12 = (V2 / V1) * Omega_12
        """
        lambda_12 = (v2 / v1) * omega_12
        lambda_21 = (v1 / v2) * omega_21
        return lambda_12, lambda_21

    def get_nrtl_params(self, omega_12, omega_21, alpha=0.3):
        """
        Convierte Omega a Tau (NRTL).
        Eq: exp(-alpha * tau_12) = Omega_12
        => tau_12 = -ln(Omega_12) / alpha
        """
        # Evitar log de cero
        omega_12 = np.maximum(omega_12, 1e-10)
        omega_21 = np.maximum(omega_21, 1e-10)
        
        tau_12 = -np.log(omega_12) / alpha
        tau_21 = -np.log(omega_21) / alpha
        return tau_12, tau_21

    def get_uniquac_params(self, omega_12, omega_21, q1, q2):
        """
        Convierte Omega a Tau (UNIQUAC - Aproximación simple).
        """
        # Depende de la implementación exacta, aquí usamos la relación de radios
        tau_12 = (q2 / q1) * omega_12
        tau_21 = (q1 / q2) * omega_21
        return tau_12, tau_21

    # =========================================================================
    # 3. MODELOS DE ACTIVIDAD (Cálculo de Gamma)
    # =========================================================================

    def activity_wilson(self, x1, lambda_12, lambda_21):
        """Calcula gamma_1 usando Wilson."""
        x2 = 1.0 - x1
        # Evitar log(0)
        term1 = x1 + lambda_12 * x2
        term2 = x2 + lambda_21 * x1
        if term1 <= 0 or term2 <= 0: return 1e6 # Valor alto de error
        
        ln_gamma1 = -np.log(term1) + x2 * (
            (lambda_12 / term1) - (lambda_21 / term2)
        )
        return np.exp(ln_gamma1)

    def activity_nrtl(self, x1, tau_12, tau_21, alpha=0.3):
        """Calcula gamma_1 usando NRTL."""
        x2 = 1.0 - x1
        G12 = np.exp(-alpha * tau_12)
        G21 = np.exp(-alpha * tau_21)
        
        term1 = tau_21 * (G21 / (x1 + x2 * G21))**2
        term2 = (tau_12 * G12) / ((x2 + x1 * G12)**2)
        
        ln_gamma1 = (x2**2) * (term1 + term2)
        return np.exp(ln_gamma1)

    def activity_uniquac(self, x1, tau12, tau21, r1, q1, r2, q2, z=10):
        """Calcula gamma_1 usando UNIQUAC."""
        x2 = 1.0 - x1
        x1 = max(1e-10, min(x1, 1.0-1e-10))
        
        # Fracciones de volumen/área promedio
        sum_xr = x1 * r1 + x2 * r2
        sum_xq = x1 * q1 + x2 * q2
        
        phi1 = (x1 * r1) / sum_xr
        phi2 = (x2 * r2) / sum_xr
        theta1 = (x1 * q1) / sum_xq
        theta2 = (x2 * q2) / sum_xq
        
        l1 = (z/2)*(r1 - q1) - (r1 - 1)
        l2 = (z/2)*(r2 - q2) - (r2 - 1)
        
        # Combinatorial
        ln_gamma_C = np.log(phi1/x1) + (z/2)*q1*np.log(theta1/phi1) + l1 - (phi1/x1)*(x1*l1 + x2*l2)
        
        # Residual
        val1 = theta1 + theta2 * tau21
        val2 = theta2 + theta1 * tau12
        ln_gamma_R = q1 * (1.0 - np.log(val1) - (theta1/val1) - (theta2*tau12/val2))
        
        return np.exp(ln_gamma_C + ln_gamma_R)

    # =========================================================================
    # 4. SOLVER DE SOLUBILIDAD (SLE) Y PREDICCIÓN DE CURVAS
    # =========================================================================

    def solve_sle_solubility(self, T_op, Tm, Hfus, model_type, params):
        """
        Resuelve la ecuación de equilibrio Sólido-Líquido para x_sat (Punto único).
        ln(x * gamma) = - (Hfus/R) * (1/T - 1/Tm)
        
        Args:
            T_op: Temperatura operación (K)
            Tm: Temperatura fusión (K)
            Hfus: Entalpía fusión (J/mol)
            model_type: 'wilson' o 'nrtl'
            params: Dict con (p12, p21) que corresponden a (lambda12, lambda21) o (tau12, tau21)
        
        Returns:
            float: Fracción molar de solubilidad (0 a 1).
        """
        # Si T > Tm, el sólido funde, solubilidad teórica infinita (o miscible) -> 1.0
        if T_op >= Tm:
            return 1.0
            
        # Lado derecho de la ecuación (Ideal solubility term)
        RHS = (Hfus / self.R) * ((1.0 / Tm) - (1.0 / T_op))
        # Objetivo: gamma * x = exp(RHS)
        target_val = np.exp(RHS) # Esto es x_ideal

        # Función de error a minimizar: x * gamma(x) - target = 0
        def error_func(x):
            if x <= 1e-9: return -target_val # Evitar log(0)
            if x >= 1.0: return 1.0 - target_val
            
            try:
                if model_type == 'wilson':
                    gamma = self.activity_wilson(x, params['p12'], params['p21'])
                elif model_type == 'nrtl':
                    gamma = self.activity_nrtl(x, params['p12'], params['p21'], params.get('alpha', 0.3))
                elif model_type == 'uniquac' or model_type == 'UNIQUAC':
                    gamma = self.activity_uniquac(
                        x, params['p12'], params['p21'],
                        params.get('r1', 1.0), params.get('q1', 1.0),
                        params.get('r2', 1.0), params.get('q2', 1.0)
                    )
                else:
                    gamma = 1.0
                
                return x * gamma - target_val
            except:
                return 1e6

        try:
            # Buscamos raíz entre 0 y 1
            sol = optimize.brentq(error_func, 1e-9, 0.9999)
            return sol
        except Exception:
            # Fallback a minimización si brentq no encuentra cambio de signo
            res = optimize.minimize_scalar(lambda x: error_func(x)**2, bounds=(0, 1), method='bounded')
            return res.x

    def predict_solubility_curve(self, temp_range, Tm, Hfus, model_type, params_at_sat):
        """
        Genera la curva completa de solubilidad iterando sobre un rango de temperaturas.
        
        Args:
            temp_range (list/array): Lista de temperaturas (K).
            Tm, Hfus: Propiedades físicas.
            model_type: 'wilson', 'nrtl'.
            params_at_sat: Parámetros calculados en una simulación (se asumen constantes o proyectables).
                           En un futuro, aquí podrías pasar un modelo de dependencia T (A + B/T).
        
        Returns:
            list: Lista de x_sat correspondientes a temp_range.
        """
        x_pred = []
        
        for T in temp_range:
            # Aquí asumimos que p12 y p21 son constantes o provienen de una única simulación.
            # Si tienes múltiples simulaciones a diferentes T, deberías ajustar A y B
            # y calcular params = A + B/T antes de llamar a solve.
            # Para la versión actual (proyección desde un punto), pasamos los params tal cual.
            
            x = self.solve_sle_solubility(T, Tm, Hfus, model_type, params_at_sat)
            x_pred.append(x)
            
        return x_pred

    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def density_mass_to_number(self, rho_kg_m3, mw_g_mol):
        """
        Convierte densidad másica (kg/m3) a densidad numérica (molecules/nm3).
        """
        avogadro = 6.02214076e23
        # 1 kg/m3 = 1000 g / 1e27 nm3 = 1e-24 g/nm3
        rho_g_nm3 = rho_kg_m3 * 1e-24 
        rho_num = (rho_g_nm3 / mw_g_mol) * avogadro
        return rho_num