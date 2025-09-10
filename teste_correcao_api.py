#!/usr/bin/env python3
"""
Teste da correção do timestamp na API
"""

import datetime
import json

def testar_correcao_timestamp():
    print("=== TESTE DA CORREÇÃO DO TIMESTAMP ===")
    
    # Simular dados do banco
    timestamp_banco = "2025-08-28 23:57:51"
    vehicle_code = 26074
    tempo_permanencia = 8.479755
    
    print(f"Dados originais do banco:")
    print(f"  Timestamp: {timestamp_banco}")
    print(f"  Vehicle Code: {vehicle_code}")
    print(f"  Tempo: {tempo_permanencia}s")
    
    # Aplicar a correção
    try:
        # Parsear timestamp do banco (formato: "2025-08-28 23:57:51")
        dt = datetime.datetime.strptime(timestamp_banco, "%Y-%m-%d %H:%M:%S")
        # Converter para ISO 8601 com timezone local (UTC-3)
        timestamp_iso = dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
    except ValueError:
        timestamp_iso = timestamp_banco
    
    # JSON que será enviado
    dados_envio = {
        "datetime": timestamp_iso,
        "dwelltime": {
            str(vehicle_code): {
                "inside": 1,
                "mean_secs": int(tempo_permanencia)
            }
        }
    }
    
    print(f"\n=== RESULTADO DA CORREÇÃO ===")
    print(f"Timestamp original: {timestamp_banco}")
    print(f"Timestamp corrigido: {timestamp_iso}")
    print(f"Diferença: Adicionado 'T' e timezone '-03:00'")
    
    print(f"\nJSON enviado para API:")
    print(json.dumps(dados_envio, indent=2))
    
    # Verificar se mantém a hora
    hora_original = timestamp_banco.split()[1]
    hora_corrigida = timestamp_iso.split('T')[1].split('-')[0]
    
    print(f"\n=== VERIFICAÇÃO ===")
    print(f"Hora original: {hora_original} (23:57:51)")  
    print(f"Hora corrigida: {hora_corrigida} (23:57:51)")
    print(f"Manteve a hora? {'✅ SIM' if hora_original == hora_corrigida else '❌ NÃO'}")
    
    return dados_envio

def comparar_formatos():
    print(f"\n=== COMPARAÇÃO DE TODOS OS FORMATOS ===")
    
    timestamp_banco = "2025-08-28 23:57:51"
    dt = datetime.datetime.strptime(timestamp_banco, "%Y-%m-%d %H:%M:%S")
    
    formatos = {
        "Original (problema)": timestamp_banco,
        "ISO simples": dt.isoformat(),
        "ISO com timezone -03:00": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "ISO com timezone UTC": dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "RFC 3339": dt.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
    }
    
    for nome, formato in formatos.items():
        print(f"{nome:20}: {formato}")

if __name__ == "__main__":
    testar_correcao_timestamp()
    comparar_formatos()