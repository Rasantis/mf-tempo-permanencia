import os
import json
import argparse
import sqlite3
import pandas as pd
import hashlib
from datetime import datetime, timedelta

# Função para arredondar timestamps para o intervalo de meia hora mais próximo
def round_timestamp_to_nearest_half_hour(timestamp_str):
    """Round a timestamp to the nearest half-hour interval."""
    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    
    # Arredonda para 00 ou 30 minutos
    if timestamp.minute >= 30:
        timestamp = (timestamp + timedelta(minutes=30)).replace(minute=0, second=0)
    else:
        timestamp = timestamp.replace(minute=30, second=0)
    
    # Se o horário for exatamente meia-noite (00:00:00), altere para 23:59:00 do dia anterior
    if timestamp.hour == 0 and timestamp.minute == 0:
        # timestamp = (timestamp - timedelta(days=1)).replace(hour=23, minute=59, second=0)
        timestamp = (timestamp - timedelta(minutes=1))

    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


# Função para gerar o nome do arquivo sem o hash, mas seguindo o padrão YYYYMMDDHHMMSS
def generate_filename_without_hash(client_code, timestamp):
    """Generate the filename with client code and timestamp, without hash."""
    time_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    formatted_time = time_obj.strftime("%Y%m%d%H%M%S")  # Usando o formato YYYYMMDDHHMMSS
    return f"{client_code}_{formatted_time}.txt"

# Função para gerar o hash baseado no conteúdo do arquivo
def generate_hash_from_file(filepath):
    """Generate a SHA-256 hash from the content of a file."""
    hash_sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        # Leitura em blocos para arquivos grandes
        for block in iter(lambda: f.read(4096), b""):
            hash_sha256.update(block)
    return hash_sha256.hexdigest().upper()


