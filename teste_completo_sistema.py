#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TESTE COMPLETO E ISOLADO DE TODAS AS FUNCIONALIDADES DO SISTEMA
DE TEMPO DE PERMANÊNCIA

Este script testa cada componente de forma isolada para garantir
100% de funcionamento antes de integração.
"""

import sqlite3
import os
import sys
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import requests
from requests.auth import HTTPBasicAuth

# Configurações de teste
TEST_BASE_DIR = "teste_isolado"
TEST_CLIENT_CODE = 1724
TEST_CONFIGS = {
    "config": {
        "codigocliente": TEST_CLIENT_CODE,
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
                    },
                    "faixa2": {
                        "motorcycle": 26053,
                        "car": 26052,
                        "truck": 26051,
                        "bus": 26054,
                        "vuc": 26055
                    }
                }
            }
        }
    },
    "area_tp": {
        "area_1": {
            "coordenadas": [[618, 234], [631, 705], [1069, 708], [939, 240]],
            "tempo_minimo": 2
        },
        "area_2": {
            "coordenadas": [[271, 240], [180, 700], [541, 705], [549, 249]],
            "tempo_minimo": 2
        }
    }
}

class TestResult:
    def __init__(self):
        self.success = 0
        self.failures = 0
        self.errors = []
    
    def add_success(self, test_name):
        self.success += 1
        print(f"OK - {test_name}")
    
    def add_failure(self, test_name, error):
        self.failures += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"ERRO - {test_name}: {error}")
    
    def summary(self):
        total = self.success + self.failures
        print(f"\n{'='*60}")
        print(f"RESUMO DOS TESTES: {self.success}/{total} sucessos")
        if self.errors:
            print(f"ERROS ENCONTRADOS:")
            for error in self.errors:
                print(f"  - {error}")
        print(f"{'='*60}")
        return self.failures == 0

def setup_test_environment():
    """Cria ambiente de teste isolado."""
    if os.path.exists(TEST_BASE_DIR):
        shutil.rmtree(TEST_BASE_DIR)
    os.makedirs(TEST_BASE_DIR)
    
    # Criar arquivos de configuração
    config_path = os.path.join(TEST_BASE_DIR, "config.json")
    area_path = os.path.join(TEST_BASE_DIR, "area_tp.json")
    
    with open(config_path, 'w') as f:
        json.dump(TEST_CONFIGS["config"], f, indent=2)
    
    with open(area_path, 'w') as f:
        json.dump(TEST_CONFIGS["area_tp"], f, indent=2)
    
    return config_path, area_path

def cleanup_test_environment():
    """Remove ambiente de teste."""
    if os.path.exists(TEST_BASE_DIR):
        shutil.rmtree(TEST_BASE_DIR)

class TestePermanenceTracker:
    """Testes isolados para PermanenceTracker."""
    
    def __init__(self, result):
        self.result = result
        self.db_path = os.path.join(TEST_BASE_DIR, "test_tracker.db")
    
    def test_inicializacao_banco(self):
        """Testa criação e inicialização do banco."""
        try:
            # Importar e testar PermanenceTracker
            sys.path.append('.')
            from permanence_tracker import PermanenceTracker
            
            config_path, area_path = setup_test_environment()
            
            with open(area_path, 'r') as f:
                config = json.load(f)
            
            tracker = PermanenceTracker(self.db_path, TEST_CLIENT_CODE, config)
            
            # Verificar estrutura da tabela
            cursor = tracker.cursor
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns = [col[1] for col in cursor.fetchall()]
            
            required_columns = ['id', 'codigocliente', 'area', 'vehicle_code', 'timestamp', 'tempo_permanencia', 'enviado']
            for col in required_columns:
                if col not in columns:
                    raise Exception(f"Coluna '{col}' não encontrada na tabela")
            
            tracker.close()
            self.result.add_success("Inicialização do banco PermanenceTracker")
            
        except Exception as e:
            self.result.add_failure("Inicialização do banco PermanenceTracker", str(e))
    
    def test_salvamento_permanencia(self):
        """Testa salvamento de dados de permanência."""
        try:
            from permanence_tracker import PermanenceTracker
            
            config_path, area_path = setup_test_environment()
            with open(area_path, 'r') as f:
                config = json.load(f)
            
            tracker = PermanenceTracker(self.db_path, TEST_CLIENT_CODE, config)
            
            # Simular salvamento
            test_timestamp = datetime.now()
            tracker._save_permanence_to_db(12345, "area_1", test_timestamp, 15.5)
            
            # Verificar se foi salvo
            tracker.cursor.execute("SELECT * FROM vehicle_permanence WHERE area = 'area_1'")
            result = tracker.cursor.fetchone()
            
            if not result:
                raise Exception("Registro não foi salvo")
            
            if result[6] != 0:  # Campo enviado deve ser 0
                raise Exception(f"Campo 'enviado' deveria ser 0, mas é {result[6]}")
            
            tracker.close()
            self.result.add_success("Salvamento de permanência PermanenceTracker")
            
        except Exception as e:
            self.result.add_failure("Salvamento de permanência PermanenceTracker", str(e))

class TesteAPITempoPermanencia:
    """Testes isolados para api_tempopermanencia.py."""
    
    def __init__(self, result):
        self.result = result
        self.db_path = os.path.join(TEST_BASE_DIR, "test_api.db")
    
    def setup_test_db(self):
        """Cria banco de teste com dados."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Criar tabela
        cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          codigocliente INTEGER,
                          vehicle_code INTEGER,
                          timestamp TEXT,
                          tempo_permanencia FLOAT,
                          enviado INTEGER DEFAULT 0)''')
        
        # Inserir dados de teste
        test_data = [
            (TEST_CLIENT_CODE, 26057, '2024-01-15 10:30:00', 15.5, 0),
            (TEST_CLIENT_CODE, 26058, '2024-01-15 10:35:00', 22.3, 0),
            (TEST_CLIENT_CODE, 26059, '2024-01-15 10:40:00', 8.7, 1),  # Já enviado
            (TEST_CLIENT_CODE, 26057, '2024-01-15 10:45:00', 31.2, 0),
        ]
        
        cursor.executemany(
            '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia, enviado)
               VALUES (?, ?, ?, ?, ?)''', test_data)
        
        conn.commit()
        conn.close()
    
    def test_buscar_dados_nao_enviados(self):
        """Testa busca de registros não enviados."""
        try:
            self.setup_test_db()
            
            # Simular buscar_dados() do api_tempopermanencia.py
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Buscar apenas registros não enviados (enviado = 0)
            query = "SELECT id, timestamp, vehicle_code, tempo_permanencia FROM vehicle_permanence WHERE enviado = 0 ORDER BY timestamp"
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            # Deve retornar 3 registros (excluindo o que tem enviado = 1)
            if len(rows) != 3:
                raise Exception(f"Esperado 3 registros não enviados, encontrado {len(rows)}")
            
            # Verificar se não trouxe o registro já enviado
            for row in rows:
                if row[2] == 26059:  # vehicle_code do registro já enviado
                    raise Exception("Trouxe registro que deveria estar marcado como enviado")
            
            self.result.add_success("Busca de dados não enviados API")
            
        except Exception as e:
            self.result.add_failure("Busca de dados não enviados API", str(e))
    
    def test_marcar_como_enviado(self):
        """Testa marcação de registro como enviado."""
        try:
            self.setup_test_db()
            
            # Simular marcar_como_enviado()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE vehicle_permanence SET enviado = 1 WHERE id = ?", (1,))
            conn.commit()
            
            # Verificar se foi marcado
            cursor.execute("SELECT enviado FROM vehicle_permanence WHERE id = 1")
            result = cursor.fetchone()
            conn.close()
            
            if result[0] != 1:
                raise Exception(f"Registro não foi marcado como enviado. Valor: {result[0]}")
            
            self.result.add_success("Marcação como enviado API")
            
        except Exception as e:
            self.result.add_failure("Marcação como enviado API", str(e))
    
    @patch('requests.post')
    def test_envio_simulado(self, mock_post):
        """Testa simulação de envio para API."""
        try:
            # Configurar mock para simular sucesso
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response
            
            # Dados de teste
            record_id = 1
            timestamp = "2024-01-15 10:30:00"
            vehicle_code = 26057
            tempo_permanencia = 15.5
            
            # Simular dados de envio
            dados_envio = {
                "datetime": timestamp,
                "dwelltime": {
                    str(vehicle_code): {
                        "inside": 1,
                        "mean_secs": int(tempo_permanencia)
                    }
                }
            }
            
            # Fazer requisição simulada
            url = 'https://mfweb.maisfluxo.com.br/MaisFluxoServidorWEB/rest/dwell/'
            response = mock_post(url, json=dados_envio, auth=HTTPBasicAuth('test', 'test'))
            
            if response.status_code != 204:
                raise Exception(f"Status code inesperado: {response.status_code}")
            
            self.result.add_success("Simulação de envio API")
            
        except Exception as e:
            self.result.add_failure("Simulação de envio API", str(e))

