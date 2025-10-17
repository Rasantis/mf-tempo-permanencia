#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste para validar o novo controle de envio por registro individual
de tempos de permanência.

Testa:
1. Criação da nova estrutura de tabela
2. Inserção de registros com campo 'enviado' = 0
3. Busca de registros não enviados
4. Simulação de envio e marcação como enviado
5. Verificação de que registros enviados não aparecem mais na busca
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta

# Configurações de teste
TEST_DB = "teste_permanencia.db"
TEST_CLIENT_CODE = 9999

def limpar_teste():
    """Remove o banco de teste se existir."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        print("OK - Banco de teste anterior removido.")

def criar_estrutura_teste():
    """Cria a estrutura da tabela com o novo campo 'enviado'."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    
    # Criar tabela principal (vehicle_counts) com controle de envio
    cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      area TEXT,
                      vehicle_code INTEGER,
                      count_in INTEGER,
                      count_out INTEGER,
                      timestamp TEXT,
                      tempo_permanencia FLOAT,
                      enviado INTEGER DEFAULT 0)''')
    
    conn.commit()
    conn.close()
    print("OK - Estrutura da tabela criada com sucesso.")

def inserir_dados_teste():
    """Insere dados de teste na tabela."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    
    # Criar alguns registros de teste (somente saídas com tempo)
    test_data = [
        ('area_1', 26057, 0, 1, '2024-01-15 10:30:00', 15.5, 0),
        ('area_1', 26058, 0, 1, '2024-01-15 10:35:00', 22.3, 0),
        ('area_1', 26059, 0, 1, '2024-01-15 10:40:00', 8.7, 0),
        ('area_2', 26057, 0, 1, '2024-01-15 10:45:00', 31.2, 0),
        ('area_2', 26060, 0, 1, '2024-01-15 10:50:00', 12.9, 0),
        ('area_1', 26057, 1, 0, '2024-01-15 10:55:00', 18.0, 0)
    ]
    
    cursor.executemany(
        '''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
           VALUES (?, ?, ?, ?, ?, ?, ?)''', test_data)
    
    conn.commit()
    conn.close()
    print(f"OK - {len(test_data)} registros de teste inseridos.")

def buscar_nao_enviados():
    """Busca registros não enviados (enviado = 0)."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    
    query = "SELECT id, timestamp, vehicle_code, tempo_permanencia FROM vehicle_counts WHERE enviado = 0 AND tempo_permanencia IS NOT NULL ORDER BY timestamp"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    print(f"OK - {len(rows)} registros não enviados encontrados:")
    for row in rows:
        print(f"  ID: {row[0]}, Timestamp: {row[1]}, Vehicle: {row[2]}, Tempo: {row[3]}s")
    
    return rows

def marcar_como_enviado(record_id):
    """Marca um registro específico como enviado."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE vehicle_counts SET enviado = 1 WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    print(f"OK - Registro ID {record_id} marcado como enviado.")

def verificar_estrutura():
    """Verifica a estrutura da tabela."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(vehicle_counts)")
    columns = cursor.fetchall()
    conn.close()
    
    print("OK - Estrutura da tabela:")
    for col in columns:
        print(f"  {col[1]} ({col[2]}) - Default: {col[4]}")

def teste_compatibilidade_banco_antigo():
    """Testa a compatibilidade com bancos antigos (sem campo 'enviado')."""
    print("\nTestando compatibilidade com banco antigo...")
    
    # Criar banco sem o campo 'enviado' em vehicle_counts
    old_db = "teste_antigo.db"
    if os.path.exists(old_db):
        os.remove(old_db)
    
    conn = sqlite3.connect(old_db)
    cursor = conn.cursor()
    
    # Estrutura antiga (sem campo 'enviado')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      area TEXT,
                      vehicle_code INTEGER,
                      count_in INTEGER,
                      count_out INTEGER,
                      timestamp TEXT,
                      tempo_permanencia FLOAT)''')
    
    # Inserir um registro
    cursor.execute(
        '''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia)
           VALUES (?, ?, 0, 1, ?, ?)''', ('area_1', 26057, '2024-01-15 11:00:00', 45.6))
    
    conn.commit()
    
    # Simular o código de compatibilidade
    cursor.execute("PRAGMA table_info(vehicle_counts)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'enviado' not in columns:
        cursor.execute("ALTER TABLE vehicle_counts ADD COLUMN enviado INTEGER DEFAULT 0")
        conn.commit()
        print("OK - Coluna 'enviado' adicionada automaticamente ao banco antigo (vehicle_counts).")
    
    # Verificar que o registro existe e tem enviado = 0
    cursor.execute("SELECT id, enviado FROM vehicle_counts")
    result = cursor.fetchone()
    print(f"OK - Registro no banco antigo: ID={result[0]}, enviado={result[1]}")
    
    conn.close()
    os.remove(old_db)

def main():
    """Executa todos os testes."""
    print("Iniciando testes do novo controle de envio por registro...\n")
    
    # Teste 1: Limpeza e criação
    limpar_teste()
    criar_estrutura_teste()
    verificar_estrutura()
    
    # Teste 2: Inserção de dados
    print("\nTeste de inserção de dados...")
    inserir_dados_teste()
    
    # Teste 3: Busca de não enviados
    print("\nTeste de busca de registros não enviados...")
    registros = buscar_nao_enviados()
    
    # Teste 4: Marcar alguns como enviados
    print("\nTeste de marcação como enviado...")
    if registros:
        # Marcar os dois primeiros como enviados
        marcar_como_enviado(registros[0][0])
        marcar_como_enviado(registros[1][0])
    
    # Teste 5: Verificar que a busca retorna apenas os não enviados
    print("\nTeste de busca após marcação...")
    registros_restantes = buscar_nao_enviados()
    
    if len(registros_restantes) == len(registros) - 2:
        print("SUCESSO: Controle por registro funcionando corretamente!")
    else:
        print("ERRO: Problema no controle por registro.")
    
    # Teste 6: Compatibilidade com banco antigo
    teste_compatibilidade_banco_antigo()
    
    # Limpeza final
    limpar_teste()
    print("\nTodos os testes concluídos!")

if __name__ == "__main__":
    main()
