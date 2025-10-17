import cv2
import json
import os
import time
from datetime import datetime, timedelta
import argparse
from ultralytics import YOLO
from ultralytics.solutions import object_counter4
from ultralytics.utils.plotting import Annotator
import torch
import sqlite3
import logging
from shapely.geometry import Polygon, Point
import numpy as np
import threading  # Importar threading
import queue  # Importar queue para comunicar entre as threads
from permanence_tracker import PermanenceTracker
from label_manager import draw_labels


# Configurar o logger para salvar erros em um arquivo
error_log_file = "error_log.txt"
logging.basicConfig(
    filename=error_log_file,
    level=logging.ERROR,
    format="%(asctime)s - ERROR - %(message)s"
)

logging.getLogger("ultralytics").setLevel(logging.WARNING)  # Suprime logs de debug e info da YOLO
# Criar um logger específico para debug de vehicle_code
# Configurar o logger para salvar os logs em um arquivo
log_file = "busca_erro.log"
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("busca_erro")

# 📌 Novo logger para depuração do código do veículo
bug_log_file = "bug_vehicle_code.log"
bug_logger = logging.getLogger("bug_vehicle_code")
bug_handler = logging.FileHandler(bug_log_file)
bug_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
bug_handler.setFormatter(formatter)
bug_logger.addHandler(bug_handler)
bug_logger.setLevel(logging.DEBUG)

# Verificar se a GPU está disponível
if torch.cuda.is_available():
    device = torch.device("cuda")
    #print(f"Using GPU: {torch.cuda.get_device_name(device)}")
else:
    device = torch.device("cpu")
    #print("Using CPU")

# Função para ler o vídeo com tentativa de reconexão
def read_video(video_path, max_retries=35):
    for attempt in range(max_retries):
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            return cap
        else:
            #print(f"Erro ao abrir o vídeo, tentativa {attempt + 1}/{max_retries}")
            time.sleep(2)
    raise Exception(f"Não foi possível abrir o vídeo após {max_retries} tentativas")

# Função para carregar o arquivo de configuração
def load_config(file_path):
    with open(file_path, 'r') as f:
        config = json.load(f)
    return config

