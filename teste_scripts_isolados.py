#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TESTES ISOLADOS DOS UTILITARIOS DA PIPELINE LOCAL

O objetivo deste script e validar, de forma rapida, se a estrutura
padrao do banco vehicle_counts esta consistente com as expectativas
atuais (tempo de permanencia e controle por envio individual).
"""

import os
import sqlite3
import json
import shutil
from datetime import datetime

TEST_DIR = "teste_scripts_isolados"


class TesteScriptsIsolados:
    def __init__(self) -> None:
        self.success = 0
        self.failures = []
        self.db_path = os.path.join(TEST_DIR, "test.db")

    # ------------------------------------------------------------------ #
    # Infra
    # ------------------------------------------------------------------ #
    def setup(self) -> None:
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
        os.makedirs(TEST_DIR, exist_ok=True)
        self._criar_configuracoes()
        self._criar_banco_base()

    def cleanup(self) -> None:
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)

    def log_ok(self, mensagem: str) -> None:
        self.success += 1
        print(f"OK  - {mensagem}")

    def log_fail(self, mensagem: str, erro: Exception) -> None:
        self.failures.append(f"{mensagem}: {erro}")
        print(f"ERRO - {mensagem}: {erro}")

    # ------------------------------------------------------------------ #
    def _criar_configuracoes(self) -> None:
        """Cria arquivos de configuracao de exemplo."""
        config = {
            "codigocliente": 1724,
            "cameras": {
                "camera1": {
                    "faixas": {
                        "faixa1": {
                            "car": 26057,
                            "motorcycle": 26058,
                        }
                    }
                }
            }
        }
        permanencia_config = {
            "area_1": {
                "coordenadas": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "tempo_minimo": 2
            }
        }

        with open(os.path.join(TEST_DIR, "config.json"), "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2)
        with open(os.path.join(TEST_DIR, "permanencia.json"), "w", encoding="utf-8") as fh:
            json.dump(permanencia_config, fh, indent=2)

    def _criar_banco_base(self) -> None:
        """Cria o banco com a estrutura atual esperada."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicle_counts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                area TEXT,
                vehicle_code INTEGER,
                count_in INTEGER,
                count_out INTEGER,
                timestamp TEXT,
                tempo_permanencia FLOAT,
                enviado INTEGER DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS export_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_export TEXT
            )
            """
        )

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # Testes
    # ------------------------------------------------------------------ #
    def teste_estrutura_vehicle_counts(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(vehicle_counts)")
            colunas = {col[1] for col in cursor.fetchall()}
            conn.close()

            esperadas = {
                "id",
                "area",
                "vehicle_code",
                "count_in",
                "count_out",
                "timestamp",
                "tempo_permanencia",
                "enviado",
            }
            faltantes = esperadas - colunas
            if faltantes:
                raise RuntimeError(f"Colunas ausentes em vehicle_counts: {sorted(faltantes)}")

            self.log_ok("Estrutura da tabela vehicle_counts")
        except Exception as err:
            self.log_fail("Estrutura da tabela vehicle_counts", err)

    def teste_insercao_e_envio(self) -> None:
        """Valida regra de insercao e atualizacao do campo enviado."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            base_timestamp = datetime(2024, 1, 15, 10, 30, 0).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
                VALUES (?, ?, 0, 1, ?, ?, 0)
                """,
                ("area_1", 26057, base_timestamp, 18.5),
            )
            conn.commit()

            cursor.execute(
                """
                SELECT id, enviado FROM vehicle_counts
                WHERE area = ? AND vehicle_code = ? AND timestamp = ?
                """,
                ("area_1", 26057, base_timestamp),
            )
            row = cursor.fetchone()
            if not row or row[1] != 0:
                raise RuntimeError("Registro nao inserido com enviado=0 conforme esperado.")

            cursor.execute(
                "UPDATE vehicle_counts SET enviado = 1 WHERE id = ?", (row[0],)
            )
            conn.commit()

            cursor.execute(
                "SELECT enviado FROM vehicle_counts WHERE id = ?", (row[0],)
            )
            status = cursor.fetchone()[0]
            if status != 1:
                raise RuntimeError("Falha ao atualizar status de envio.")

            conn.close()
            self.log_ok("Insercao e atualizacao de envio")
        except Exception as err:
            self.log_fail("Insercao e atualizacao de envio", err)

    def teste_export_log(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO export_log (last_export) VALUES (?)", (timestamp,)
            )
            conn.commit()

            cursor.execute(
                "SELECT last_export FROM export_log ORDER BY id DESC LIMIT 1"
            )
            ultimo = cursor.fetchone()
            conn.close()

            if not ultimo or ultimo[0] != timestamp:
                raise RuntimeError("Registro em export_log nao correspondente.")

            self.log_ok("Registro de export_log")
        except Exception as err:
            self.log_fail("Registro de export_log", err)

    # ------------------------------------------------------------------ #
    def executar(self) -> None:
        print("INICIANDO TESTES ISOLADOS (vehicle_counts)")
        print("=" * 60)

        self.setup()
        try:
            self.teste_estrutura_vehicle_counts()
            self.teste_insercao_e_envio()
            self.teste_export_log()
        finally:
            self.cleanup()

        total_testes = self.success + len(self.failures)
        print("\n" + "=" * 60)
        print(f"RESULTADO: {self.success} sucesso(s), {len(self.failures)} falha(s)")

        if self.failures:
            print("\nFalhas encontradas:")
            for erro in self.failures:
                print(f"  - {erro}")
        else:
            print("\nTodos os testes passaram.")


def main() -> None:
    tester = TesteScriptsIsolados()
    tester.executar()


if __name__ == "__main__":
    main()
