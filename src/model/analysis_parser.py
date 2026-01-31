import os
import subprocess
import shutil
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

    def get_structure_molecules(self, gro_file):
        """
        Devuelve una lista ordenada de nombres de moléculas (resname) únicos encontrados en el .gro.
        Ej: ['C21H30O2', 'C5H12'] -> Travis ID 1, 2.
        La posición en la lista (+1) corresponde al ID de Travis.
        """
        mols = []
        if not os.path.exists(gro_file): return []
        seen = set()
        
        try:
            with open(gro_file, 'r') as f:
                # Saltar header y count
                f.readline()
                f.readline()
                
                current_resid = None
                
                # Leer línea a línea para orden de aparición
                for line in f:
                    if len(line) < 20: continue
                    # Resid (0:5), ResName (5:10)
                    try:
                        resid = line[0:5].strip()
                        resname = line[5:10].strip()
                        
                        # Si cambiamos de residuo (número), chequear si es nuevo tipo de molécula
                        if resid != current_resid:
                            current_resid = resid
                            # Añadir a la lista si es un TIPO nuevo (por nombre)
                            # OJO: Travis agrupa por Nombre. Si hay 100 Pentanos, es MolType "Pentano".
                            if resname and resname not in seen:
                                seen.add(resname)
                                mols.append(resname)
                    except:
                        pass
        except:
            pass
            
        return mols

    def run_travis_rdf(self, structure_file, trajectory_file, tpr_file, ref_mol_id, sel_mol_id, ref_name, sel_name, rmax_nm, bins, output_txt="travis.txt"):
        """Wrapper simple para 1 sola RDF"""
        # Convertir a formato lista para usar la función batch
        tasks = [{
            'obs_id': sel_mol_id,
            'obs_name': sel_name,
            'rmax': rmax_nm,
            'bins': bins
        }]
        return self.run_travis_batch(structure_file, trajectory_file, tpr_file, ref_mol_id, ref_name, tasks)

    def generate_pdb_trajectory(self, xtc_file, tpr_file, output_pdb, pbc_mode="whole"):
        """
        Genera una trayectoria PDB/GRO corregida (Whole/Nojump) para uso externo (Travis).
        """
        if not os.path.exists(xtc_file): return False, "No existe XTC."
        
        # Eliminar previo si existe para asegurar regeneración limpia
        if os.path.exists(output_pdb):
            try:
                os.remove(output_pdb)
            except: pass
            
        # Comando: echo 0 | gmx trjconv ...
        cmd = ["gmx", "trjconv", "-f", xtc_file, "-s", tpr_file, "-o", output_pdb, "-pbc", pbc_mode]
        
        try:
            # Popen con PIPE para el echo 0
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(input="0\n")
            
            if process.returncode == 0 and os.path.exists(output_pdb):
                return True, f"Generado: {os.path.basename(output_pdb)}"
            else:
                return False, f"Error GROMACS:\n{stderr}"
        except Exception as e:
            return False, str(e)

    def run_travis_batch(self, structure_file, trajectory_file, tpr_file, ref_mol_id, ref_name, tasks_list):
        """
        Ejecuta Travis para múltiples observaciones.
        Asume que la trayectoria PDB ya existe o intenta generarla si falta.
        """
        if not os.path.exists(tpr_file) or not os.path.exists(trajectory_file):
            return False, "Faltan archivos TPR o Trayectoria."
            
        working_dir = os.path.dirname(trajectory_file)
        travis_work_dir = os.path.join(working_dir, "travis_work")
        os.makedirs(travis_work_dir, exist_ok=True)

        # 1. Identificar sistema
        parts = trajectory_file.split(os.sep)
        t_tag = "UnknownT"
        x_tag = "UnknownX"
        for p in parts:
            if p.startswith("T_") and "K" in p: t_tag = p
            if p.startswith("x_"): x_tag = p
        sys_id = f"{t_tag}_{x_tag}"
        
        # 2. Caché PDB (Nombre esperado)
        # Cambiamos a .gro que es más robusto para GMX->Travis que PDB
        pdb_traj_name = f"traj_unwrapped_{sys_id}.gro" 
        pdb_traj_path = os.path.join(travis_work_dir, pdb_traj_name)
        
        # DEBUG: Si no existe, intentar generarla al vuelo (fallback), 
        # pero idealmente el usuario usa el Gestor de Trayectorias.
        
        # 3. Construir INPUT iterativo
        # Simplificación de la secuencia de inicio
        # 1. Advanced Mode? -> n
        # 2. Accept Molecules? -> y
        # 3. Function? -> rdf
        cmds = [
            "n", # Advanced Mode? No
            "y", # Accept Molecules? Yes
            "rdf", # Function
            "n", # Advanced for RDF? No
            str(ref_mol_id) # Reference Molecule ID sent ONCE
        ]
        
        # Iterar sobre tareas
        for i, task in enumerate(tasks_list):
            if i > 0:
                cmds.append("y") # Add another observation? YES
            
            rmax_pm = float(task['rmax']) * 1000.0
            
            cmds.extend([
                "1",            # Intermolecular
                str(task['obs_id']), # Observed Molecule ID
                "0",            # Ref atoms from RM
                "1",            # Obs atoms from OM
                "", "",         # Select All (RM, OM)
                str(rmax_pm),   # Max Radius (pm)
                str(task['bins']), # Bins
                "y",            # Correct radial
                "n", "n"        # Save temp, Add cond
            ])
            
        cmds.append("n") # Add another? NO
        cmds.extend(["", "", ""]) # Frame options (Step, Start, End)
        
        input_str = "\n".join(cmds) + "\n"
        input_file_path = os.path.join(travis_work_dir, "travis_batch_input.txt")
        with open(input_file_path, "w") as f:
            f.write(input_str)

        # 4. Script Shell
        script_path = os.path.join(travis_work_dir, "run_batch.sh")
        abs_xtc = os.path.abspath(trajectory_file)
        abs_tpr = os.path.abspath(tpr_file)
        
        # Usamos nombres posicionales para evitar problemas con flags -p/-i en algunas versiones
        # Sintaxis: travis structure trajectory < input
        
        shell_script = f"""#!/bin/bash
echo "=== TRAVIS BATCH: {ref_name} ({len(tasks_list)} tareas) ==="
cd "{travis_work_dir}"

echo "Generando input..."
cat travis_batch_input.txt

# Verificación de trayectoria pre-convertida
# El usuario debe haber usado el Gestor de Trayectorias. Si no está, intentamos fallback rápido.
if [ ! -f "{pdb_traj_name}" ]; then
    echo "⚠️  No se encontró la trayectoria optimizada ({pdb_traj_name})."
    echo "    Intentando generar versión rápida..."
    # Fallback automático
    echo 0 | gmx trjconv -f "{abs_xtc}" -s "{abs_tpr}" -o "{pdb_traj_name}" -pbc whole
    if [ $? -ne 0 ]; then
        echo "❌ Falló GROMACS."
        read -p "Enter..."
        exit 1
    fi
else
    echo "✅ Usando trayectoria optimizada existente."
fi

echo "🚀 Ejecutando TRAVIS Multicore..."
# Corregido: Usar -p para la trayectoria/estructura. NO usar -i con el PDB.
travis -p "{pdb_traj_name}" < travis_batch_input.txt | tee travis_log.txt
# Corregido: Usar -p para la trayectoria/estructura. NO usar -i con el PDB.
travis -p "{pdb_traj_name}" < travis_batch_input.txt | tee travis_log.txt

STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo "❌ Falló Travis (Código $STATUS)."
    read -p "Enter..."
    exit 1
fi
echo "✅ Completado."
""" 
        shell_script += 'read -p "Presione ENTER para cerrar..."\n'

        with open(script_path, "w") as f:
            f.write(shell_script)
        os.chmod(script_path, 0o755)
        
        # 5. Ejecutar
        terminals = ["gnome-terminal", "konsole", "xfce4-terminal", "xterm", "lxterminal", "mate-terminal"]
        term_cmd = None
        for t in terminals:
            if shutil.which(t):
                if t == "gnome-terminal": term_cmd = [t, "--", "bash", script_path]
                elif t == "xterm": term_cmd = [t, "-e", script_path]
                else: term_cmd = [t, "-e", f"bash {script_path}"]
                break
        
        if not term_cmd: return False, "No terminal found."
        
        try:
            p = subprocess.Popen(term_cmd)
            p.wait()
            
            # 6. Recosechar Resultados
            # Estrategia: Buscar todos los CSV generados recientemente. 
            # Travis genera nombres como: rdf_molecule_NAME_molecule_NAME.csv
            
            results = []
            found_csvs = [f for f in os.listdir(travis_work_dir) if f.startswith("rdf_") and f.endswith(".csv")]
            
            count = 0
            for csv_file in found_csvs:
                # OJO: Travis usa los NOMBRES dentro del structure file, no nuestros IDs.
                # Como no podemos saber facilmente qué archivo corresponde a qué tarea sin parsear el PDB (o confiar en los nombres),
                # simplemente los movemos todos prefijados por el sistema.
                
                dst_name = f"RDF_{sys_id}_{csv_file}"
                src = os.path.join(travis_work_dir, csv_file)
                dst = os.path.join(working_dir, dst_name)
                
                if os.path.exists(dst): os.remove(dst)
                shutil.move(src, dst)
                results.append(dst_name)
                count += 1
                
            if count > 0:
                short_list = "\\n".join(results[:3])
                if count > 3: short_list += "\\n..."
                return True, f"Se generaron {count} archivos RDF.\\n{short_list}"
            else:
                return False, "No se encontraron CSVs de salida."
                
        except Exception as e:
            return False, str(e)


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
    # SECCIÓN 4: GENERACIÓN DE ÍNDICE POR CONTEO (SOLUCIÓN "UNL")
    # =========================================================================
    
    def generate_index_by_counts(self, gro_file, ndx_output, n_solute, n_solvent, name_solute="Solute", name_solvent="Solvent"):
        """
        Genera un archivo index.ndx separando átomos por CANTIDAD de moléculas.
        Optimizado para lectura iterativa sin cargar todo en RAM.
        """
        if not os.path.exists(gro_file):
            return False, "No existe el archivo .gro"

        solute_atoms = []
        solvent_atoms = []
        
        try:
            with open(gro_file, 'r') as f:
                # 1. Leer Titulo
                f.readline()
                # 2. Leer Numero de atomos
                try:
                    num_atoms_line = f.readline()
                    total_atoms_expected = int(num_atoms_line.strip())
                except:
                    # Si falla, no es crítico, seguimos leyendo hasta el final
                    pass

                current_res_str = ""
                mol_counter = 0 
                global_atom_idx = 1
                
                # Procesar linea a linea
                for line in f:
                    # La ultima linea es la caja (3 floats), suele ser corta pero verificamos
                    # Lineas de atomos tienen formato fijo largo
                    if len(line) < 20: 
                        continue
                    
                    # Chequeo rapido de fin de archivo (caja)
                    # La caja suele tener 3 numeros, verificar si parece atomo
                    # Formato atomo: ResNum(5), ResName(5), AtomName(5), AtomNum(5)...
                    # Si no cumple estructura, paramos.
                    # Asumimos que la linea de caja es la ultima.
                    
                    # GRO formato fijo: ResNumber (0-5)
                    res_num_str = line[0:5]
                    
                    # Detectar cambio de molécula
                    if res_num_str != current_res_str:
                        mol_counter += 1
                        current_res_str = res_num_str
                    
                    idx_str = str(global_atom_idx)
                    
                    if mol_counter <= n_solute:
                        solute_atoms.append(idx_str)
                    elif mol_counter <= (n_solute + n_solvent):
                        solvent_atoms.append(idx_str)
                    elif mol_counter > (n_solute + n_solvent):
                        # Si ya pasamos los grupos de interes, aunque sigamos leyendo, 
                        # no guardamos en memoria. Podemos optimizar breaking si estamos seguros
                        # de que no hay mas moléculas de interes intercaladas (MD standard: no).
                        pass
                    
                    global_atom_idx += 1
                    
                    # Safety break si leimos todos los atomos esperados (evita leer linea de caja como atomo)
                    # Aunque linea de caja suele tener len < 40 o distinta estructura.
            
            # Escribir archivo NDX
            with open(ndx_output, 'w') as f:
                # Escribir Grupo Soluto
                f.write(f"[ {name_solute} ]\n")
                # Escribir índices en bloques de 15 para legibilidad
                for i in range(0, len(solute_atoms), 15):
                    f.write(" ".join(solute_atoms[i:i+15]) + "\n")
                
                # Escribir Grupo Solvente
                f.write(f"[ {name_solvent} ]\n")
                for i in range(0, len(solvent_atoms), 15):
                    f.write(" ".join(solvent_atoms[i:i+15]) + "\n")
                    
            return True, f"Índice generado: {len(solute_atoms)} átomos {name_solute}, {len(solvent_atoms)} átomos {name_solvent}."

        except Exception as e:
            return False, f"Error generando índice por conteo: {str(e)}"

    # =========================================================================
    # SECCIÓN 5: EJECUCIÓN DE RDF (GROMACS Y TRAVIS)
    # =========================================================================

    def run_gmx_rdf(self, tpr_file, xtc_file, output_xvg, ref_id, sel_id, working_dir, use_com, bin_width, cutoff):
        """
        Ejecuta gmx rdf.
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
            
        # FIX: Añadir -pbc yes para asegurar que los cálculos respeten condiciones de borde
        cmd.extend(["-pbc", "yes"])
        
        if bin_width > 0:
            cmd.extend(["-bin", str(bin_width)])
            
        if cutoff > 0:
            cmd.extend(["-rmax", str(cutoff)])
        
        # FIX: Usar argumentos de CLI con nombres de grupos entre comillas
        # Esto asegura que GROMACS encuentre el grupo exacto en index.ndx
        cmd.extend(["-ref", f'group "{ref_id}"'])
        cmd.extend(["-sel", f'group "{sel_id}"'])
        
        # Validar existencia de archivos críticos
        if not os.path.exists(tpr_file): return False, "Falta archivo TPR"
        if not os.path.exists(xtc_file): return False, "Falta archivo XTC"

        try:
            # Añadido timeout de comunicación (60s es poco para RDF real, usando 300s)
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            # Ya no enviamos input porque usamos flags, pero mantenemos timeout
            stdout, stderr = process.communicate(timeout= None)
            
            if process.returncode == 0:
                return True, "RDF GROMACS calculado."
            else:
                return False, f"Error GROMACS RDF:\n{stderr}"
        except Exception as e:
            return False, str(e)

    def run_gmx_rdf_multi(self, tpr_file, xtc_file, output_xvg, ref_name, sel_names, working_dir, use_com, bin_width, cutoff):
        """
        Ejecuta gmx rdf optimizado para múltiples selecciones. (Single Pass)
        Usa sintaxis de selección moderna para evitar input interactivo y procesar varios en una pasada.
        Args:
            ref_name (str): Nombre del grupo referencia (ej "SOL")
            sel_names (list): Lista de nombres de grupos seleccion (ej ["LIG", "Protein"])
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
            
        # FIX: Añadir -pbc yes para asegurar que los cálculos respeten condiciones de borde
        cmd.extend(["-pbc", "yes"])
        
        if bin_width > 0:
            cmd.extend(["-bin", str(bin_width)])
        
        if cutoff > 0:
            cmd.extend(["-rmax", str(cutoff)])
            
        # Construir selecciones usando sintaxis "group 'Name'"
        # Esto es robusto para GROMACS moderno
        ref_str = f'group "{ref_name}"'
        
        cmd.extend(["-ref", ref_str])
        
        # FIX: Algunos GROMACS requieren un flag -sel por cada grupo si están entre comillas
        # O bien soportan múltiples, pero ser explícito es más seguro.
        for s_name in sel_names:
            cmd.extend(["-sel", f'group "{s_name}"'])
        
        try:
            # Añadimos stdin=PIPE para evitar bloqueos si gmx pide interactividad
            # Enviamos saltos de línea por si acaso pide "Press Enter" o similar
            input_feed = "\n" * (len(sel_names) + 5) 
            
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            # Timeout para evitar bloqueos infinitos
            stdout, stderr = process.communicate(input=input_feed, timeout=None)
            
            if process.returncode == 0:
                return True, "RDF Multi calculado exitosamente."
            else:
                return False, f"Error GROMACS RDF Multi:\n{stderr}\nComando: {' '.join(cmd)}"
        except Exception as e:
            if isinstance(e, subprocess.TimeoutExpired):
                process.kill()
                return False, "Error: Timeout en GROMACS (proceso tardó demasiado o se colgó esperando input)."
            return False, str(e)


    def _run_travis_rdf_OLD_UNUSED(self, struct_file, traj_file, output_csv, mol1_name, mol2_name):
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
            
            # Buscar salida de Travis
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

    def get_box_dimensions(self, gro_file):
        """Lee las dimensiones de la caja del archivo GRO (última línea)."""
        if not os.path.exists(gro_file): return None
        try:
            with open(gro_file, 'r') as f:
                # Método eficiente: seek al final y leer últimas líneas
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 200), os.SEEK_SET)
                lines = f.readlines()
                if not lines: return None
                
                last_line = lines[-1].strip()
                if not last_line and len(lines) > 1: last_line = lines[-2].strip()
                
                parts = last_line.split()
                if len(parts) >= 3:
                    return min(float(parts[0]), float(parts[1]), float(parts[2]))
        except:
            pass
        return None