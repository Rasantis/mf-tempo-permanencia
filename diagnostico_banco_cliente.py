#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIAGNÓSTICO COMPLETO DO BANCO DE DADOS DO CLIENTE
Analisa e identifica exatamente as diferenças entre Local e MFWeb
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

def conectar_banco(db_path):
    """Conecta ao banco e verifica se existe."""
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        print(f"ERRO ao conectar no banco {db_path}: {e}")
        return None

def verificar_estrutura(conn):
    """Verifica estrutura completa do banco."""
    cursor = conn.cursor()
    
    print("=" * 60)
    print("ESTRUTURA DO BANCO")
    print("=" * 60)
    
    # Listar tabelas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tabelas = cursor.fetchall()
    print(f"Tabelas: {[t[0] for t in tabelas]}")
    
    # Verificar tabela vehicle_permanence
    if any('vehicle_permanence' in t for t in tabelas):
        cursor.execute("PRAGMA table_info(vehicle_permanence)")
        colunas = cursor.fetchall()
        print(f"\nColunas da tabela vehicle_permanence:")
        for col in colunas:
            default = f" DEFAULT {col[4]}" if col[4] else ""
            print(f"  {col[1]} {col[2]}{default}")
        
        # Verificar índices
        cursor.execute("PRAGMA index_list(vehicle_permanence)")
        indices = cursor.fetchall()
        if indices:
            print(f"\nÍndices: {[idx[1] for idx in indices]}")
    
    return True

def contagem_detalhada(conn):
    """Faz contagem detalhada dos registros."""
    cursor = conn.cursor()
    
    print("\n" + "=" * 60)
    print("CONTAGEM DETALHADA")
    print("=" * 60)
    
    try:
        # Total geral
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence")
        total = cursor.fetchone()[0]
        print(f"Total de registros: {total:,}")
        
        # Verificar se tem campo enviado
        cursor.execute("PRAGMA table_info(vehicle_permanence)")
        colunas = [col[1] for col in cursor.fetchall()]
        tem_enviado = 'enviado' in colunas
        
        print(f"Campo 'enviado' presente: {'SIM' if tem_enviado else 'NÃO'}")
        
        if tem_enviado:
            cursor.execute("SELECT enviado, COUNT(*) FROM vehicle_permanence GROUP BY enviado")
            por_enviado = cursor.fetchall()
            print("\nPor status de envio:")
            for status, qtd in por_enviado:
                status_nome = "Não enviado" if status == 0 else "Enviado" if status == 1 else f"Status {status}"
                print(f"  {status_nome}: {qtd:,}")
        
        # Por código de cliente
        cursor.execute("SELECT codigocliente, COUNT(*) FROM vehicle_permanence GROUP BY codigocliente ORDER BY COUNT(*) DESC")
        por_cliente = cursor.fetchall()
        print("\nPor código de cliente:")
        for cliente, qtd in por_cliente:
            print(f"  Cliente {cliente}: {qtd:,}")
        
        # Por vehicle_code
        cursor.execute("SELECT vehicle_code, COUNT(*) FROM vehicle_permanence WHERE vehicle_code IS NOT NULL GROUP BY vehicle_code ORDER BY COUNT(*) DESC")
        por_vehicle = cursor.fetchall()
        print(f"\nPor vehicle_code (top 10):")
        for vehicle, qtd in por_vehicle[:10]:
            print(f"  {vehicle}: {qtd:,}")
        
        # Por período (últimos 30 dias)
        cursor.execute("""
        SELECT DATE(timestamp) as data, COUNT(*) 
        FROM vehicle_permanence 
        WHERE timestamp >= date('now', '-30 days')
        GROUP BY DATE(timestamp) 
        ORDER BY data DESC 
        LIMIT 15
        """)
        por_dia = cursor.fetchall()
        print(f"\nPor dia (últimos 15 dias):")
        for data, qtd in por_dia:
            print(f"  {data}: {qtd:,}")
            
    except Exception as e:
        print(f"ERRO na contagem detalhada: {e}")

