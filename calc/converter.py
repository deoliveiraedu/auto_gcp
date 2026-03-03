import csv
import re
import os
import config

def parse_coordinate_system(line):
    # Procura por "zone XX" e "N" ou "S" dentro da string
    match = re.search(r'zone\s+(\d+)\s*([NS])', line, re.IGNORECASE)
    if match:
        zone = int(match.group(1))
        hem = match.group(2).upper()
        if hem == 'S':
            # SIRGAS 2000 / UTM zones 18S to 25S (Brasil Sul)
            if 18 <= zone <= 25:
                return f"EPSG:{31978 + (zone - 18)}"
        else:
            # SIRGAS 2000 / UTM zones 19N to 22N (Brasil Norte)
            if 19 <= zone <= 22:
                return f"EPSG:{31972 + (zone - 18)}"
    return "EPSG:31982" # Default: 22S

def process_survey(input_file, qgis_output, gcp_output):
    if not os.path.exists(input_file):
        print(f"Erro: {input_file} não encontrado.")
        return

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Erro ao ler arquivo de entrada: {e}")
        return
        
    if not lines: return

    proj_string = "EPSG:31982"

    qgis_data = [['Ponto', 'Norte', 'Este', 'Elevacao', 'Status', 'HRMS', 'VRMS']]
    gcp_data = [proj_string]

    for line in lines:
        parts = line.strip().split(';')
        if len(parts) > 20 and parts[0] == 'GP':
            try:
                p_id = parts[1]
                n = parts[4].replace(',', '.')
                e = parts[5].replace(',', '.')
                z = parts[6].replace(',', '.')
                st = parts[13]
                h = parts[19].replace(',', '.')
                v = parts[20].replace(',', '.')
                
                # Validar se são números
                float(n); float(e); float(z)
                
                qgis_data.append([p_id, n, e, z, st, h, v])
                gcp_data.append(f"{e} {n} {z} {p_id}") # Formato ODM: X Y Z ID
            except (IndexError, ValueError): 
                continue

    os.makedirs(os.path.dirname(qgis_output), exist_ok=True)
    
    with open(qgis_output, 'w', newline='', encoding='utf-8') as f_q:
        csv.writer(f_q).writerows(qgis_data)
        
    with open(gcp_output, 'w', encoding='utf-8') as f_g:
        f_g.write("\n".join(gcp_data) + "\n")

if __name__ == "__main__":
    process_survey(config.INPUT_RELATORIO, config.PONTOS_QGIS, config.GCP_LIST_ODM)
