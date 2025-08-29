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
logging.basicConfig(level=logging.INFO, filename=f'.\\log\\tmpprm_api_{data_log}.log', filemode='a',
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


# Consulta a última data/hora de controle do envio do tempo de permanência
def get_last_processed_timestamp():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS vehicle_permanence_log_exportacao (last_processed TEXT)")
    cursor.execute("SELECT last_processed FROM vehicle_permanence_log_exportacao ORDER BY last_processed DESC LIMIT 1")
    last_processed = cursor.fetchone()
    conn.close()
    return last_processed[0] if last_processed else None


# Atualiza a data/hora de controle do envio do tempo de permanência
def update_last_processed_timestamp_specific(timestamp):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vehicle_permanence_log_exportacao (last_processed) VALUES (?)", (timestamp,))
    conn.commit()
    conn.close()


# Consulta os dados de tempo de permanência que ainda não foram enviados
# e faz uma lista para iteração
def buscar_dados():
    last_processed = get_last_processed_timestamp()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT timestamp, vehicle_code, tempo_permanencia FROM vehicle_permanence"

    if last_processed:
        # Ignora os milissegundos ao fazer a comparação
        query += f" WHERE datetime(timestamp, 'localtime') > datetime('{last_processed}', 'localtime')"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        logging.info('Nenhum dado novo para processar.')
        return False
    else:
        return rows


# Formata o tempo de permanência em um json para que seja enviado para a API.
def enviar_dados(timestamp, vehicle_code, tempo_permanencia):
    dados_envio = {
        "datetime": timestamp,
        "dwelltime": {
            str(vehicle_code): {
                "inside": 1,
                "mean_secs": int(tempo_permanencia)
            }
        }
    }

    # logging.info('Enviando dados: %s', json.dumps(dados_envio))
    while True:  # Repetir até obter sucesso

        try:
            response = requests.post(url, json=dados_envio, auth=HTTPBasicAuth(username, password))

            # Se tudo der certo, então atualiza a data/hora controle
            # Caso dê falha, tentará enviar novamente o mesmo registro, até que tenha sucesso
            if response.status_code == 204:
                # logging.info(f'Dados enviados com sucesso para veículo código {vehicle_code}.')
                update_last_processed_timestamp_specific(timestamp)  # Atualiza o timestamp ao enviar
                # break  # Sai do loop quando o envio for bem-sucedido
                return True  # Sai do loop quando o envio for bem-sucedido
            else:
                logging.error(
                    f"""Erro ao enviar dados para veículo código {vehicle_code} | Status Code: {response.status_code}  
                    \t{response.text}""")
        except Exception as e:
            logging.error(f'Erro ao fazer a requisição para veículo código {vehicle_code}: {e.args}')


if __name__ == "__main__":
    dados = buscar_dados()
    if dados:
        for dado in dados:
            enviar_dados(*dado)