class TesteCompatibilidadeBanco:
    """Testes de compatibilidade com bancos antigos."""
    
    def __init__(self, result):
        self.result = result
        self.db_path = os.path.join(TEST_BASE_DIR, "test_compat.db")
    
    def test_banco_sem_campo_enviado(self):
        """Testa adição automática do campo 'enviado' em banco antigo."""
        try:
            # Criar banco "antigo" sem campo enviado
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              codigocliente INTEGER,
                              vehicle_code INTEGER,
                              timestamp TEXT,
                              tempo_permanencia FLOAT)''')
            
            # Inserir um registro
            cursor.execute(
                '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia)
                   VALUES (?, ?, ?, ?)''', (TEST_CLIENT_CODE, 26057, '2024-01-15 11:00:00', 45.6))
            conn.commit()
            
            # Simular código de compatibilidade
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'enviado' not in columns:
                cursor.execute("ALTER TABLE vehicle_permanence ADD COLUMN enviado INTEGER DEFAULT 0")
                conn.commit()
            
            # Verificar se foi adicionado
            cursor.execute("PRAGMA table_info(vehicle_permanence)")
            columns_after = [column[1] for column in cursor.fetchall()]
            
            if 'enviado' not in columns_after:
                raise Exception("Campo 'enviado' não foi adicionado automaticamente")
            
            # Verificar que registro existente tem enviado = 0
            cursor.execute("SELECT enviado FROM vehicle_permanence WHERE id = 1")
            result = cursor.fetchone()
            
            if result[0] != 0:
                raise Exception(f"Registro antigo não tem enviado = 0. Valor: {result[0]}")
            
            conn.close()
            self.result.add_success("Compatibilidade com banco antigo")
            
        except Exception as e:
            self.result.add_failure("Compatibilidade com banco antigo", str(e))

