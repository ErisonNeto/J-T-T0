import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "Defina DATABASE_URL no arquivo .env. Exemplo: "
            "postgresql://postgres:SUA_SENHA@localhost:5432/jt_t0"
        )
    return url


@contextmanager
def get_conn():
    conn = psycopg.connect(get_database_url(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def test_connection() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database() as banco, current_user as usuario, version() as versao")
            return cur.fetchone()
