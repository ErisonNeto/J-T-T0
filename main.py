from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import query_rows, test_connection

BASE_DIR = Path(__file__).resolve().parent
META_T0 = 0.70

app = FastAPI(title="T0 - Regional | J&T Express")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def fetch_rows(data_ini=None, data_fim=None, rm=None, sc=None, uf=None, base=None):
    where = []
    params = []

    if data_ini:
        where.append("data >= %s::date")
        params.append(data_ini)
    if data_fim:
        where.append("data <= %s::date")
        params.append(data_fim)
    if rm:
        where.append("rm = %s")
        params.append(rm)
    if sc:
        where.append("sc = %s")
        params.append(sc)
    if uf:
        where.append("uf = %s")
        params.append(uf)
    if base:
        where.append("base = %s")
        params.append(base)

    sql = "SELECT * FROM t0_diario"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY data, base;"

    rows = query_rows(sql, params)

    for r in rows:
        if r.get("taxa_t0") is not None:
            r["taxa_t0"] = float(r["taxa_t0"])
    return rows


def taxa(rows):
    total = sum(int(r.get("total_pedidos") or 0) for r in rows)
    ok = sum(int(r.get("t0_ok") or 0) for r in rows)
    return total, ok, (ok / total if total else 0)


def latest_date():
    rows = query_rows("SELECT MAX(data) AS data FROM t0_diario;")
    if rows and rows[0].get("data"):
        return str(rows[0]["data"])
    return None


def has_data_for(target_date: str) -> bool:
    rows = query_rows(
        "SELECT 1 AS ok FROM t0_diario WHERE data = %s::date LIMIT 1;",
        [target_date],
    )
    return bool(rows)


def default_dashboard_date() -> str:
    d1 = (date.today() - timedelta(days=1)).isoformat()
    if has_data_for(d1):
        return d1
    return latest_date() or d1


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"meta": int(META_T0 * 100)},
    )


@app.get("/api/health")
def api_health():
    info = test_connection()
    return {"ok": True, **info}


@app.get("/api/datas")
def datas():
    rows = query_rows(
        "SELECT DISTINCT data FROM t0_diario ORDER BY data DESC LIMIT 365;"
    )
    return [str(r["data"]) for r in rows if r.get("data")]


@app.get("/api/filtros")
def filtros():
    rows = query_rows("SELECT rm, sc, uf, base FROM t0_diario;")
    return {
        "rm": sorted({r["rm"] for r in rows if r.get("rm")}),
        "sc": sorted({
            r["sc"]
            for r in rows
            if r.get("sc") and r.get("sc") != "—"
        }),
        "uf": sorted({r["uf"] for r in rows if r.get("uf")}),
        "base": sorted({r["base"] for r in rows if r.get("base")}),
    }


@app.get("/api/dashboard")
def dashboard(
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
    rm: Optional[str] = None,
    sc: Optional[str] = None,
    uf: Optional[str] = None,
    base: Optional[str] = None,
):
    if not data_ini or not data_fim:
        d = default_dashboard_date()
        data_ini = data_ini or d
        data_fim = data_fim or d

    rows = fetch_rows(data_ini, data_fim, rm, sc, uf, base)
    total, ok, tx = taxa(rows)

    def group(key):
        groups = {}
        for r in rows:
            k = r.get(key) or "—"
            groups.setdefault(k, []).append(r)

        out = []
        for k, rs in groups.items():
            t, o, p = taxa(rs)
            out.append({
                "nome": k,
                "total": t,
                "ok": o,
                "perdido": t - o,
                "taxa": round(p * 100, 2),
            })
        return out

    evolucao = sorted(group("data"), key=lambda x: x["nome"])
    scs = sorted(group("sc"), key=lambda x: x["taxa"])
    bases = sorted(group("base"), key=lambda x: (x["taxa"], -x["total"]))

    return {
        "meta": META_T0 * 100,
        "kpis": {
            "taxa": round(tx * 100, 2),
            "total": total,
            "t0_ok": ok,
            "t0_perdido": total - ok,
            "status": "META" if tx >= META_T0 else "ABAIXO",
        },
        "evolucao": evolucao,
        "sc": scs,
        "piores_bases": bases,
    }
