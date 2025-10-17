#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIAGNOSTICO DO BANCO LOCAL (vehicle_counts)

Gera um relatorio completo com a saude dos registros gravados localmente,
incluindo verificacoes de estrutura, duplicidades, tempos invalidados e
status de envio para a MFWeb.
"""

import sqlite3
import argparse
from datetime import datetime, timedelta


def conectar_banco(db_path: str) -> sqlite3.Connection | None:
    try:
        return sqlite3.connect(db_path)
    except sqlite3.Error as err:
        print(f"ERRO ao conectar no banco {db_path}: {err}")
        return None


def listar_tabelas(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [t[0] for t in cursor.fetchall()]


def verificar_estrutura(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    print("=" * 60)
    print("ESTRUTURA DO BANCO")
    print("=" * 60)

    tabelas = listar_tabelas(conn)
    print(f"Tabelas: {tabelas}")

    if "vehicle_counts" in tabelas:
        cursor.execute("PRAGMA table_info(vehicle_counts)")
        colunas = cursor.fetchall()
        print("\nColunas de vehicle_counts:")
        for col in colunas:
            default = f" DEFAULT {col[4]}" if col[4] else ""
            print(f"  {col[1]} {col[2]}{default}")

        nomes_colunas = {col[1] for col in colunas}
        for campo in ("tempo_permanencia", "enviado"):
            if campo not in nomes_colunas:
                print(f"  ATENCAO: coluna {campo} ausente!")
    else:
        print("ERRO: tabela vehicle_counts nao encontrada!")

    if "export_log" in tabelas:
        cursor.execute("PRAGMA table_info(export_log)")
        colunas = cursor.fetchall()
        print("\nColunas de export_log:")
        for col in colunas:
            print(f"  {col[1]} {col[2]}")

    if "vehicle_permanence" in tabelas:
        print("\nOBS: tabela legada vehicle_permanence ainda existe (nao utilizada).")


def contagem_detalhada(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("CONTAGEM DETALHADA")
    print("=" * 60)

    try:
        cursor.execute("SELECT COUNT(*) FROM vehicle_counts")
        total = cursor.fetchone()[0]
        print(f"Total de linhas em vehicle_counts: {total:,}")

        cursor.execute(
            """
            SELECT COUNT(*) FROM vehicle_counts
            WHERE count_out = 1 AND tempo_permanencia IS NOT NULL
            """
        )
        total_saidas = cursor.fetchone()[0]
        print(f"Saidas com tempo registrado: {total_saidas:,}")

        cursor.execute(
            """
            SELECT COUNT(*) FROM vehicle_counts
            WHERE count_out = 1 AND tempo_permanencia IS NULL
            """
        )
        total_pendentes = cursor.fetchone()[0]
        print(f"Saidas sem tempo (pendentes do tracker): {total_pendentes:,}")

        cursor.execute(
            """
            SELECT enviado, COUNT(*) FROM vehicle_counts
            WHERE count_out = 1 AND tempo_permanencia IS NOT NULL
            GROUP BY enviado
            ORDER BY enviado
            """
        )
        por_enviado = cursor.fetchall()
        if por_enviado:
            print("\nDistribuicao por status de envio:")
            for enviado, qtd in por_enviado:
                label = "Nao enviado" if enviado == 0 else "Enviado"
                print(f"  {label:<12}: {qtd:,}")

        cursor.execute(
            """
            SELECT vehicle_code, COUNT(*) FROM vehicle_counts
            WHERE count_out = 1 AND tempo_permanencia IS NOT NULL
            GROUP BY vehicle_code
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """
        )
        top_codes = cursor.fetchall()
        if top_codes:
            print("\nTop 10 vehicle_code (saidas):")
            for code, qtd in top_codes:
                print(f"  {code}: {qtd:,}")

    except sqlite3.Error as err:
        print(f"ERRO na contagem detalhada: {err}")


def detectar_problemas(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.cursor()
    problemas: list[str] = []

    print("\n" + "=" * 60)
    print("DETECCAO DE PROBLEMAS")
    print("=" * 60)

    # Duplicados
    cursor.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT timestamp, vehicle_code, tempo_permanencia
            FROM vehicle_counts
            WHERE count_out = 1 AND tempo_permanencia IS NOT NULL
            GROUP BY timestamp, vehicle_code, tempo_permanencia
            HAVING COUNT(*) > 1
        )
        """
    )
    duplicados = cursor.fetchone()[0]
    if duplicados:
        problemas.append(f"Registros duplicados de saida: {duplicados}")
        print(f"  DUPLICADOS: {duplicados} grupos encontrados.")
    else:
        print("  DUPLICADOS: nenhum grupo encontrado.")

    # Vehicle codes invalidos
    cursor.execute(
        """
        SELECT COUNT(*) FROM vehicle_counts
        WHERE count_out = 1
          AND (vehicle_code IS NULL OR vehicle_code <= 0)
        """
    )
    invalidos = cursor.fetchone()[0]
    if invalidos:
        problemas.append(f"Vehicle_code invalido em saidas: {invalidos}")
        print(f"  VEHICLE_CODE: {invalidos} registros invalidos.")
    else:
        print("  VEHICLE_CODE: ok.")

    # Tempos extremos
    cursor.execute(
        """
        SELECT COUNT(*) FROM vehicle_counts
        WHERE count_out = 1
          AND tempo_permanencia IS NOT NULL
          AND tempo_permanencia < 1
        """
    )
    tempos_baixos = cursor.fetchone()[0]
    if tempos_baixos:
        problemas.append(f"Tempos abaixo de 1 segundo: {tempos_baixos}")
        print(f"  TEMPOS BAIXOS: {tempos_baixos} registros.")
    else:
        print("  TEMPOS BAIXOS: ok.")

    cursor.execute(
        """
        SELECT COUNT(*) FROM vehicle_counts
        WHERE count_out = 1
          AND tempo_permanencia IS NOT NULL
          AND tempo_permanencia >= 3600
        """
    )
    tempos_altos = cursor.fetchone()[0]
    if tempos_altos:
        problemas.append(f"Tempos acima de 1h: {tempos_altos}")
        print(f"  TEMPOS ALTOS: {tempos_altos} registros.")
    else:
        print("  TEMPOS ALTOS: ok.")

    # Timestamp
    cursor.execute(
        """
        SELECT COUNT(*) FROM vehicle_counts
        WHERE timestamp IS NULL OR timestamp = ''
        """
    )
    ts_invalidos = cursor.fetchone()[0]
    if ts_invalidos:
        problemas.append(f"Timestamps vazios: {ts_invalidos}")
        print(f"  TIMESTAMP: {ts_invalidos} registros sem data/hora.")
    else:
        print("  TIMESTAMP: ok.")

    return problemas


