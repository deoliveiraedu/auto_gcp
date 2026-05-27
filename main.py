import os
import json
import shutil
import threading
import statistics

import numpy as np

import config
from calc import converter, find_points_in_photos, visualize_points

# DJI Mini 2 sensor width — mirrors calc/camera.py
_SENSOR_WIDTH_MM = 6.17

# Plausible altitude range of drone above GCP during a survey
_MIN_DRONE_ABOVE_GCP_M = 5.0
_MAX_DRONE_ABOVE_GCP_M = 600.0

WORLD_FILE = os.path.join(config.OUTPUT_DIR, 'world.json')
STATE_FILE = os.path.join(config.OUTPUT_DIR, 'refine_state.json')

# ── CLI helpers ───────────────────────────────────────────────────────────────

def _header():
    print()
    print("=" * 58)
    print("  LEVANTAMENTO TOPOGRÁFICO — ORQUESTRADOR")
    print("=" * 58)
    print()

def _step(n, total, label):
    print(f"\n[{n}/{total}] {label}...")

def _ok(msg):   print(f"      ✓ {msg}")
def _warn(msg): print(f"      ⚠ {msg}")
def _err(msg):  print(f"      ✗ {msg}")

def _sep():
    print()

# ── Output directory ──────────────────────────────────────────────────────────

def _clear_output(keep_state=False):
    if os.path.exists(config.OUTPUT_DIR):
        for name in os.listdir(config.OUTPUT_DIR):
            if keep_state and name in ('refine_state.json',):
                continue
            path = os.path.join(config.OUTPUT_DIR, name)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception:
                pass
    else:
        os.makedirs(config.OUTPUT_DIR)

# ── Projection quality ────────────────────────────────────────────────────────

def _quality_ok(stats):
    total = stats['total_gcps']
    if total == 0:
        return False
    return stats['found_count'] >= total / 2

def _print_projection_result(stats):
    total = stats['total_gcps']
    found = stats['found_count']
    entries = stats['total_entries']
    photos = stats['photos_count']
    pct = (found / total * 100) if total > 0 else 0

    if entries == 0:
        _err(f"Nenhum ponto projetado | 0/{total} GCPs encontrados")
    elif _quality_ok(stats):
        _ok(f"{photos} fotos | {entries} marcações | {found}/{total} GCPs ({pct:.0f}%)")
    else:
        _warn(f"{photos} fotos | {entries} marcações | {found}/{total} GCPs ({pct:.0f}%)")

# ── Calibration helpers ───────────────────────────────────────────────────────

def _extract_bias_from_calibration():
    """
    Compute GPS offset from user-placed GCPs via back-projection.

    For each GCP manually placed (and photo verified with V), back-projects
    the user pixel through the camera model to find the implied drone position,
    then returns the average delta from the EXIF GPS position.

    Works with 1+ GCPs per photo — does NOT require PnP (no minimum point count).
    """
    if not os.path.exists(STATE_FILE) or not os.path.exists(WORLD_FILE):
        return None

    with open(STATE_FILE, encoding='utf-8') as f:
        saved = json.load(f)
    with open(WORLD_FILE, encoding='utf-8') as f:
        world = json.load(f)

    data = saved.get('data', {}) if isinstance(saved, dict) else {}

    offsets_e, offsets_n = [], []

    for img_name, info in data.items():
        if not info.get('verified'):
            continue
        cam = world.get(img_name)
        if not cam or 'exif_pos' not in cam or 'R_w2c' not in cam:
            continue

        exif_pos = cam['exif_pos']           # [e, n, z] GPS position with current offset
        R_w2c = np.array(cam['R_w2c'])
        R_c2w = R_w2c.T                      # camera→world rotation
        f_px = cam['f_mm'] * cam['width'] / _SENSOR_WIDTH_MM
        cx, cy = cam['width'] / 2.0, cam['height'] / 2.0
        drone_z = exif_pos[2]

        for pt in info.get('points', []):
            if pt.get('deleted'):
                continue

            u, v = pt['u'], pt['v']
            gcp_e, gcp_n, gcp_z = pt['e'], pt['n'], pt['z']

            # Back-project pixel → ray in camera frame → world frame
            ray_c = np.array([(u - cx) / f_px, (v - cy) / f_px, 1.0])
            ray_w = R_c2w @ ray_c

            # Intersect ray with horizontal plane at GCP altitude
            if abs(ray_w[2]) < 1e-6:
                continue                     # ray nearly horizontal, skip
            t = (gcp_z - drone_z) / ray_w[2]

            # Physically plausible: drone must be 5–600 m above GCP plane
            if not (_MIN_DRONE_ABOVE_GCP_M <= t <= _MAX_DRONE_ABOVE_GCP_M):
                continue

            # Implied drone position from this GCP + user pixel
            drone_e_implied = gcp_e - t * ray_w[0]
            drone_n_implied = gcp_n - t * ray_w[1]

            offsets_e.append(drone_e_implied - exif_pos[0])
            offsets_n.append(drone_n_implied - exif_pos[1])

    if not offsets_e:
        return None

    # Median is robust against outlier placements in wrong photos
    return {
        'e': statistics.median(offsets_e),
        'n': statistics.median(offsets_n),
        'z': 0.0,
        'n_samples': len(offsets_e),
    }

