import math
import numpy as np
import cv2

# Constantes para DJI Mini 2 (FC3170)
# Sensor 1/2.3" CMOS (Active area approx 6.17 x 4.55 mm)
SENSOR_WIDTH_MM = 6.17
SENSOR_HEIGHT_MM = 4.55

def rot_z(angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[c, -s, 0], [s,  c, 0], [0,  0, 1]])

def rot_x(angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[1, 0,  0], [0, c, -s], [0, s,  c]])

def rot_y(angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[ c, 0, s], [ 0, 1, 0], [-s, 0, c]])

def create_camera_matrix(yaw, pitch, roll, declination=0.0):
    """
    Constrói a matriz de transformação de World (ENU) para Camera.
    yaw: 0=Norte, 90=Leste (Graus)
    pitch: 0=Horizonte, -90=Olhando pra baixo (Nadir)
    roll: 0=Nivelado
    """
    y = math.radians(yaw + declination)
    p = math.radians(pitch)
    r = math.radians(roll)

    # Rotação do Drone/Gimbal no mundo ENU
    # -y porque no ENU Norte->Leste é rotação horária
    R_a2w = rot_z(-y) @ rot_x(p) @ rot_y(r)
    
    # Eixos da Câmera em relação ao Drone
    R_c2a = np.array([
        [1,  0,  0], # X_c = Right
        [0,  0, -1], # Y_c = Down
        [0,  1,  0]  # Z_c = Forward
    ]).T
    
    R_c2w = R_a2w @ R_c2a
    R_w2c = R_c2w.T
    return R_w2c

def get_focal_len_px(f_mm, img_width_px):
    return (f_mm * img_width_px) / SENSOR_WIDTH_MM

def get_intrinsic_matrix(f_mm, img_width_px, img_height_px):
    f_px = get_focal_len_px(f_mm, img_width_px)
    cx, cy = img_width_px / 2.0, img_height_px / 2.0
    return np.array([
        [f_px, 0,    cx],
        [0,    f_px, cy],
        [0,    0,    1]
    ], dtype=np.float64)

def project_point(gcp, drone_pos, R, focal_len_px, cx, cy):
    pt_w = np.array(gcp) - np.array(drone_pos)
    pt_c = R @ pt_w
    
    if pt_c[2] <= 0:
        return None
    
    u = (pt_c[0] / pt_c[2]) * focal_len_px + cx
    v = (pt_c[1] / pt_c[2]) * focal_len_px + cy
    
    return u, v

def resection_pnp(points_2d, points_3d, img_width, img_height, f_mm, initial_rvec=None, initial_tvec=None):
    """
    Calcula a posição e orientação da câmera a partir de pontos 2D e 3D.
    points_2d: lista de (u, v)
    points_3d: lista de (e, n, z)
    """
    if len(points_2d) < 3: return None
    
    K = get_intrinsic_matrix(f_mm, img_width, img_height)
    dist_coeffs = np.zeros(5) # Assumindo distorção zero por enquanto
    
    pts_2d = np.array(points_2d, dtype=np.float64)
    pts_3d = np.array(points_3d, dtype=np.float64)
    
    use_guess = False
    rvec, tvec = None, None
    
    if initial_rvec is not None and initial_tvec is not None:
        rvec = np.array(initial_rvec, dtype=np.float64).reshape(3, 1)
        tvec = np.array(initial_tvec, dtype=np.float64).reshape(3, 1)
        use_guess = True
        flag = cv2.SOLVEPNP_ITERATIVE
    else:
        # SQPNP é mais robusto para 3+ pontos sem chute inicial
        flag = cv2.SOLVEPNP_SQPNP
    
    try:
        if use_guess:
            success, rvec, tvec = cv2.solvePnP(pts_3d, pts_2d, K, dist_coeffs, 
                                              rvec=rvec, tvec=tvec, 
                                              useExtrinsicGuess=True, 
                                              flags=cv2.SOLVEPNP_ITERATIVE)
        else:
            success, rvec, tvec = cv2.solvePnP(pts_3d, pts_2d, K, dist_coeffs, 
                                              flags=cv2.SOLVEPNP_SQPNP)
    except cv2.error as e:
        print(f"Erro no solvePnP: {e}")
        return None
    
    if not success: return None
    
    # R é a rotação de World para Camera
    R_w2c, _ = cv2.Rodrigues(rvec)
    
    # C = -R^T * t (Posição da câmera no mundo)
    camera_pos = -R_w2c.T @ tvec
    
    return {
        "pos": camera_pos.flatten().tolist(),
        "R_w2c": R_w2c.tolist(),
        "rvec": rvec.flatten().tolist(),
        "tvec": tvec.flatten().tolist()
    }