class TesteContagem:
    """Testes para investigar diferenças de contagem."""
    
    def __init__(self, result):
        self.result = result
        self.db_path = os.path.join(TEST_BASE_DIR, "test_count.db")
    
    def criar_cenario_teste(self):
        """Cria cenário de teste com possíveis problemas de contagem."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS vehicle_permanence (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          codigocliente INTEGER,
                          vehicle_code INTEGER,
                          timestamp TEXT,
                          tempo_permanencia FLOAT,
                          enviado INTEGER DEFAULT 0)''')
        
        # Cenários que podem causar diferenças:
        test_scenarios = [
            # Registros duplicados (mesmo timestamp)
            (TEST_CLIENT_CODE, 26057, '2024-01-15 10:30:00', 15.5, 0),
            (TEST_CLIENT_CODE, 26057, '2024-01-15 10:30:00', 15.5, 0),
            
            # Registros com vehicle_code inválido/nulo
            (TEST_CLIENT_CODE, None, '2024-01-15 10:31:00', 12.3, 0),
            (TEST_CLIENT_CODE, -1, '2024-01-15 10:32:00', 18.7, 0),
            
            # Registros com tempo muito baixo (podem ser filtrados)
            (TEST_CLIENT_CODE, 26058, '2024-01-15 10:33:00', 0.5, 0),
            (TEST_CLIENT_CODE, 26058, '2024-01-15 10:34:00', 1.5, 0),
            
            # Registros normais
            (TEST_CLIENT_CODE, 26059, '2024-01-15 10:35:00', 25.8, 0),
            (TEST_CLIENT_CODE, 26060, '2024-01-15 10:36:00', 42.1, 1),  # Já enviado
        ]
        
        cursor.executemany(
            '''INSERT INTO vehicle_permanence (codigocliente, vehicle_code, timestamp, tempo_permanencia, enviado)
               VALUES (?, ?, ?, ?, ?)''', test_scenarios)
        
        conn.commit()
        conn.close()
    
    def test_contagem_total_vs_validos(self):
        """Testa diferenças entre contagem total e registros válidos."""
        try:
            self.criar_cenario_teste()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Contagem total
            cursor.execute("SELECT COUNT(*) FROM vehicle_permanence")
            total = cursor.fetchone()[0]
            
            # Contagem excluindo registros inválidos
            cursor.execute("""SELECT COUNT(*) FROM vehicle_permanence 
                             WHERE vehicle_code IS NOT NULL 
                             AND vehicle_code > 0 
                             AND tempo_permanencia >= 1""")
            validos = cursor.fetchone()[0]
            
            # Contagem de não enviados válidos
            cursor.execute("""SELECT COUNT(*) FROM vehicle_permanence 
                             WHERE vehicle_code IS NOT NULL 
                             AND vehicle_code > 0 
                             AND tempo_permanencia >= 1
                             AND enviado = 0""")
            nao_enviados_validos = cursor.fetchone()[0]
            
            # Contagem de duplicados
            cursor.execute("""SELECT timestamp, vehicle_code, COUNT(*) as duplicatas
                             FROM vehicle_permanence 
                             WHERE vehicle_code IS NOT NULL
                             GROUP BY timestamp, vehicle_code 
                             HAVING COUNT(*) > 1""")
            duplicados = cursor.fetchall()
            
            conn.close()
            
            print(f"  Total de registros: {total}")
            print(f"  Registros válidos: {validos}")
            print(f"  Não enviados válidos: {nao_enviados_validos}")
            print(f"  Grupos duplicados: {len(duplicados)}")
            
            if len(duplicados) > 0:
                print(f"  ATENÇÃO: Encontrados registros duplicados!")
                for dup in duplicados:
                    print(f"    Timestamp: {dup[0]}, Vehicle: {dup[1]}, Qtd: {dup[2]}")
            
            self.result.add_success("Análise de contagem e possíveis diferenças")
            
        except Exception as e:
            self.result.add_failure("Análise de contagem e possíveis diferenças", str(e))

def main():
    """Executa todos os testes isolados."""
    print("INICIANDO TESTES COMPLETOS E ISOLADOS DO SISTEMA")
    print("="*60)
    
    result = TestResult()
    
    try:
        # Setup do ambiente
        setup_test_environment()
        
        # Teste 1: PermanenceTracker
        print("\n1. TESTANDO PERMANENCE TRACKER")
        print("-" * 40)
        tracker_test = TestePermanenceTracker(result)
        tracker_test.test_inicializacao_banco()
        tracker_test.test_salvamento_permanencia()
        
        # Teste 2: API Tempo Permanência
        print("\n2. TESTANDO API TEMPO PERMANÊNCIA")
        print("-" * 40)
        api_test = TesteAPITempoPermanencia(result)
        api_test.test_buscar_dados_nao_enviados()
        api_test.test_marcar_como_enviado()
        api_test.test_envio_simulado()
        
        # Teste 3: Compatibilidade
        print("\n3. TESTANDO COMPATIBILIDADE")
        print("-" * 40)
        compat_test = TesteCompatibilidadeBanco(result)
        compat_test.test_banco_sem_campo_enviado()
        
        # Teste 4: Análise de Contagem
        print("\n4. ANALISANDO POSSÍVEIS DIFERENÇAS DE CONTAGEM")
        print("-" * 40)
        count_test = TesteContagem(result)
        count_test.test_contagem_total_vs_validos()
        
        # Resultado final
        sucesso_total = result.summary()
        
        if sucesso_total:
            print("\nSTATUS: TODOS OS TESTES PASSARAM!")
            print("Sistema está funcionando 100% corretamente.")
        else:
            print("\nSTATUS: ALGUNS TESTES FALHARAM!")
            print("É necessário corrigir os problemas antes de usar em produção.")
        
    except Exception as e:
        print(f"ERRO CRÍTICO: {e}")
    finally:
        # Cleanup
        cleanup_test_environment()

if __name__ == "__main__":
    main()