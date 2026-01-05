import math
import os

class ChemistryTools:
    def calculate_box_size(self, molecules, target_density):
        """
        Calcula la arista de una caja cúbica necesaria para una densidad dada.
        molecules: Lista de diccionarios [{'mw': 18.015, 'count': 1000}, ...]
        target_density: g/cm3
        Retorna: Lado de la caja (Angstroms)
        """
        if target_density <= 0:
            return 0.0
        
        avogadro = 6.022e23
        total_mass_g = 0.0
        
        # Sumar masa total de todos los componentes
        for mol in molecules:
            # Masa (g) = (MW * Numero de moleculas) / Avogadro
            mass = (float(mol['mw']) * int(mol['count'])) / avogadro
            total_mass_g += mass
            
        # Volumen = Masa / Densidad
        vol_cm3 = total_mass_g / float(target_density)
        
        # Convertir cm3 a Angstroms cubicos (1 cm = 10^8 A -> 1 cm3 = 10^24 A3)
        vol_A3 = vol_cm3 * 1e24
        
        # Arista del cubo
        box_side = math.pow(vol_A3, 1/3)
        
        # Retornamos con un pequeño buffer para evitar errores de redondeo
        return round(box_side, 2)

    def generate_packmol_input(self, output_path, box_size, molecules, tolerance=2.0):
        """
        Genera el archivo input.inp para Packmol.
        molecules debe tener: {'pdb': 'ruta.pdb', 'count': 100, ...}
        """
        try:
            with open(output_path, 'w') as f:
                f.write(f"# Generado por ChemSimGUI\n")
                f.write(f"tolerance {tolerance}\n")
                f.write(f"filetype pdb\n")
                f.write(f"output system_init.pdb\n\n")
                
                for mol in molecules:
                    f.write(f"structure {mol['pdb']}\n")
                    f.write(f"  number {mol['count']}\n")
                    f.write(f"  inside cube 0. 0. 0. {box_size}\n")
                    f.write(f"end structure\n\n")
            return True, f"Input generado en {output_path}"
        except Exception as e:
            return False, str(e)