def _broad_scan_for_candidates():
    """
    Run projection with relaxed params to populate candidate photos with rough
    initial markers. These become the top-listed photos in the calibration UI.
    Temporarily overrides pitch/radius/center-distance limits.
    """
    old_pitch  = config.MAX_PITCH_OFFSET
    old_radius = config.RADIUS_METERS
    old_center = config.MAX_PIXEL_DIST_FROM_CENTER

    config.MAX_PITCH_OFFSET          = 80.0   # allow oblique shots down to -10°
    config.RADIUS_METERS             = 600.0  # wider search radius
    config.MAX_PIXEL_DIST_FROM_CENTER = 9999.0 # full image area

    stats = find_points_in_photos.main()

    config.MAX_PITCH_OFFSET          = old_pitch
    config.RADIUS_METERS             = old_radius
    config.MAX_PIXEL_DIST_FROM_CENTER = old_center

    return stats

def _run_web_calibration():
    """Start a stoppable calibration server. Returns bias dict or None."""
    # Pre-populate the UI with candidate photos that likely show GCPs
    print()
    print("  Procurando fotos candidatas (parâmetros amplos)...")
    broad = _broad_scan_for_candidates()
    if broad['photos_count'] > 0:
        _ok(f"{broad['photos_count']} fotos candidatas pré-carregadas com posições aproximadas.")
        _ok("Ajuste os marcadores para as posições exatas antes de verificar.")
    else:
        _warn("Nenhuma foto candidata encontrada automaticamente.")
        _warn("Navegue manualmente até fotos onde os GCPs estão visíveis.")

    from calc import server as srv
    srv.reinit_state()
    httpd = srv.make_server_instance(port=5000)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    print()
    print("  Servidor de calibração iniciado: http://localhost:5000")
    print()
    print("  Instruções:")
    print("    1. As fotos com GCPs aproximados aparecem primeiro na lista")
    print("    2. Arraste cada marcador para a posição exata do GCP na foto")
    print("    3. Pressione V para verificar (marcador fica verde)")
    print("    4. Repita em 2-3 fotos diferentes para maior precisão")
    print("    → Basta 1 GCP por foto; não é necessário ter 3 por foto")
    print()
    input("  Pressione ENTER quando terminar a calibração... ")

    httpd.shutdown()
    t.join(timeout=3)

    return _extract_bias_from_calibration()

def _calibration_menu(stats):
    """Show calibration options and return user choice ('1','2','3')."""
    total = stats['total_gcps']
    found = stats['found_count']
    pct = (found / total * 100) if total > 0 else 0

    print()
    print("  ┌─ ATENÇÃO " + "─" * 44 + "┐")
    print(f"  │  Apenas {found}/{total} GCPs encontrados ({pct:.0f}%).{' ' * (39 - len(str(found)) - len(str(total)))}│")
    print( "  │  O offset de GPS pode estar incorreto para este voo. │")
    print( "  └" + "─" * 55 + "┘")
    print()
    print("  Como deseja prosseguir?")
    print("    [1] Calibrar offset via interface web  (recomendado)")
    print("    [2] Informar offset manualmente (Norte/Leste em metros)")
    print("    [3] Continuar sem calibrar")
    print()
    choice = input("  Opção [1]: ").strip() or "1"
    return choice

# ── Main ──────────────────────────────────────────────────────────────────────

