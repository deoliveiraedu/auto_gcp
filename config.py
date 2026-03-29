# Configurações Globais do Projeto
import os

# Diretórios Principais
INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
OUTPUT_IMG_DIR = os.path.join(OUTPUT_DIR, 'fotos_conferencia')
PHOTO_DIR = 'input/drone'

# Arquivos de Entrada e Saída (Caminhos Relativos à Raiz)
INPUT_RELATORIO = os.path.join(INPUT_DIR, 'relatorio_levantamento.csv')
PONTOS_QGIS = os.path.join(OUTPUT_DIR, 'pontos_qgis.csv')
GCP_LIST_ODM = os.path.join(OUTPUT_DIR, 'gcp_list.txt')
GCP_LIST_IM = os.path.join(OUTPUT_DIR, 'gcp_list_im.txt')
PONTOS_NAS_FOTOS_TXT = os.path.join(OUTPUT_DIR, 'pontos_nas_fotos.txt')

# Parâmetros Geográficos e de Câmera
UTM_PROJ = "epsg:31980"  # SIRGAS 2000 / UTM zone 
YAW_OFFSET = 0.0          # Ajuste de Declinação/Orientação
RADIUS_METERS = 150.0    # Raio de busca para projetar pontos na foto
MAX_PITCH_OFFSET = 5.0    # Ignorar fotos se Pitch > -85 (5 graus fora do Nadir)

# Offsets de GPS (Correção sistemática da posição do Drone em metros)
GPS_OFFSET_NORTH = 6.0
GPS_OFFSET_EAST = 2.0
GPS_OFFSET_Z = 0.0

# Parâmetros de Filtro de Qualidade (ODM)
MAX_POINTS_PER_PHOTO = 10     # Limite de pontos por imagem no gcp_list_im.txt
MAX_PIXEL_DIST_FROM_CENTER = 1200.0 # Ignorar pontos muito na borda (em pixels)
TOTAL_MAX_POINTS = 500        # Limite máximo de linhas (marcações) no arquivo final

# Parâmetros de Visualização
TOP_N_IMAGES = 1000        # Quantidade de imagens para gerar no output
FONT_SCALE = 1.5         # Tamanho do texto (OpenCV)
FONT_THICKNESS = 3       # Espessura da linha do texto
MARKER_SIZE = 40         # Tamanho do X
MARKER_THICKNESS = 5     # Espessura do X
