import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def get_supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Defina SUPABASE_URL no ambiente.")
    return url


def get_supabase_key() -> str:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        raise RuntimeError("Defina SUPABASE_SERVICE_ROLE_KEY no ambiente.")
    return key


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(get_supabase_url(), get_supabase_key())


def test_connection() -> dict:
    client = get_supabase()
    response = client.table("t0_diario").select("id", count="exact").limit(1).execute()
    return {
        "backend": "Supabase",
        "tabela": "t0_diario",
        "registros": response.count if response.count is not None else 0,
    }
