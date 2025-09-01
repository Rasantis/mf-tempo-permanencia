#!/usr/bin/env python3
"""
Script de teste para verificar se o tempo de permanência está sendo salvo corretamente
na tabela vehicle_counts após as correções.
"""

import sqlite3
import os
import sys

def test_database_structure(db_path):
    """
    Verifica se a estrutura do banco de dados está correta.
    """
    print("Verificando estrutura do banco de dados...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar se a tabela vehicle_counts tem a coluna tempo_permanencia
        cursor.execute("PRAGMA table_info(vehicle_counts)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'tempo_permanencia' in columns:
            print("OK - Coluna 'tempo_permanencia' encontrada na tabela vehicle_counts")
        else:
            print("ERRO - Coluna 'tempo_permanencia' NAO encontrada na tabela vehicle_counts")
            return False
            
        # Verificar estrutura da tabela vehicle_permanence
        cursor.execute("PRAGMA table_info(vehicle_permanence)")
        columns_vp = [column[1] for column in cursor.fetchall()]
        
        required_columns = ['codigocliente', 'area', 'vehicle_code', 'timestamp', 'tempo_permanencia']
        missing_columns = [col for col in required_columns if col not in columns_vp]
        
        if missing_columns:
            print(f"ERRO - Colunas ausentes em vehicle_permanence: {missing_columns}")
            return False
        else:
            print("OK - Estrutura da tabela vehicle_permanence esta correta")
            
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"ERRO - Erro ao verificar estrutura do banco: {e}")
        return False

def test_recent_data(db_path):
    """
    Verifica os dados mais recentes nas tabelas.
    """
    print("\nVerificando dados recentes...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar dados recentes em vehicle_counts
        cursor.execute("""SELECT COUNT(*) as total, 
                          COUNT(tempo_permanencia) as com_tempo,
                          SUM(CASE WHEN tempo_permanencia IS NOT NULL THEN 1 ELSE 0 END) as nao_null
                          FROM vehicle_counts""")
        result = cursor.fetchone()
        
        print(f"vehicle_counts - Total de registros: {result[0]}")
        print(f"vehicle_counts - Registros com tempo_permanencia nao-NULL: {result[2]}")
        print(f"vehicle_counts - Percentual com tempo: {(result[2]/result[0]*100):.1f}%" if result[0] > 0 else "0%")
        
        # Verificar registros mais recentes com tempo de permanência
        cursor.execute("""SELECT id, area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia 
                          FROM vehicle_counts 
                          WHERE tempo_permanencia IS NOT NULL 
                          ORDER BY id DESC LIMIT 5""")
        
        recent_with_time = cursor.fetchall()
        
        if recent_with_time:
            print("\nRegistros recentes com tempo de permanencia:")
            for record in recent_with_time:
                print(f"   ID: {record[0]}, Area: {record[1]}, Codigo: {record[2]}, "
                      f"In: {record[3]}, Out: {record[4]}, Tempo: {record[6]:.2f}s, "
                      f"Data: {record[5]}")
        else:
            print("Nenhum registro com tempo de permanencia encontrado")
            
        # Verificar dados em vehicle_permanence
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence")
        vp_count = cursor.fetchone()[0]
        print(f"\nvehicle_permanence - Total de registros: {vp_count}")
        
        cursor.execute("""SELECT area, vehicle_code, timestamp, tempo_permanencia 
                          FROM vehicle_permanence 
                          ORDER BY id DESC LIMIT 5""")
        recent_permanence = cursor.fetchall()
        
        if recent_permanence:
            print("Registros recentes em vehicle_permanence:")
            for record in recent_permanence:
                print(f"   Area: {record[0]}, Codigo: {record[1]}, "
                      f"Tempo: {record[3]:.2f}s, Data: {record[2]}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"ERRO - Erro ao verificar dados: {e}")

def main():
    # Caminho para o banco de dados
    db_path = "yolo8.db"
    
    if not os.path.exists(db_path):
        print(f"ERRO - Arquivo de banco de dados nao encontrado: {db_path}")
        sys.exit(1)
        
    print("TESTE DO SISTEMA DE TEMPO DE PERMANENCIA")
    print("=" * 50)
    
    # Teste 1: Verificar estrutura
    structure_ok = test_database_structure(db_path)
    
    # Teste 2: Verificar dados
    test_recent_data(db_path)
    
    print("\n" + "=" * 50)
    if structure_ok:
        print("OK - Estrutura do banco esta correta")
        print("Se ainda nao ha dados com tempo de permanencia, execute o sistema")
        print("   e aguarde que veiculos saiam das areas monitoradas.")
    else:
        print("ERRO - Problemas na estrutura do banco detectados")
        print("Execute novamente o sistema para corrigir a estrutura")

if __name__ == "__main__":
    main()