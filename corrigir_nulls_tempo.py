#!/usr/bin/env python3
"""
Corrige registros de saida com tempo_permanencia NULL utilizando a propria
tabela vehicle_counts como referencia.

Estrategia:
1. Para cada saida (count_out = 1) com tempo NULL, procura outro registro
   da mesma area + vehicle_code com tempo preenchido e timestamp proximo.
2. Se nao encontrar, utiliza a media das permanencias da area em uma janela
   configuravel.
"""

from __future__ import annotations

import sqlite3
import argparse
from datetime import datetime


def fetch_null_records(cursor: sqlite3.Cursor, limit: int | None) -> list[tuple]:
    query = """
        SELECT id, area, vehicle_code, timestamp
        FROM vehicle_counts
        WHERE count_out = 1
          AND tempo_permanencia IS NULL
        ORDER BY id DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    cursor.execute(query)
    return cursor.fetchall()


def find_exact_match(
    cursor: sqlite3.Cursor,
    area: str,
    vehicle_code: int,
    timestamp: str,
    window_seconds: int,
) -> float | None:
    query = """
        SELECT tempo_permanencia
        FROM vehicle_counts
        WHERE count_out = 1
          AND tempo_permanencia IS NOT NULL
          AND area = ?
          AND vehicle_code = ?
          AND ABS(strftime('%s', ?) - strftime('%s', timestamp)) <= ?
        ORDER BY ABS(strftime('%s', ?) - strftime('%s', timestamp)) ASC
        LIMIT 1
    """
    cursor.execute(query, (area, vehicle_code, timestamp, window_seconds, timestamp))
    row = cursor.fetchone()
    return float(row[0]) if row else None


def find_area_average(
    cursor: sqlite3.Cursor,
    area: str,
    timestamp: str,
    window_seconds: int,
) -> float | None:
    query = """
        SELECT AVG(tempo_permanencia)
        FROM vehicle_counts
        WHERE count_out = 1
          AND tempo_permanencia BETWEEN 1 AND 300
          AND area = ?
          AND ABS(strftime('%s', ?) - strftime('%s', timestamp)) <= ?
    """
    cursor.execute(query, (area, timestamp, window_seconds))
    row = cursor.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def update_record(cursor: sqlite3.Cursor, record_id: int, tempo: float) -> None:
    cursor.execute(
        """
        UPDATE vehicle_counts
        SET tempo_permanencia = ?, enviado = 0
        WHERE id = ?
        """,
        (tempo, record_id),
    )


def process_database(
    db_path: str,
    limit: int | None,
    match_window: int,
    average_window: int,
) -> None:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NULL AND count_out = 1"
        )
        total_null = cursor.fetchone()[0]
        if total_null == 0:
            print("Nenhum registro com tempo_permanencia NULL encontrado.")
            return

        print(f"Encontrados {total_null} registros de saida com tempo_permanencia NULL.")
        registros = fetch_null_records(cursor, limit)
        print(f"Processando {len(registros)} registros...")

        atualizados = 0
        via_media = 0

        for rec_id, area, vehicle_code, ts in registros:
            match = find_exact_match(cursor, area, vehicle_code, ts, match_window)
            if match is not None:
                update_record(cursor, rec_id, match)
                atualizados += 1
                continue

            media = find_area_average(cursor, area, ts, average_window)
            if media is not None:
                update_record(cursor, rec_id, media)
                via_media += 1
                atualizados += 1

        conn.commit()
        print("\nRESULTADO DA CORRECAO")
        print(f"  Total atualizados.........: {atualizados}")
        print(f"  Via correspondencia exata.: {atualizados - via_media}")
        print(f"  Via media por area........: {via_media}")

        cursor.execute(
            "SELECT COUNT(*) FROM vehicle_counts WHERE tempo_permanencia IS NULL AND count_out = 1"
        )
        restantes = cursor.fetchone()[0]
        print(f"  Registros ainda NULL......: {restantes}")
        conn.close()

    except sqlite3.Error as err:
        print(f"ERRO ao processar banco de dados: {err}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Corrige tempos de permanencia NULL em vehicle_counts."
    )
    parser.add_argument(
        "--db_path",
        type=str,
        default="yolo8.db",
        help="Caminho para o banco SQLite.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limitar o numero de registros processados (mais recente primeiro).",
    )
    parser.add_argument(
        "--match_window",
        type=int,
        default=600,
        help="Janela (em segundos) para considerar uma correspondencia exata. Padrao: 600s.",
    )
    parser.add_argument(
        "--average_window",
        type=int,
        default=1800,
        help="Janela (em segundos) para calcular media por area. Padrao: 1800s.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("CORRECAO DE REGISTROS COM TEMPO_PERMANENCIA NULL")
    print("=" * 60)
    print(f"Banco........: {args.db_path}")
    process_database(args.db_path, args.limit, args.match_window, args.average_window)


if __name__ == "__main__":
    main()
