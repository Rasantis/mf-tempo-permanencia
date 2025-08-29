import os
import sqlite3
import pandas as pd
import argparse
import hashlib
from datetime import datetime, timedelta


# Função para gerar o hash do nome do arquivo .txt
def generate_hash_from_file(filepath):
    """Gera um hash SHA-256 a partir do conteúdo de um arquivo."""
    hash_sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(4096), b""):
            hash_sha256.update(block)
    return hash_sha256.hexdigest().upper()

def floor_timestamp_to_half_hour(timestamp_str):
    """Round a timestamp to the nearest half-hour interval."""
    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    
    # Se o horário for exatamente meia-noite (00:00:00), altere para 23:59:00 do dia anterior
    if timestamp.hour == 0 and timestamp.minute == 0:
        # timestamp = (timestamp - timedelta(days=1)).replace(hour=23, minute=59, second=0)
        timestamp = (timestamp - timedelta(minutes=1))
    # Arredonda para 00 ou 30 minutos
    elif timestamp.minute >= 30:
        timestamp = (timestamp + timedelta(minutes=30)).replace(minute=0, second=0)
    else:
        timestamp = timestamp.replace(minute=30, second=0)

    return timestamp.strftime("%Y-%m-%d %H:%M:%S")

def get_data_from_db(db_path, start_time=None, end_time=None):
    """Obtém dados do banco SQLite dentro do intervalo especificado ou desde o último export_log."""
    if not os.path.exists(db_path):
        print(f"Erro: Banco de dados {db_path} não encontrado!")
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if start_time and end_time:
        query = """
            SELECT 
                area, 
                vehicle_code, 
                count_in, 
                count_out, 
                timestamp
            FROM vehicle_counts
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp;
        """
        params = (start_time, end_time)
        print(f"Executando consulta ao banco de dados de {start_time} até {end_time}...")
    else:
        cursor.execute("SELECT last_export FROM export_log ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        last_export_time = result[0] if result else '1970-01-01 00:00:00'
        query = """
            SELECT 
                area, 
                vehicle_code, 
                count_in, 
                count_out, 
                timestamp
            FROM vehicle_counts
            WHERE timestamp > ?
            ORDER BY timestamp;
        """
        params = (last_export_time,)
        print(f"Executando consulta ao banco de dados desde {last_export_time}...")
    
    data = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if data.empty:
        print("Nenhum dado encontrado.")
    else:
        print(f"{len(data)} registros encontrados.")
    
    return data

# função para gerar o range de 48 meias-hora (de 00:30 à 23:59) para todos os dias informados nos parâmetros
def build_time_range(start_time, end_time):
    start_time = pd.to_datetime(start_time)
    end_time   = pd.to_datetime(end_time)

    # pega o "agora" (momento da execução)
    now = pd.Timestamp.now().floor("min")

    # Gera os dias dentro do range
    all_days = pd.date_range(start=start_time.normalize(),
                             end=end_time.normalize(),
                             freq="D")

    full_time_ranges = []
    for day in all_days:
        # slots de 00:30 até 23:30
        slots = pd.date_range(start=day + pd.Timedelta("00:30:00"),
                              end=day + pd.Timedelta("23:30:00"),
                              freq="30min")

        # adiciona 23:59
        slots = slots.append(pd.DatetimeIndex([day + pd.Timedelta("23:59:00")]))

        # --- Ajuste dependendo do dia ---
        if day.date() < now.date():
            # dia passado → mantém até 23:59
            pass
        elif day.date() == now.date():
            # dia atual → corta no horário válido
            last_valid = now.floor("30min")
            slots = slots[slots <= last_valid]
        else:
            # dia futuro → ignora
            slots = []

        full_time_ranges.extend(slots)

    return pd.DatetimeIndex(full_time_ranges)

def aggregate_data(data, start_time, end_time):
    """Agrupa os dados por área, veículo e intervalo de 30 minutos e preenche lacunas."""
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    data['rounded_time'] = data['timestamp'].apply(lambda x: floor_timestamp_to_half_hour(x.strftime("%Y-%m-%d %H:%M:%S")))
    data['rounded_time'] = pd.to_datetime(data['rounded_time'])
    
    # transforma a variável start_time de string para datetime e troca o primeiro registro para 30min
    start_time = (datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        .replace(minute=30, second=0)
    )
    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
    
    # --- Gera range fixo com base no intervalo informado ---
    time_range = build_time_range(start_time, end_time)
    
    all_vehicle_codes = data['vehicle_code'].unique()
    full_index = pd.MultiIndex.from_product(
        [all_vehicle_codes, time_range], 
        names=['vehicle_code', 'rounded_time']
    )
    
    aggregated_data = (
        data.groupby(['vehicle_code', 'rounded_time'])
            .agg(
                total_in=('count_in', 'sum'),
                total_out=('count_out', 'sum')
            )
            .reindex(full_index, fill_value=0)
            .reset_index()
    )
    
    print(f"{len(aggregated_data)} registros agregados por intervalos de 30 minutos.")
    return aggregated_data

def save_consolidated_file(aggregated_data, client_code, output_directory):
    """Gera um arquivo TXT consolidado com os dados agregados."""
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    temp_filename = f"{client_code}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
    temp_file_path = os.path.join(output_directory, temp_filename)
    
    with open(temp_file_path, 'w') as file:
        file.write("<inicio cabecalho>\n")
        file.write(f"empresa={client_code}\n")
        file.write("fonte=pixforce\n")
        file.write("servidor=servidor\n")
        file.write("<fim cabecalho>\n")
        file.write("<inicio dados>\n")
        
        for _, row in aggregated_data.iterrows():
            timestamp_str = row['rounded_time'].strftime("%Y-%m-%d %H:%M:%S")
            file.write(f"{row['vehicle_code']};{timestamp_str};{row['total_in']};{row['total_out']};\n")
        
        file.write("<fim dados>\n")
    
    file_hash = generate_hash_from_file(temp_file_path)
    final_filename = f"{client_code}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_hash}.txt"
    final_file_path = os.path.join(output_directory, final_filename)
    os.rename(temp_file_path, final_file_path)
    
    print(f"Arquivo consolidado salvo como {final_filename}")

def main():
    parser = argparse.ArgumentParser(description='Consolida dados de contagem de veículos.')
    parser.add_argument('--client_code', type=str, required=True, help='Código do cliente.')
    parser.add_argument('--db_path', type=str, required=True, help='Caminho do banco de dados.')
    parser.add_argument('--output_directory', type=str, required=True, help='Diretório de saída.')
    parser.add_argument('--start_time', type=str, help='(Opcional) Data e hora inicial no formato "YYYY-MM-DD HH:MM:SS".')
    parser.add_argument('--end_time', type=str, help='(Opcional) Data e hora final no formato "YYYY-MM-DD HH:MM:SS".')
    
    args = parser.parse_args()
    
    data = get_data_from_db(args.db_path, args.start_time, args.end_time)
    if data is None or data.empty:
        print("Nenhum dado encontrado. Arquivo não será gerado.")
        return
    
    aggregated_data = aggregate_data(data, args.start_time, args.end_time)
    save_consolidated_file(aggregated_data, args.client_code, args.output_directory)

if __name__ == "__main__":
    main()
