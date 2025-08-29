#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIPT PARA ANALISAR DIFERENÇAS DE CONTAGEM ENTRE BANCO LOCAL E MFWEB

Este script investiga possíveis causas das diferenças:
- Registros duplicados
- Registros com vehicle_code inválido
- Registros com tempo < 1s
- Registros não enviados por falhas
- Timestamps problemáticos
"""

import sqlite3
import argparse
import pandas as pd
from datetime import datetime, timedelta
from collections import Counter

class AnalisadorContagem:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
    
    def verificar_estrutura_banco(self):
        """Verifica a estrutura atual do banco."""
        print("=" * 60)
        print("ESTRUTURA DO BANCO DE DADOS")
        print("=" * 60)
        
        # Verificar tabelas existentes
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = self.cursor.fetchall()
        print(f"Tabelas encontradas: {[t[0] for t in tabelas]}")
        
        # Verificar estrutura da tabela vehicle_permanence
        if any('vehicle_permanence' in t for t in tabelas):
            self.cursor.execute("PRAGMA table_info(vehicle_permanence)")
            colunas = self.cursor.fetchall()
            print(f"\nColunas da tabela vehicle_permanence:")
            for col in colunas:
                print(f"  {col[1]} ({col[2]}) - Default: {col[4]}")
            
            # Verificar se tem campo 'enviado'
            tem_campo_enviado = any('enviado' in col for col in colunas)
            print(f"\nCampo 'enviado' presente: {'SIM' if tem_campo_enviado else 'NÃO'}")
            
            if not tem_campo_enviado:
                print("ATENÇÃO: Campo 'enviado' não existe! Banco precisa ser atualizado.")
        else:
            print("ERRO: Tabela 'vehicle_permanence' não encontrada!")
    
    def contagem_geral(self):
        """Análise geral de contagem."""
        print("\n" + "=" * 60)
        print("CONTAGEM GERAL")
        print("=" * 60)
        
        try:
            # Total geral
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence")
            total = self.cursor.fetchone()[0]
            print(f"Total de registros: {total}")
            
            # Verificar se campo enviado existe
            self.cursor.execute("PRAGMA table_info(vehicle_permanence)")
            colunas = [col[1] for col in self.cursor.fetchall()]
            tem_enviado = 'enviado' in colunas
            
            if tem_enviado:
                # Com campo enviado
                self.cursor.execute("SELECT enviado, COUNT(*) FROM vehicle_permanence GROUP BY enviado")
                por_status = self.cursor.fetchall()
                print("Registros por status de envio:")
                for status, qtd in por_status:
                    status_text = "Não enviado" if status == 0 else "Enviado" if status == 1 else f"Status {status}"
                    print(f"  {status_text}: {qtd}")
            else:
                print("Campo 'enviado' não existe - todos os registros serão considerados não enviados")
            
            # Por período
            self.cursor.execute("""SELECT DATE(timestamp) as data, COUNT(*) as qtd 
                                 FROM vehicle_permanence 
                                 GROUP BY DATE(timestamp) 
                                 ORDER BY data DESC 
                                 LIMIT 10""")
            por_dia = self.cursor.fetchall()
            print(f"\nRegistros por dia (últimos 10 dias):")
            for data, qtd in por_dia:
                print(f"  {data}: {qtd} registros")
            
        except Exception as e:
            print(f"ERRO na contagem geral: {e}")
    
    def analisar_duplicados(self):
        """Analisa registros duplicados."""
        print("\n" + "=" * 60)
        print("ANÁLISE DE REGISTROS DUPLICADOS")
        print("=" * 60)
        
        try:
            # Duplicados por timestamp + vehicle_code
            query = """
            SELECT timestamp, vehicle_code, COUNT(*) as qtd_duplicadas,
                   GROUP_CONCAT(id) as ids
            FROM vehicle_permanence 
            GROUP BY timestamp, vehicle_code 
            HAVING COUNT(*) > 1
            ORDER BY qtd_duplicadas DESC, timestamp DESC
            """
            
            self.cursor.execute(query)
            duplicados = self.cursor.fetchall()
            
            if duplicados:
                print(f"ENCONTRADOS {len(duplicados)} GRUPOS DE REGISTROS DUPLICADOS!")
                total_duplicados = sum(d[2] - 1 for d in duplicados)  # -1 porque 1 é o original
                print(f"Total de registros duplicados extras: {total_duplicados}")
                
                print("\nDetalhes dos duplicados:")
                for i, (timestamp, vehicle_code, qtd, ids) in enumerate(duplicados[:20]):  # Mostra só os primeiros 20
                    print(f"  {i+1}. Timestamp: {timestamp}, Vehicle: {vehicle_code}")
                    print(f"      Quantidade: {qtd}, IDs: {ids}")
                
                if len(duplicados) > 20:
                    print(f"  ... e mais {len(duplicados) - 20} grupos duplicados")
                
                # Duplicados por período
                self.cursor.execute("""
                SELECT DATE(timestamp) as data, 
                       COUNT(*) - COUNT(DISTINCT timestamp, vehicle_code) as duplicados_extras
                FROM vehicle_permanence 
                GROUP BY DATE(timestamp) 
                HAVING duplicados_extras > 0
                ORDER BY data DESC
                """)
                duplicados_por_dia = self.cursor.fetchall()
                
                if duplicados_por_dia:
                    print(f"\nDuplicados por dia:")
                    for data, extras in duplicados_por_dia:
                        print(f"  {data}: {extras} duplicados extras")
            else:
                print("Nenhum registro duplicado encontrado.")
                
        except Exception as e:
            print(f"ERRO na análise de duplicados: {e}")
    
    def analisar_registros_invalidos(self):
        """Analisa registros com dados inválidos."""
        print("\n" + "=" * 60)
        print("ANÁLISE DE REGISTROS INVÁLIDOS")
        print("=" * 60)
        
        try:
            # Vehicle_code nulo ou inválido
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE vehicle_code IS NULL")
            nulos = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE vehicle_code <= 0")
            invalidos = self.cursor.fetchone()[0]
            
            print(f"Vehicle_code nulo: {nulos}")
            print(f"Vehicle_code <= 0: {invalidos}")
            
            # Tempo de permanência muito baixo
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE tempo_permanencia < 1")
            tempo_baixo = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE tempo_permanencia >= 1")
            tempo_valido = self.cursor.fetchone()[0]
            
            print(f"Tempo < 1 segundo: {tempo_baixo}")
            print(f"Tempo >= 1 segundo: {tempo_valido}")
            
            # Timestamps problemáticos
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_permanence WHERE timestamp IS NULL OR timestamp = ''")
            timestamp_invalido = self.cursor.fetchone()[0]
            print(f"Timestamp inválido: {timestamp_invalido}")
            
            # Registros que podem ser considerados válidos para envio
            self.cursor.execute("""SELECT COUNT(*) FROM vehicle_permanence 
                                 WHERE vehicle_code IS NOT NULL 
                                 AND vehicle_code > 0 
                                 AND tempo_permanencia >= 1
                                 AND timestamp IS NOT NULL 
                                 AND timestamp != ''""")
            registros_validos = self.cursor.fetchone()[0]
            print(f"\nRegistros teoricamente válidos para envio: {registros_validos}")
            
        except Exception as e:
            print(f"ERRO na análise de registros inválidos: {e}")
    
    def analisar_por_cliente(self):
        """Analisa registros por código de cliente."""
        print("\n" + "=" * 60)
        print("ANÁLISE POR CÓDIGO DE CLIENTE")
        print("=" * 60)
        
        try:
            self.cursor.execute("""SELECT codigocliente, COUNT(*) as qtd 
                                 FROM vehicle_permanence 
                                 GROUP BY codigocliente 
                                 ORDER BY qtd DESC""")
            por_cliente = self.cursor.fetchall()
            
            print("Registros por código de cliente:")
            for cliente, qtd in por_cliente:
                print(f"  Cliente {cliente}: {qtd} registros")
                
        except Exception as e:
            print(f"ERRO na análise por cliente: {e}")
    
    def analisar_por_vehicle_code(self):
        """Analisa distribuição por vehicle_code."""
        print("\n" + "=" * 60)
        print("ANÁLISE POR VEHICLE_CODE")
        print("=" * 60)
        
        try:
            self.cursor.execute("""SELECT vehicle_code, COUNT(*) as qtd 
                                 FROM vehicle_permanence 
                                 WHERE vehicle_code IS NOT NULL
                                 GROUP BY vehicle_code 
                                 ORDER BY qtd DESC""")
            por_vehicle = self.cursor.fetchall()
            
            print("Registros por vehicle_code:")
            for vehicle, qtd in por_vehicle:
                print(f"  Vehicle {vehicle}: {qtd} registros")
                
        except Exception as e:
            print(f"ERRO na análise por vehicle_code: {e}")
    
    def sugerir_limpeza(self):
        """Sugere comandos para limpeza de dados."""
        print("\n" + "=" * 60)
        print("SUGESTÕES DE LIMPEZA")
        print("=" * 60)
        
        print("Para remover registros duplicados:")
        print("""