def detectar_problemas(conn):
    """Detecta problemas específicos que podem causar diferenças."""
    cursor = conn.cursor()
    
    print("\n" + "=" * 60)
    print("DETECÇÃO DE PROBLEMAS")
    print("=" * 60)
    
    problemas = []
    
    try:
        # 1. Registros duplicados
        cursor.execute("""
        SELECT timestamp, vehicle_code, COUNT(*) as qtd
        FROM vehicle_permanence 
        GROUP BY timestamp, vehicle_code 
        HAVING COUNT(*) > 1 
        ORDER BY qtd DESC
        LIMIT 20
        """)
        duplicados = cursor.fetchall()
        
        if duplicados:
            total_duplicados = sum(d[2] - 1 for d in duplicados)  # -1 porque 1 é original
            problemas.append(f"Registros duplicados: {len(duplicados)} grupos, {total_duplicados} extras")
            print(f"❌ DUPLICADOS: {len(duplicados)} grupos encontrados")
            print("   Exemplos:")
            for i, (ts, vc, qtd) in enumerate(duplicados[:5]):
                print(f"   {i+1}. {ts}, vehicle {vc}: {qtd} registros")
        else:
            print("✅ Sem duplicados detectados")
        
        # 2. Vehicle_code inválidos
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE vehicle_code IS NULL OR vehicle_code <= 0")
        vehicle_invalidos = cursor.fetchone()[0]
        if vehicle_invalidos > 0:
            problemas.append(f"Vehicle_codes inválidos: {vehicle_invalidos}")
            print(f"❌ VEHICLE_CODE INVÁLIDO: {vehicle_invalidos} registros")
        else:
            print("✅ Todos vehicle_codes válidos")
        
        # 3. Tempos muito baixos
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE tempo_permanencia < 1")
        tempo_baixo = cursor.fetchone()[0]
        if tempo_baixo > 0:
            problemas.append(f"Tempos < 1s: {tempo_baixo}")
            print(f"❌ TEMPO BAIXO: {tempo_baixo} registros com < 1 segundo")
        else:
            print("✅ Todos tempos >= 1 segundo")
        
        # 4. Timestamps inválidos
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE timestamp IS NULL OR timestamp = ''")
        ts_invalidos = cursor.fetchone()[0]
        if ts_invalidos > 0:
            problemas.append(f"Timestamps inválidos: {ts_invalidos}")
            print(f"❌ TIMESTAMP INVÁLIDO: {ts_invalidos} registros")
        else:
            print("✅ Todos timestamps válidos")
        
        # 5. Registros órfãos (sem codigocliente)
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE codigocliente IS NULL")
        sem_cliente = cursor.fetchone()[0]
        if sem_cliente > 0:
            problemas.append(f"Sem código cliente: {sem_cliente}")
            print(f"❌ SEM CLIENTE: {sem_cliente} registros")
        else:
            print("✅ Todos registros têm código cliente")
        
        # 6. Análise de tempos extremos
        cursor.execute("SELECT MIN(tempo_permanencia), MAX(tempo_permanencia), AVG(tempo_permanencia) FROM vehicle_permanence")
        min_tempo, max_tempo, avg_tempo = cursor.fetchone()
        print(f"\n📊 ESTATÍSTICAS DE TEMPO:")
        print(f"   Mínimo: {min_tempo:.2f}s")
        print(f"   Máximo: {max_tempo:.2f}s") 
        print(f"   Média: {avg_tempo:.2f}s")
        
        if max_tempo > 3600:  # > 1 hora
            cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE tempo_permanencia > 3600")
            muito_altos = cursor.fetchone()[0]
            print(f"   ⚠️  {muito_altos} registros com > 1 hora")
        
        # 7. Resumo de registros válidos para envio
        cursor.execute("""
        SELECT COUNT(*) FROM vehicle_permanence 
        WHERE vehicle_code IS NOT NULL 
        AND vehicle_code > 0 
        AND tempo_permanencia >= 1 
        AND timestamp IS NOT NULL 
        AND timestamp != ''
        AND codigocliente IS NOT NULL
        """)
        registros_validos = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vehicle_permanence")
        total_registros = cursor.fetchone()[0]
        
        print(f"\n📈 RESUMO:")
        print(f"   Total de registros: {total_registros:,}")
        print(f"   Registros válidos: {registros_validos:,}")
        print(f"   Taxa de validade: {(registros_validos/total_registros)*100:.1f}%")
        
        invalidos = total_registros - registros_validos
        if invalidos > 0:
            print(f"   ❌ Registros inválidos: {invalidos:,}")
        
        return problemas
        
    except Exception as e:
        print(f"ERRO na detecção de problemas: {e}")
        return []

