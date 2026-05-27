import csv
import re
import os
import config

def parse_coordinate_system(line):
    match = re.search(r'zone\s+(\d+)\s*([NS])', line, re.IGNORECASE)
    if match:
        zone = int(match.group(1))
        hem = match.group(2).upper()
        if hem == 'S':
            if 18 <= zone <= 25:
                return f"EPSG:{31978 + (zone - 18)}"
        else:
            if 19 <= zone <= 22:
                return f"EPSG:{31972 + (zone - 18)}"
    return None

def _detect_epsg(lines):
    for line in lines[:10]:
        detected = parse_coordinate_system(line)
        if detected:
            return detected
    return config.UTM_PROJ.upper()

def _is_txt_format(lines):
    return any('[JOB INFO]' in l for l in lines[:5])

def _parse_txt_points(lines, proj_string):
    """Parse comma-delimited TXT from GNSS tools (Mapit/Emlid style).
    Format: Nome,Descrição,Leste,Norte,Altitude(Elip.),SigmaE,SigmaN,SigmaH,TipoDeSolução
    """
    qgis_data = [['Ponto', 'Norte', 'Este', 'Elevacao', 'Status', 'HRMS', 'VRMS']]
    gcp_data = [proj_string]
    in_points = False
    for line in lines:
        s = line.strip()
        if s == '[SURVEY POINTS]':
            in_points = True
            continue
        if not in_points or not s or not s[0].isdigit():
            continue
        parts = s.split(',')
        if len(parts) < 5:
            continue
        try:
            p_id    = parts[0].strip()
            e       = parts[2].strip()
            n       = parts[3].strip()
            z       = parts[4].strip()
            float(e); float(n); float(z)
            sigma_e  = parts[5].strip() if len(parts) > 5 else '0'
            sigma_h  = parts[7].strip() if len(parts) > 7 else '0'
            sol_type = parts[8].strip() if len(parts) > 8 else ''
            qgis_data.append([p_id, n, e, z, sol_type, sigma_e, sigma_h])
            gcp_data.append(f"{e} {n} {z} {p_id}")
        except (IndexError, ValueError):
            continue
    return qgis_data, gcp_data

def _parse_csv_points(lines, proj_string):
    """Parse semicolon-delimited CSV (legacy topographic survey format)."""
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
                float(n); float(e); float(z)
                qgis_data.append([p_id, n, e, z, st, h, v])
                gcp_data.append(f"{e} {n} {z} {p_id}")
            except (IndexError, ValueError):
                continue
    return qgis_data, gcp_data

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

    if not lines:
        return

    proj_string = _detect_epsg(lines)
    if _is_txt_format(lines):
        qgis_data, gcp_data = _parse_txt_points(lines, proj_string)
    else:
        qgis_data, gcp_data = _parse_csv_points(lines, proj_string)

    os.makedirs(os.path.dirname(qgis_output), exist_ok=True)
    with open(qgis_output, 'w', newline='', encoding='utf-8') as f_q:
        csv.writer(f_q).writerows(qgis_data)
    with open(gcp_output, 'w', encoding='utf-8') as f_g:
        f_g.write("\n".join(gcp_data) + "\n")

if __name__ == "__main__":
    process_survey(config.INPUT_RELATORIO, config.PONTOS_QGIS, config.GCP_LIST_ODM)
