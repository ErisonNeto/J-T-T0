from __future__ import annotations

import os
import re
from dataclasses import dataclass
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

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_TABLES = {"t0_diario"}


def _ident(value: str) -> str:
    value = str(value).strip()
    if not _IDENT.fullmatch(value):
        raise ValueError(f"Identificador SQL inválido: {value!r}")
    return value


def _placeholder(column: str) -> str:
    if column == "data":
        return "%s::date"
    if column in {"id", "total_pedidos", "t0_ok", "t0_perdido"}:
        return "%s::bigint"
    return "%s"


@dataclass
class APIResult:
    data: list[dict[str, Any]]
    count: int | None = None


class TableQuery:
    def __init__(self, table: str):
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Tabela não permitida: {table}")
        self.table = table
        self.columns = "*"
        self.filters: list[tuple[str, str, Any]] = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_value: int | None = None
        self.offset_value: int | None = None
        self.count_mode: str | None = None
        self.upsert_rows: list[dict[str, Any]] | None = None
        self.conflict_columns: list[str] = []

    def select(self, columns: str = "*", count: str | None = None) -> "TableQuery":
        columns = (columns or "*").strip()
        self.count_mode = count

        if columns == "*":
            self.columns = "*"
            return self

        parsed = []
        for raw in columns.split(","):
            parsed.append(_ident(raw.strip()))
        self.columns = ", ".join(parsed)
        return self

    def eq(self, column: str, value: Any) -> "TableQuery":
        self.filters.append((_ident(column), "=", value))
        return self

    def gte(self, column: str, value: Any) -> "TableQuery":
        self.filters.append((_ident(column), ">=", value))
        return self

    def lte(self, column: str, value: Any) -> "TableQuery":
        self.filters.append((_ident(column), "<=", value))
        return self

    def order(self, column: str, desc: bool = False) -> "TableQuery":
        self.orders.append((_ident(column), bool(desc)))
        return self

    def limit(self, value: int) -> "TableQuery":
        self.limit_value = max(1, int(value))
        return self

    def range(self, start: int, end: int) -> "TableQuery":
        start = max(0, int(start))
        end = max(start, int(end))
        self.offset_value = start
        self.limit_value = end - start + 1
        return self

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str) -> "TableQuery":
        self.upsert_rows = rows
        self.conflict_columns = [
            _ident(col.strip())
            for col in on_conflict.split(",")
            if col.strip()
        ]
        return self

    def _where(self) -> tuple[str, list[Any]]:
        if not self.filters:
            return "", []

        clauses = []
        params: list[Any] = []

        for column, operator, value in self.filters:
            clauses.append(f"{column} {operator} {_placeholder(column)}")
            params.append(value)

        return " WHERE " + " AND ".join(clauses), params

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": JT_API_KEY,
            "Content-Type": "application/json",
        }

    def _execute_upsert(self) -> APIResult:
        rows = self.upsert_rows or []
        if not rows:
            return APIResult(data=[])

        response = requests.post(
            f"{JT_API_URL}/import",
            headers=self._headers(),
            json={
                "tabela": self.table,
                "chave": self.conflict_columns,
                "registros": rows,
                "criar_tabela": False,
                "adicionar_colunas": False,
            },
            timeout=(15, 180),
        )

        if not response.ok:
            raise RuntimeError(
                f"JT API /import retornou HTTP {response.status_code}: {response.text}"
            )

        return APIResult(data=response.json().get("registros", []) if isinstance(response.json(), dict) else [])

    def execute(self) -> APIResult:
        if self.upsert_rows is not None:
            return self._execute_upsert()

        where_sql, params = self._where()
        sql = f"SELECT {self.columns} FROM {self.table}{where_sql}"

        if self.orders:
            sql += " ORDER BY " + ", ".join(
                f"{column} {'DESC' if desc else 'ASC'}"
                for column, desc in self.orders
            )

        if self.limit_value is not None:
            sql += f" LIMIT {self.limit_value}"

        if self.offset_value is not None:
            sql += f" OFFSET {self.offset_value}"

        sql += ";"

        response = requests.post(
            f"{JT_API_URL}/query",
            headers=self._headers(),
            json={"sql": sql, "params": params},
            timeout=(15, 120),
        )

        if not response.ok:
            raise RuntimeError(
                f"JT API /query retornou HTTP {response.status_code}: {response.text}"
            )

        payload = response.json()
        columns = payload.get("colunas") or []
        rows = payload.get("rows") or []
        data = [dict(zip(columns, row)) for row in rows]

        total_count = None
        if self.count_mode == "exact":
            count_sql = f"SELECT COUNT(*) AS total FROM {self.table}{where_sql};"
            count_response = requests.post(
                f"{JT_API_URL}/query",
                headers=self._headers(),
                json={"sql": count_sql, "params": params},
                timeout=(15, 120),
            )
            if not count_response.ok:
                raise RuntimeError(
                    f"JT API /query count retornou HTTP {count_response.status_code}: {count_response.text}"
                )
            count_payload = count_response.json()
            count_rows = count_payload.get("rows") or []
            total_count = int(count_rows[0][0]) if count_rows else 0

        return APIResult(data=data, count=total_count)


class JTAPIClient:
    def table(self, table: str) -> TableQuery:
        return TableQuery(table)


_CLIENT = JTAPIClient()


def get_supabase() -> JTAPIClient:
    """Compatibilidade com o código antigo; agora usa a JT API/PostgreSQL local."""
    return _CLIENT


def test_connection() -> dict:
    response = (
        get_supabase()
        .table("t0_diario")
        .select("id", count="exact")
        .limit(1)
        .execute()
    )
    return {
        "backend": "JT API / PostgreSQL local",
        "tabela": "t0_diario",
        "registros": response.count or 0,
    }
