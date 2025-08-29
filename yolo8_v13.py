import cv2
import json
import os
import time
from datetime import datetime, timedelta
import argparse
from ultralytics import YOLO
from ultralytics.solutions import object_counter4
import torch
import sqlite3
import logging
from shapely.geometry import Polygon, Point
import numpy as np
import threading  # Importar threading
import queue  # Importar queue para comunicar entre as threads


# Configurar o logging para suprimir mensagens de debug da YOLOv8
# logging.getLogger("ultralytics").setLevel(logging.ERROR)

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
                      tempo_permanencia FLOAT,
                      enviado INTEGER DEFAULT 0)''')
    
    # **Adicionar colunas se não existirem**
    cursor.execute('''PRAGMA table_info(vehicle_permanence)''')
    columns = [column[1] for column in cursor.fetchall()]
    if 'codigocliente' not in columns:
        cursor.execute('''ALTER TABLE vehicle_permanence ADD COLUMN codigocliente INTEGER''')
    if 'enviado' not in columns:
        cursor.execute('''ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0''')
    
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
def save_counts_to_db(area_counts, cursor, conn, previous_counts, config):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Mapeamento da área para as faixas
    area_to_faixa = {
        'area_1': 'faixa1',
        'area_2': 'faixa2'
    }

    for area, counts in area_counts.items():
        faixa = area_to_faixa.get(area)
        if not faixa:
            #print(f"Faixa não encontrada para a área {area}")
            continue

        for vehicle_type, type_counts in counts['types'].items():
            # Buscar o código do veículo baseado na faixa e no tipo
            vehicle_code = config['cameras']['camera1']['faixas'].get(faixa, {}).get(vehicle_type)
            if not vehicle_code:
                #print(f"Código do veículo não encontrado para {vehicle_type} na faixa {faixa}")
                continue

            # Cada detecção é considerada um evento único com valor de 1
            count_in = type_counts['in']
            count_out = type_counts['out']

            # Verifica se houve mudança na contagem comparado com a última vez
            if previous_counts.get(area, {}).get(vehicle_code, {}).get('in', 0) < count_in:
                # Inserir nova linha para cada detecção de entrada
                for _ in range(count_in - previous_counts.get(area, {}).get(vehicle_code, {}).get('in', 0)):
                    cursor.execute('''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
                                      VALUES (?, ?, 1, 0, ?)''', 
                                      (area, vehicle_code, current_time))
                    conn.commit()
                    #print(f"Nova entrada registrada: {count_in} entradas, {count_out} saídas para {vehicle_code} em {area}")

                # Atualiza o estado anterior com o novo valor
                previous_counts.setdefault(area, {}).setdefault(vehicle_code, {})['in'] = count_in

            if previous_counts.get(area, {}).get(vehicle_code, {}).get('out', 0) < count_out:
                # Inserir nova linha para cada detecção de saída
                for _ in range(count_out - previous_counts.get(area, {}).get(vehicle_code, {}).get('out', 0)):
                    cursor.execute('''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
                                      VALUES (?, ?, 0, 1, ?)''', 
                                      (area, vehicle_code, current_time))
                    conn.commit()
                    #print(f"Evento de saída salvo para veículo de código {vehicle_code} na área {area}")

                # Atualiza o estado anterior com o novo valor
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

def calcular_tempo_permanencia(track_id, centro, area, timestamp):
    if track_id not in permanencia_timestamps[area]:
        permanencia_timestamps[area][track_id] = timestamp
    tempo_dentro = (timestamp - permanencia_timestamps[area][track_id]).total_seconds()
    return tempo_dentro




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
vehicles_crossed_line = {}  # Formato: {track_id: {"vehicle_code": vehicle_code, "class_name": class_name}}

# Inicializa o banco de dados
# Inicializa o banco de dados com o caminho fornecido
conn, cursor = init_db(args.db_path)

# Variável para armazenar as últimas contagens
previous_counts = {}


# Dicionário para armazenar timestamps de entrada por objeto para cada área de permanência
permanencia_timestamps = {area: {} for area in permanencia_areas}
last_seen_times = {area: {} for area in permanencia_areas}
vehicle_codes = {area: {} for area in permanencia_areas}  # Inicializar aqui

# Função principal
def desenhar_areas(im0, permanencia_areas):
    for area_name, area_info in permanencia_areas.items():
        area_coords = np.array(area_info['coordenadas'], np.int32)
        area_coords = area_coords.reshape((-1, 1, 2))
        # Desenha as áreas no frame (em verde, por exemplo)
        cv2.polylines(im0, [area_coords], isClosed=True, color=(0, 255, 0), thickness=2)


# Função principal
frame_count = 0

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


# Função principal
while True:
    success, im0 = cap.read()
    if not success:
        #print("Falha ao capturar o quadro, tentando reconectar...")
        cap.release()
        cap = read_video(args.video_path)
        continue

    frame_count += 1
    if frame_count % frame_skip_interval != 0:
        continue  # Pular os frames que não precisam ser processados


    current_timestamp = datetime.now()

# # Verifica se o intervalo de tempo foi atingido para criar um novo vídeo
#     if args.save_video and (datetime.now() - start_time >= video_duration):
#         # Cria um novo video_writer
#         video_writer, current_video_filepath = start_new_video_writer(args.output_width, args.output_height, fps)
#         # Envia o novo video_writer para a thread
#         frame_queue.put(('change_writer', video_writer))
#         start_time = datetime.now()  # Atualiza o tempo de início para o novo vídeo

    # Realizar inferência com YOLOv8 e rastreamento (suprimindo as mensagens)
    tracks = model.track(im0, persist=True, show=False, classes=classes_to_count, conf=0.20, imgsz=940)
    
    # Desenhar as áreas de permanência
    desenhar_areas(im0, permanencia_areas)
    # Primeira área de contagem
    im0 = counter.start_counting(im0, tracks, region_points, 'area_1', fps=fps)

    # Segunda área de contagem, se existir
    if second_region_points:
        im0 = counter.start_counting(im0, tracks, second_region_points, 'area_2', fps=fps)

    for track in tracks:
        if hasattr(track, 'boxes') and track.boxes is not None:
            # Certificar-se de que os atributos não são None antes de tentar acessá-los
            if track.boxes.id is not None and track.boxes.xyxy is not None and track.boxes.cls is not None:
                for box, track_id_tensor, class_id_tensor in zip(track.boxes.xyxy.cpu(), track.boxes.id.cpu(), track.boxes.cls.cpu()):
                    x1, y1, x2, y2 = box
                    # Converter track_id e class_id para inteiros padrão
                    track_id = int(track_id_tensor.item())
                    class_id = int(class_id_tensor.item())

                    # Verifica se o veículo cruzou a linha de contagem
                    if track_id not in vehicles_crossed_line:
                        # Pega o rótulo fixo do veículo que cruzou a linha de contagem
                        class_name = model.names[class_id]
                        # Definir a faixa (você pode mudar esta lógica para adaptar à sua necessidade)
                        area = 'area_1'  # Esta lógica precisa ser ajustada dependendo da área a que o veículo pertence
                        vehicle_code = config['cameras']['camera1']['faixas'].get(area_to_faixa[area], {}).get(class_name)

                        # Armazenar informações do veículo que cruzou a linha de contagem
                        vehicles_crossed_line[track_id] = {"vehicle_code": vehicle_code, "class_name": class_name}


    # Calcular tempo de permanência em cada área
    for area_name, area_info in permanencia_areas.items():
        area_coords = area_info['coordenadas']
        min_time = 1  # Tempo mínimo de permanência fixo em 1 segundo
        polygon_area = Polygon(area_coords)

        if tracks and hasattr(tracks[0], 'boxes') and tracks[0].boxes is not None:
            if tracks[0].boxes.id is not None and tracks[0].boxes.xyxy is not None and tracks[0].boxes.cls is not None:
                for box, track_id_tensor, class_id_tensor in zip(tracks[0].boxes.xyxy.cpu(), tracks[0].boxes.id.cpu(), tracks[0].boxes.cls.cpu()):
                    x1, y1, x2, y2 = box
                    # Converter track_id e class_id para inteiros padrão
                    track_id = int(track_id_tensor.item())
                    class_id = int(class_id_tensor.item())
                    # Converter coordenadas para float
                    centro_x = float((x1 + x2) / 2)
                    centro_y = float((y1 + y2) / 2)
                    centro = Point(centro_x, centro_y)

                    # Verifica se o veículo cruzou a linha de contagem
                    if track_id not in vehicles_crossed_line:
                        continue  # Ignorar veículos que não cruzaram a linha de contagem

                    # Pega o rótulo fixo do veículo que cruzou a linha de contagem
                    vehicle_code = vehicles_crossed_line[track_id]['vehicle_code']
                    class_name = vehicles_crossed_line[track_id]['class_name']

                    # Verifica se o centro do objeto está dentro da área de permanência
                    if polygon_area.contains(centro):
                        # Se o objeto não estava na área antes, registra o timestamp de entrada
                        if track_id not in permanencia_timestamps[area_name]:
                            permanencia_timestamps[area_name][track_id] = current_timestamp
                            vehicle_codes[area_name][track_id] = vehicle_code  # Armazena o código do veículo
                            # LOG de entrada na área
                            print(f"Veículo {track_id} entrou na área {area_name} em {current_timestamp}")

                        # Atualiza o timestamp da última vez que o veículo foi visto
                        last_seen_times[area_name][track_id] = current_timestamp

                        # Calcula o tempo de permanência
                        tempo_dentro = (current_timestamp - permanencia_timestamps[area_name][track_id]).total_seconds()

                        # Cria o rótulo com o tempo de permanência
                        label = f"{class_name} {track_id}: {tempo_dentro:.1f}s"
                        # Desenha o rótulo no frame
                        cv2.putText(im0, label, (int(x1), int(y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Após processar todos os objetos, removemos os track_ids que não foram vistos por mais de `tempo_limite`
                tempo_limite = 2  # Tempo em segundos, aumentado para evitar remoções prematuras
                track_ids_to_remove = []
                ultima_vez_visto_dict = {}  # Dicionário para armazenar a última vez que o track_id foi visto

                for track_id in list(permanencia_timestamps[area_name].keys()):
                    ultima_vez_visto = last_seen_times[area_name].get(track_id, current_timestamp)
                    tempo_desde_ultima_vista = (current_timestamp - ultima_vez_visto).total_seconds()
                    if tempo_desde_ultima_vista > tempo_limite:
                        track_ids_to_remove.append(track_id)
                        ultima_vez_visto_dict[track_id] = ultima_vez_visto  # Armazena a última vez que foi visto

                for track_id in track_ids_to_remove:
                    # Antes de remover, calcular o tempo de permanência total
                    timestamp_entrada = permanencia_timestamps[area_name][track_id]
                    ultima_vez_visto = ultima_vez_visto_dict[track_id]
                    tempo_permanencia = (ultima_vez_visto - timestamp_entrada).total_seconds()

                    # Verifica se o tempo de permanência é maior que o tempo mínimo especificado
                    if tempo_permanencia > 1:
                        # Obter o código do veículo associado ao track_id
                        vehicle_code = vehicle_codes[area_name].get(track_id, None)

                        # Salvar no banco de dados usando `codigocliente` e o `vehicle_code` correto
                        cursor.execute('''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia, enviado)
                                        VALUES (?, ?, ?, ?, 0)''', (client_code, vehicle_code, ultima_vez_visto.strftime('%Y-%m-%d %H:%M:%S'), tempo_permanencia))
                        conn.commit()

                        # Log de permanência
                        print(f"Veículo {track_id} permaneceu por {tempo_permanencia:.2f}s, registrado em {ultima_vez_visto}")

                    # Remover o track_id dos dicionários
                    del permanencia_timestamps[area_name][track_id]
                    del last_seen_times[area_name][track_id]
                    del vehicle_codes[area_name][track_id]



    # Exibe contagens no terminal
    #print("Contagens de veículos por área:")
    for area, counts in counter.area_counts.items():
        for vehicle_type, type_counts in counts['types'].items():
            #print(f"Veículo detectado: {vehicle_type}")
            print(f"Entrada: {type_counts['in']}, Saída: {type_counts['out']}")

    # Salvamento em tempo real apenas se os valores mudarem
    try:
        save_counts_to_db(counter.area_counts, cursor, conn, previous_counts, config)
    except Exception as e:
        print(f"Erro ao salvar no banco de dados: {e}")

    # Gravação de frames na thread
    if args.save_video:
        resized_im0 = cv2.resize(im0, (args.output_width, args.output_height))
        frame_queue.put(resized_im0)
        frames_written += 1  # Incrementa o contador de frames escritos

        # Verifica se o número de frames escritos atingiu o limite
        if frames_written >= frames_per_video:
            # Cria um novo video_writer
            video_writer, current_video_filepath = start_new_video_writer(args.output_width, args.output_height, effective_fps)
            # Envia o novo video_writer para a thread
            frame_queue.put(('change_writer', video_writer))
            frames_written = 0  # Reseta o contador



    cv2.imshow('YOLOv8 Object Counter', im0)
    # Captura a tecla pressionada enquanto a janela está ativa
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        #print("Tecla 'q' pressionada. Finalizando operação.")
        break
cap.release()
if args.save_video:
    # Colocar None na fila para informar à thread que ela deve encerrar
    frame_queue.put(None)
    video_thread.join()  # Esperar a thread de gravação terminar

cv2.destroyAllWindows()
conn.close()