def get_data_from_db(db_path):
    """Fetch vehicle data from the database since the last export time."""
    if not os.path.exists(db_path):
        print(f"Erro: Banco de dados {db_path} não encontrado!")
        return None, None

    conn = sqlite3.connect(db_path)

    # Obter o último horário de exportação
    cursor = conn.cursor()
    cursor.execute("SELECT last_export FROM export_log ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    if result:
        """
        if result[0].split(' ', 1)[1] == '23:30:00':
            last_export_time = f"{result[0].split(' ', 1)[0]} 00:00:00"
            cursor = conn.cursor()
            cursor.execute("INSERT INTO export_log (last_export) VALUES (?)", (last_export_time,))
            conn.commit()
        else:
        """
        last_export_time = result[0]
    else:
        last_export_time = '1970-01-01 00:00:00'

    query = """
    SELECT area, vehicle_code, count_in, count_out, timestamp
    FROM vehicle_counts
    WHERE timestamp > ?
    ORDER BY timestamp;
    """
    print(f"Executando consulta ao banco de dados desde {last_export_time}...")
    data = pd.read_sql_query(query, conn, params=(last_export_time,))
    
    cursor.close()
    conn.close()

    if data.empty:
        print(f"Nenhum dado encontrado no banco de dados depois de {last_export_time}")
    else:
        print(f"{len(data)} registros encontrados no banco de dados.")
    
    return data, last_export_time


def format_content(aggregated_data, client_code):
    """Format the content of the aggregated data for the output TXT file."""
    formatted_content = []
    
    # Ordena os dados pelo campo 'rounded_time'
    aggregated_data = aggregated_data.sort_values(by='rounded_time', ascending=True)

    for _, row in aggregated_data.iterrows():
        area, vehicle_type, rounded_time, total_in, total_out = row

        # Formata a linha com o código do veículo, timestamp arredondado e totais
        formatted_line = f"{vehicle_type};{rounded_time};{total_in};{total_out};"
        formatted_content.append(formatted_line)
    
    return formatted_content

# Função para agrupar os dados por intervalo de 30 minutos e somar as contagens
def aggregate_data(data):
    """Aggregate data by 30-minute intervals and sum the counts."""
    # Converte o timestamp para o formato datetime e arredonda para o intervalo mais próximo
    data['rounded_time'] = data['timestamp'].apply(round_timestamp_to_nearest_half_hour)
    
    # Agrupa os dados por área, tipo de veículo e intervalo arredondado, somando as contagens
    aggregated_data = data.groupby(['area', 'vehicle_code', 'rounded_time']).agg(
        total_in=('count_in', 'sum'),
        total_out=('count_out', 'sum')
    ).reset_index()

    print(f"{len(aggregated_data)} registros agregados por intervalos de 30 minutos.")
    return aggregated_data

def save_files_per_interval(aggregated_data, client_code, output_directory, db_path):
    """Save the aggregated data into separate files for each 30-minute interval and handle empty data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Obter todos os códigos de veículos do banco de dados e garantir ordenação consistente
    cursor.execute("SELECT DISTINCT vehicle_code FROM vehicle_counts ORDER BY vehicle_code")
    all_vehicle_codes = [row[0] for row in cursor.fetchall()]

    if aggregated_data.empty:
        print("Nenhum dado encontrado. Gerando arquivo com valores zerados.")
        timestamps = pd.Series(dtype='datetime64[ns]')  # DataFrame vazio para compatibilidade
    else:
        timestamps = pd.to_datetime(aggregated_data['rounded_time']).sort_values()

    if timestamps.empty:
        # Use o timestamp atual se não houver dados
        start_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        end_time = start_time
    else:
        # Obtenha o primeiro e o último timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()

    # Gerar intervalos de 30 minutos entre o início e o fim
    intervals = pd.date_range(start=start_time, end=end_time, freq='30T')

    for interval in intervals:
        rounded_time = interval.strftime("%Y-%m-%d %H:%M:%S")
        data_for_interval = aggregated_data[aggregated_data['rounded_time'] == rounded_time]

        # Criar um dicionário com contagens zeradas para todos os códigos
        counts_dict = {code: {'total_in': 0, 'total_out': 0} for code in all_vehicle_codes}

        # Atualizar o dicionário com os dados reais, se disponíveis
        for _, row in data_for_interval.iterrows():
            vehicle_code = int(row['vehicle_code'])
            counts_dict[vehicle_code] = {
                'total_in': int(row['total_in']),
                'total_out': int(row['total_out'])
            }

        # Gerar o conteúdo do arquivo com os pontos
        formatted_content = "\n".join(
            [f"{code};{rounded_time};{counts['total_in']};{counts['total_out']};"
             for code, counts in counts_dict.items()]
        )

        # Gera o nome do arquivo sem o hash inicialmente
        file_name = generate_filename_without_hash(client_code, rounded_time)
        file_path = os.path.join(output_directory, file_name)

        # Verifica se o diretório existe, caso contrário, cria
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        # Salva o arquivo
        with open(file_path, 'w') as file:
            file.write("<inicio cabecalho>\n")
            file.write(f"empresa={client_code}\n")
            file.write("fonte=pixforce\n")
            file.write("servidor=servidor\n")
            file.write("<fim cabecalho>\n")
            file.write("<inicio dados>\n")
            file.write(formatted_content + "\n")
            file.write("<fim dados>\n")

        # Gerar o hash e renomear o arquivo
        file_hash = generate_hash_from_file(file_path)
        new_file_name = f"{client_code}_{interval.strftime('%Y%m%d%H%M%S')}_{file_hash}.txt"
        os.rename(file_path, os.path.join(output_directory, new_file_name))

        print(f"Arquivo salvo e renomeado: {new_file_name}")

    # Atualizar o last_export_time na tabela export_log
    cursor.execute("INSERT INTO export_log (last_export) VALUES (?)", (end_time.strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()
    print(f"Último horário de exportação atualizado para {end_time.strftime('%Y-%m-%d %H:%M:%S')}")


# Função para deletar registros mais antigos que "X" dias
def delete_old_records(db_path, days_to_keep):
    """Delete records older than the specified number of days."""
    if not os.path.exists(db_path):
        print(f"Erro: Banco de dados {db_path} não encontrado!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Calcular a data limite com base no número de dias
    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')

    # Deletar registros antigos
    query = "DELETE FROM vehicle_counts WHERE timestamp < ?"
    cursor.execute(query, (cutoff_date,))
    deleted_rows = cursor.rowcount
    conn.commit()

    cursor.close()
    conn.close()

    print(f"{deleted_rows} registros mais antigos que {days_to_keep} dias foram deletados.")


def main():
    parser = argparse.ArgumentParser(description='Process database data and format their content.')
    parser.add_argument('--client_code', type=str, required=True, help='Client code for file naming.')
    parser.add_argument('--db_path', type=str, required=True, help='Path to the SQLite database file.')
    parser.add_argument('--output_directory', type=str, required=True, help='Directory to save the formatted TXT files.')
    parser.add_argument('--days_to_keep', type=int, default=90, help='Number of days to keep in the database. Older records will be deleted.')

    args = parser.parse_args()

    # Deleta registros mais antigos que "days_to_keep"
    delete_old_records(args.db_path, args.days_to_keep)
    # Busca os dados no banco
    data, last_export_time = get_data_from_db(args.db_path)
    if data is None or len(data) == 0:
        print("Nenhum dado encontrado. Gerando arquivo com valores zerados.")
        aggregated_data = pd.DataFrame(columns=['area', 'vehicle_code', 'rounded_time', 'total_in', 'total_out'])
    else:
        # Agrega os dados por intervalos de 30 minutos
        aggregated_data = aggregate_data(data)

    # Salva os dados em arquivos separados por intervalo de 30 minutos
    save_files_per_interval(aggregated_data, args.client_code, args.output_directory, args.db_path)


if __name__ == "__main__":
    main()
