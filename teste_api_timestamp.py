#!/usr/bin/env python3
"""
Teste para verificar como os timestamps estão sendo formatados na API
"""

import sqlite3
from datetime import datetime
import json

# Simular dados como se fosse a API
def testar_formatacao_api():
    print("=== TESTE DE FORMATAÇÃO DE TIMESTAMP NA API ===")
    
    # 1. Como o timestamp está sendo salvo no banco
    agora = datetime.now()
    timestamp_banco = agora.strftime('%Y-%m-%d %H:%M:%S')
    print(f"1. Timestamp salvo no banco: {timestamp_banco}")
    
    # 2. Como está sendo enviado para a API (código atual)
    dados_envio_atual = {
        "datetime": timestamp_banco,  # PROBLEMA: String simples
        "dwelltime": {
            "26057": {
                "inside": 1,
                "mean_secs": 60
            }
        }
    }
    print(f"2. JSON atual enviado para API:")
    print(json.dumps(dados_envio_atual, indent=2))
    
    # 3. Como deveria ser formatado (ISO 8601)
    timestamp_iso = agora.isoformat()
    dados_envio_correto = {
        "datetime": timestamp_iso,  # SOLUÇÃO: Formato ISO
        "dwelltime": {
            "26057": {
                "inside": 1,
                "mean_secs": 60
            }
        }
    }
    print(f"3. JSON CORRETO para API (ISO 8601):")
    print(json.dumps(dados_envio_correto, indent=2))
    
    # 4. Comparar diferentes formatos
    print(f"\n=== COMPARAÇÃO DE FORMATOS ===")
    print(f"Formato atual (problema): {timestamp_banco}")
    print(f"Formato ISO correto: {timestamp_iso}")
    print(f"Com timezone explícito: {agora.strftime('%Y-%m-%dT%H:%M:%S-03:00')}")
    
    return timestamp_banco, timestamp_iso

def verificar_banco_dados():
    print(f"\n=== VERIFICAÇÃO DO BANCO DE DADOS ===")
    try:
        conn = sqlite3.connect('yolo8.db')
        cursor = conn.cursor()
        
        # Ver alguns registros recentes
        cursor.execute("""SELECT id, timestamp, vehicle_code, tempo_permanencia 
                          FROM vehicle_counts 
                          WHERE count_out = 1 AND tempo_permanencia IS NOT NULL ORDER BY id DESC LIMIT 3""")
        
        registros = cursor.fetchall()
        print(f"Registros recentes no banco:")
        for registro in registros:
            id_reg, timestamp, vehicle_code, tempo = registro
            print(f"  ID: {id_reg}, Time: {timestamp}, Code: {vehicle_code}, Duration: {tempo}s")
            
            # Simular como seria enviado
            dados_api = {
                "datetime": timestamp,
                "dwelltime": {
                    str(vehicle_code): {
                        "inside": 1,
                        "mean_secs": int(tempo)
                    }
                }
            }
            print(f"  API JSON: {json.dumps(dados_api)}")
        
        conn.close()
        
    except Exception as e:
        print(f"Erro ao acessar banco: {e}")

if __name__ == "__main__":
    testar_formatacao_api()
    verificar_banco_dados()