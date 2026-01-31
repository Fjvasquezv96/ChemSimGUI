import math
import numpy as np

class StructureAnalyzer:
    """
    Clase especializada en analizar estructuras geométricas (.gro, .pdb)
    para deducir propiedades fisicoquímicas, como los parámetros de UNIQUAC (r y q)
    basándose en contribución de grupos (UNIFAC).
    """
    def __init__(self):
        # Radios covalentes para heurística de conectividad (Angstroms)
        self.COVALENT_RADII = {
            'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66, 
            'P': 1.07, 'S': 1.05, 'F': 0.57, 'CL': 1.02, 
            'BR': 1.20, 'I': 1.39
        }
        
        # Base de datos simplificada de grupos UNIFAC para UNIQUAC (R y Q)
        # Valores típicos de bibliografía (Abrams & Prausnitz / Hansen)
        self.UNIFAC_GROUPS = {
            # Alkanes
            'CH3':  {'R': 0.9011, 'Q': 0.848},
            'CH2':  {'R': 0.6744, 'Q': 0.540},
            'CH':   {'R': 0.4469, 'Q': 0.228},
            'C':    {'R': 0.2195, 'Q': 0.000}, 
            # Aromatics 
            'ACH':  {'R': 0.5313, 'Q': 0.400}, # Aromatic CH
            'AC':   {'R': 0.3652, 'Q': 0.120}, # Aromatic C substituted
            # Alcohols
            'OH':   {'R': 1.0000, 'Q': 1.200}, # Hydroxyl group
            # Water
            'H2O':  {'R': 0.9200, 'Q': 1.400},
            # Ketones / Aldehydes
            'CH2=O':{'R': 1.6724, 'Q': 1.488}, # Carbonyl group approx (como grupo entero)
            'C=O':  {'R': 0.7713, 'Q': 0.640}, # Solo el grupo carbonilo funcional
            # Ethers
            'CH2-O':{'R': 0.9183, 'Q': 0.780}, # Eter group
            '-O-':  {'R': 0.2459, 'Q': 0.245}, # Oxygen ether link
            # Acids
            'COOH': {'R': 1.3013, 'Q': 1.224},
             # Amides/Amines
            'NH2':  {'R': 0.6323, 'Q': 0.505}, # Primary Amine
            'NH':   {'R': 0.4570, 'Q': 0.298}, # Secondary Amine
            'N':    {'R': 0.2840, 'Q': 0.092}, # Tertiary Amine
             # Halogens
            'CL':   {'R': 0.7121, 'Q': 0.702}, 
            'F':    {'R': 0.3530, 'Q': 0.372}, # Approx
             # Default fallback
            'UNKNOWN': {'R': 0.5, 'Q': 0.5}
        }

    def get_element_from_name(self, atom_name):
        """Deduce elemento desde nombre PDB/GRO (ej CA -> C, HG1 -> H)"""
        clean = ''.join([i for i in atom_name if not i.isdigit()]).strip().upper()
        if not clean: return 'C'
        
        # Prioridad a elementos de 2 letras conocidos
        if len(clean) >= 2 and clean[:2] in self.COVALENT_RADII: return clean[:2]
        return clean[0]

    def parse_gro_atoms(self, gro_file, target_res_name=None):
        """
        Extrae átomos y coordenadas del primer residuo encontrado en un .gro
        Si target_res_name es None, toma el primer residuo que aparezca.
        """
        atoms = []
        found = False
        target_id = None
        
        if not gro_file or not str(gro_file).endswith('.gro'): return []

        try:
            with open(gro_file, 'r') as f: lines = f.readlines()
        except: return []

        # GRO Format: Header(2), Lines, Box(1)
        if len(lines) < 3: return []

        for line in lines[2:-1]:
            try:
                # Estricto formato GRO fixed width
                if len(line) < 40: continue
                res_num = line[0:5].strip()
                res_name = line[5:10].strip()
                atom_name = line[10:15].strip()
                # Coordenadas en nm -> pasar a Angstroms (x10) para unifac radii check
                x = float(line[20:28]) * 10.0 
                y = float(line[28:36]) * 10.0
                z = float(line[36:44]) * 10.0
                
                # Si no se especificó nombre, tomamos el primero que venga
                if target_res_name is None: target_res_name = res_name
                
                if res_name == target_res_name:
                    if target_id is None: target_id = res_num
                    
                    if res_num == target_id:
                        atoms.append({
                            'id': len(atoms), # Indice local 0...N
                            'name': atom_name,
                            'x': x, 'y': y, 'z': z,
                            'elem': self.get_element_from_name(atom_name),
                            'bonds': [] 
                        })
                        found = True
                    else:
                        break # Fin de la molécula
                elif found:
                    break # Ya procesamos la molécula y cambiamos de residuo
            except ValueError:
                continue
            
        return atoms

    def build_connectivity(self, atoms):
        """
        Genera lista de adyacencia (grafo) basada en distancias interatómicas.
        Complejidad O(N^2), aceptable para moléculas < 200 átomos.
        """
        n = len(atoms)
        for i in range(n):
            for j in range(i + 1, n):
                a1 = atoms[i]
                a2 = atoms[j]
                
                dist = math.sqrt((a1['x']-a2['x'])**2 + (a1['y']-a2['y'])**2 + (a1['z']-a2['z'])**2)
                
                r1 = self.COVALENT_RADII.get(a1['elem'], 1.5)
                r2 = self.COVALENT_RADII.get(a2['elem'], 1.5)
                
                # Criterio: Distancia < SumaRadios + 25% tolerancia
                threshold = (r1 + r2) * 1.25 
                
                # Filtro inferior 0.4A para evitar superposiciones erróneas
                if 0.4 < dist < threshold:
                    atoms[i]['bonds'].append(j)
                    atoms[j]['bonds'].append(i)
        return atoms

    def calculate_uniquac_params(self, gro_file, res_name=None):
        """
        Calcula R y Q escaneando los grupos funcionales de la estructura.
        Retorna (r, q, log_string)
        """
        atoms = self.parse_gro_atoms(gro_file, res_name)
        if not atoms: return 0, 0, "No se pudieron leer átomos del archivo GRO."
        
        atoms = self.build_connectivity(atoms)
        
        total_r = 0.0
        total_q = 0.0
        groups_detected = {} # 'CH3': 2, 'OH': 1...
        
        # --- Detección de Grupos (Heurística) ---
        # Iteramos solo átomos pesados ("Main Group Atoms")
        
        # Caso especial: Agua
        if len(atoms) == 3 and any(a['elem']=='O' for a in atoms):
             # Chequear si es H-O-H
             oxy = next((a for a in atoms if a['elem']=='O'), None)
             if oxy and len(oxy['bonds']) == 2:
                 groups_detected['H2O'] = 1
                 total_r = self.UNIFAC_GROUPS['H2O']['R']
                 total_q = self.UNIFAC_GROUPS['H2O']['Q']
                 return total_r, total_q, "H2O detectada"

        processed_indices = set()
        
        for i, atom in enumerate(atoms):
            if atom['elem'] == 'H': continue # Los H se cuentan como parte del grupo del pesado
            if i in processed_indices: continue
            
            elem = atom['elem']
            neighbors = [atoms[idx] for idx in atom['bonds']]
            
            n_H = sum(1 for nb in neighbors if nb['elem'] == 'H')
            n_C = sum(1 for nb in neighbors if nb['elem'] == 'C')
            n_O = sum(1 for nb in neighbors if nb['elem'] == 'O')
            
            group_key = 'UNKNOWN'
            
            # -- Lógica Carbonos --
            if elem == 'C':
                # TODO: Detectar aromaticidad viendo si forma parte de anillos (complejo sin bond-order)
                # Aproximación: Si tiene 3 vecinos C que forman triángulo/ciclo -> Aromático
                
                if n_H == 3: group_key = 'CH3'
                elif n_H == 2: group_key = 'CH2'
                elif n_H == 1: group_key = 'CH'
                else: group_key = 'C'
            
            # -- Lógica Oxígenos --
            elif elem == 'O':
                if n_H >= 1: group_key = 'OH'
                else:
                    # Eter (-O-) o Carbonilo (C=O)
                    # Si solo tiene 1 vecino y es C -> Carbonilo terminal C=O?
                    if len(neighbors) == 1 and neighbors[0]['elem'] == 'C':
                         group_key = 'C=O' # Approx ketone/aldehyde carbonyl
                    else:
                         group_key = '-O-' # Eter link
            
            # -- Lógica Nitrógenos --
            elif elem == 'N':
                if n_H >= 2: group_key = 'NH2'
                elif n_H == 1: group_key = 'NH'
                else: group_key = 'N'

            # -- Lógica Halógenos --
            elif elem == 'CL': group_key = 'CL'
            elif elem == 'F': group_key = 'F'
            
            # Sumar al total
            vals = self.UNIFAC_GROUPS.get(group_key, self.UNIFAC_GROUPS['UNKNOWN'])
            total_r += vals['R']
            total_q += vals['Q']
            
            groups_detected[group_key] = groups_detected.get(group_key, 0) + 1
        
        # Generar reporte string
        details = ", ".join([f"{k}x{v}" for k, v in groups_detected.items()])
        return round(total_r, 4), round(total_q, 4), details