def analise_periodo_recente(conn: sqlite3.Connection, dias: int) -> None:
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print(f"ANALISE DOS ULTIMOS {dias} DIAS")
    print("=" * 60)

    try:
        data_limite = (datetime.now() - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
        cursor.execute(
            """
            SELECT DATE(timestamp) as data,
                   COUNT(*) as total,
                   COUNT(DISTINCT vehicle_code) as codigos,
                   MIN(tempo_permanencia),
                   MAX(tempo_permanencia),
                   AVG(tempo_permanencia)
            FROM vehicle_counts
            WHERE count_out = 1
              AND tempo_permanencia IS NOT NULL
              AND DATE(timestamp) >= ?
            GROUP BY DATE(timestamp)
            ORDER BY data DESC
            """,
            (data_limite,),
        )
        linhas = cursor.fetchall()

        if not linhas:
            print("Sem registros no periodo informado.")
            return

        for data, total, codigos, min_t, max_t, avg_t in linhas:
            print(
                f"  {data}: {total} registros, {codigos} codigos unicos, "
                f"tempo {min_t:.1f}s - {max_t:.1f}s (media {avg_t:.1f}s)"
            )

        # procurar lacunas
        datas_observadas = {linha[0] for linha in linhas}
        lacunas = []
        for i in range(dias):
            dia = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            if dia < data_limite:
                break
            if dia not in datas_observadas:
                lacunas.append(dia)

        if lacunas:
            print("\nATENCAO: dias sem registros de saida:")
            for dia in sorted(lacunas):
                print(f"  - {dia}")

    except sqlite3.Error as err:
        print(f"ERRO na analise do periodo recente: {err}")


def gerar_comandos_limpeza(problemas: list[str]) -> None:
    if not problemas:
        return

    print("\n" + "=" * 60)
    print("COMANDOS DE LIMPEZA RECOMENDADOS")
    print("=" * 60)
    print("ATENCAO: faca backup antes de executar quaisquer comandos!")

    if any("duplicados" in p.lower() for p in problemas):
        print(
            """
-- Remover duplicados mantendo o menor id
DELETE FROM vehicle_counts
WHERE id NOT IN (
    SELECT MIN(id)
    FROM vehicle_counts
    WHERE count_out = 1
      AND tempo_permanencia IS NOT NULL
    GROUP BY timestamp, vehicle_code, tempo_permanencia
);
"""
        )

    if any("vehicle_code" in p.lower() for p in problemas):
        print(
            """
-- Remover vehicle_code invalidos
DELETE FROM vehicle_counts
WHERE count_out = 1
  AND (vehicle_code IS NULL OR vehicle_code <= 0);
"""
        )

    if any("tempo" in p.lower() for p in problemas):
        print(
            """
-- Remover tempos abaixo de 1s
DELETE FROM vehicle_counts
WHERE count_out = 1
  AND tempo_permanencia IS NOT NULL
  AND tempo_permanencia < 1;
"""
        )

    if any("timestamp" in p.lower() for p in problemas):
        print(
            """
-- Remover timestamps vazios
DELETE FROM vehicle_counts
WHERE timestamp IS NULL OR timestamp = '';
"""
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnostico do banco local vehicle_counts."
    )
    parser.add_argument(
        "--db_path", type=str, default="yolo8.db", help="Caminho para o banco SQLite"
    )
    parser.add_argument(
        "--dias", type=int, default=7, help="Janela em dias para analise recente"
    )
    args = parser.parse_args()

    print("DIAGNOSTICO COMPLETO DO BANCO DE DADOS")
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
        print("RESUMO DOS PROBLEMAS")
        print("=" * 60)
        if problemas:
            for idx, problema in enumerate(problemas, start=1):
                print(f"  {idx}. {problema}")
            gerar_comandos_limpeza(problemas)
        else:
            print("Nenhum problema critico detectado.")

        print("\n" + "=" * 60)
        print("DIAGNOSTICO CONCLUIDO")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
