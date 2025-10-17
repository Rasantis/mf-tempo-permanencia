#!/usr/bin/env python3
"""
Valida se o tempo de permanencia esta sendo salvo corretamente na tabela vehicle_counts.
"""

import os
import sys
import sqlite3


def test_database_structure(db_path: str) -> bool:
    """Confere colunas essenciais da tabela vehicle_counts."""
    print("Verificando estrutura do banco de dados...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(vehicle_counts)")
        columns = {column[1] for column in cursor.fetchall()}
        conn.close()

        expected = {"tempo_permanencia", "enviado", "count_out", "timestamp"}
        missing = expected - columns
        if missing:
            print(f"ERRO - Colunas ausentes em vehicle_counts: {sorted(missing)}")
            return False

        print("OK - Estrutura de vehicle_counts contem as colunas esperadas.")
        return True
    except sqlite3.Error as err:
        print(f"ERRO - Falha ao verificar estrutura: {err}")
        return False


def test_recent_data(db_path: str) -> None:
    """Apresenta estatisticas e exemplos recentes de saidas com tempo."""
    print("\nVerificando dados recentes...")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN tempo_permanencia IS NOT NULL THEN 1 ELSE 0 END) AS com_tempo,
                   SUM(CASE WHEN enviado = 0 AND tempo_permanencia IS NOT NULL AND count_out = 1 THEN 1 ELSE 0 END) AS pendentes
            FROM vehicle_counts
            """
        )
        total, com_tempo, pendentes = cursor.fetchone()
        print(f"Total de linhas em vehicle_counts: {total}")
        print(f"Linhas com tempo registrado: {com_tempo}")
        if total:
            print(f"Percentual com tempo: {(com_tempo / total) * 100:.1f}%")
        print(f"Permanencias pendentes de envio: {pendentes}")

        cursor.execute(
            """
            SELECT id, area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado
            FROM vehicle_counts
            WHERE tempo_permanencia IS NOT NULL
              AND count_out = 1
            ORDER BY id DESC
            LIMIT 5
            """
        )
        rows = cursor.fetchall()
        if rows:
            print("\nRegistros recentes com tempo:")
            for row in rows:
                print(
                    f"  ID {row[0]} | area={row[1]} | codigo={row[2]} | "
                    f"in={row[3]} | out={row[4]} | tempo={row[6]:.2f}s | "
                    f"timestamp={row[5]} | enviado={row[7]}"
                )
        else:
            print("Nenhum registro com tempo encontrado.")

        conn.close()
    except sqlite3.Error as err:
        print(f"ERRO - Falha ao consultar dados: {err}")


def main() -> None:
    db_path = "yolo8.db"
    if not os.path.exists(db_path):
        print(f"ERRO - Arquivo de banco de dados nao encontrado: {db_path}")
        sys.exit(1)

    print("TESTE DO SISTEMA DE TEMPO DE PERMANENCIA")
    print("=" * 50)

    estrutura_ok = test_database_structure(db_path)
    test_recent_data(db_path)

    print("\n" + "=" * 50)
    if estrutura_ok:
        print("OK - Estrutura valida. Caso nao haja dados, execute o sistema e aguarde novas saidas.")
    else:
        print("ERRO - Ajuste a estrutura executando novamente o sistema principal.")


if __name__ == "__main__":
    main()