def analise_periodo_recente(conn, dias=7):
    """Analisa período recente em detalhes."""
    cursor = conn.cursor()
    
    print(f"\n" + "=" * 60)
    print(f"ANÁLISE PERÍODO RECENTE ({dias} DIAS)")
    print("=" * 60)
    
    try:
        # Registros dos últimos X dias
        cursor.execute("""
        SELECT DATE(timestamp) as data,
               COUNT(*) as total,
               COUNT(DISTINCT vehicle_code) as vehicles_unicos,
               MIN(tempo_permanencia) as min_tempo,
               MAX(tempo_permanencia) as max_tempo,
               AVG(tempo_permanencia) as avg_tempo
        FROM vehicle_permanence 
        WHERE timestamp >= date('now', '-{} days')
        GROUP BY DATE(timestamp)
        ORDER BY data DESC
        """.format(dias))
        
        dados_recentes = cursor.fetchall()
        
        if dados_recentes:
            print("Detalhes por dia:")
            for data, total, unicos, min_t, max_t, avg_t in dados_recentes:
                print(f"  {data}: {total:,} registros, {unicos} vehicles únicos")
                print(f"    Tempo: {min_t:.1f}s - {max_t:.1f}s (média: {avg_t:.1f}s)")
        else:
            print(f"Nenhum registro encontrado nos últimos {dias} dias")
            
        # Verificar se há lacunas nos dados
        if dados_recentes:
            print("\n🔍 Verificando continuidade dos dados...")
            datas_esperadas = []
            data_inicio = datetime.now() - timedelta(days=dias-1)
            for i in range(dias):
                data_esperada = (data_inicio + timedelta(days=i)).strftime('%Y-%m-%d')
                datas_esperadas.append(data_esperada)
            
            datas_encontradas = [d[0] for d in dados_recentes]
            lacunas = [d for d in datas_esperadas if d not in datas_encontradas]
            
            if lacunas:
                print(f"   ❌ Lacunas nos dados: {len(lacunas)} dias sem registros")
                for lacuna in lacunas:
                    print(f"      Sem dados em: {lacuna}")
            else:
                print("   ✅ Dados contínuos nos últimos dias")
                
    except Exception as e:
        print(f"ERRO na análise de período recente: {e}")

def gerar_comandos_limpeza(problemas):
    """Gera comandos SQL para limpeza dos problemas encontrados."""
    if not problemas:
        return
    
    print("\n" + "=" * 60)
    print("COMANDOS DE LIMPEZA RECOMENDADOS")
    print("=" * 60)
    print("⚠️  ATENÇÃO: Faça backup antes de executar!")
    
    # Para duplicados
    if any('duplicado' in p for p in problemas):
        print("\n-- Remover registros duplicados (manter o mais antigo)")
        print("""DELETE FROM vehicle_permanence 
WHERE id NOT IN (
    SELECT MIN(id) 
    FROM vehicle_permanence 
    GROUP BY timestamp, vehicle_code, tempo_permanencia
);""")
    
    # Para vehicle_codes inválidos
    if any('Vehicle_code' in p for p in problemas):
        print("\n-- Remover registros com vehicle_code inválido")
        print("""DELETE FROM vehicle_permanence 
WHERE vehicle_code IS NULL OR vehicle_code <= 0;""")
    
    # Para tempos baixos
    if any('Tempos' in p for p in problemas):
        print("\n-- Remover registros com tempo muito baixo")
        print("""DELETE FROM vehicle_permanence 
WHERE tempo_permanencia < 1;""")
    
    # Para timestamps inválidos
    if any('Timestamp' in p for p in problemas):
        print("\n-- Remover registros com timestamp inválido")
        print("""DELETE FROM vehicle_permanence 
WHERE timestamp IS NULL OR timestamp = '';""")
    
    # Adicionar campo enviado se não existir
    print("\n-- Adicionar campo 'enviado' se não existir")
    print("""ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0;""")
    
    print("\n-- Verificar quantos registros serão removidos (EXECUTE PRIMEIRO!)")
    print("""SELECT 'Total atual' as tipo, COUNT(*) as quantidade FROM vehicle_permanence
UNION ALL
SELECT 'Após limpeza' as tipo, COUNT(*) as quantidade 
FROM vehicle_permanence 
WHERE vehicle_code IS NOT NULL 
  AND vehicle_code > 0 
  AND tempo_permanencia >= 1 
  AND timestamp IS NOT NULL 
  AND timestamp != '';""")

def main():
    parser = argparse.ArgumentParser(description='Diagnóstico completo do banco de permanência')
    parser.add_argument('--db_path', type=str, default='yolo8.db', 
                       help='Caminho para o banco SQLite')
    parser.add_argument('--dias', type=int, default=7,
                       help='Número de dias para análise recente')
    args = parser.parse_args()
    
    print("DIAGNÓSTICO COMPLETO DO BANCO DE DADOS")
    print(f"Banco: {args.db_path}")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    conn = conectar_banco(args.db_path)
    if not conn:
        return
    
    try:
        verificar_estrutura(conn)
        contagem_detalhada(conn)
        problemas = detectar_problemas(conn)
        analise_periodo_recente(conn, args.dias)
        
        print("\n" + "=" * 60)
        print("RESUMO DOS PROBLEMAS ENCONTRADOS")
        print("=" * 60)
        
        if problemas:
            print("❌ Problemas que podem causar diferenças:")
            for i, problema in enumerate(problemas, 1):
                print(f"  {i}. {problema}")
            
            gerar_comandos_limpeza(problemas)
        else:
            print("✅ Nenhum problema detectado!")
            print("   O banco parece estar íntegro.")
        
        print("\n" + "=" * 60)
        print("DIAGNÓSTICO CONCLUÍDO")
        print("=" * 60)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()