#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANALISE DE CONSISTENCIA DO vehicle_counts

Ferramenta de apoio para investigar diferencas entre os dados locais
salvos em vehicle_counts e o que foi ou nao enviado para a MFWeb.
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
class AnalisadorContagem:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    # ------------------------------------------------------------------ #
    # Estrutura
    # ------------------------------------------------------------------ #
    def verificar_estrutura_banco(self) -> None:
        """Lista tabelas e valida a estrutura de vehicle_counts."""
        print("=" * 60)
        print("ESTRUTURA DO BANCO DE DADOS")
        print("=" * 60)

        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = [t[0] for t in self.cursor.fetchall()]
        print(f"Tabelas encontradas: {tabelas}")

        if "vehicle_counts" not in tabelas:
            print("ERRO: tabela vehicle_counts nao encontrada!")
            return

        self.cursor.execute("PRAGMA table_info(vehicle_counts)")
        colunas = self.cursor.fetchall()
        print("\nColunas da tabela vehicle_counts:")
        for col in colunas:
            print(f"  {col[1]} ({col[2]}) - Default: {col[4]}")

        col_names = {col[1] for col in colunas}
        if "tempo_permanencia" not in col_names:
            print("\nATENCAO: coluna tempo_permanencia nao existe.")
        if "enviado" not in col_names:
            print("\nATENCAO: coluna enviado nao existe.")

        if "vehicle_permanence" in tabelas:
            print("\nOBS: tabela antiga vehicle_permanence ainda existe (nao utilizada).")

    # ------------------------------------------------------------------ #
    # Contagens gerais
    # ------------------------------------------------------------------ #
    def contagem_geral(self) -> None:
        """Relatorio resumido das contagens e status de envio."""
        print("\n" + "=" * 60)
        print("CONTAGEM GERAL")
        print("=" * 60)

        try:
            self.cursor.execute("SELECT COUNT(*) FROM vehicle_counts")
            total = self.cursor.fetchone()[0]
            print(f"Total de registros na tabela: {total}")

            self.cursor.execute(
                """
                SELECT COUNT(*) FROM vehicle_counts
                WHERE count_out = 1
                  AND tempo_permanencia IS NOT NULL
                """
            )
            total_saidas = self.cursor.fetchone()[0]
            print(f"Saidas com tempo (count_out=1): {total_saidas}")

            self.cursor.execute(
                """
                SELECT COUNT(*) FROM vehicle_counts
                WHERE count_out = 1
                  AND tempo_permanencia IS NULL
                """
            )
            saidas_sem_tempo = self.cursor.fetchone()[0]
            print(f"Saidas sem tempo registrado: {saidas_sem_tempo}")

            self.cursor.execute(
                """
                SELECT enviado, COUNT(*) FROM vehicle_counts
                WHERE count_out = 1
                  AND tempo_permanencia IS NOT NULL
                GROUP BY enviado
                """
            )
            status_envio = self.cursor.fetchall()
            if status_envio:
                print("\nRegistros de saida por status de envio:")
                for enviado, qtd in status_envio:
                    label = "Nao enviado" if enviado == 0 else "Enviado"
                    print(f"  {label:<12}: {qtd}")

            self.cursor.execute(
                """
                SELECT DATE(timestamp) AS data, COUNT(*) as qtd
                FROM vehicle_counts
                WHERE count_out = 1
                  AND tempo_permanencia IS NOT NULL
                GROUP BY DATE(timestamp)
                ORDER BY data DESC
                LIMIT 10
                """
            )
            por_dia = self.cursor.fetchall()
            if por_dia:
                print("\nSaidas com tempo por dia (ultimos 10):")
                for data, qtd in por_dia:
                    print(f"  {data}: {qtd}")

        except sqlite3.Error as err:
            print(f"ERRO na contagem geral: {err}")

    # ------------------------------------------------------------------ #
    # Duplicados e inconsistencias
    # ------------------------------------------------------------------ #
    def analisar_duplicados(self) -> None:
        """Procura registros duplicados de saida."""
        print("\n" + "=" * 60)
        print("ANALISE DE REGISTROS DUPLICADOS")
        print("=" * 60)

        try:
            query = """
            SELECT timestamp, vehicle_code, tempo_permanencia,
                   COUNT(*) AS qtd, GROUP_CONCAT(id) AS ids
            FROM vehicle_counts
            WHERE count_out = 1
              AND tempo_permanencia IS NOT NULL
            GROUP BY timestamp, vehicle_code, tempo_permanencia
            HAVING COUNT(*) > 1
            ORDER BY timestamp DESC
            """
            self.cursor.execute(query)
            duplicados = self.cursor.fetchall()

            if not duplicados:
                print("Nenhum registro duplicado encontrado.")
                return

            total_duplicados = sum(row[3] - 1 for row in duplicados)
            print(f"Encontrados {len(duplicados)} grupos duplicados ({total_duplicados} registros extras).")
            for ts, code, tempo, qtd, ids in duplicados[:10]:
                print(f"  {ts} | code={code} | tempo={tempo:.2f}s | qtd={qtd} | ids={ids}")
            if len(duplicados) > 10:
                print("  ...")

        except sqlite3.Error as err:
            print(f"ERRO na analise de duplicados: {err}")

    def analisar_registros_invalidos(self) -> None:
        """Aponta registros com valores questionaveis."""
        print("\n" + "=" * 60)
        print("ANALISE DE REGISTROS INVALIDOS")
        print("=" * 60)

        try:
            checks = {
                "vehicle_code NULL ou <= 0": """
                    SELECT COUNT(*) FROM vehicle_counts
                    WHERE vehicle_code IS NULL OR vehicle_code <= 0
                """,
                "tempo_permanencia < 1s (saidas)": """
                    SELECT COUNT(*) FROM vehicle_counts
                    WHERE count_out = 1
                      AND tempo_permanencia IS NOT NULL
                      AND tempo_permanencia < 1
                """,
                "tempo_permanencia >= 3600s (saidas)": """
                    SELECT COUNT(*) FROM vehicle_counts
                    WHERE count_out = 1
                      AND tempo_permanencia IS NOT NULL
                      AND tempo_permanencia >= 3600
                """,
                "timestamp NULL ou vazio": """
                    SELECT COUNT(*) FROM vehicle_counts
                    WHERE timestamp IS NULL OR timestamp = ''
                """,
            }

            for descricao, query in checks.items():
                self.cursor.execute(query)
                qtd = self.cursor.fetchone()[0]
                print(f"{descricao}: {qtd}")

        except sqlite3.Error as err:
            print(f"ERRO na analise de registros invalidos: {err}")

    # ------------------------------------------------------------------ #
    # Distribuicoes
    # ------------------------------------------------------------------ #
    def analisar_por_area(self) -> None:
        """Resumo de saidas com tempo por area."""
        print("\n" + "=" * 60)
        print("ANALISE POR AREA")
        print("=" * 60)

        try:
            self.cursor.execute(
                """
                SELECT area, COUNT(*) FROM vehicle_counts
                WHERE count_out = 1
                  AND tempo_permanencia IS NOT NULL
                GROUP BY area
                ORDER BY COUNT(*) DESC
                """
            )
            por_area = self.cursor.fetchall()
            if por_area:
                for area, qtd in por_area:
                    print(f"  Area {area}: {qtd}")
            else:
                print("Nenhum dado de saida encontrado.")
        except sqlite3.Error as err:
            print(f"ERRO na analise por area: {err}")

    def analisar_por_vehicle_code(self) -> None:
        """Resumo por vehicle_code."""
        print("\n" + "=" * 60)
        print("ANALISE POR VEHICLE_CODE")
        print("=" * 60)

        try:
            self.cursor.execute(
                """
                SELECT vehicle_code, COUNT(*) FROM vehicle_counts
                WHERE vehicle_code IS NOT NULL
                  AND count_out = 1
                  AND tempo_permanencia IS NOT NULL
                GROUP BY vehicle_code
                ORDER BY COUNT(*) DESC
                """
            )
            por_vehicle = self.cursor.fetchall()
            if por_vehicle:
                for code, qtd in por_vehicle[:20]:
                    print(f"  Codigo {code}: {qtd}")
                if len(por_vehicle) > 20:
                    print("  ...")
            else:
                print("Nenhum dado encontrado.")
        except sqlite3.Error as err:
            print(f"ERRO na analise por vehicle_code: {err}")

    # ------------------------------------------------------------------ #
    # Sugerir comandos de limpeza
    # ------------------------------------------------------------------ #
    def sugerir_limpeza(self) -> None:
        """Exibe comandos SQL uteis para correcoes manuais."""
        print("\n" + "=" * 60)
        print("SUGESTOES DE LIMPEZA")
        print("=" * 60)

        print("\n-- Remover duplicados mantendo o menor id por combinacao basica")
        print(
            """DELETE FROM vehicle_counts
WHERE id NOT IN (
    SELECT MIN(id)
    FROM vehicle_counts
    WHERE count_out = 1
      AND tempo_permanencia IS NOT NULL
    GROUP BY timestamp, vehicle_code, tempo_permanencia
);"""
        )

        print("\n-- Remover registros de saida com vehicle_code invalido")
        print(
            """DELETE FROM vehicle_counts
WHERE count_out = 1
  AND (vehicle_code IS NULL OR vehicle_code <= 0);"""
        )

        print("\n-- Remover saidas com tempo menor que 1s")
        print(
            """DELETE FROM vehicle_counts
WHERE count_out = 1
  AND tempo_permanencia IS NOT NULL
  AND tempo_permanencia < 1;"""
        )

        print("\n-- Consultar resumo apos limpeza")
        print(
            """SELECT enviado, COUNT(*) FROM vehicle_counts
WHERE count_out = 1
  AND tempo_permanencia IS NOT NULL
GROUP BY enviado;"""
        )

    # ------------------------------------------------------------------ #
    def relatorio_completo(self) -> None:
        """Executa todo o relatorio."""
        print("RELATORIO DE ANALISE DE vehicle_counts")
        print("Data/Hora:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Banco analisado:", self.db_path)

        self.verificar_estrutura_banco()
        self.contagem_geral()
        self.analisar_duplicados()
        self.analisar_registros_invalidos()
        self.analisar_por_area()
        self.analisar_por_vehicle_code()
        self.sugerir_limpeza()

        print("\n" + "=" * 60)
        print("ANALISE CONCLUIDA")
        print("=" * 60)

    def close(self) -> None:
        """Fecha conexao."""
        self.conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analisa diferencas e inconsistencias no vehicle_counts."
    )
    parser.add_argument(
        "--db_path",
        type=str,
        default="yolo8.db",
        help="Caminho para o banco de dados SQLite",
    )
    args = parser.parse_args()

    try:
        analisador = AnalisadorContagem(args.db_path)
        analisador.relatorio_completo()
        analisador.close()
    except FileNotFoundError:
        print(f"ERRO: arquivo de banco nao encontrado: {args.db_path}")
    except Exception as err:
        print(f"ERRO inesperado: {err}")


if __name__ == "__main__":
    main()