DELETE FROM vehicle_permanence 
WHERE id NOT IN (
    SELECT MIN(id) 
    FROM vehicle_permanence 
    GROUP BY timestamp, vehicle_code, tempo_permanencia
);
""")
        
        print("Para remover registros inválidos:")
        print("""
DELETE FROM vehicle_permanence 
WHERE vehicle_code IS NULL 
   OR vehicle_code <= 0 
   OR tempo_permanencia < 1 
   OR timestamp IS NULL 
   OR timestamp = '';
""")
        
        print("Para adicionar campo 'enviado' se não existir:")
        print("""
ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0;
""")
    
    def relatorio_completo(self):
        """Gera relatório completo."""
        print("RELATÓRIO DE ANÁLISE DE DIFERENÇAS DE CONTAGEM")
        print("Data/Hora:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Banco analisado:", self.db_path)
        
        self.verificar_estrutura_banco()
        self.contagem_geral()
        self.analisar_duplicados()
        self.analisar_registros_invalidos()
        self.analisar_por_cliente()
        self.analisar_por_vehicle_code()
        self.sugerir_limpeza()
        
        print("\n" + "=" * 60)
        print("ANÁLISE CONCLUÍDA")
        print("=" * 60)
    
    def close(self):
        """Fecha conexão com banco."""
        self.conn.close()

def main():
    parser = argparse.ArgumentParser(description='Analisa diferenças de contagem no banco de permanência')
    parser.add_argument('--db_path', type=str, default='yolo8.db', 
                       help='Caminho para o banco de dados SQLite')
    args = parser.parse_args()
    
    try:
        analisador = AnalisadorContagem(args.db_path)
        analisador.relatorio_completo()
        analisador.close()
        
    except FileNotFoundError:
        print(f"ERRO: Arquivo de banco não encontrado: {args.db_path}")
        print("Verifique se o caminho está correto.")
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    main()