import os
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv("POSH_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("POSH_DB_PORT", "5432")),
            user=os.getenv("POSH_DB_USER", "postgres"),
            password=os.getenv("POSH_DB_PASSWORD", "Moto#1234"),
            dbname=os.getenv("POSH_DB_NAME", "postgres"),
        )
    return _pool


@contextmanager
def get_posh_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        yield conn
    finally:
        pool.putconn(conn)


def posh_query(sql: str, params=None) -> list[dict]:
    with get_posh_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]


def posh_query_one(sql: str, params=None) -> dict | None:
    with get_posh_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
