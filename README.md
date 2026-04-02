# Ferramenta de Refinamento de GCP (Levantamento Topográfico)

Esta ferramenta automatiza a projeção de pontos de controle terrestre (GCP) em fotos de drone e permite o refinamento manual através de uma interface web, utilizando um modelo de mundo 3D para propagar correções e recalcular posições de câmera (PnP).

## 🚀 Requisitos e Instalação

### Pré-requisitos
- **Python 3.8+**
- (Opcional) Ambiente virtual (`venv`)

### Instalação
1. Clone o repositório ou baixe os arquivos.
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # ou
   .venv\Scripts\activate     # Windows
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## 📂 Estrutura de Dados (Inputs e Outputs)

### Inputs
- **`input/relatorio_levantamento.csv`**: Arquivo bruto do levantamento topográfico (RTK). Deve conter linhas iniciadas por `GP` com as coordenadas Norte, Este e Elevação.
- **`input/drone/`**: Pasta contendo as fotos originais do drone (JPG/JPEG) com metadados EXIF (GPS e Gimbal).

### Outputs (Pasta `output/`)
- **`gcp_list.txt`**: Lista de GCPs no formato X Y Z ID (padrão OpenDroneMap).
- **`gcp_list_im.txt`**: Arquivo final com as projeções (X Y Z U V imagem ID) para processamento fotogramétrico.
- **`pontos_qgis.csv`**: Versão limpa dos pontos para conferência no QGIS.
- **`pontos_nas_fotos.txt`**: Relatório legível de quais pontos foram encontrados em quais fotos.
- **`fotos_conferencia/`**: Imagens com marcações (X) sobrepostas para validação visual.
- **`refine_state.json`**: Estado atual do refinamento web.
- **`world.json`**: Parâmetros extrínsecos (posição e orientação) calculados para cada câmera.

## 🛠️ Como Usar

1. **Preparação**: Coloque o relatório CSV em `input/` e as fotos em `input/drone/`.
2. **Execução**:
   ```bash
   python main.py
   ```
3. **Orquestração**:
   - O programa perguntará se deseja **Recalcular (c)** ou **Refinar (r)**.
   - Use **c** na primeira vez para processar o CSV e gerar as projeções iniciais.
   - Use **r** se já tiver iniciado um refinamento e quiser continuar de onde parou.
4. **Refinamento Web**:
   - Acesse `http://localhost:5000` no seu navegador.
   - **Navegação**: Use o scroll para zoom e arraste com o botão do meio para mover o mapa.
   - **Ajuste**: Arraste os pontos com o botão esquerdo para a posição correta na foto.
   - **Atalhos**:
     - `V`: Aceita a imagem, recalcula a câmera e propaga a correção para as demais fotos.
     - `A`: Adiciona um ponto novo no centro da visão.
     - `F`: Finaliza e exporta o arquivo `gcp_list_im.txt`.
     - `Seta Direita/Esquerda`: Navega entre as imagens.

## ⚙️ Configurações
As configurações de projeção (EPSG), offsets de GPS e limites de pontos podem ser ajustadas diretamente no arquivo `config.py`.