def run_main():
    _header()

    # ── Mode selection ────────────────────────────────────────────────────────
    recalc = True
    state_exists = os.path.exists(STATE_FILE)
    gcp_exists = os.path.exists(config.GCP_LIST_IM)

    if state_exists or gcp_exists:
        print("  Estado anterior detectado.")
        ans = input("  [r] Refinar existente   [c] Recalcular tudo\n  Opção [r]: ").strip().lower() or 'r'
        recalc = (ans == 'c')

    if not recalc:
        _step(1, 1, "Iniciando servidor de refinamento")
        print("      Acesse: http://localhost:5000")
        from calc import server as srv
        srv.run_server()
        return

    # ── Full pipeline ─────────────────────────────────────────────────────────
    _clear_output(keep_state=False)
    if not os.path.exists(config.INPUT_DIR):
        _err(f"Pasta '{config.INPUT_DIR}' não encontrada.")
        return

    # Step 1: survey → GCPs (auto-detect format: TXT preferred, CSV fallback)
    input_file = config.INPUT_COORDENADAS if os.path.exists(config.INPUT_COORDENADAS) else config.INPUT_RELATORIO
    _step(1, 4, f"Convertendo levantamento ({os.path.basename(input_file)})")
    converter.process_survey(input_file, config.PONTOS_QGIS, config.GCP_LIST_ODM)

    # Read detected projection for display
    detected_proj = config.UTM_PROJ.upper()
    if os.path.exists(config.GCP_LIST_ODM):
        with open(config.GCP_LIST_ODM) as f:
            line1 = f.readline().strip()
            if line1.startswith("EPSG:") or line1.startswith("+proj"):
                detected_proj = line1

    # Count GCPs
    n_gcps = 0
    if os.path.exists(config.PONTOS_QGIS):
        import csv as _csv
        with open(config.PONTOS_QGIS, encoding='utf-8') as f:
            n_gcps = sum(1 for _ in _csv.DictReader(f))

    if n_gcps == 0:
        _err("Nenhum GCP detectado no CSV. Verifique o arquivo de entrada.")
        return
    _ok(f"{n_gcps} GCPs detectados | Projeção: {detected_proj}")

    # Step 2: Projection (with calibration loop)
    for attempt in range(3):
        label = "Calculando projeção de pontos nas fotos" if attempt == 0 \
                else f"Recalculando projeção com offset calibrado (tentativa {attempt + 1})"
        _step(2, 4, label)

        stats = find_points_in_photos.main()
        _print_projection_result(stats)

        if _quality_ok(stats):
            break

        # Poor quality — offer calibration
        choice = _calibration_menu(stats)

        if choice == '1':
            bias = _run_web_calibration()
            if bias:
                config.GPS_OFFSET_EAST  += bias['e']
                config.GPS_OFFSET_NORTH += bias['n']
                config.GPS_OFFSET_Z     += bias['z']
                print()
                _ok(f"Offset calculado a partir de {bias['n_samples']} ponto(s).")
                _ok(f"Norte={config.GPS_OFFSET_NORTH:+.1f}m  "
                    f"Leste={config.GPS_OFFSET_EAST:+.1f}m  "
                    f"Z={config.GPS_OFFSET_Z:+.1f}m")
                # Discard world built with old offsets so server rebuilds it fresh
                if os.path.exists(WORLD_FILE):
                    os.unlink(WORLD_FILE)
            else:
                print()
                _warn("Nenhuma foto verificada detectada na calibração.")
                _warn("Passos necessários: [+] Adicionar Ponto → posicionar → pressionar V.")
                print()
                retry = input("  Tentar calibrar novamente? [s/n]: ").strip().lower()
                if retry == 's':
                    continue   # restart outer loop iteration (re-enter calibration menu)
                break

        elif choice == '2':
            print()
            try:
                raw_n = input(f"  Offset Norte (atual {config.GPS_OFFSET_NORTH:+.1f}m): ").strip()
                raw_e = input(f"  Offset Leste (atual {config.GPS_OFFSET_EAST:+.1f}m): ").strip()
                if raw_n: config.GPS_OFFSET_NORTH = float(raw_n)
                if raw_e: config.GPS_OFFSET_EAST  = float(raw_e)
                _ok(f"Offsets definidos: Norte={config.GPS_OFFSET_NORTH:+.1f}m  "
                    f"Leste={config.GPS_OFFSET_EAST:+.1f}m")
            except ValueError:
                _warn("Valor inválido. Continuando sem alteração.")
                break

        else:
            # User chose to continue without calibrating
            break

    # Step 3: Visualizations
    _step(3, 4, "Gerando visualizações técnicas")
    if os.path.exists(config.GCP_LIST_IM):
        visualize_points.main()
        # Count generated images
        img_dir = config.OUTPUT_IMG_DIR
        n_imgs = len(os.listdir(img_dir)) if os.path.exists(img_dir) else 0
        _ok(f"{n_imgs} imagens de conferência geradas em output/fotos_conferencia/")
    else:
        _warn("Sem marcações para visualizar")

    # Step 4: Refinement server
    _step(4, 4, "Iniciando servidor de refinamento")
    print("      Acesse: http://localhost:5000")
    _sep()
    from calc import server as srv
    srv.run_server()


if __name__ == "__main__":
    run_main()
