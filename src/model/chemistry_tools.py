import math
import os

class ChemistryTools:
    def calculate_box_size(self, molecules, target_density_kg_m3, margin_percent=0.0):
        """
        Calcula la arista de la caja cúbica.
        
        Args:
            molecules: [{'mw': g/mol, 'count': int}, ...]
            target_density_kg_m3: Densidad en kg/m3 (SI Standard)
            margin_percent: Porcentaje extra al tamaño de la caja (0-100)
                            Ej: 10 significa aumentar un 10% el lado.
        """
        if target_density_kg_m3 <= 0:
            return 0.0
        
        # 1. Conversión de Unidades
        # 1000 kg/m3 = 1 g/cm3
        density_g_cm3 = target_density_kg_m3 / 1000.0
        
        avogadro = 6.022e23
        total_mass_g = sum([(float(m['mw']) * int(m['count'])) / avogadro for m in molecules])
        
        # 2. Volumen teórico estricto
        vol_cm3 = total_mass_g / density_g_cm3
        vol_A3 = vol_cm3 * 1e24
        
        # 3. Arista base
        box_side_base = math.pow(vol_A3, 1/3)
        
        # 4. Aplicar Margen
        # Si lado es 30A y margen 10%, nuevo lado es 33A.
        margin_factor = 1.0 + (margin_percent / 100.0)
        box_side_final = box_side_base * margin_factor
        
        return round(box_side_final, 2)

    def generate_packmol_input(self, inp_file_path, output_pdb_name, box_size, molecules, tolerance=2.0):
        """Genera packmol.inp con rutas relativas"""
        try:
            os.makedirs(os.path.dirname(inp_file_path), exist_ok=True)

            with open(inp_file_path, 'w') as f:
                f.write(f"# Generado por ChemSimGUI\n")
                f.write(f"tolerance {tolerance}\n")
                f.write(f"filetype pdb\n")
                f.write(f"output {output_pdb_name}\n\n")
                
                for mol in molecules:
                    f.write(f"structure {mol['pdb']}\n")
                    f.write(f"  number {mol['count']}\n")
                    # Usamos box_size calculado con el margen incluido
                    f.write(f"  inside cube 0. 0. 0. {box_size}\n")
                    f.write(f"end structure\n\n")
            
            return True, f"Input generado en: {inp_file_path}"
        except Exception as e:
            return False, str(e)