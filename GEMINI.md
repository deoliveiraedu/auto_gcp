# Workspace: lev-topog

## Project Description
Ferramenta para processamento de dados de levantamento topográfico (RTK/GNSS). Converte relatórios LandStar em formatos QGIS e OpenDroneMap (ODM), projeta pontos de controle em fotos de drone e oferece uma interface web para refinamento manual de GCPs.

## Project Structure
- `main.py`: Orquestrador central. Gerencia o workflow e inicia o servidor de refinamento.
- `config.py`: Configurações centralizadas (Offsets, caminhos, limites de pontos).
- `calc/`: Pacote com lógica de conversão, câmera (Pinhole), projeção e o servidor Flask.
- `static/`: Interface frontend (HTML5 Canvas) para refinamento via navegador.
- `input/`: Diretório para o arquivo bruto `relatorio_levantamento.csv`.
- `output/`: Resultados (GCP lists, JSON de estado e fotos de conferência).
- `26-02-19/`: Diretório de imagens brutas do drone.

## Workflow de Uso
1. Coloque o arquivo de levantamento em `input/relatorio_levantamento.csv`.
2. Execute o orquestrador: `.venv/bin/python main.py`
3. O sistema perguntará se deseja **Recalcular (c)** (limpa output e reprojeta) ou **Refinar (r)** (mantém progresso).
4. Acesse `http://localhost:5000` no navegador para refinar os pontos:
   - **Zoom/Pan:** Scroll e Botão do Meio.
   - **Mover:** Arrastar com botão esquerdo.
   - **Deletar/Restaurar:** Botão direito (ponto fica translúcido).
   - **Adicionar:** Botão "Add Ponto" ou tecla 'A'.
   - **Aceitar:** Botão "Aceitar Atual" ou tecla 'V'.
5. Clique em **FINALIZAR (F)** para exportar o `gcp_list_im.txt` final.

## Technical Specifications
- **Datum:** SIRGAS 2000 / UTM zone 22S (EPSG:31982).
- **Ambiente:** Otimizado para WSL/Linux (OpenCV-Headless).
- **Interface:** Web-based (Flask + HTML5 Canvas), permite acesso via rede local.

## Gemini CLI Mandates
- **Persistência:** O arquivo `output/refine_state.json` contém todo o progresso manual e NÃO é apagado automaticamente ao escolher "Refinar".
- **Imagens:** O servidor busca imagens recursivamente em `config.PHOTO_DIR`.
- **OpenCV:** Use apenas a versão `headless` para evitar erros de biblioteca gráfica em ambientes de servidor/WSL.
