import requests
import sqlite3
from requests.auth import HTTPBasicAuth
import json
import logging
import datetime
import argparse
import os


# Configuração de logging
data_log = datetime.datetime.now().strftime("%Y-%m-%d")
# Garante diretório de logs
try:
    os.makedirs('log', exist_ok=True)
    logfile = os.path.join('log', f'tmpprm_api_{data_log}.log')
except Exception:
    # fallback para diretório atual
    logfile = f'tmpprm_api_{data_log}.log'

logging.basicConfig(level=logging.INFO, filename=logfile, filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Dados para autenticação
url = 'https://mfweb.maisfluxo.com.br/MaisFluxoServidorWEB/rest/dwell/'

# Dados para autenticação utilizando variáveis de ambiente
# username = os.getenv('API_USERNAME', 'default_username')  # 'default_username' é um valor padrão opcional
# password = os.getenv('API_PASSWORD', 'default_password')  # 'default_password' é um valor padrão opcional
username = 'veiculos.t.permanencia'
password = 'u41t.0r14'


# Configuração de argparse para capturar o caminho do banco de dados como argumento
parser = argparse.ArgumentParser(description="Envia dados de permanência de veículos para a API.")
parser.add_argument('--db_path', type=str, default='yolo8.db', help='Caminho para o banco de dados SQLite.')
args = parser.parse_args()

# Caminho para o banco de dados SQLite
db_path = args.db_path


# Consulta os dados de tempo de permanência que ainda não foram enviados
# e faz uma lista para iteração baseada no campo 'enviado'
def buscar_dados():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Garantir coluna 'enviado' na vehicle_counts
    cursor.execute("PRAGMA table_info(vehicle_counts)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'enviado' not in columns:
        cursor.execute("ALTER TABLE vehicle_counts ADD COLUMN enviado INTEGER DEFAULT 0")
        conn.commit()
        logging.info("Coluna 'enviado' adicionada à tabela 'vehicle_counts'.")

    # Buscar apenas registros de saída com tempo e não enviados
    query = (
        "SELECT id, timestamp, vehicle_code, tempo_permanencia "
        "FROM vehicle_counts "
        "WHERE enviado = 0 AND tempo_permanencia IS NOT NULL "
        "ORDER BY timestamp"
    )
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        logging.info('Nenhum dado novo para processar.')
        return False
    else:
        logging.info(f'Encontrados {len(rows)} registros não enviados para processar.')
        return rows


# Marca um registro específico como enviado
def marcar_como_enviado(record_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE vehicle_counts SET enviado = 1 WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    logging.info(f'Registro ID {record_id} marcado como enviado.')


# Formata o tempo de permanência em um json para que seja enviado para a API.
def enviar_dados(record_id, timestamp, vehicle_code, tempo_permanencia):
    # Normaliza timestamp para formato "YYYY-MM-DD HH:MM:SS" (sem 'T' e sem timezone)
    timestamp_api = timestamp
    try:
        # Caso venha em ISO (com 'T' e offset), converter mantendo somente até segundos
        if 'T' in timestamp_api:
            # Substitui 'T' por espaço e remove qualquer sufixo de timezone
            ts = timestamp_api.replace('Z', '')
            ts = ts.split('T', 1)[0] + ' ' + ts.split('T', 1)[1]
            timestamp_api = ts[:19] if len(ts) >= 19 else ts
        # Caso tenha offset sem 'T' (raro), truncar após segundos
        if len(timestamp_api) > 19 and (timestamp_api[19] in ['+', '-']):
            timestamp_api = timestamp_api[:19]
        # Validar formato; se não bater, tenta parsear e reformatar
        try:
            datetime.datetime.strptime(timestamp_api, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt2 = datetime.datetime.fromisoformat(timestamp)
                timestamp_api = dt2.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                # Mantém como veio se não conseguir parsear
                pass
    except Exception as e:
        logging.warning(f"Falha ao normalizar timestamp '{timestamp}': {e}")

    dados_envio = {
        "datetime": timestamp_api,
        "dwelltime": {
            str(vehicle_code): {
                "inside": 1,
                "mean_secs": int(tempo_permanencia)
            }
        }
    }
    
    # LOG para debug
    logging.info(f"Enviando timestamp: '{timestamp}' -> '{timestamp_api}' para vehicle_code {vehicle_code}")

    try:
        response = requests.post(url, json=dados_envio, auth=HTTPBasicAuth(username, password))

        # Se tudo der certo, marca o registro como enviado
        if response.status_code == 204:
            marcar_como_enviado(record_id)  # Marca este registro específico como enviado
            logging.info(f'Dados enviados com sucesso para registro ID {record_id} - veículo código {vehicle_code}.')
            return True
        else:
            logging.error(
                f"""Erro ao enviar dados para registro ID {record_id} - veículo código {vehicle_code} | Status Code: {response.status_code}  
                \t{response.text}""")
            return False
    except Exception as e:
        logging.error(f'Erro ao fazer a requisição para registro ID {record_id} - veículo código {vehicle_code}: {e}')
        return False


if __name__ == "__main__":
    dados = buscar_dados()
    if dados:
        sucessos = 0
        falhas = 0
        for dado in dados:
            record_id, timestamp, vehicle_code, tempo_permanencia = dado
            if enviar_dados(record_id, timestamp, vehicle_code, tempo_permanencia):
                sucessos += 1
            else:
                falhas += 1
        
        logging.info(f'Processamento concluído: {sucessos} sucessos, {falhas} falhas.')
