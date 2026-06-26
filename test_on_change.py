"""
Script de teste para o monitor on_change.

Uso:
  python test_on_change.py -a   # insere uma linha de teste em alert_resolve
  python test_on_change.py -r   # remove a linha inserida anteriormente
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

_STATE_FILE = Path(__file__).with_name(".test_on_change_id")

_CONN_KWARGS = {
    "host": os.getenv("POSH_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("POSH_DB_PORT", "5432")),
    "user": os.getenv("POSH_DB_USER", "postgres"),
    "password": os.getenv("POSH_DB_PASSWORD", "Moto#1234"),
    "dbname": os.getenv("POSH_DB_NAME", "postgres"),
    "options": "-c search_path=brazil",
}


def _connect():
    return psycopg2.connect(**_CONN_KWARGS)


def add_row():
    """Insere uma linha de teste em alert_resolve e salva o id em arquivo local."""
    if _STATE_FILE.exists():
        existing = _STATE_FILE.read_text(encoding="utf-8").strip()
        print(f"AVISO  Ja existe uma linha de teste (id={existing}). Remova primeiro com -r.")
        sys.exit(1)

    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM purchase_order "
                "WHERE id NOT IN (SELECT purchase_order_id FROM alert_resolve) "
                "LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                print("ERRO Nenhum purchase_order disponivel. Remova algum alert_resolve existente.")
                sys.exit(1)

            po_id = row["id"]
            cur.execute(
                "INSERT INTO alert_resolve (purchase_order_id, created_at, updated_at) "
                "VALUES (%s, NOW(), NOW()) RETURNING id",
                (po_id,),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    _STATE_FILE.write_text(str(new_id), encoding="utf-8")
    print(f"OK Linha inserida - alert_resolve.id={new_id}, purchase_order_id={po_id}")
    print("   O monitor on_change deve disparar na proxima verificacao do daemon.")


def remove_row():
    """Remove a linha de teste inserida anteriormente pelo id salvo em arquivo local."""
    if not _STATE_FILE.exists():
        print("ERRO Nenhuma linha de teste encontrada. Rode primeiro com -a.")
        sys.exit(1)

    row_id = int(_STATE_FILE.read_text(encoding="utf-8").strip())
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alert_resolve WHERE id = %s", (row_id,))
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    _STATE_FILE.unlink()

    if deleted:
        print(f"OK Linha removida - alert_resolve.id={row_id}")
        print("   O monitor on_change deve disparar novamente na proxima verificacao.")
    else:
        print(f"AVISO  Linha id={row_id} nao encontrada no banco (ja removida manualmente?).")


def main():
    """Ponto de entrada: parseia -a / -r e delega para add_row ou remove_row."""
    parser = argparse.ArgumentParser(description="Testa monitor on_change alterando alert_resolve.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--add", action="store_true", help="Insere linha de teste")
    group.add_argument("-r", "--remove", action="store_true", help="Remove linha de teste")
    args = parser.parse_args()

    if args.add:
        add_row()
    else:
        remove_row()


if __name__ == "__main__":
    main()
