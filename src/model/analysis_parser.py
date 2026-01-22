import os
import subprocess
import numpy as np
import csv

class AnalysisParser:
    def __init__(self):
        pass

    # =========================================================================
    # SECCIÓN 1: LECTURA Y PARSEO DE ARCHIVOS DE DATOS
    # =========================================================================

    def get_data_from_file(self, filepath):
        """
        Lee archivos de resultados para graficar.
        Soporta formato .xvg (GROMACS) y .csv (TRAVIS).
        
        Args:
            filepath (str): Ruta al archivo.
            
        Returns:
            tuple: (lista_etiquetas, array_x, lista_de_arrays_y)
        """
        x_data = []
        y_data = []
        labels = ["Eje X", "Eje Y"]
        
        if not os.path.exists(filepath):
            return labels, [], []

        try:
            # --- CASO A: ARCHIVO TRAVIS (.CSV) ---
            if filepath.endswith('.csv'):
                with open(filepath, 'r') as f:
                    # Travis suele usar punto y coma ';' como delimitador
                    reader = csv.reader(f, delimiter=';')
                    
                    for row in reader:
                        if not row:
                            continue
                        
                        # Intentar detectar etiquetas en la cabecera
                        if not row[0][0].isdigit() and not row[0].startswith('-'): 
                            if len(row) > 1 and ("r / pm" in row[0] or "Distance" in row[0]):
                                labels = [row[0], row[1]]
                            continue
                        
                        try:
                            # Columna 0: X (Distancia), Columna 1: Y (RDF)
                            val_x = float(row[0])
                            val_y = float(row[1])
                            x_data.append(val_x)
                            y_data.append(val_y)
                        except ValueError:
                            continue
                
                # Retornar formato estándar (Y como lista de arrays)
                return labels, np.array(x_data), [np.array(y_data)]

            # --- CASO B: ARCHIVO GROMACS (.XVG) ---
            else:
                with open(filepath, 'r') as f:
                    lines = f.readlines()

                raw_data = []
                for line in lines:
                    line = line.strip()
                    
                    # Leer metadatos de los ejes (@)
                    if line.startswith("@"):
                        if "xaxis" in line and "label" in line:
                            parts = line.split('"')
                            if len(parts) > 1:
                                labels[0] = parts[1]
                        if "yaxis" in line and "label" in line:
                            parts = line.split('"')
                            if len(parts) > 1:
                                labels[1] = parts[1]
                        continue
                    
                    # Ignorar comentarios (#)
                    if line.startswith("#"):
                        continue
                    
                    # Leer datos numéricos
                    try:
                        parts = line.split()
                        nums = [float(p) for p in parts]
                        raw_data.append(nums)
                    except ValueError:
                        pass

                if not raw_data:
                    return labels, [], []
                
                # Convertir a matriz numpy
                data_np = np.array(raw_data)
                
                # La primera columna es X
                x_col = data_np[:, 0]
                
                # El resto de columnas son Y
                y_cols = []
                for i in range(1, data_np.shape[1]):
                    y_cols.append(data_np[:, i])
                
                return labels, x_col, y_cols

        except Exception as e:
            print(f"Error parseando archivo {filepath}: {e}")
            return labels, [], []

    # =========================================================================
    # SECCIÓN 2: HERRAMIENTAS GROMACS (ENERGÍA Y PBC)
    # =========================================================================

    def run_gmx_energy(self, edr_file, output_xvg, terms):
        """Ejecuta 'gmx energy' para extraer propiedades."""
        if not os.path.exists(edr_file):
            return False, "No existe el archivo .edr"

        input_str = "\n".join(terms) + "\n0\n"
        
        cmd = ["gmx", "energy", "-f", edr_file, "-o", output_xvg]
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            stdout, stderr = process.communicate(input=input_str)
            
            if process.returncode == 0:
                return True, "Análisis de energía completado."
            else:
                return False, f"Error GROMACS Energy:\n{stderr}"
        except Exception as Ex:
            return False, str(Ex)

    def run_trjconv(self, tpr_file, xtc_file, output_xtc, center_group_id, output_group_id):
        """
        Corrige PBC centrando un grupo.
        Recibe IDs numéricos de grupos (ej: 1, 0).
        """
        # Input interactivo: Grupo para centrar + Grupo de salida
        input_str = f"{center_group_id}\n{output_group_id}\n"
        
        cmd = [
            "gmx", "trjconv", 
            "-s", tpr_file, 
            "-f", xtc_file, 
            "-o", output_xtc, 
            "-pbc", "mol", 
            "-center"
        ]
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            stdout, stderr = process.communicate(input=input_str)
            
            if process.returncode == 0:
                return True, "Trayectoria corregida."
            else:
                return False, f"Error TRJCONV:\n{stderr}"
        except Exception as Ex:
            return False, str(Ex)

    # =========================================================================
    # SECCIÓN 3: GESTIÓN DE GRUPOS Y ESTRUCTURA (MAKE_NDX)
    # =========================================================================
    
    def scan_structure_atoms(self, gro_file):
        """Lee el archivo .gro para saber qué átomos existen."""
        if not os.path.exists(gro_file):
            return {}
        
        structure_map = {}
        
        try:
            with open(gro_file, 'r') as f:
                lines = f.readlines()
            
            for line in lines[2:-1]:
                if len(line) < 15:
                    continue
                    
                res_name = line[5:10].strip()
                atom_name = line[10:15].strip()
                
                if not res_name or not atom_name:
                    continue
                
                if res_name not in structure_map:
                    structure_map[res_name] = set()
                
                structure_map[res_name].add(atom_name)
                
            return structure_map
        except Exception as e:
            print(f"Error escaneando GRO: {e}")
            return {}

    def add_custom_group(self, tpr_file, working_dir, selection_str):
        """Usa make_ndx para crear un grupo personalizado."""
        ndx_file = os.path.join(working_dir, "index.ndx")
        
        cmd = ["gmx", "make_ndx", "-f", tpr_file, "-o", ndx_file]
        
        if os.path.exists(ndx_file):
            cmd.extend(["-n", ndx_file])
        
        input_str = f"{selection_str}\nq\n"
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            stdout, stderr = process.communicate(input=input_str)
            
            if process.returncode == 0:
                return True, "Grupo agregado exitosamente."
            else:
                return False, f"Error make_ndx:\n{stderr}"
        except Exception as e:
            return False, str(e)

    def get_gromacs_groups(self, tpr_file, working_dir):
        """
        Obtiene el diccionario de grupos {Nombre: ID} del archivo index.ndx.
        Si no existe, ejecuta gmx make_ndx una vez para generarlo por defecto.
        """
        ndx_file = os.path.join(working_dir, "index.ndx")
        
        # Si no existe, creamos el default
        if not os.path.exists(ndx_file):
            self.add_custom_group(tpr_file, working_dir, "q")
            
        groups = {}
        if not os.path.exists(ndx_file):
            return groups
        
        current_id = 0
        try:
            with open(ndx_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        group_name = line.strip()[1:-1].strip()
                        groups[group_name] = current_id
                        current_id += 1
            return groups
        except Exception:
            return {}

    # =========================================================================
    # SECCIÓN 4: EJECUCIÓN DE RDF (GROMACS Y TRAVIS)
    # =========================================================================

    def run_gmx_rdf(self, tpr_file, xtc_file, output_xvg, ref_id, sel_id, working_dir, use_com, bin_width, cutoff):
        """
        Ejecuta gmx rdf.
        
        Args:
            use_com (bool): Si True, usa centros de masa.
            bin_width (float): Ancho del bin en nm.
            cutoff (float): Distancia máxima en nm (-rmax).
        """
        ndx_file = os.path.join(working_dir, "index.ndx")
        
        cmd = [
            "gmx", "rdf", 
            "-s", tpr_file, 
            "-f", xtc_file, 
            "-o", output_xvg, 
            "-n", ndx_file
        ]
        
        if use_com:
            cmd.extend(["-selrpos", "mol_com", "-seltype", "mol_com"])
        
        if bin_width > 0:
            cmd.extend(["-bin", str(bin_width)])
            
        # --- NUEVO: Soporte para Cut-off (-rmax) ---
        if cutoff > 0:
            cmd.extend(["-rmax", str(cutoff)])
        
        # Input: ID Referencia + ID Selección
        input_str = f"{ref_id}\n{sel_id}\n"
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            stdout, stderr = process.communicate(input=input_str)
            
            if process.returncode == 0:
                return True, "RDF GROMACS calculado."
            else:
                return False, f"Error GROMACS RDF:\n{stderr}"
        except Exception as e:
            return False, str(e)

    def run_travis_rdf(self, struct_file, traj_file, output_csv, mol1_name, mol2_name):
        """Ejecuta TRAVIS para RDF."""
        input_filename = "travis_input.txt"
        
        try:
            with open(input_filename, 'w') as f:
                f.write(f"rdf molecule {mol1_name} molecule {mol2_name}\n")
        except Exception as e:
            return False, f"Error creando input Travis: {e}"
            
        cmd = ["travis", "-p", struct_file, "-i", traj_file]
        
        try:
            with open(input_filename, 'r') as f_in:
                process = subprocess.Popen(
                    cmd, 
                    stdin=f_in, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True
                )
                stdout, stderr = process.communicate()
            
            if os.path.exists(input_filename):
                os.remove(input_filename)
            
            expected_name = f"rdf_molecule_{mol1_name}_molecule_{mol2_name}.csv"
            
            if not os.path.exists(expected_name):
                 files = os.listdir('.')
                 for f in files:
                     if f.startswith('rdf_molecule') and f.endswith('.csv'):
                         expected_name = f
                         break

            if os.path.exists(expected_name):
                if os.path.exists(output_csv):
                    os.remove(output_csv)
                os.rename(expected_name, output_csv)
                return True, "RDF TRAVIS calculado."
            else:
                return False, f"No se encontró salida de Travis.\nLog:\n{stdout}\n{stderr}"
                
        except Exception as e:
            return False, str(e)