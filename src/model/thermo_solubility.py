import numpy as np
from scipy import integrate, optimize

class ThermoMath:
    """
    Motor matemático para cálculos de Equilibrio Sólido-Líquido (SLE)
    basados en Dinámica Molecular.
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
                                      Nota: No usar densidad másica.
        
        Returns:
            np.array: Array del mismo tamaño que r_nm con el CN acumulado.
        """
        # Integrando: 4 * pi * r^2 * g(r)
        # Nota: r_nm debe estar en las mismas unidades que 1/rho^(1/3)
        integrand = 4 * np.pi * (r_nm ** 2) * g_r
        
        # Integración numérica acumulativa (Regla del trapecio)
        # Esto nos permite ver cómo cambia el CN a medida que aumenta el radio
        cumulative_integral = integrate.cumulative_trapezoid(integrand, r_nm, initial=0)
        
        cn_profile = number_density_j * cumulative_integral
        return cn_profile

    def calculate_local_composition_ratio(self, n_ij, n_jj):
        """
        Calcula el ratio de composición local (Omega_ij).
        Basado en la relación de números de coordinación.
        Ref: Yousefi Seyf & Haghtalab (2017), Eq 3-5.
        
        Omega_ij = n_ij / n_jj
        
        (Nota: Esta es una simplificación común donde se asume que las especies
         están distribuidas según la Boltzmann factor relativa).
        """
        # Evitar división por cero
        with np.errstate(divide='ignore', invalid='ignore'):
            omega = n_ij / n_jj
            omega[n_jj == 0] = 0
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
        # Evitar log de cero o negativos
        omega_12 = np.maximum(omega_12, 1e-10)
        omega_21 = np.maximum(omega_21, 1e-10)
        
        tau_12 = -np.log(omega_12) / alpha
        tau_21 = -np.log(omega_21) / alpha
        return tau_12, tau_21

    def get_uniquac_params(self, omega_12, omega_21, q1, q2):
        """
        Convierte Omega a Tau (UNIQUAC).
        tau_12 ~ (q2/q1) * Omega_12 (Aproximación basada en paper)
        """
        # Nota: La implementación exacta depende de la formulación específica del paper
        # Usamos la relación proporcional sugerida.
        tau_12 = (q2 / q1) * omega_12
        tau_21 = (q1 / q2) * omega_21
        # UNIQUAC requiere logaritmo en la energía, pero a veces se reporta
        # el parámetro de interacción exponencial. Asumiremos retorno directo
        # para visualización, pero el modelo de actividad usa exp(-tau).
        # Si el paper dice que tau_UNIQUAC son parámetros de energía:
        # tau_energy = -RT * ln(tau_param)
        return tau_12, tau_21

    # =========================================================================
    # 3. MODELOS DE ACTIVIDAD (Cálculo de Gamma)
    # =========================================================================

    def activity_wilson(self, x1, lambda_12, lambda_21):
        """
        Calcula gamma_1 usando Wilson.
        x1: Fracción molar soluto.
        """
        x2 = 1.0 - x1
        ln_gamma1 = -np.log(x1 + lambda_12 * x2) + x2 * (
            (lambda_12 / (x1 + lambda_12 * x2)) - (lambda_21 / (x2 + lambda_21 * x1))
        )
        return np.exp(ln_gamma1)

    def activity_nrtl(self, x1, tau_12, tau_21, alpha=0.3):
        """
        Calcula gamma_1 usando NRTL.
        """
        x2 = 1.0 - x1
        G12 = np.exp(-alpha * tau_12)
        G21 = np.exp(-alpha * tau_21)
        
        term1 = tau_21 * (G21 / (x1 + x2 * G21))**2
        term2 = (tau_12 * G12) / ((x2 + x1 * G12)**2)
        
        ln_gamma1 = (x2**2) * (term1 + term2)
        return np.exp(ln_gamma1)

    # =========================================================================
    # 4. SOLVER DE SOLUBILIDAD (SLE)
    # =========================================================================

    def solve_sle_solubility(self, T_op, Tm, Hfus, model_type, params):
        """
        Resuelve la ecuación de equilibrio Sólido-Líquido para x_sat.
        ln(x * gamma) = - (Hfus/R) * (1/T - 1/Tm)
        
        Args:
            T_op: Temperatura operación (K)
            Tm: Temperatura fusión (K)
            Hfus: Entalpía fusión (J/mol)
            model_type: 'wilson' o 'nrtl'
            params: Dict con (lambda12, lambda21) o (tau12, tau21, alpha)
        
        Returns:
            float: Fracción molar de solubilidad (0 a 1).
        """
        # Lado derecho de la ecuación (Constante para una T dada)
        # Términos de capacidad calorífica (Cp) ignorados por simplicidad (asunción común)
        RHS = (Hfus / self.R) * ((1.0 / Tm) - (1.0 / T_op))
        # La ecuación es: ln(x) + ln(gamma(x)) = -RHS (si definimos RHS positivo como término de fusión)
        # O mejor: ln(x) + ln(gamma) = (Hfus/R)*(1/Tm - 1/T)
        # Nota: (1/Tm - 1/T) suele ser negativo si T < Tm.
        
        target_val = np.exp((Hfus / self.R) * ((1.0 / Tm) - (1.0 / T_op)))

        # Función de error a minimizar: x * gamma(x) - target = 0
        def error_func(x):
            if x <= 0 or x >= 1: return 1e6
            
            if model_type == 'wilson':
                gamma = self.activity_wilson(x, params['p12'], params['p21'])
            elif model_type == 'nrtl':
                gamma = self.activity_nrtl(x, params['p12'], params['p21'], params.get('alpha', 0.3))
            else:
                gamma = 1.0 # Ideal
                
            return x * gamma - target_val

        try:
            # Buscamos raíz entre 0.0001 y 0.9999
            # Brentq es robusto y rápido para búsqueda de raíces en intervalos
            sol = optimize.brentq(error_func, 1e-9, 0.9999)
            return sol
        except Exception:
            # Si falla (ej. solubilidad muy baja o muy alta), intentamos minimizar el cuadrado
            res = optimize.minimize_scalar(lambda x: error_func(x)**2, bounds=(0, 1), method='bounded')
            return res.x
            
    # =========================================================================
    # HELPERS DE UNIDADES
    # =========================================================================
    
    def density_mass_to_number(self, rho_kg_m3, mw_g_mol):
        """
        Convierte densidad másica (kg/m3) a densidad numérica (molecules/nm3).
        
        rho_num = (rho_mass * Avogadro) / MW
        Unidades: 
          rho_mass: kg/m^3 = g/L = 1e-21 g/nm^3
          MW: g/mol
          Avogadro: 6.022e23 mol^-1
        """
        avogadro = 6.02214076e23
        
        # 1 kg/m3 = 1000 g / 1e27 nm3 = 1e-24 g/nm3
        rho_g_nm3 = rho_kg_m3 * 1e-24 
        
        rho_num = (rho_g_nm3 / mw_g_mol) * avogadro
        return rho_num