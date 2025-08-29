import os
import sqlite3
# Adição de argumentos via terminal
import argparse

def criar_tabela_dados(conexao):
    conexao.execute("""
    CREATE TABLE IF NOT EXISTS dados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_veiculo TEXT,
        data_hora TEXT,
        entradas INTEGER,
        saidas INTEGER
    )
    """)
    conexao.commit()

def registrar_arquivo_processado(conexao, nome_arquivo):
    cursor = conexao.cursor()
    cursor.execute("INSERT INTO arquivos_processados (nome_arquivo) VALUES (?)", (nome_arquivo,))
    conexao.commit()

def ja_processado(conexao, nome_arquivo):
    cursor = conexao.cursor()
    cursor.execute("SELECT 1 FROM arquivos_processados WHERE nome_arquivo = ?", (nome_arquivo,))
    return cursor.fetchone() is not None

def processar_arquivos_pasta(pasta, conexao):
    arquivos_txt = [f for f in os.listdir(pasta) if f.endswith('.txt')]
    
    for arquivo in arquivos_txt:
        if ja_processado(conexao, arquivo):
            print(f"Arquivo já processado: {arquivo}")
            continue
        
        caminho_arquivo = os.path.join(pasta, arquivo)
        processar_arquivo(caminho_arquivo, conexao)
        
        # Registrar que o arquivo foi processado
        registrar_arquivo_processado(conexao, arquivo)

def processar_arquivo(caminho_arquivo, conexao):
    with open(caminho_arquivo, 'r') as file:
        linhas = file.readlines()
    
    for linha in linhas:
        linha = linha.strip()
        
        if linha.startswith("<") or linha.startswith("empresa=") or linha.startswith("fonte=") or linha.startswith("servidor="):
            print(f"Ignorando linha de cabeçalho: {linha}")
            continue
        
        linha = linha.rstrip(';')
        valores = linha.split(';')
        
        if len(valores) == 4:
            codigo_veiculo = valores[0]
            data_hora = valores[1]
            entradas = valores[2]
            saidas = valores[3]
            
            cursor = conexao.cursor()
            
            # Verificar se o registro já existe
            cursor.execute("""
                SELECT 1 FROM dados WHERE codigo_veiculo = ? AND data_hora = ? AND entradas = ? AND saidas = ?
            """, (codigo_veiculo, data_hora, entradas, saidas))
            
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO dados (codigo_veiculo, data_hora, entradas, saidas) 
                    VALUES (?, ?, ?, ?)
                """, (codigo_veiculo, data_hora, entradas, saidas))
                conexao.commit()
                print(f"Inserido: Codigo Veiculo = {codigo_veiculo}, Data/Hora = {data_hora}, Entradas = {entradas}, Saídas = {saidas}")
            else:
                print(f"Registro já existe: Codigo Veiculo = {codigo_veiculo}, Data/Hora = {data_hora}")
        else:
            print(f"Erro de formato na linha: {linha}")



# Argumentos do terminal
parser = argparse.ArgumentParser(description='Processa arquivos TXT e armazena os dados em um banco de dados SQLite.')
parser.add_argument('--pasta', type=str, required=True, help='Caminho da pasta onde os arquivos .txt estão localizados.')
parser.add_argument('--banco', type=str, required=True, help='Nome do arquivo de banco de dados SQLite de saída.')
args = parser.parse_args()

# Usar os caminhos fornecidos como argumentos
pasta = args.pasta

# Conectar ao banco de dados SQLite
conexao = sqlite3.connect(args.banco)


# Criar a tabela para registrar os arquivos processados, se ela não existir
conexao.execute("""
CREATE TABLE IF NOT EXISTS arquivos_processados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_arquivo TEXT UNIQUE
)
""")

# Criar a tabela dados, se ela não existir
criar_tabela_dados(conexao)

# Chama a função para processar os arquivos da pasta
processar_arquivos_pasta(pasta, conexao)

# Fechar a conexão com o banco de dados
conexao.close()
