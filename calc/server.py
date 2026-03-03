import os
import json
import collections
import csv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import config
import cv2

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)

STATE_FILE = os.path.join(config.OUTPUT_DIR, 'refine_state.json')

class RefineState:
    def __init__(self):
        self.projection_line = "+proj=utm +zone=22 +south +datum=SIRGAS2000 +units=m +no_defs"
        self.path_cache = {}
        self.gcps_master = self.load_master_gcps()
        self.data = self.load_data()
        # image_names now includes ALL images in the directory
        self.image_names = self.scan_all_images()
        os.makedirs(config.OUTPUT_IMG_DIR, exist_ok=True)

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
        
        # Sort: First those with points (from load_data), then others
        imgs_with_points = [i for i in imgs if i in self.data and len(self.data[i]['points']) > 0]
        imgs_without_points = [i for i in imgs if i not in imgs_with_points]
        
        imgs_with_points.sort(key=lambda x: len(self.data[x]['points']), reverse=True)
        imgs_without_points.sort()
        
        return imgs_with_points + imgs_without_points

    def load_data(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state_obj = json.load(f)
                    if isinstance(state_obj, dict) and "projection_line" in state_obj:
                        self.projection_line = state_obj["projection_line"]
                        return state_obj["data"]
                    return state_obj
            except Exception as e:
                print(f"Erro ao ler JSON: {e}")
        
        data = collections.defaultdict(lambda: {'points': [], 'verified': False})
        if os.path.exists(config.GCP_LIST_IM):
            with open(config.GCP_LIST_IM, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines: self.projection_line = lines[0].strip()
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        e, n, z, u, v, filename, gcp_id = parts
                        data[filename]['points'].append({
                            'id': gcp_id, 'e': float(e), 'n': float(n), 'z': float(z),
                            'u': float(u), 'v': float(v), 'deleted': False
                        })
        return {k: v for k, v in data.items()}

    def get_stats(self):
        total_imgs = len(self.image_names)
        verified_imgs = sum(1 for name in self.image_names if self.data.get(name, {}).get('verified'))
        
        gcp_stats = {pid: {"id": pid, "found": 0, "verified": 0} for pid in self.gcps_master}
        
        total_points = 0
        verified_points = 0
        
        for name, info in self.data.items():
            is_verified = info.get('verified', False)
            for p in info.get('points', []):
                if p.get('deleted'): continue
                pid = str(p['id'])
                if pid in gcp_stats:
                    gcp_stats[pid]["found"] += 1
                    if is_verified:
                        gcp_stats[pid]["verified"] += 1
                        verified_points += 1
                total_points += 1
                    
        return {
            "total_images": total_imgs,
            "verified_images": verified_imgs,
            "total_points": total_points,
            "verified_points": verified_points,
            "total_project_gcp": len(self.gcps_master),
            "gcp_list": list(gcp_stats.values())
        }

    def save(self):
        state_obj = {"projection_line": self.projection_line, "data": self.data}
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state_obj, f, indent=4)

    def update_conference_image(self, name):
        img_path = self.get_img_full_path(name)
        if not img_path: return
        img = cv2.imread(img_path)
        if img is None: return
        points = self.data.get(name, {}).get('points', [])
        verified = self.data.get(name, {}).get('verified', False)
        for p in points:
            if p.get('deleted'): continue
            x, y, pid = int(p['u']), int(p['v']), p['id']
            color = (0, 255, 0) if verified else (0, 0, 255)
            cv2.drawMarker(img, (x, y), color, cv2.MARKER_TILTED_CROSS, config.MARKER_SIZE, config.MARKER_THICKNESS)
            cv2.putText(img, str(pid), (x+15, y-15), cv2.FONT_HERSHEY_SIMPLEX, config.FONT_SCALE, color, config.FONT_THICKNESS)
        cv2.imwrite(os.path.join(config.OUTPUT_IMG_DIR, f"check_{name}"), img)

    def get_img_full_path(self, name):
        if name in self.path_cache: return self.path_cache[name]
        photo_dir = os.path.abspath(config.PHOTO_DIR)
        for root, _, files in os.walk(photo_dir):
            if name in files:
                full_path = os.path.join(root, name)
                self.path_cache[name] = full_path
                return full_path
        return None

    def export(self):
        output_lines = [self.projection_line]
        for name in self.image_names:
            if self.data.get(name, {}).get('verified', False):
                for p in self.data.get(name, {}).get('points', []):
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
        "gcps": state.gcps_master
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
    state.data[name]['points'] = req['points']
    state.data[name]['verified'] = req.get('verified', False)
    state.save()
    state.update_conference_image(name)
    return jsonify({"status": "ok", "stats": state.get_stats()})

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
