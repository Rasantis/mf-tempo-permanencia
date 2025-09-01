#!/usr/bin/env python3
"""
Script para corrigir registros com tempo_permanencia NULL na tabela vehicle_counts,
usando dados da tabela vehicle_permanence.
"""

import sqlite3
import os
import sys

def fix_null_permanence_records(db_path):
    """
    Corrige registros com tempo_permanencia NULL usando dados da vehicle_permanence.
    """
    print("Iniciando correção de registros NULL...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Contar quantos registros estão NULL
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NULL")
        null_count = cursor.fetchone()[0]
        print(f"Registros com tempo_permanencia NULL: {null_count}")
        
        if null_count == 0:
            print("Nenhum registro NULL encontrado!")
            return
        
        # Buscar registros de saída com tempo NULL
        cursor.execute('''SELECT id, area, vehicle_code, timestamp 
                          FROM vehicle_counts 
                          WHERE count_out = 1 AND tempo_permanencia IS NULL 
                          ORDER BY id DESC LIMIT 1000''')
        
        null_records = cursor.fetchall()
        print(f"Processando {len(null_records)} registros de saída...")
        
        updated_count = 0
        fallback_count = 0
        
        for record in null_records:
            record_id, area, vehicle_code, timestamp = record
            
            # Estratégia 1: Buscar tempo exato para o vehicle_code e área
            cursor.execute('''SELECT tempo_permanencia FROM vehicle_permanence 
                              WHERE area = ? AND vehicle_code = ? 
                              AND ABS(julianday(?) - julianday(timestamp)) * 24 * 60 < 15
                              ORDER BY ABS(julianday(?) - julianday(timestamp)) LIMIT 1''', 
                              (area, vehicle_code, timestamp, timestamp))
            
            exact_result = cursor.fetchone()
            if exact_result and exact_result[0] is not None:
                tempo = float(exact_result[0])
                
                # Atualizar o registro
                cursor.execute('''UPDATE vehicle_counts 
                                  SET tempo_permanencia = ? 
                                  WHERE id = ?''', (tempo, record_id))
                
                updated_count += 1
                if updated_count % 100 == 0:
                    print(f"Atualizados {updated_count} registros...")
                continue
            
            # Estratégia 2: Fallback - usar média dos tempos da área
            cursor.execute('''SELECT AVG(tempo_permanencia) FROM vehicle_permanence 
                              WHERE area = ? 
                              AND ABS(julianday(?) - julianday(timestamp)) * 24 * 60 < 60
                              AND tempo_permanencia > 1 AND tempo_permanencia < 300''', 
                              (area, timestamp))
            
            avg_result = cursor.fetchone()
            if avg_result and avg_result[0] is not None:
                tempo = float(avg_result[0])
                
                # Atualizar o registro
                cursor.execute('''UPDATE vehicle_counts 
                                  SET tempo_permanencia = ? 
                                  WHERE id = ?''', (tempo, record_id))
                
                fallback_count += 1
                updated_count += 1
                if updated_count % 100 == 0:
                    print(f"Atualizados {updated_count} registros...")
        
        # Commit das alterações
        conn.commit()
        
        print(f"\nResultados da correção:")
        print(f"- Registros atualizados com tempo exato: {updated_count - fallback_count}")
        print(f"- Registros atualizados com tempo médio: {fallback_count}")
        print(f"- Total de registros corrigidos: {updated_count}")
        
        # Verificar quantos ainda estão NULL
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NULL")
        remaining_null = cursor.fetchone()[0]
        print(f"- Registros NULL restantes: {remaining_null}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Erro ao processar banco de dados: {e}")

def show_statistics(db_path):
    """
    Mostra estatísticas dos dados após a correção.
    """
    print("\n" + "="*50)
    print("ESTATÍSTICAS APÓS CORREÇÃO")
    print("="*50)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Estatísticas gerais
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NOT NULL")
        with_time = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NULL")
        null_time = cursor.fetchone()[0]
        
        print(f"Total de registros: {total}")
        print(f"Com tempo de permanência: {with_time}")
        print(f"Com tempo NULL: {null_time}")
        print(f"Percentual corrigido: {(with_time/total*100):.1f}%")
        
        # Alguns exemplos
        cursor.execute("""SELECT area, vehicle_code, timestamp, tempo_permanencia, count_in, count_out 
                          FROM vehicle_counts 
                          WHERE tempo_permanencia IS NOT NULL 
                          ORDER BY id DESC LIMIT 5""")
        
        examples = cursor.fetchall()
        if examples:
            print(f"\nExemplos de registros corrigidos:")
            for ex in examples:
                print(f"  Área: {ex[0]}, Código: {ex[1]}, Tempo: {ex[3]:.2f}s, In: {ex[4]}, Out: {ex[5]}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Erro ao gerar estatísticas: {e}")

def main():
    db_path = "yolo8.db"
    
    if not os.path.exists(db_path):
        print(f"Erro: Arquivo de banco de dados não encontrado: {db_path}")
        sys.exit(1)
    
    print("CORREÇÃO DE REGISTROS COM TEMPO_PERMANENCIA NULL")
    print("="*50)
    
    # Executar correção
    fix_null_permanence_records(db_path)
    
    # Mostrar estatísticas
    show_statistics(db_path)
    
    print("\n" + "="*50)
    print("CORREÇÃO CONCLUÍDA!")
    print("Execute o sistema novamente para continuar salvando os tempos corretamente.")

if __name__ == "__main__":
    main()