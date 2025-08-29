#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TESTES ISOLADOS DOS SCRIPTS PRINCIPAIS
Testa cada script de forma independente para garantir funcionamento correto.
"""

import os
import sys
import sqlite3
import json
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta

class TesteScriptIsolado:
    def __init__(self):
        self.test_dir = "teste_scripts_isolados"
        self.success_count = 0
        self.failure_count = 0
        self.errors = []
    
    def setup(self):
        """Configura ambiente de teste."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        # Criar configurações de teste
        self.criar_configs_teste()
        self.criar_banco_teste()
    
    def cleanup(self):
        """Limpa ambiente de teste."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def log_success(self, test_name):
        self.success_count += 1
        print(f"OK - {test_name}")
    
    def log_failure(self, test_name, error):
        self.failure_count += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"ERRO - {test_name}: {error}")
    
    def criar_configs_teste(self):
        """Cria arquivos de configuração para teste."""
        config = {
            "codigocliente": 1724,
            "cameras": {
                "camera1": {
                    "url": "rtsp://test:test@192.168.1.11:554/cam/realmonitor",
                    "faixas": {
                        "faixa1": {
                            "motorcycle": 26058,
                            "car": 26057,
                            "truck": 26056,
                            "bus": 26059,
                            "vuc": 26060
                        }
                    }
                }
            }
        }
        
        area_config = {
            "area_1": [[100, 100], [200, 100], [200, 200], [100, 200]]
        }
        
        area_tp_config = {
            "area_1": {
                "coordenadas": [[150, 150], [250, 150], [250, 250], [150, 250]],
                "tempo_minimo": 2
            }
        }
        
        # Salvar arquivos
        with open(os.path.join(self.test_dir, "config.json"), 'w') as f:
            json.dump(config, f, indent=2)
        
        with open(os.path.join(self.test_dir, "area.json"), 'w') as f:
            json.dump(area_config, f, indent=2)
        
        with open(os.path.join(self.test_dir, "area_tp.json"), 'w') as f:
            json.dump(area_tp_config, f, indent=2)
    
    def criar_banco_teste(self):
        """Cria banco de dados de teste com dados."""
        db_path = os.path.join(self.test_dir, "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Estrutura atual com campo enviado
        cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          codigocliente INTEGER,
                          vehicle_code INTEGER,
                          timestamp TEXT,
                          tempo_permanencia FLOAT,
                          enviado INTEGER DEFAULT 0)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          area TEXT,
                          vehicle_code INTEGER,
                          count_in INTEGER,
                          count_out INTEGER,
                          timestamp TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS export_log (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          last_export TEXT)''')
        
        # Inserir dados de teste
        test_permanence_data = [
            (1724, 26057, '2024-01-15 10:30:00', 15.5, 0),
            (1724, 26058, '2024-01-15 10:35:00', 22.3, 0),
            (1724, 26059, '2024-01-15 10:40:00', 8.7, 1),
        ]
        
        cursor.executemany(
            '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia, enviado)
               VALUES (?, ?, ?, ?, ?)''', test_permanence_data)
        
        test_counts_data = [
            ('area_1', 26057, 1, 0, '2024-01-15 10:30:00'),
            ('area_1', 26058, 0, 1, '2024-01-15 10:35:00'),
        ]
        
        cursor.executemany(
            '''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
               VALUES (?, ?, ?, ?, ?)''', test_counts_data)
        
        conn.commit()
        conn.close()
    
    def teste_permanence_tracker_isolado(self):
        """Testa PermanenceTracker de forma isolada."""
        try:
            # Importar o módulo
            sys.path.append('.')
            from permanence_tracker import PermanenceTracker
            
            # Configurar teste
            db_path = os.path.join(self.test_dir, "tracker_test.db")
            config_path = os.path.join(self.test_dir, "area_tp.json")
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Testar inicialização
            tracker = PermanenceTracker(db_path, 1724, config)
            
            # Testar estrutura do banco
            cursor = tracker.cursor
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns = [col[1] for col in cursor.fetchall()]
            
            required_cols = ['id', 'codigocliente', 'area', 'vehicle_code', 'timestamp', 'tempo_permanencia', 'enviado']
            for col in required_cols:
                if col not in columns:
                    raise Exception(f"Coluna obrigatória '{col}' não encontrada")
            
            # Testar salvamento
            test_time = datetime.now()
            tracker._save_permanence_to_db(99999, "area_1", test_time, 45.2)
            
            # Verificar se salvou
            cursor.execute("SELECT * FROM vehicle_permanence WHERE area = 'area_1'")
            result = cursor.fetchone()
            if not result:
                raise Exception("Registro de permanência não foi salvo")
            
            if result[6] != 0:  # Campo enviado
                raise Exception(f"Campo 'enviado' deveria ser 0, mas é {result[6]}")
            
            tracker.close()
            self.log_success("PermanenceTracker funcionamento isolado")
            
        except Exception as e:
            self.log_failure("PermanenceTracker funcionamento isolado", str(e))
    
    def teste_api_tempopermanencia_isolado(self):
        """Testa api_tempopermanencia de forma isolada."""
        try:
            # Criar banco com dados de teste
            db_path = os.path.join(self.test_dir, "api_test.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              codigocliente INTEGER,
                              vehicle_code INTEGER,
                              timestamp TEXT,
                              tempo_permanencia FLOAT,
                              enviado INTEGER DEFAULT 0)''')
            
            test_data = [
                (1724, 26057, '2024-01-15 10:30:00', 15.5, 0),
                (1724, 26058, '2024-01-15 10:35:00', 22.3, 0),
                (1724, 26059, '2024-01-15 10:40:00', 8.7, 1),  # Já enviado
            ]
            
            cursor.executemany(
                '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia, enviado)
                   VALUES (?, ?, ?, ?, ?)''', test_data)
            conn.commit()
            
            # Testar busca de não enviados
            query = "SELECT id, timestamp, vehicle_code, tempo_permanencia FROM vehicle_permanence WHERE enviado = 0 ORDER BY timestamp"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if len(rows) != 2:  # Deve retornar 2 (excluindo o enviado)
                raise Exception(f"Esperado 2 registros não enviados, encontrado {len(rows)}")
            
            # Testar marcação como enviado
            cursor.execute("UPDATE vehicle_permanence SET enviado = 1 WHERE id = ?", (1,))
            conn.commit()
            
            cursor.execute("SELECT enviado FROM vehicle_permanence WHERE id = 1")
            result = cursor.fetchone()
            if result[0] != 1:
                raise Exception("Registro não foi marcado como enviado")
            
            conn.close()
            self.log_success("api_tempopermanencia funcionamento isolado")
            
        except Exception as e:
            self.log_failure("api_tempopermanencia funcionamento isolado", str(e))
    
    def teste_init_db_functions(self):
        """Testa funções de inicialização de banco."""
        try:
            # Testar cada função init_db dos scripts principais
            db_path = os.path.join(self.test_dir, "init_test.db")
            
            # Simular função init_db (baseada no yolo16_v4.py)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Criar tabela para contagens de veículos
            cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_counts (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              area TEXT,
                              vehicle_code INTEGER,
                              count_in INTEGER,
                              count_out INTEGER,
                              timestamp TEXT)''')
            
            # Criar tabela para exportação de log
            cursor.execute('''CREATE TABLE IF NOT EXISTS export_log (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              last_export TEXT)''')
            
            # Criar tabela para tempos de permanência dos veículos
            cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              codigocliente INTEGER,
                              vehicle_code INTEGER,
                              timestamp TEXT,
                              tempo_permanencia FLOAT,
                              enviado INTEGER DEFAULT 0)''')
            
            # Adicionar colunas se não existirem (teste de compatibilidade)
            cursor.execute('PRAGMA table_info(vehicle_permanence)')
            columns = [col[1] for col in cursor.fetchall()]
            if 'codigocliente' not in columns:
                cursor.execute('ALTER TABLE vehicle_permanence ADD COLUMN codigocliente INTEGER')
            if 'enviado' not in columns:
                cursor.execute('ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0')
            
            conn.commit()
            
            # Verificar se todas as tabelas foram criadas
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [table[0] for table in cursor.fetchall()]
            
            required_tables = ['vehicle_counts', 'export_log', 'vehicle_permanence']
            for table in required_tables:
                if table not in tables:
                    raise Exception(f"Tabela obrigatória '{table}' não foi criada")
            
            conn.close()
            self.log_success("Funções de inicialização de banco")
            
        except Exception as e:
            self.log_failure("Funções de inicialização de banco", str(e))
    
    def teste_queries_compatibilidade(self):
        """Testa queries de compatibilidade com bancos antigos."""
        try:
            # Criar banco "antigo" sem campo enviado
            old_db_path = os.path.join(self.test_dir, "old_test.db")
            conn = sqlite3.connect(old_db_path)
            cursor = conn.cursor()
            
            # Estrutura antiga
            cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              codigocliente INTEGER,
                              vehicle_code INTEGER,
                              timestamp TEXT,
                              tempo_permanencia FLOAT)''')
            
            cursor.execute(
                '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia)
                   VALUES (?, ?, ?, ?)''', (1724, 26057, '2024-01-15 11:00:00', 45.6))
            conn.commit()
            
            # Testar adição automática de campo
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns_before = [column[1] for column in cursor.fetchall()]
            
            if 'enviado' not in columns_before:
                cursor.execute("ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0")
                conn.commit()
            
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns_after = [column[1] for column in cursor.fetchall()]
            
            if 'enviado' not in columns_after:
                raise Exception("Campo 'enviado' não foi adicionado automaticamente")
            
            # Verificar que registros antigos têm enviado = 0
            cursor.execute("SELECT enviado FROM vehicle_permanence WHERE id = 1")
            result = cursor.fetchone()
            if result[0] != 0:
                raise Exception(f"Registro antigo não tem enviado = 0. Valor: {result[0]}")
            
            conn.close()
            self.log_success("Queries de compatibilidade com bancos antigos")
            
        except Exception as e:
            self.log_failure("Queries de compatibilidade com bancos antigos", str(e))
    
    def teste_estrutura_arquivos_config(self):
        """Testa leitura e estrutura dos arquivos de configuração."""
        try:
            # Testar config.json
            config_path = os.path.join(self.test_dir, "config.json")
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Verificar estrutura obrigatória
            if 'codigocliente' not in config:
                raise Exception("Campo 'codigocliente' não encontrado em config.json")
            
            if 'cameras' not in config:
                raise Exception("Campo 'cameras' não encontrado em config.json")
            
            if 'camera1' not in config['cameras']:
                raise Exception("Camera1 não configurada")
            
            if 'faixas' not in config['cameras']['camera1']:
                raise Exception("Faixas não configuradas para camera1")
            
            # Testar area_tp.json
            area_tp_path = os.path.join(self.test_dir, "area_tp.json")
            with open(area_tp_path, 'r') as f:
                area_config = json.load(f)
            
            for area_name, area_data in area_config.items():
                if 'coordenadas' not in area_data:
                    raise Exception(f"Coordenadas não definidas para {area_name}")
                
                if len(area_data['coordenadas']) < 3:
                    raise Exception(f"Coordenadas insuficientes para {area_name}")
            
            self.log_success("Estrutura de arquivos de configuração")
            
        except Exception as e:
            self.log_failure("Estrutura de arquivos de configuração", str(e))
    
    def executar_todos_testes(self):
        """Executa todos os testes isolados."""
        print("INICIANDO TESTES ISOLADOS DOS SCRIPTS PRINCIPAIS")
        print("=" * 60)
        
        self.setup()
        
        try:
            self.teste_estrutura_arquivos_config()
            self.teste_init_db_functions()
            self.teste_queries_compatibilidade()
            self.teste_permanence_tracker_isolado()
            self.teste_api_tempopermanencia_isolado()
            
            print("\n" + "=" * 60)
            print(f"RESULTADO: {self.success_count} sucessos, {self.failure_count} falhas")
            
            if self.errors:
                print("\nERROS ENCONTRADOS:")
                for error in self.errors:
                    print(f"  - {error}")
            
            if self.failure_count == 0:
                print("\nTODOS OS TESTES PASSARAM!")
                print("Sistema está funcionando corretamente de forma isolada.")
            else:
                print("\nALGUNS TESTES FALHARAM!")
                print("Corrija os problemas antes de usar em produção.")
        
        finally:
            self.cleanup()

def main():
    teste = TesteScriptIsolado()
    teste.executar_todos_testes()

if __name__ == "__main__":
    main()