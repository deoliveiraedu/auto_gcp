import os
import shutil
import config
from calc import converter, find_points_in_photos, visualize_points

def clear_output_dir(directory):
    if os.path.exists(directory):
        print(f"Limpando pasta de saída: {directory}...")
        for filename in os.listdir(directory):
            if filename == 'refine_state.json': continue
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path): os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception: pass
    else: os.makedirs(directory)

def run_main():
    print("=== ORQUESTRADOR DE LEVANTAMENTO TOPOGRÁFICO ===")
    
    if not os.path.exists(config.INPUT_DIR):
        os.makedirs(config.INPUT_DIR)
        print(f"Aviso: Pasta '{config.INPUT_DIR}' criada.")
        return

    recalc = "s"
    state_exists = os.path.exists(os.path.join(config.OUTPUT_DIR, 'refine_state.json'))
    gcp_exists = os.path.exists(config.GCP_LIST_IM)
    
    if state_exists or gcp_exists:
        ans = input("Deseja recalcular todos os pontos ou apenas refinar os existentes? (r=refinar/c=recalcular): ").lower()
        if ans == 'r': recalc = "n"

    if recalc == "s":
        clear_output_dir(config.OUTPUT_DIR)
        print("\n[1/3] Convertendo relatório CSV...")
        converter.process_survey(config.INPUT_RELATORIO, config.PONTOS_QGIS, config.GCP_LIST_ODM)
        print("\n[2/3] Calculando projeção de pontos nas fotos...")
        find_points_in_photos.main()
        print("\n[3/3] Gerando visualizações técnicas...")
        visualize_points.main()
        state_path = os.path.join(config.OUTPUT_DIR, 'refine_state.json')
        if os.path.exists(state_path): os.unlink(state_path)
    
    print("\n[4] Iniciando Servidor de Refinamento Web...")
    from calc import server
    server.run_server()

if __name__ == "__main__":
    run_main()
