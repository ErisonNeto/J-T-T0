from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import get_supabase

BASE_DIR = Path(__file__).resolve().parent
META_T0 = 0.70
PAGE_SIZE = 1000

app = FastAPI(title="T0 - Regional | J&T Express")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def execute_all(query):
    rows = []
    start = 0
    while True:
        response = query.range(start, start + PAGE_SIZE - 1).execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def fetch_rows(data_ini=None, data_fim=None, rm=None, sc=None, uf=None, base=None):
    client = get_supabase()
    query = client.table("t0_diario").select("*")

    if data_ini:
        query = query.gte("data", data_ini)
    if data_fim:
        query = query.lte("data", data_fim)
    if rm:
        query = query.eq("rm", rm)
    if sc:
        query = query.eq("sc", sc)
    if uf:
        query = query.eq("uf", uf)
    if base:
        query = query.eq("base", base)

    query = query.order("data").order("base")
    rows = execute_all(query)

    for r in rows:
        if r.get("taxa_t0") is not None:
            r["taxa_t0"] = float(r["taxa_t0"])
    return rows


def taxa(rows):
    total = sum(int(r.get("total_pedidos") or 0) for r in rows)
    ok = sum(int(r.get("t0_ok") or 0) for r in rows)
    return total, ok, (ok / total if total else 0)


def latest_date():
    client = get_supabase()
    response = (
        client.table("t0_diario")
        .select("data")
        .order("data", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0].get("data")
    return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "meta": int(META_T0 * 100)})


@app.get("/api/datas")
def datas():
    client = get_supabase()
    rows = execute_all(client.table("t0_diario").select("data").order("data", desc=True))
    return sorted({r["data"] for r in rows if r.get("data")}, reverse=True)[:365]


@app.get("/api/filtros")
def filtros():
    client = get_supabase()
    rows = execute_all(client.table("t0_diario").select("rm,sc,uf,base"))
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
        latest = latest_date()
        d = latest or (date.today() - timedelta(days=1)).isoformat()
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
            out.append({"nome": k, "total": t, "ok": o, "perdido": t - o, "taxa": round(p * 100, 2)})
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
