import sqlite3
import logging
from shapely.geometry import Polygon, Point
from datetime import datetime, timedelta

# Configurar o logger
logger = logging.getLogger("permanence_tracker.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class PermanenceTracker:
    def __init__(self, cursor, conn, client_code, config):
        """
        Inicializa o tracker para calcular o tempo de permanência de veículos.

        :param db_path: Caminho para o banco de dados SQLite
        :param client_code: Código do cliente para identificar os registros
        :param config: Configurações das áreas monitoradas
        """
        self.cursor = cursor
        self.conn = conn
        self.client_code = client_code
        self.config = config

        self.permanence_data = {
             area_name: {
                 "timestamps": {},
                 "last_seen": {},
                 "processed": set(),
                 "vehicle_codes": {}
             }
             for area_name in config.keys()
         }

        self._initialize_db()

    def _initialize_db(self):
        """Garante estrutura necessária na tabela vehicle_counts."""
        # Criar tabela vehicle_counts caso não exista (estrutura mínima)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              area TEXT,
                              vehicle_code INTEGER,
                              count_in INTEGER,
                              count_out INTEGER,
                              timestamp TEXT,
                              tempo_permanencia FLOAT)''')
        self.conn.commit()

        # Garantir colunas necessárias em vehicle_counts
        self.cursor.execute("PRAGMA table_info(vehicle_counts)")
        columns_vc = [column[1] for column in self.cursor.fetchall()]
        if 'tempo_permanencia' not in columns_vc:
            self.cursor.execute('''ALTER TABLE vehicle_counts ADD COLUMN tempo_permanencia FLOAT''')
            self.conn.commit()
            logger.info("Coluna 'tempo_permanencia' adicionada à tabela 'vehicle_counts'.")
        if 'enviado' not in columns_vc:
            self.cursor.execute('''ALTER TABLE vehicle_counts ADD COLUMN enviado INTEGER DEFAULT 0''')
            self.conn.commit()
            logger.info("Coluna 'enviado' adicionada à tabela 'vehicle_counts'.")

    def calculate_permanence(self, tracks, current_timestamp):
        """
        Atualiza os tempos de permanência dos veículos nas áreas monitoradas.

        :param tracks: Lista de objetos rastreados pelo modelo
        :param current_timestamp: Timestamp atual do frame processado
        """
        for area_name, area_info in self.config.items():
            polygon_area = Polygon(area_info['coordenadas'])
            timeout = area_info.get('timeout', 3)

            for track in tracks:
                if not hasattr(track, 'boxes') or track.boxes is None:
                    continue

                if track.boxes.id is None or track.boxes.xyxy is None:
                    continue

                for box, track_id_tensor in zip(track.boxes.xyxy.cpu(), track.boxes.id.cpu()):
                    track_id = int(track_id_tensor.item())
                    centro_x = float((box[0] + box[2]) / 2)
                    centro_y = float((box[1] + box[3]) / 2)
                    centro = Point(centro_x, centro_y)

                    if polygon_area.contains(centro):
                        # Se o veículo entra na área pela primeira vez
                        if track_id not in self.permanence_data[area_name]['timestamps']:
                            self.permanence_data[area_name]['timestamps'][track_id] = current_timestamp
                            logger.info(f"Track ID {track_id} entrou na área {area_name} em {current_timestamp}")

                        # Atualiza o último momento visto dentro da área
                        self.permanence_data[area_name]['last_seen'][track_id] = current_timestamp
                        continue

            # Processar veículos que não foram vistos recentemente
            self._process_exited_vehicles(area_name, current_timestamp, timeout)

    def _process_exited_vehicles(self, area_name, current_timestamp, timeout):
        """
        Processa veículos que saíram da área e salva o tempo de permanência.

        :param area_name: Nome da área monitorada
        :param current_timestamp: Timestamp atual
        :param timeout: Tempo limite para considerar que o veículo saiu
        """
        expired_tracks = []
        for track_id, last_seen in self.permanence_data[area_name]['last_seen'].items():
            # Verifica se o veículo não foi visto dentro do tempo limite
            if (current_timestamp - last_seen).total_seconds() > timeout:
                expired_tracks.append(track_id)

        for track_id in expired_tracks:
            # Evita salvar múltiplos registros para o mesmo veículo
            if track_id in self.permanence_data[area_name]['processed']:
                logger.debug(f"Track ID {track_id} já processado para a área {area_name}.")
                continue

            entry_time = self.permanence_data[area_name]['timestamps'].pop(track_id, None)
            if entry_time:
                tempo_permanencia = (last_seen - entry_time).total_seconds()
                if tempo_permanencia > 1:  # Somente salva se o tempo for maior que 1 segundo
                    self._save_permanence_to_db(track_id, area_name, last_seen, tempo_permanencia)
                    self.permanence_data[area_name]['processed'].add(track_id)  # Marca como processado

            # Remove rastreamentos antigos
            del self.permanence_data[area_name]['last_seen'][track_id]


    def has_vehicle_left(self, track_id, area_name):
        """
        Verifica se o veículo saiu da área.
        Retorna True se o veículo saiu da área monitorada.
        """
        if area_name not in self.permanence_data:
            return False  # Retorna False se a área não existe no tracker

        return track_id not in self.permanence_data[area_name]['timestamps']



    def get_permanence_time(self, track_id):
        """
        Retorna o tempo de permanência de um track_id em qualquer área.

        :param track_id: ID do objeto rastreado
        :return: Dicionário {area_name: tempo_permanencia} ou {} se não encontrado
        """
        tempos = {}
        current_timestamp = datetime.now()
        
        for area_name, area_data in self.permanence_data.items():
            if track_id in area_data['timestamps']:
                entry_time = area_data['timestamps'][track_id]
                tempo_permanencia = (current_timestamp - entry_time).total_seconds()
                tempos[area_name] = tempo_permanencia

        return tempos if tempos else {}  # Retorna um dicionário vazio ao invés de None



    def _save_permanence_to_db(self, track_id, area_name, last_seen, tempo_permanencia):
        """
        Salva o tempo de permanência no banco de dados (vehicle_counts).

        :param track_id: ID do veículo rastreado
        :param area_name: Nome da área
        :param last_seen: Último timestamp visto
        :param tempo_permanencia: Tempo de permanência calculado
        """
        try:
            # Obtem o vehicle_code armazenado no dicionário (ou usa track_id se não existir)
            vehicle_code = self.permanence_data[area_name]['vehicle_codes'].get(track_id, -1)
            timestamp_str = last_seen.strftime('%Y-%m-%d %H:%M:%S')

            # Primeiro tenta ATUALIZAR uma saída previamente inserida (count_out=1 e tempo_permanencia NULL)
            self.cursor.execute(
                '''SELECT id FROM vehicle_counts 
                   WHERE area = ? AND vehicle_code = ? AND count_out = 1 
                     AND tempo_permanencia IS NULL 
                     AND datetime(timestamp) >= datetime(?, '-600 seconds')
                   ORDER BY id DESC LIMIT 1''',
                (area_name, vehicle_code, timestamp_str)
            )
            row = self.cursor.fetchone()
            if row:
                rec_id = row[0]
                self.cursor.execute(
                    '''UPDATE vehicle_counts 
                       SET tempo_permanencia = ?, timestamp = ?, enviado = 0 
                       WHERE id = ?''',
                    (tempo_permanencia, timestamp_str, rec_id)
                )
                logger.info(f"ATUALIZADO vehicle_counts ID={rec_id}: Tempo {tempo_permanencia:.2f}s (area {area_name})")
            else:
                # Se não houver registro de saída prévio, insere um novo
                self.cursor.execute(
                    '''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
                       VALUES (?, ?, 0, 1, ?, ?, 0)''',
                    (area_name, vehicle_code, timestamp_str, tempo_permanencia)
                )
                logger.info(f"INSERIDO em vehicle_counts: Track {track_id}, Area {area_name}, Tempo {tempo_permanencia:.2f}s (enviado=0)")
            
            self.conn.commit()
            logger.info(f"Veiculo {track_id} saiu da area {area_name} com tempo {tempo_permanencia:.2f}s - SALVO EM AMBAS AS TABELAS!")
            logger.info(f"CENARIO: Veiculo pode ter aparecido na area SEM cruzar linha de contagem - tempo registrado independentemente")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao salvar permanencia no banco para Track ID={track_id}: {e}")

    def close(self):
        """Fecha a conexão com o banco de dados."""
        self.conn.close()
