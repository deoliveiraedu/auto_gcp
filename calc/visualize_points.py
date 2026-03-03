import os
import collections
import cv2
import numpy as np
import config

def main():
    if not os.path.exists(config.GCP_LIST_IM):
        print(f"Erro: {config.GCP_LIST_IM} não encontrado em output/.")
        return

    # Cache de caminhos das fotos para evitar busca recursiva lenta
    path_cache = {}
    photo_dir = os.path.abspath(config.PHOTO_DIR)
    for root, _, files in os.walk(photo_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg')):
                path_cache[f] = os.path.join(root, f)

    image_points = collections.defaultdict(list)
    with open(config.GCP_LIST_IM, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) >= 7:
                # Formato esperado: E N Z U V FOTO ID
                im_x, im_y, img_name, gcp_id = float(parts[3]), float(parts[4]), parts[5], parts[6]
                image_points[img_name].append({'x': int(im_x), 'y': int(im_y), 'id': gcp_id})

    if not image_points: return

    sorted_images = sorted(image_points.items(), key=lambda x: len(x[1]), reverse=True)
    top_images = sorted_images[:config.TOP_N_IMAGES]
    os.makedirs(config.OUTPUT_IMG_DIR, exist_ok=True)
    
    print(f"Gerando visualizações para {len(top_images)} fotos...")
    for img_name, points in top_images:
        img_path = path_cache.get(img_name)
        if not img_path: continue

        try:
            img = cv2.imread(img_path)
            if img is None: continue
            for pt in points:
                x, y, pid = pt['x'], pt['y'], pt['id']
                size, thick = config.MARKER_SIZE, config.MARKER_THICKNESS
                # Desenhar X
                cv2.line(img, (x-size, y-size), (x+size, y+size), (0, 0, 255), thick)
                cv2.line(img, (x+size, y-size), (x-size, y+size), (0, 0, 255), thick)
                
                # Texto ID com fundo
                text = str(pid)
                font_face, font_scale, font_thick = cv2.FONT_HERSHEY_DUPLEX, config.FONT_SCALE, config.FONT_THICKNESS
                (tw, th), bl = cv2.getTextSize(text, font_face, font_scale, font_thick)
                tx, ty = x + size + 10, y - size
                cv2.rectangle(img, (tx - 5, ty - th - 5), (tx + tw + 5, ty + 5), (0, 0, 255), cv2.FILLED)
                cv2.putText(img, text, (tx, ty), font_face, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)
            
            cv2.imwrite(os.path.join(config.OUTPUT_IMG_DIR, f"check_{img_name}"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            print(f" - Concluída: {img_name}")
        except Exception as e: print(f"Erro em {img_name}: {e}")

if __name__ == "__main__":
    main()