def init_db(db_path):
    conn = sqlite3.connect(db_path, timeout=10)  # Adiciona timeout de 10 segundos
    cursor = conn.cursor()
    
    # Criar tabela para contagens de veículos
    cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      area TEXT,
                      vehicle_code INTEGER,
                      count_in INTEGER,
                      count_out INTEGER,
                      timestamp TEXT,
                      tempo_permanencia FLOAT)''')

    # Criar tabela para exportação de log
    cursor.execute('''CREATE TABLE IF NOT EXISTS export_log (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      last_export TEXT)''')
    
    # Garantir colunas na vehicle_counts
    cursor.execute('''PRAGMA table_info(vehicle_counts)''')
    columns_vc = [column[1] for column in cursor.fetchall()]
    if 'tempo_permanencia' not in columns_vc:
        cursor.execute('''ALTER TABLE vehicle_counts ADD COLUMN tempo_permanencia FLOAT''')
    if 'enviado' not in columns_vc:
        cursor.execute('''ALTER TABLE vehicle_counts ADD COLUMN enviado INTEGER DEFAULT 0''')
    
    conn.commit()
    return conn, cursor

# Função utilitária para retry em operações de escrita no banco
import time

def safe_execute(cursor, query, params=(), max_retries=5, delay=0.5):
    for attempt in range(max_retries):
        try:
            cursor.execute(query, params)
            return True
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                time.sleep(delay)
            else:
                raise
    raise sqlite3.OperationalError('database is locked (após múltiplas tentativas)')

def get_average_area_time(cursor, area):
    """
    Retorna o tempo médio de permanência de uma área baseado nos registros recentes.
    Baseado em vehicle_counts (count_out=1 com tempo_permanencia).
    """
    try:
        # Média da área nas últimas 24h
        cursor.execute('''SELECT AVG(tempo_permanencia) FROM vehicle_counts 
                          WHERE area = ? AND count_out = 1
                          AND tempo_permanencia > 1 AND tempo_permanencia < 300 
                          AND datetime(timestamp) >= datetime('now', '-24 hours')''', (area,))
        result = cursor.fetchone()
        if result and result[0] is not None:
            tempo_medio = round(float(result[0]), 2)
            bug_logger.info(f"OK - Tempo medio da {area}: {tempo_medio}s")
            return tempo_medio
        else:
            # fallback: média geral
            cursor.execute('''SELECT AVG(tempo_permanencia) FROM vehicle_counts 
                              WHERE count_out = 1 AND tempo_permanencia > 1 AND tempo_permanencia < 300 
                              AND datetime(timestamp) >= datetime('now', '-24 hours')''')
            fallback = cursor.fetchone()
            if fallback and fallback[0] is not None:
                tempo_geral = round(float(fallback[0]), 2)
                bug_logger.info(f"AVISO - Usando tempo medio geral: {tempo_geral}s")
                return tempo_geral
            else:
                bug_logger.warning(f"AVISO - Sem dados recentes, usando 15s para {area}")
                return 15.0
    except Exception as e:
        bug_logger.error(f"Erro ao buscar tempo medio (vehicle_counts): {e}")
        return 15.0

def get_latest_permanence_time(cursor, area, vehicle_code, current_time):
    """
    Busca o tempo de permanência mais recente para um veículo específico na área.
    Retorna o tempo encontrado ou valor padrão se não houver registro recente.
    """
    try:
        # Buscar na tabela vehicle_counts o registro de saída mais recente
        # Considera registros dos últimos 60s com tempo_permanencia
        cursor.execute('''SELECT tempo_permanencia FROM vehicle_counts 
                          WHERE area = ? AND vehicle_code = ? 
                          AND count_out = 1
                          AND tempo_permanencia IS NOT NULL
                          AND datetime(timestamp) >= datetime(?, '-60 seconds')
                          ORDER BY id DESC LIMIT 1''', (area, vehicle_code, current_time))
        
        result = cursor.fetchone()
        if result and result[0] is not None:
            tempo = float(result[0])
            bug_logger.info(f"OK - Tempo encontrado na tabela permanence: {tempo}s para codigo {vehicle_code} na {area}")
            return tempo
        else:
            # Se não encontrou, tenta média recente da área na vehicle_counts
            cursor.execute('''SELECT AVG(tempo_permanencia) FROM vehicle_counts 
                              WHERE area = ? AND tempo_permanencia > 1
                              AND datetime(timestamp) >= datetime(?, '-300 seconds')''', (area, current_time))
            
            fallback = cursor.fetchone()
            if fallback and fallback[0] is not None:
                tempo = float(fallback[0])
                bug_logger.info(f"AVISO - Usando tempo medio como fallback: {tempo}s para {area}")
                return tempo
            else:
                bug_logger.warning(f"ERRO - Nenhum tempo de permanencia encontrado para codigo {vehicle_code} na {area}")
                return 5.0  # Valor padrão de 5 segundos se não encontrar nada
                
    except Exception as e:
        bug_logger.error(f"Erro ao buscar tempo de permanência (vehicle_counts): {e}")
        return 5.0  # Valor padrão em caso de erro

def update_null_permanence_records(cursor, conn):
    """Função desativada: vehicle_permanence descontinuada. Não realiza backfill."""
    bug_logger.info("update_null_permanence_records desativada (vehicle_permanence descontinuada)")
    return 0

# Função para verificar se os valores de entrada/saída mudaram em relação ao último salvo
def has_count_changed(area, vehicle_code, count_in, count_out, cursor):
    query = '''SELECT count_in, count_out FROM vehicle_counts 
               WHERE area = ? AND vehicle_code = ? ORDER BY id DESC LIMIT 1'''
    cursor.execute(query, (area, vehicle_code))
    last_record = cursor.fetchone()

    if last_record:
        last_count_in, last_count_out = last_record
        
        # Verifica se houve um evento de entrada ou saída (detecção de mudança)
        if count_in > last_count_in or count_out > last_count_out:
            return True  # Houve um evento, deve salvar
    else:
        # Se não houver nenhum registro anterior, devemos salvar o primeiro evento
        return True  # Considera como evento inicial
    
    return False  # Nenhuma mudança

# Função para salvar contagens no banco de dados com tempo de permanência
def save_counts_to_db(area_counts, cursor, conn, previous_counts, config, im0, tracker):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    area_to_faixa = {
        'area_1': 'faixa1',
        'area_2': 'faixa2'
    }

    for area, counts in area_counts.items():
        faixa = area_to_faixa.get(area)
        if not faixa:
            logger.warning(f'Faixa nao encontrada para a area {area}')
            continue

        for vehicle_type, type_counts in counts['types'].items():
            faixa_config = config['cameras']['camera1']['faixas'].get(faixa, {})
            vehicle_code = faixa_config.get(vehicle_type)
            if not vehicle_code and vehicle_type.endswith('s'):
                vehicle_code = faixa_config.get(vehicle_type[:-1])
            if not vehicle_code:
                logger.warning(f'Codigo de veiculo nao encontrado para {vehicle_type} na faixa {faixa}')
                continue

            count_in = type_counts['in']
            count_out = type_counts['out']

            state = previous_counts.setdefault(area, {}).setdefault(vehicle_code, {'in': 0, 'out': 0})
            prev_in = state.get('in', 0)
            prev_out = state.get('out', 0)

            if count_in < prev_in:
                bug_logger.info(f'RESET de entrada detectado (area {area}, codigo {vehicle_code}): {prev_in} -> {count_in}')
                prev_in = count_in
                state['in'] = count_in
            if count_out < prev_out:
                bug_logger.info(f'RESET de saida detectado (area {area}, codigo {vehicle_code}): {prev_out} -> {count_out}')
                prev_out = count_out
                state['out'] = count_out

            if count_in > prev_in:
                delta_in = count_in - prev_in
                authorize_vehicle('CROSSING_EVENT', area, vehicle_code, (0, 0), datetime.now())

                try:
                    insert_entry = (
                        """INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
                               VALUES (?, ?, 1, 0, ?, NULL, 0)"""
                    )
                    for _ in range(delta_in):
                        ts_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        safe_execute(cursor, insert_entry, (area, vehicle_code, ts_now))
                    conn.commit()
                    bug_logger.info(f'ENTRADA(S) SALVA(S) -> Area: {area}, Codigo: {vehicle_code}, Qtde: {delta_in}')
                except Exception as e:
                    logger.error(f'Falha ao salvar ENTRADA em vehicle_counts (Area: {area}, Codigo: {vehicle_code}): {e}')

                state['in'] = count_in
                bug_logger.info(f'ENTRADA AUTORIZADA -> Area: {area}, Codigo: {vehicle_code}')
            else:
                state['in'] = count_in

            if count_out > prev_out:
                delta_out = count_out - prev_out

                try:
                    insert_exit = (
                        """INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
                               VALUES (?, ?, 0, 1, ?, NULL, 0)"""
                    )
                    for _ in range(delta_out):
                        ts_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        safe_execute(cursor, insert_exit, (area, vehicle_code, ts_now))
                    conn.commit()
                    bug_logger.info(f'SAIDA(S) SALVA(S) -> Area: {area}, Codigo: {vehicle_code}, Qtde: {delta_out}')
                except Exception as e:
                    logger.error(f'Falha ao salvar SAIDA em vehicle_counts (Area: {area}, Codigo: {vehicle_code}): {e}')

                state['out'] = count_out
            else:
                state['out'] = count_out

# FUNÇÃO DESATIVADA - Agora apenas o permanence_tracker salva na vehicle_counts
# Isso garante regra 1:1 sem duplicações
def save_permanence_to_vehicle_counts(cursor, conn, area, vehicle_code, timestamp, tempo_permanencia):
    """
    FUNÇÃO DESATIVADA - Para evitar duplicações na tabela vehicle_counts.
    Apenas o permanence_tracker.py salva nesta tabela agora.
    """
    bug_logger.info(f"FUNCAO DESATIVADA - permanence_tracker vai salvar: Area {area}, Codigo {vehicle_code}, Tempo {tempo_permanencia}s")
    return True

def start_new_video_writer(output_width, output_height, effective_fps):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_filename = f"{client_code}_{timestamp}.avi"
    video_filepath = os.path.join(output_directory, video_filename)
    video_writer = cv2.VideoWriter(video_filepath, cv2.VideoWriter_fourcc(*'mp4v'), effective_fps, (output_width, output_height))
    return video_writer, video_filepath

# Função para verificar mudanças nas contagens
def counts_changed(current_counts, last_counts):
    if last_counts is None:
        return True
    for area, counts in current_counts.items():
        for vehicle_type, type_counts in counts['types'].items():
            last_type_counts = last_counts.get(area, {}).get('types', {}).get(vehicle_type, None)
            if not last_type_counts or type_counts != last_type_counts:
                return True
    return False

# Configurar argumentos de linha de comando
parser = argparse.ArgumentParser(description='Processamento de vídeo com YOLO e contagem de objetos.')
parser.add_argument('--video_path', type=str, required=True, help='Caminho para o vídeo ou link do streaming.')
parser.add_argument('--config_path', type=str, required=True, help='Caminho para o arquivo de configuração JSON.')
parser.add_argument('--area_config_path', type=str, required=True, help='Caminho para o arquivo JSON com as áreas de contagem.')
parser.add_argument('--output_dir', type=str, required=True, help='Diretório de saída para os arquivos de contagem.')
parser.add_argument('--save_video', type=lambda x: (str(x).lower() == 'true'), default=False, help='Define se o vídeo gerado deve ser salvo (True ou False).')
parser.add_argument('--video_interval', type=int, default=60, help='Intervalo de tempo para salvar novos vídeos (em minutos).')
parser.add_argument('--model_path', type=str, required=True, help='Caminho para o modelo YOLO (.pt).')
parser.add_argument('--output_width', type=int, default=320, help='Largura do vídeo de saída.')
parser.add_argument('--output_height', type=int, default=240, help='Altura do vídeo de saída.')
parser.add_argument('--db_path', type=str, required=True, help='Caminho para o arquivo SQLite (.db).')  # Adicionar o argumento para o banco de dados
parser.add_argument('--permanencia_config_path', type=str, required=True, help='Caminho para o arquivo JSON com as áreas para o tempo de permanência.')
args = parser.parse_args()

# Inicializar o modelo YOLO
model = YOLO(args.model_path)

# Inicializar a captura de vídeo
cap = read_video(args.video_path)

# Definir largura, altura e FPS do vídeo
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
if fps == 0 or fps is None:
    fps = 25  # ou qualquer valor padrão apropriado para sua câmera
fps = int(fps)

# Definir intervalo de pulo de frames e FPS efetivo
frame_skip_interval = 2  # Processar 1 a cada 2 frames
effective_fps = fps / frame_skip_interval

# Definir o intervalo em segundos e calcular frames por vídeo
video_interval_in_seconds = args.video_interval * 60  # Converter minutos para segundos
frames_per_video = int(effective_fps * video_interval_in_seconds)

# Carregar configurações
config = load_config(args.config_path)

client_code = config['codigocliente']

# Obter o mapeamento de faixas e códigos de veículos
faixa_1_veiculos = config['cameras']['camera1']['faixas']['faixa1']
faixa_2_veiculos = config['cameras']['camera1']['faixas']['faixa2']

# Definir o mapeamento de área para faixa
area_to_faixa = {
    'area_1': 'faixa1',
    'area_2': 'faixa2'
}

# Carregar áreas de contagem do arquivo JSON
area_config = load_config(args.area_config_path)
region_points = area_config['area_1']
second_region_points = area_config.get('area_2', None)

# Carregar configurações de permanência do arquivo JSON
permanencia_config = load_config(args.permanencia_config_path)
permanencia_areas = permanencia_config

classes_to_count = [0,1,2,3,4]
# classe 0 = onibus
#classe 1 = carro
#classe 2 = moto
# Classe 3 = caminhão
# classe 4 = vuc 

# Inicializar contador de objetos
counter = object_counter4.ObjectCounter4(config)
counter.set_args(view_img=True,
                 reg_pts=region_points,
                 classes_names=model.names,
                 draw_tracks=True)  

# Criar o diretório de saída, se não existir
output_directory = args.output_dir
if not os.path.exists(output_directory):
    os.makedirs(output_directory)
    # Dicionário para armazenar veículos que cruzaram a linha de contagem
vehicles_crossed_line = {}  # Formato: {track_id: {"vehicle_code": vehicle_code, "class_name": class_name, "area"}}

# Inicializa o banco de dados
# Inicializa o banco de dados com o caminho fornecido
conn, cursor = init_db(args.db_path)
# CORREÇÃO 1.2: Usar WAL (Write-Ahead Logging) ao invés de DELETE para melhor performance e menos locks
cursor.execute('PRAGMA journal_mode=WAL;')
logger.info(f"Banco de dados inicializado em {args.db_path} com WAL ativado.")

# Variável para armazenar as últimas contagens
previous_counts = {}

# SISTEMA DE AUTORIZAÇÃO - Apenas veículos que cruzaram linha podem ter tempo de permanência
authorized_vehicles = {
    'vehicle_ids': set(),  # IDs autorizados
    'recent_crossings': [],  # Lista: [(timestamp, area, vehicle_code, last_position)]
    'lost_vehicles': {}  # Veículos perdidos: {area: [(timestamp, vehicle_code, last_position)]}
}

tracker = PermanenceTracker(cursor, conn, config['codigocliente'], permanencia_config)

# Dicionário para persistência de rótulos dos veículos
label_persistence = {}

# Função principal
def desenhar_areas(im0, permanencia_areas):
    for area_name, area_info in permanencia_areas.items():
        area_coords = np.array(area_info['coordenadas'], np.int32)
        area_coords = area_coords.reshape((-1, 1, 2))
        overlay = im0.copy()
        cv2.polylines(overlay, [area_coords], isClosed=True, color=(0, 255, 0), thickness=2)
        cv2.addWeighted(overlay, 0.4, im0, 0.6, 0, im0)  # Ajusta transparência

# Função principal
frame_count = 0

# Fila para frames que serão gravados
# CORREÇÃO 1.1: Queue com limite de 100 frames (~8s de buffer) para evitar pulos nos vídeos
frame_queue = queue.Queue(maxsize=100)

# Função para a thread de gravação de vídeo
def video_writer_thread(frame_queue):
    current_video_writer = None
    while True:
        item = frame_queue.get()
        if item is None:
            break
        elif isinstance(item, tuple) and item[0] == 'change_writer':
            # Fecha o video_writer atual, se houver
            if current_video_writer is not None:
                current_video_writer.release()
            # Atualiza para o novo video_writer
            current_video_writer = item[1]
        else:
            frame = item
            if current_video_writer is not None:
                current_video_writer.write(frame)
    # Libera o último video_writer
    if current_video_writer is not None:
        current_video_writer.release()

# Inicializa o primeiro gravador de vídeo e inicializa o contador de frames escritos
if args.save_video:
    video_writer, current_video_filepath = start_new_video_writer(args.output_width, args.output_height, effective_fps)
    # Definir o intervalo em segundos e calcular frames por vídeo
    video_interval_in_seconds = args.video_interval * 60  # Converter minutos para segundos
    frames_per_video = int(effective_fps * video_interval_in_seconds)
    frames_written = 0  # Inicializar o contador de frames escritos

    # Inicia a thread de gravação
    video_thread = threading.Thread(target=video_writer_thread, args=(frame_queue,))
    video_thread.start()

    # Envia o video_writer inicial para a thread
    frame_queue.put(('change_writer', video_writer))

# SISTEMA DE AUTORIZAÇÃO - Funções de gerenciamento
def authorize_vehicle(track_id, area, vehicle_code, position, timestamp):
    """
    Autoriza um veículo que cruzou a linha de contagem.
    """
    authorized_vehicles['vehicle_ids'].add(track_id)
    authorized_vehicles['recent_crossings'].append((timestamp, area, vehicle_code, position))
    
    # Limpar crossings antigos (mais de 5 minutos)
    current_time = datetime.now()
    authorized_vehicles['recent_crossings'] = [
        crossing for crossing in authorized_vehicles['recent_crossings'] 
        if (current_time - crossing[0]).total_seconds() < 300
    ]
    
    bug_logger.info(f"AUTORIZADO -> Track {track_id} cruzou linha na {area} (codigo {vehicle_code})")

def check_vehicle_authorization(track_id, area, position, timestamp):
    """
    Verifica se um veículo está autorizado a ter tempo de permanência.
    Retorna: (autorizado: bool, vehicle_code: int)
    """
    # 1. AUTORIZAÇÃO PRIMÁRIA: ID já está na lista
    if track_id in authorized_vehicles['vehicle_ids']:
        return True, None  # vehicle_code será obtido depois
    
    # 2. FALLBACK POR PROXIMIDADE: Novo ID próximo de onde outro desapareceu
    for lost_timestamp, lost_area, lost_vehicle_code, lost_position in authorized_vehicles.get('lost_vehicles', {}).get(area, []):
        if (timestamp - lost_timestamp).total_seconds() < 30:  # Máximo 30s de diferença
            distance = ((position[0] - lost_position[0])**2 + (position[1] - lost_position[1])**2)**0.5
            if distance < 100:  # Máximo 100 pixels de distância
                # Transferir autorização
                authorized_vehicles['vehicle_ids'].add(track_id)
                bug_logger.info(f"AUTORIZADO POR PROXIMIDADE -> Track {track_id} (similar ao perdido na {area})")
                return True, lost_vehicle_code
    
    # 3. FALLBACK TEMPORAL: Crossing recente na área
    current_time = datetime.now()
    for crossing_timestamp, crossing_area, vehicle_code, crossing_position in authorized_vehicles['recent_crossings']:
        if crossing_area == area and (current_time - crossing_timestamp).total_seconds() < 60:  # 60s de janela
            authorized_vehicles['vehicle_ids'].add(track_id)
            bug_logger.info(f"AUTORIZADO TEMPORAL -> Track {track_id} na {area} (crossing recente)")
            return True, vehicle_code
    
    # 4. NÃO AUTORIZADO
    bug_logger.warning(f"NAO AUTORIZADO -> Track {track_id} na {area} (nao cruzou linha)")
    return False, None

def handle_lost_vehicle(track_id, area, vehicle_code, position, timestamp):
    """
    Registra um veículo autorizado que foi perdido (para matching posterior).
    """
    if area not in authorized_vehicles['lost_vehicles']:
        authorized_vehicles['lost_vehicles'][area] = []
    
    authorized_vehicles['lost_vehicles'][area].append((timestamp, area, vehicle_code, position))
    
    # Limitar histórico a 10 veículos perdidos por área
    authorized_vehicles['lost_vehicles'][area] = authorized_vehicles['lost_vehicles'][area][-10:]
    
    bug_logger.info(f"VEICULO PERDIDO -> Track {track_id} na {area} (registrado para matching)")

def get_vehicle_code(area_detectada, class_name, config):
    """
    Retorna o código do veículo baseado na área detectada e na classe.
    """
    faixa_map = {"area_1": "faixa1", "area_2": "faixa2"}
    faixa_detectada = faixa_map.get(area_detectada, None)
    
    if faixa_detectada:
        vehicle_code = config["cameras"]["camera1"]["faixas"].get(faixa_detectada, {}).get(class_name, None)
        if vehicle_code is not None:
            return vehicle_code

    print(f"Código do veículo não encontrado para '{class_name}' na área '{area_detectada}' (faixa: {faixa_detectada}). Usando -1.")
    return -1  # Retorna -1 caso não seja encontrado



while True:
    success, im0 = cap.read()
    if not success:
        logger.warning("Falha ao capturar o quadro, tentando reconectar...")
        cap.release()
        cap = read_video(args.video_path)
        continue

    raw_frame_for_video = im0.copy() if args.save_video else None

    frame_count += 1
    if frame_count % frame_skip_interval != 0:
        if args.save_video:
            resized_frame = cv2.resize(raw_frame_for_video, (args.output_width, args.output_height))
            frame_queue.put(resized_frame)
            frames_written += 1
            if frames_written >= frames_per_video:
                video_writer, current_video_filepath = start_new_video_writer(args.output_width, args.output_height, effective_fps)
                frame_queue.put(('change_writer', video_writer))
                frames_written = 0
        continue

    current_timestamp = datetime.now()

    # Realizar inferência com YOLOv8 e rastreamento
    results = model.track(im0, persist=True, stream=True, show=False, classes=classes_to_count, conf=0.60, imgsz=1024)
    tracks = list(results)  # Converter o gerador para lista

    # Criar um único Annotator para desenhar rótulos personalizados
    annotator = Annotator(im0, line_width=2, example=str(model.names))

    # Desenhar as áreas de permanência
    desenhar_areas(im0, permanencia_areas)

    # Desenhar as linhas de contagem para área 1 e área 2
    im0 = counter.start_counting(im0, tracks, region_points, 'area_1', fps=fps)
    if second_region_points:
        im0 = counter.start_counting(im0, tracks, second_region_points, 'area_2', fps=fps)

    # Atualizar os tempos de permanência no tracker
    tracker.calculate_permanence(tracks, current_timestamp)

    # Processar cada track e adicionar rótulos personalizados com tempo de permanência
    for track in tracks:
        if hasattr(track, 'boxes') and track.boxes is not None:
            if track.boxes.id is not None and track.boxes.xyxy is not None and track.boxes.cls is not None:
                for box, track_id_tensor, class_id_tensor in zip(
                    track.boxes.xyxy.cpu(), track.boxes.id.cpu(), track.boxes.cls.cpu()
                ):
                    x1, y1, x2, y2 = map(int, box.tolist())
                    track_id = int(track_id_tensor.item())
                    class_id = int(class_id_tensor.item())
                    class_name = model.names[class_id]  # Nome da classe detectada (motorcycle, cars, etc.)

                    vehicle_code = None   # Inicializa como None antes da busca

                    # Descobrir em qual área/faixa o veículo está
                    area_detectada = None
                    for area_name, area_info in permanencia_areas.items():
                        polygon_area = Polygon(area_info['coordenadas'])
                        centro_x = float((box[0] + box[2]) / 2)
                        centro_y = float((box[1] + box[3]) / 2)
                        centro = Point(centro_x, centro_y)

                        if polygon_area.contains(centro):
                            area_detectada = area_name
                            break  # Assim que encontrar a área, podemos sair do loop

                    # 🔹 VERIFICAÇÃO: Se `area_detectada` for None, pula para o próximo track
                    if area_detectada is None:
                        logger.warning(f"Track ID {track_id} não está dentro de nenhuma área válida. Pulando para o próximo veículo.")
                        continue  # Ignora esse veículo e passa para o próximo
                    
                    # CORREÇÃO 2.1: Relaxar autorização (conservadora) - permite tempo de permanência mesmo sem crossing
                    # Mantém o sistema de autorização para tracking, mas não descarta veículos não autorizados
                    # Isso resolve o problema de contagens baixas causadas por veículos descartados
                    center_position = (centro_x, centro_y)
                    is_authorized, fallback_vehicle_code = check_vehicle_authorization(track_id, area_detectada, center_position, current_timestamp)

                    if not is_authorized:
                        # MUDANÇA: Ao invés de descartar, apenas loga e continua processando
                        logger.info(f"Track ID {track_id} na {area_detectada} sem autorização formal - mas permitindo tempo de permanência")
                        # NÃO descarta mais: permite que o veículo seja rastreado para permanência

                    # Se a área ainda não foi inicializada no tracker, criamos ela
                    if area_detectada not in tracker.permanence_data:
                        tracker.permanence_data[area_detectada] = {
                            "timestamps": {}, "last_seen": {}, "processed": set(), "vehicle_codes": {}
                        }
                        print(f"🟢 Criando estrutura de dados para a área {area_detectada}")


                    # 🔹 ADICIONANDO VERIFICAÇÃO: Se `vehicle_codes` ainda não existe, criamos o dicionário
                    if "vehicle_codes" not in tracker.permanence_data[area_detectada]:
                        tracker.permanence_data[area_detectada]["vehicle_codes"] = {}

                    # Se o veículo ainda não tiver um código armazenado, buscamos um novo
                    if track_id not in tracker.permanence_data[area_detectada]["vehicle_codes"]:
                        faixa_map = {"area_1": "faixa1", "area_2": "faixa2"}
                        faixa_detectada = faixa_map.get(area_detectada)

                        if faixa_detectada:
                            vehicle_code = config["cameras"]["camera1"]["faixas"].get(faixa_detectada, {}).get(class_name, None)

                        if vehicle_code is None:
                            logger.warning(f"Não foi possível mapear vehicle_code para {class_name} na {area_detectada} (faixa: {faixa_detectada})")
                            vehicle_code = -1  # Código de fallback para veículos sem correspondência

                        tracker.permanence_data[area_detectada]['vehicle_codes'][track_id] = vehicle_code
                        logger.info(f"Veículo {track_id} identificado como {class_name} na {area_detectada} com código {vehicle_code}.")

                    # Obter tempos de permanência
                    tempos_permanencia = tracker.get_permanence_time(track_id)

                    # Se não encontrou tempo de permanência, loga e continua para o próximo track_id
                    if not tempos_permanencia:
                        logger.warning(f"Track ID {track_id} não encontrado em nenhuma área.")
                        continue

                    # Construir o rótulo personalizado
                    label = f"{class_name} ID:{track_id}"

                    for area, tempo in tempos_permanencia.items():
                        label += f" {area}: {tempo:.1f}s"


                    # 🚗 Salvar tempo de permanência quando o veículo sair
                    if tracker.has_vehicle_left(track_id, area_detectada):
                        vehicle_code = get_vehicle_code(area_detectada, class_name, config)

                        bug_logger.info(f"VEICULO SAIU -> Cliente: {client_code}, Area: {area_detectada}, Veiculo: {track_id}, Codigo: {vehicle_code}, Tempo: {tempo:.2f}s")

                        # A gravação na tabela vehicle_counts é feita pelo PermanenceTracker
                        # Nenhum insert manual aqui (vehicle_permanence descontinuada)
                            

                    # Desenhar o rótulo e a bounding box no frame
                    annotator.box_label((x1, y1, x2, y2), label)

    # Atualizar o frame com o Annotator
    im0 = annotator.result()

    # Exibe contagens no terminal
    for area, counts in counter.area_counts.items():
        for vehicle_type, type_counts in counts['types'].items():
            logger.info(f"Entrada: {type_counts['in']}, Saída: {type_counts['out']}")

    # Salvamento em tempo real apenas se os valores mudarem
    try:
        save_counts_to_db(counter.area_counts, cursor, conn, previous_counts, config, im0, tracker)
        
        # A cada 100 frames, tenta atualizar registros NULL com dados da vehicle_permanence
        if frame_count % 100 == 0:
            update_null_permanence_records(cursor, conn)
            
    except Exception as e:
        logger.error(f"Erro ao salvar no banco de dados: {e}")

    # Gravação de frames na thread
    if args.save_video:
        resized_im0 = cv2.resize(im0, (args.output_width, args.output_height))
        try:
            # CORREÇÃO 1.1b: put_nowait evita travamento se a fila estiver cheia
            frame_queue.put_nowait(resized_im0)
            frames_written += 1
        except queue.Full:
            # Se a fila estiver cheia, descarta o frame atual (melhor que travar)
            logger.warning("Fila de gravação de vídeo cheia - frame descartado para evitar travamento")

        if frames_written >= frames_per_video:
            video_writer, current_video_filepath = start_new_video_writer(args.output_width, args.output_height, effective_fps)
            frame_queue.put(('change_writer', video_writer))
            frames_written = 0

    # Mostrar frame
    cv2.imshow('YOLOv8 Object Counter', im0)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
if args.save_video:
    frame_queue.put(None)
    video_thread.join()

cv2.destroyAllWindows()
tracker.close()
conn.close()






