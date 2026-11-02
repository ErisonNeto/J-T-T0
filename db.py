from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

JT_API_URL = os.getenv(
    "JT_API_URL",
    "https://jt-api.rockettechbr.com.br",
).rstrip("/")
JT_API_KEY = os.getenv("JT_API_KEY", "").strip()

if not JT_API_KEY:
    raise RuntimeError("JT_API_KEY não configurada.")


def query_rows(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    response = requests.post(
        f"{JT_API_URL}/query",
        headers={
            "X-API-Key": JT_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "sql": sql,
            "params": params or [],
        },
        timeout=(15, 120),
    )

    if not response.ok:
        raise RuntimeError(
            f"JT API /query retornou HTTP {response.status_code}: {response.text}"
        )

    payload = response.json()
    columns = payload.get("colunas") or []
    rows = payload.get("rows") or []

    return [dict(zip(columns, row)) for row in rows]


def test_connection() -> dict:
    rows = query_rows("SELECT COUNT(*) AS total FROM t0_diario;")
    total = int(rows[0]["total"]) if rows else 0
    return {
        "backend": "JT API / PostgreSQL local",
        "tabela": "t0_diario",
        "registros": total,
    }
