import math
import numpy as np

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
    yaw: 0=Norte, 90=Leste
    pitch: 0=Horizonte, -90=Olhando pra baixo (Nadir)
    roll: 0=Nivelado
    declination: Offset para corrigir Yaw (Declinação Magnética ou convergência de grade)
    """
    # Adicionando correção de declinação (se houver erro sistemático no Yaw)
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
    """
    Converte distância focal de MM para PIXELS usando a largura real do sensor.
    f_mm: Distância focal real (não a equivalente de 35mm)
    """
    # f_px = (f_mm * img_width_px) / sensor_width_mm
    return (f_mm * img_width_px) / SENSOR_WIDTH_MM

def project_point(gcp, drone_pos, R, focal_len_px, cx, cy):
    pt_w = np.array(gcp) - np.array(drone_pos)
    pt_c = R @ pt_w
    
    if pt_c[2] <= 0:
        return None
    
    u = (pt_c[0] / pt_c[2]) * focal_len_px + cx
    v = (pt_c[1] / pt_c[2]) * focal_len_px + cy
    
    return u, v
