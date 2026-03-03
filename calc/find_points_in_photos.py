import os
import csv
import math
import numpy as np
from pyproj import Transformer
import config

from .exif import get_image_metadata
from .camera import create_camera_matrix, project_point, get_focal_len_px

def load_gcps(file_path):
    gcps = []
    if not os.path.exists(file_path): return []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            gcps.append({'id': row['Ponto'], 'e': float(row['Este']), 'n': float(row['Norte']), 'z': float(row['Elevacao'])})
    return gcps

def estimate_ground_z(drone_e, drone_n, gcps):
    dists = []
    for p in gcps:
        d2 = (p['e'] - drone_e)**2 + (p['n'] - drone_n)**2
        dists.append((d2, p['z']))
    dists.sort()
    nearby = dists[:3]
    if not nearby: return 350.0
    sz, sw = 0, 0
    for d2, z in nearby:
        w = 1.0 / (math.sqrt(d2) + 0.001)
        sz += z * w; sw += w
    return sz / sw if sw > 0 else 350.0

def main():
    gcps = load_gcps(config.PONTOS_QGIS)
    if not gcps: 
        print("Erro: Nenhum GCP carregado.")
        return
    
    # Usar projeção do config para consistência
    transformer = Transformer.from_crs("epsg:4326", config.UTM_PROJ, always_xy=True)
    
    # Obter a string de projeção correta do gcp_list.txt se possível
    proj_line = "+proj=utm +zone=22 +south +datum=SIRGAS2000 +units=m +no_defs"
    if os.path.exists(config.GCP_LIST_ODM):
        with open(config.GCP_LIST_ODM, 'r') as f:
            line1 = f.readline().strip()
            if line1.startswith("+proj"): proj_line = line1

    photos_data = {}
    print(f"Calculando projeções em todas as fotos...")
    
    for root, dirs, files in os.walk(config.PHOTO_DIR):
        for file in sorted(files):
            if file.lower().endswith(('.jpg', '.jpeg')):
                img_path = os.path.join(root, file)
                try:
                    meta = get_image_metadata(img_path)
                    if 'lat' not in meta or 'lon' not in meta: continue
                    
                    gimbal_pitch = meta.get('gimbal_pitch', -90.0)
                    if gimbal_pitch > (-90.0 + config.MAX_PITCH_OFFSET): continue
                        
                    drone_e, drone_n = transformer.transform(meta['lon'], meta['lat'])
                    drone_e += config.GPS_OFFSET_EAST
                    drone_n += config.GPS_OFFSET_NORTH
                    
                    ground_z = estimate_ground_z(drone_e, drone_n, gcps)
                    drone_z = ground_z + meta.get('rel_alt', 30.0) + config.GPS_OFFSET_Z
                    
                    R = create_camera_matrix(meta['gimbal_yaw'], meta['gimbal_pitch'], meta['gimbal_roll'], config.YAW_OFFSET)
                    width, height = meta['width'], meta['height']
                    cx, cy = width / 2.0, height / 2.0
                    f_px = get_focal_len_px(meta.get('focal_length', 4.5), width)
                    
                    photo_candidates = []
                    for gcp in gcps:
                        dist_xy = math.sqrt((gcp['e'] - drone_e)**2 + (gcp['n'] - drone_n)**2)
                        if dist_xy > config.RADIUS_METERS: continue
                        
                        proj = project_point([gcp['e'], gcp['n'], gcp['z']], [drone_e, drone_n, drone_z], R, f_px, cx, cy)
                        if proj:
                            u, v = proj
                            if 0 <= u < width and 0 <= v < height:
                                dist_center = math.sqrt((u - cx)**2 + (v - cy)**2)
                                if dist_center <= config.MAX_PIXEL_DIST_FROM_CENTER:
                                    photo_candidates.append({
                                        'file': file,
                                        'gcp_id': gcp['id'],
                                        'line': f"{gcp['e']:.4f} {gcp['n']:.4f} {gcp['z']:.4f} {u:.1f} {v:.1f} {file} {gcp['id']}",
                                        'rep': f"    - Ponto {gcp['id']}: Pix({u:>6.1f}, {v:>6.1f}) | Centro: {dist_center:>6.1f}px | Dist: {dist_xy:>5.1f}m",
                                        'dist_center': dist_center,
                                        'gimbal_yaw': meta['gimbal_yaw']
                                    })
                    
                    if photo_candidates:
                        photo_candidates.sort(key=lambda x: x['dist_center'])
                        best_in_photo = photo_candidates[:config.MAX_POINTS_PER_PHOTO]
                        photos_data[file] = {
                            'candidates': best_in_photo,
                            'count': len(best_in_photo),
                            'avg_dist': sum(p['dist_center'] for p in best_in_photo) / len(best_in_photo),
                            'yaw': meta['gimbal_yaw']
                        }
                except Exception as e: print(f"Erro em {file}: {e}")

    if not photos_data:
        print("Aviso: Nenhum ponto projetado em nenhuma foto.")
        return

    sorted_photos = sorted(photos_data.keys(), key=lambda k: (-photos_data[k]['count'], photos_data[k]['avg_dist']))
    final_list = []
    total_count = 0
    
    for f_name in sorted_photos:
        candidates = photos_data[f_name]['candidates']
        if total_count + len(candidates) <= config.TOTAL_MAX_POINTS:
            final_list.extend(candidates)
            total_count += len(candidates)
        else:
            remaining = config.TOTAL_MAX_POINTS - total_count
            if remaining > 0:
                final_list.extend(candidates[:remaining])
                total_count += remaining
            break

    gcp_output_lines = [proj_line]
    for item in final_list:
        gcp_output_lines.append(item['line'])
        
    with open(config.GCP_LIST_IM, 'w', encoding='utf-8') as f:
        f.write("\n".join(gcp_output_lines) + "\n")
        
    report_dict = {}
    for item in final_list:
        if item['file'] not in report_dict:
            report_dict[item['file']] = {'yaw': photos_data[item['file']]['yaw'], 'points': []}
        report_dict[item['file']]['points'].append(item['rep'])
        
    with open(config.PONTOS_NAS_FOTOS_TXT, 'w', encoding='utf-8') as f_rep:
        f_rep.write(f"RELATÓRIO DE POSICIONAMENTO (PRIORIDADE: MULTI-PONTOS)\n" + "=" * 65 + "\n\n")
        final_files_ordered = []
        seen = set()
        for item in final_list:
            if item['file'] not in seen:
                final_files_ordered.append(item['file'])
                seen.add(item['file'])
                
        for f_name in final_files_ordered:
            info = report_dict[f_name]
            f_rep.write(f"FOTO: {f_name} (GimbalYaw: {info['yaw']}\u00b0) - {len(info['points'])} pontos\n")
            f_rep.write("\n".join(info['points']) + "\n")
            f_rep.write("-" * 65 + "\n")

    print(f"\nFinalizado! Total de marcações no arquivo: {len(final_list)}")

if __name__ == "__main__":
    main()
