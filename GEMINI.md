# Workspace: lev-topog

## Project Description
Ferramenta para refinamento de pontos de controle terrestre (GCP) em fotos de drone. Mantém um "mundo" 3D para propagar correções manuais através de recalculação de posição de câmera (PnP).

## Project Structure
- `main.py`: Orquestrador central e início do servidor.
- `config.py`: Configurações centralizadas (Offsets, caminhos, limites de pontos).
- `calc/`: Lógica de conversão, câmera (Pinhole), projeção (PnP) e o servidor Flask.
- `static/`: Interface frontend (HTML5 Canvas) para refinamento via navegador.
- `input/`: Diretório para o arquivo bruto `relatorio_levantamento.csv`.
- `output/`: Resultados (GCP lists, JSON de estado e fotos de conferência).

## Mandatos de Engenharia
1. **Modelo de Mundo:** O sistema mantém um estado global ("mundo") com as posições 3D dos GCPs e os parâmetros extrínsecos (posição e orientação) de cada câmera.
2. **Integridade de Dados:** As coordenadas (E, N, Z) dos GCPs são sagradas e provêm do levantamento topográfico. Apenas as posições das câmeras e as projeções estimadas (u, v) nas imagens podem ser alteradas.
3. **Refinamento Incremental:** Sempre que uma imagem é "Aceita" (Tecla 'V'), a posição daquela câmera é recalculada via PnP e o deslocamento (bias GPS) é propagado para todas as outras câmeras não-manuais, atualizando suas projeções.
4. **Interface Fluida:** A interface deve priorizar velocidade (atalhos, movimentação rápida de pontos, filtros de imagem).

## Notas de Lançamento (Fixes)
- **Correção PnP:** Corrigido erro do OpenCV quando menos de 4 pontos eram usados. Agora utiliza `SOLVEPNP_SQPNP` e chute inicial (Iterative with guess) para maior estabilidade com 3+ pontos.
- **Propagação de Bias:** Implementada a propagação automática do bias de GPS para imagens não verificadas, agilizando o refinamento de grandes conjuntos de dados.
- **Importação NumPy:** Corrigido local das importações para evitar erros de escopo durante o refinamento.

## Workflow de Uso
1. Coloque o arquivo de levantamento em `input/relatorio_levantamento.csv`.
2. Execute o orquestrador: `.venv/bin/python main.py`
3. O sistema perguntará se deseja **Recalcular (c)** ou **Refinar (r)**.
4. Acesse `http://localhost:5000` no navegador:
   - **Zoom/Pan:** Scroll e Botão do Meio.
   - **Mover:** Arrastar com botão esquerdo ou clicar com o esquerdo (move o mais próximo).
   - **Deletar/Restaurar:** Botão direito.
   - **Adicionar:** Tecla 'A' (posiciona no centro da visão atual).
   - **Aceitar:** Tecla 'V' (recalcula a câmera e atualiza o mundo).
5. Clique em **FINALIZAR (F)** para exportar o `gcp_list_im.txt` final.
