import os
import json
import collections
import csv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import numpy as np
import config
import cv2
import pyproj
from calc import camera, exif

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)

STATE_FILE = os.path.join(config.OUTPUT_DIR, 'refine_state.json')
WORLD_FILE = os.path.join(config.OUTPUT_DIR, 'world.json')

class RefineState:
    def __init__(self):
        self.projection_line = config.UTM_PROJ.upper()
        self.path_cache = {}
        self.data: dict = self.load_data() # Loads projection from file if available
        self.gcps_master = self.load_master_gcps()
        self.world = self.load_world()
        os.makedirs(config.OUTPUT_IMG_DIR, exist_ok=True)
        
        # UTM Converter - INITIALIZE BEFORE SCANNING
        self.wgs84 = pyproj.Proj(proj='latlong', datum='WGS84')
        self.utm = pyproj.Proj(self.projection_line)
        self.transformer = pyproj.Transformer.from_proj(self.wgs84, self.utm, always_xy=True)

        self.image_names = self.scan_all_images()

    def load_master_gcps(self):
        gcps = {}
        if os.path.exists(config.PONTOS_QGIS):
            with open(config.PONTOS_QGIS, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    gcps[row['Ponto']] = {
                        'id': row['Ponto'],
                        'e': float(row['Este']),
                        'n': float(row['Norte']),
                        'z': float(row['Elevacao'])
                    }
        return gcps

    def scan_all_images(self):
        imgs = []
        photo_dir = os.path.abspath(config.PHOTO_DIR)
        for root, _, files in os.walk(photo_dir):
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    imgs.append(f)
                    self.path_cache[f] = os.path.join(root, f)
                    if f not in self.world:
                        self.init_camera_from_exif(f)
        
        # Sort: First those with points (from load_data), then others
        data_dict = self.data if isinstance(self.data, dict) else {}
        imgs_with_points = [i for i in imgs if i in data_dict and len(data_dict[i].get('points', [])) > 0]
        imgs_without_points = [i for i in imgs if i not in imgs_with_points]
        
        imgs_with_points.sort(key=lambda x: len(data_dict[x].get('points', [])), reverse=True)
        imgs_without_points.sort()
        
        return imgs_with_points + imgs_without_points

    def estimate_ground_z(self, drone_e, drone_n):
        dists = []
        for p in self.gcps_master.values():
            d2 = (p['e'] - drone_e)**2 + (p['n'] - drone_n)**2
            dists.append((d2, p['z']))
        dists.sort()
        nearby = dists[:3]
        if not nearby: return 350.0 # Default fallback
        sz, sw = 0, 0
        for d2, z in nearby:
            w = 1.0 / (np.sqrt(d2) + 0.001)
            sz += z * w; sw += w
        return sz / sw if sw > 0 else 350.0

    def init_camera_from_exif(self, name):
        path = self.get_img_full_path(name)
        if not path: return
        try:
            meta = exif.get_image_metadata(path)
            e, n = self.transformer.transform(meta['lon'], meta['lat'])
            
            # Aplica offsets iniciais do config para manter consistência com find_points_in_photos.py
            e += config.GPS_OFFSET_EAST
            n += config.GPS_OFFSET_NORTH
            
            # Calcula Z com base no relevo local (GCPs) + Altura Relativa do Drone
            ground_z = self.estimate_ground_z(e, n)
            z = ground_z + meta.get('rel_alt', 30.0) + config.GPS_OFFSET_Z
            
            # Matriz de rotação inicial via Gimbal
            R = camera.create_camera_matrix(meta['gimbal_yaw'], meta['gimbal_pitch'], meta['gimbal_roll'], config.YAW_OFFSET)
            
            pos = [e, n, z]
            self.world[name] = {
                'pos': pos,
                'exif_pos': pos, # Guarda original para propagação de bias
                'yaw': meta['gimbal_yaw'],
                'pitch': meta['gimbal_pitch'],
                'roll': meta['gimbal_roll'],
                'width': meta['width'],
                'height': meta['height'],
                'f_mm': meta['f_real'],
                'rel_alt': meta['rel_alt'],
                'R_w2c': R.tolist(),
                'manual': False
            }
        except Exception as e:
            print(f"Erro ao ler EXIF de {name}: {e}")

    def load_data(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state_obj = json.load(f)
                    if isinstance(state_obj, dict):
                        if "projection_line" in state_obj and isinstance(state_obj.get("data"), dict):
                            self.projection_line = state_obj["projection_line"]
                            return state_obj["data"]
                        return state_obj
            except Exception as e:
                print(f"Erro ao ler JSON: {e}")
        
        # Use a temporary dict for construction
        temp_data = {}
        if os.path.exists(config.GCP_LIST_IM):
            with open(config.GCP_LIST_IM, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines: 
                    first_line = lines[0].strip()
                    if first_line.startswith("EPSG:") or first_line.startswith("+proj"):
                        self.projection_line = first_line
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        e, n, z, u, v, filename, gcp_id = parts
                        if filename not in temp_data:
                            temp_data[filename] = {'points': [], 'verified': False}
                        temp_data[filename]['points'].append({
                            'id': gcp_id, 'e': float(e), 'n': float(n), 'z': float(z),
                            'u': float(u), 'v': float(v), 'deleted': False, 'manual': True
                        })
        return temp_data

    def load_world(self):
        if os.path.exists(WORLD_FILE):
            with open(WORLD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save(self):
        state_obj = {"projection_line": self.projection_line, "data": self.data}
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state_obj, f, indent=4)
        with open(WORLD_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.world, f, indent=4)

    def update_camera_pose(self, name):
        data_dict = self.data if isinstance(self.data, dict) else {}
        info = data_dict.get(name, {})
        valid_points = [p for p in info.get('points', []) if not p.get('deleted')]
        
        # Pelo menos 3 pontos para PnP
        if len(valid_points) >= 3:
            cam = self.world.get(name)
            if not cam: return
            
            pts_2d = [[p['u'], p['v']] for p in valid_points]
            pts_3d = [[p['e'], p['n'], p['z']] for p in valid_points]
            
            # Chute inicial a partir do estado atual (EXIF ou anterior)
            initial_rvec, initial_tvec = None, None
            if 'R_w2c' in cam and 'pos' in cam:
                R = np.array(cam['R_w2c'])
                pos = np.array(cam['pos']).reshape(3, 1)
                initial_rvec, _ = cv2.Rodrigues(R)
                initial_tvec = (-R @ pos).flatten().tolist()
                initial_rvec = initial_rvec.flatten().tolist()

            res = camera.resection_pnp(pts_2d, pts_3d, cam['width'], cam['height'], cam['f_mm'],
                                       initial_rvec=initial_rvec, initial_tvec=initial_tvec)
            if res:
                cam['pos'] = res['pos']
                cam['R_w2c'] = res['R_w2c']
                cam['manual'] = True
                self.reproject_all_points(name)
                
                # Propagação: se esta imagem foi verificada (aceita), propaga o bias para as outras
                if info.get('verified'):
                    self.propagate_bias(name)

    def propagate_bias(self, source_name):
        """Calcula o shift (bias) da imagem fonte e aplica em todas as não-manuais."""
        src_cam = self.world.get(source_name)
        if not src_cam or 'exif_pos' not in src_cam: return
        
        # Bias = Posição Refinada - Posição EXIF
        bias = np.array(src_cam['pos']) - np.array(src_cam['exif_pos'])
        
        for name, cam in self.world.items():
            if name == source_name: continue
            if cam.get('manual'): continue # Não sobrescreve o que já foi refinado
            
            # Aplica o bias na posição original de EXIF
            exif_pos = np.array(cam.get('exif_pos', cam['pos']))
            cam['pos'] = (exif_pos + bias).tolist()
            
            # Reprojeta os pontos para esta câmera
            self.reproject_all_points(name)

    def reproject_all_points(self, name):
        """Reprojeta GCPs que NÃO foram editados manualmente na imagem atual."""
        cam = self.world.get(name)
        if not cam: return
        
        data_dict = self.data if isinstance(self.data, dict) else {}
        info = data_dict.get(name, {'points': [], 'verified': False})
        
        R = np.array(cam['R_w2c'])
        f_px = camera.get_focal_len_px(cam['f_mm'], cam['width'])
        cx, cy = cam['width']/2, cam['height']/2
        
        # Atualiza pontos existentes que não são manuais ou todos se for a primeira vez?
        # A lógica solicitada: "atualizar a posição deles que foi feita apenas a partir do gps"
        for p in info['points']:
            if p.get('manual'): continue # Se marcarmos como manual, não mexemos
            proj = camera.project_point([p['e'], p['n'], p['z']], cam['pos'], R, f_px, cx, cy)
            if proj:
                p['u'], p['v'] = proj[0], proj[1]

    def get_stats(self):
        total_imgs = len(self.image_names)
        data_dict = self.data if isinstance(self.data, dict) else {}
        verified_imgs = sum(1 for name in self.image_names if data_dict.get(name, {}).get('verified'))
        
        gcp_stats = {pid: {"id": pid, "found": 0, "verified": 0} for pid in self.gcps_master}
        
        total_points = 0
        verified_points = 0
        unique_verified = set()
        
        avg_ground_z = 0
        if self.gcps_master:
            avg_ground_z = sum(g['z'] for g in self.gcps_master.values()) / len(self.gcps_master)
        
        for name, info in data_dict.items():
            is_verified = info.get('verified', False)
            for p in info.get('points', []):
                if p.get('deleted'): continue
                pid = str(p['id'])
                if pid in gcp_stats:
                    gcp_stats[pid]["found"] += 1
                    if is_verified:
                        gcp_stats[pid]["verified"] += 1
                        verified_points += 1
                        unique_verified.add(pid)
                total_points += 1
                    
        return {
            "total_images": total_imgs,
            "verified_images": verified_imgs,
            "total_points": total_points,
            "verified_points": verified_points,
            "total_project_gcp": len(self.gcps_master),
            "unique_verified_gcp": len(unique_verified),
            "avg_ground_z": avg_ground_z,
            "gcp_list": list(gcp_stats.values())
        }

    def update_conference_image(self, name):
        img_path = self.get_img_full_path(name)
        if not img_path: return
        img = cv2.imread(img_path)
        if img is None: return
        data_dict = self.data if isinstance(self.data, dict) else {}
        info = data_dict.get(name, {})
        points = info.get('points', [])
        verified = info.get('verified', False)
        for p in points:
            if p.get('deleted'): continue
            x, y, pid = int(p['u']), int(p['v']), p['id']
            color = (0, 255, 0) if verified else (0, 0, 255)
            cv2.drawMarker(img, (x, y), color, cv2.MARKER_TILTED_CROSS, config.MARKER_SIZE, config.MARKER_THICKNESS)
            cv2.putText(img, str(pid), (x+15, y-15), cv2.FONT_HERSHEY_SIMPLEX, config.FONT_SCALE, color, config.FONT_THICKNESS)
        cv2.imwrite(os.path.join(config.OUTPUT_IMG_DIR, f"check_{name}"), img)

    def get_img_full_path(self, name):
        if name in self.path_cache: return self.path_cache[name]
        return None

    def export(self):
        output_lines = [self.projection_line]
        data_dict = self.data if isinstance(self.data, dict) else {}
        for name in self.image_names:
            info = data_dict.get(name, {})
            if info.get('verified', False):
                for p in info.get('points', []):
                    if p.get('deleted'): continue
                    line = f"{p['e']:.4f} {p['n']:.4f} {p['z']:.4f} {p['u']:.1f} {p['v']:.1f} {name} {p['id']}"
                    output_lines.append(line)
        with open(config.GCP_LIST_IM, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines) + "\n")

state = RefineState()

@app.route('/api/images')
def get_images():
    return jsonify({
        "images": state.image_names, 
        "data": state.data,
        "stats": state.get_stats(),
        "gcps": state.gcps_master,
        "world": state.world
    })

@app.route('/api/image/<name>')
def get_image_file(name):
    full_path = state.get_img_full_path(name)
    if not full_path: return "Not found", 404
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

@app.route('/api/update', methods=['POST'])
def update_points():
    req = request.json
    name = req['name']
    if name not in state.data:
        state.data[name] = {'points': [], 'verified': False}
    
    # Marcamos pontos como manuais se vierem do frontend e não existiam ou foram movidos?
    # Para simplificar: qualquer ponto vindo do /api/update que não seja deletado é considerado "ajustado"
    # mas o ideal é diferenciar.
    state.data[name]['points'] = req['points']
    state.data[name]['verified'] = req.get('verified', False)
    
    # Requirement 2: Atualiza câmera e pontos ANTES de salvar
    state.update_camera_pose(name)
    
    state.save()
    state.update_conference_image(name)
    return jsonify({"status": "ok", "stats": state.get_stats(), "data": state.data, "world": state.world})

@app.route('/api/finish', methods=['POST'])
def finish():
    state.export()
    return jsonify({"status": "exported"})

@app.route('/')
def serve_gui():
    return send_from_directory(STATIC_DIR, 'index.html')

def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    run_server()
