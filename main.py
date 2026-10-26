from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import get_conn

BASE_DIR = Path(__file__).resolve().parent
META_T0 = 0.70

app = FastAPI(title="T0 - Regional | J&T Express")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def fetch_rows(data_ini=None, data_fim=None, rm=None, sc=None, uf=None, base=None):
    clauses = []
    params = []

    if data_ini:
        clauses.append("data >= %s")
        params.append(data_ini)
    if data_fim:
        clauses.append("data <= %s")
        params.append(data_fim)
    if rm:
        clauses.append("rm = %s")
        params.append(rm)
    if sc:
        clauses.append("sc = %s")
        params.append(sc)
    if uf:
        clauses.append("uf = %s")
        params.append(uf)
    if base:
        clauses.append("base = %s")
        params.append(base)

    where = f" where {' and '.join(clauses)}" if clauses else ""
    query = f"select * from public.t0_diario{where} order by data, base"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    for r in rows:
        if r.get("data") is not None:
            r["data"] = r["data"].isoformat()
        if r.get("taxa_t0") is not None:
            r["taxa_t0"] = float(r["taxa_t0"])
    return rows


def taxa(rows):
    total = sum(int(r.get("total_pedidos") or 0) for r in rows)
    ok = sum(int(r.get("t0_ok") or 0) for r in rows)
    return total, ok, (ok / total if total else 0)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "meta": int(META_T0 * 100)})


@app.get("/api/datas")
def datas():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select distinct data from public.t0_diario order by data desc limit 365")
            rows = cur.fetchall()
    return [r["data"].isoformat() for r in rows if r.get("data")]


@app.get("/api/filtros")
def filtros():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select distinct rm, sc, uf, base from public.t0_diario")
            rows = cur.fetchall()
    return {
        "rm": sorted({r["rm"] for r in rows if r.get("rm")}),
        "sc": sorted({r["sc"] for r in rows if r.get("sc") and r.get("sc") != "—"}),
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
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select max(data) as data from public.t0_diario")
                latest = cur.fetchone()
        d = latest["data"].isoformat() if latest and latest.get("data") else (date.today() - timedelta(days=1)).isoformat()
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
            out.append({"nome": k, "total": t, "ok": o, "perdido": t-o, "taxa": round(p*100, 2)})
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
