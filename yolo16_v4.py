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
from collections import deque
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
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Criar tabela para contagens de veículos
    cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      area TEXT,
                      vehicle_code INTEGER,
                      count_in INTEGER,
                      count_out INTEGER,
                      timestamp TEXT)''')

    # Criar tabela para exportação de log
    cursor.execute('''CREATE TABLE IF NOT EXISTS export_log (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      last_export TEXT)''')
    
    # Criar tabela para tempos de permanência dos veículos
    cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      codigocliente INTEGER,
                      vehicle_code INTEGER,
                      timestamp TEXT,
                      tempo_permanencia FLOAT)''')
    
    # **Adicionar coluna 'codigocliente' se não existir**
    cursor.execute('''PRAGMA table_info(vehicle_permanence)''')
    columns = [column[1] for column in cursor.fetchall()]
    if 'codigocliente' not in columns:
        cursor.execute('''ALTER TABLE vehicle_permanence ADD COLUMN codigocliente INTEGER''')
    
    conn.commit()
    return conn, cursor

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

# Função para salvar contagens no banco de dados
def save_counts_to_db(area_counts, cursor, conn, previous_counts, config, im0):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Mapeamento da área para as faixas
    area_to_faixa = {
        'area_1': 'faixa1',
        'area_2': 'faixa2'
    }

    for area, counts in area_counts.items():
        faixa = area_to_faixa.get(area)
        if not faixa:
            logger.warning(f"Faixa não encontrada para a área {area}")
            continue

        for vehicle_type, type_counts in counts['types'].items():
            vehicle_code = config['cameras']['camera1']['faixas'].get(faixa, {}).get(vehicle_type)
            if not vehicle_code:
                logger.warning(f"Código do veículo não encontrado para {vehicle_type} na faixa {faixa}")
                continue

            count_in = type_counts['in']
            count_out = type_counts['out']

            if previous_counts.get(area, {}).get(vehicle_code, {}).get('in', 0) < count_in:
                for _ in range(count_in - previous_counts.get(area, {}).get(vehicle_code, {}).get('in', 0)):
                    cursor.execute('''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
                                      VALUES (?, ?, 1, 0, ?)''', 
                                      (area, vehicle_code, current_time))
                    conn.commit()
                    logger.info(f"Contagem salva: Área {area}, Veículo {vehicle_code}, Entrada 1, Saída 0 em {current_time}")
                    # Adicionar notificação visual
                    cv2.putText(im0, f"Contagem salva: {vehicle_code} na {area}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                previous_counts.setdefault(area, {}).setdefault(vehicle_code, {})['in'] = count_in

            if previous_counts.get(area, {}).get(vehicle_code, {}).get('out', 0) < count_out:
                for _ in range(count_out - previous_counts.get(area, {}).get(vehicle_code, {}).get('out', 0)):
                    cursor.execute('''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
                                      VALUES (?, ?, 0, 1, ?)''', 
                                      (area, vehicle_code, current_time))
                    conn.commit()
                    logger.info(f"Evento de saída salvo para veículo de código {vehicle_code} na área {area}")
                    # Adicionar notificação visual
                    cv2.putText(im0, f"Saída salva: {vehicle_code} na {area}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                previous_counts.setdefault(area, {}).setdefault(vehicle_code, {})['out'] = count_out

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
cursor.execute('PRAGMA journal_mode=DELETE;')  # Ativa o modo WAL para gravação simultânea
# logger.info(f"Banco de dados inicializado em {args.db_path} com WAL ativado.")

# Variável para armazenar as últimas contagens
previous_counts = {}

tracker = PermanenceTracker(args.db_path, config['codigocliente'], permanencia_config)

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
commit_counter = 0  # Contador para batch commits

# Fila para frames que serão gravados
frame_queue = queue.Queue()

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

video_thread = None
if args.save_video:
    # Inicia a thread de gravação
    video_thread = threading.Thread(target=video_writer_thread, args=(frame_queue,))
    video_thread.start()

    frame_intervals = deque(maxlen=120)
    pending_frames = []
    last_video_frame_time = None
    current_video_fps = None
    video_segment_start = None
else:
    frame_intervals = None
    pending_frames = None
    last_video_frame_time = None
    current_video_fps = None
    video_segment_start = None

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

    print(f"❌ Código do veículo não encontrado para '{class_name}' na área '{area_detectada}' (faixa: {faixa_detectada}). Usando -1.")
    return -1  # Retorna -1 caso não seja encontrado



while True:
    success, im0 = cap.read()
    if not success:
        logger.warning("Falha ao capturar o quadro, tentando reconectar...")
        cap.release()
        cap = read_video(args.video_path)
        continue

    frame_count += 1
    if frame_count % frame_skip_interval != 0:
        continue  # Pular os frames que não precisam ser processados

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

                    # 🔹 ADICIONANDO VERIFICAÇÃO: Se `area_detectada` for None, pula para o próximo track
                    if area_detectada is None:
                        logger.warning(f"Track ID {track_id} não está dentro de nenhuma área válida. Pulando para o próximo veículo.")
                        continue  # Ignora esse veículo e passa para o próximo

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


                    # 🚗 Salvar tempo de permanência apenas quando o veículo sair
                    if tracker.has_vehicle_left(track_id, area_detectada):
                        vehicle_code = get_vehicle_code(area_detectada, class_name, config)  # Pega o código correto

                        bug_logger.info(f"🔍 Antes da inserção no banco -> Cliente: {client_code}, Área: {area_detectada}, Veículo: {track_id}, Código: {vehicle_code}, Tempo: {tempo:.2f}s")

                        try:
                            cursor.execute(
                                '''INSERT INTO vehicle_permanence 
                                (codigocliente, area, vehicle_code, timestamp, tempo_permanencia)
                                VALUES (?, ?, ?, ?, ?)''',
                                (client_code, area_detectada, vehicle_code, current_timestamp.strftime('%Y-%m-%d %H:%M:%S'), tempo)
                            )
                            conn.commit()
                            bug_logger.info(f"✅ Tempo de permanência salvo -> Veículo {track_id} ({class_name}) na {area_detectada}: {tempo:.2f}s (Código: {vehicle_code})")
                        except sqlite3.Error as e:
                            bug_logger.error(f"⚠️ Erro ao registrar tempo de permanência no banco para {track_id}: {e}")
                            
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
        save_counts_to_db(counter.area_counts, cursor, conn, previous_counts, config, im0)
    except Exception as e:
        logger.error(f"Erro ao salvar no banco de dados: {e}")

    # Gravação de frames na thread
    if args.save_video:
        resized_im0 = cv2.resize(im0, (args.output_width, args.output_height))
        current_time = time.time()

        if last_video_frame_time is not None:
            frame_intervals.append(max(current_time - last_video_frame_time, 1e-6))
        last_video_frame_time = current_time

        if current_video_fps is None:
            pending_frames.append(resized_im0)

            if len(frame_intervals) >= 5:
                avg_interval = sum(frame_intervals) / len(frame_intervals)
                estimated_fps = 1.0 / max(avg_interval, 1e-6)
                estimated_fps = min(fps, max(0.5, estimated_fps))

                current_video_fps = estimated_fps
                logger.info(f"Iniciando gravação de vídeo com FPS estimado em {current_video_fps:.2f}")

                video_writer, current_video_filepath = start_new_video_writer(
                    args.output_width, args.output_height, current_video_fps
                )
                frame_queue.put(('change_writer', video_writer))
                video_segment_start = current_time

                for frame in pending_frames:
                    frame_queue.put(frame)
                pending_frames.clear()
        else:
            frame_queue.put(resized_im0)

            if video_segment_start is not None and (current_time - video_segment_start) >= video_interval_in_seconds:
                if frame_intervals:
                    avg_interval = sum(frame_intervals) / len(frame_intervals)
                    updated_fps = 1.0 / max(avg_interval, 1e-6)
                    updated_fps = min(fps, max(0.5, updated_fps))
                else:
                    updated_fps = current_video_fps

                if abs(updated_fps - current_video_fps) >= 0.1:
                    logger.info(f"Ajustando FPS de gravação de {current_video_fps:.2f} para {updated_fps:.2f}")
                    current_video_fps = updated_fps

                new_video_writer, current_video_filepath = start_new_video_writer(
                    args.output_width, args.output_height, current_video_fps
                )
                frame_queue.put(('change_writer', new_video_writer))
                video_segment_start = current_time

    # Mostrar frame
    cv2.imshow('YOLOv8 Object Counter', im0)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
if args.save_video:
    if current_video_fps is None and pending_frames:
        if frame_intervals:
            avg_interval = sum(frame_intervals) / len(frame_intervals)
            fallback_fps = 1.0 / max(avg_interval, 1e-6)
        else:
            fallback_fps = effective_fps
        fallback_fps = min(fps, max(0.5, fallback_fps))
        logger.info(f"Finalizando gravação pendente com FPS estimado em {fallback_fps:.2f}")

        video_writer, current_video_filepath = start_new_video_writer(
            args.output_width, args.output_height, fallback_fps
        )
        frame_queue.put(('change_writer', video_writer))
        video_segment_start = time.time()

        for frame in pending_frames:
            frame_queue.put(frame)
        pending_frames.clear()

    frame_queue.put(None)
    if video_thread is not None:
        video_thread.join()

cv2.destroyAllWindows()
tracker.close()
conn.close()
