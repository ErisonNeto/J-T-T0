from __future__ import annotations

import argparse
import glob
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


load_dotenv()

META_T0 = 0.70
RM_ALVO = "ORLEAN DA SILVA DO NASCIMENTO"


def norm_text(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper()


def norm_code(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def normalized_columns(df: pd.DataFrame) -> dict[str, str]:
    return {norm_text(c): c for c in df.columns}


def pick_col(df: pd.DataFrame, *aliases: str) -> str | None:
    cols = normalized_columns(df)
    for alias in aliases:
        key = norm_text(alias)
        if key in cols:
            return cols[key]
    return None


def classify_t0_file(path: str) -> tuple[str, str | None]:
    """Retorna (tipo, aba): padrao, consolidado ou ignorar."""
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
    except Exception:
        return "ignorar", None

    ordered_sheets = sorted(xls.sheet_names, key=lambda s: 0 if norm_text(s) == "SHEET0" else 1)
    for sheet in ordered_sheets:
        try:
            amostra = pd.read_excel(path, sheet_name=sheet, nrows=3, engine="openpyxl")
        except Exception:
            continue
        cols = {norm_text(c) for c in amostra.columns}
        if {
            norm_text("Código da base"),
            norm_text("quantidade a entregar"),
            norm_text("entregue"),
        }.issubset(cols) and (
            norm_text("T日签收率-签收率") in cols
            or norm_text("Horário de término do prazo de coleta") in cols
        ):
            return "consolidado", sheet

    for sheet in xls.sheet_names[:3]:
        try:
            amostra = pd.read_excel(path, sheet_name=sheet, nrows=3, engine="openpyxl")
        except Exception:
            continue
        cols = {norm_text(c) for c in amostra.columns}
        required = {
            norm_text("Número da Remessa"),
            norm_text("Código da base"),
            norm_text("Horário bipagem de recebimento"),
            norm_text("Horário da entrega"),
        }
        if required.issubset(cols):
            return "padrao", sheet

    return "ignorar", None


def find_files() -> tuple[list[tuple[str, str, str]], str]:
    files = [f for f in glob.glob("*.xlsx") if not os.path.basename(f).startswith("~$")]
    gestao_files: list[str] = []
    candidates: list[str] = []

    for f in files:
        n = norm_text(Path(f).name)
        if "GESTAO DE COLABORADORES" in n or "RESPONSAVEIS" in n:
            gestao_files.append(f)
        else:
            candidates.append(f)

    if not gestao_files:
        raise FileNotFoundError("Nenhum arquivo de Gestão de colaboradores .xlsx encontrado na pasta.")

    fontes: list[tuple[str, str, str]] = []
    for f in sorted(candidates):
        nome = norm_text(Path(f).name)
        if "T0" in nome and "ASSINATURA" in nome and "LISTA" in nome:
            try:
                xls = pd.ExcelFile(f, engine="openpyxl")
                fontes.append((f, "padrao", xls.sheet_names[0]))
                continue
            except Exception:
                pass

        if "T0" not in nome:
            continue
        tipo, sheet = classify_t0_file(f)
        if tipo != "ignorar" and sheet is not None:
            fontes.append((f, tipo, sheet))

    if not fontes:
        raise FileNotFoundError(
            "Nenhum relatório T0 reconhecido. Aceitos: relatório padrão/lista e consolidado histórico."
        )

    gestao_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return fontes, gestao_files[0]


def read_t0_padrao(path: str, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")

    c_remessa = pick_col(df, "Número da Remessa")
    c_base = pick_col(df, "Nome da base")
    c_codigo = pick_col(df, "Código da base")
    c_receb = pick_col(df, "Horário bipagem de recebimento")
    c_entrega = pick_col(df, "Horário da entrega")
    missing = [
        nome for nome, col in [
            ("Número da Remessa", c_remessa),
            ("Nome da base", c_base),
            ("Código da base", c_codigo),
            ("Horário bipagem de recebimento", c_receb),
            ("Horário da entrega", c_entrega),
        ] if col is None
    ]
    if missing:
        raise ValueError(f"{Path(path).name}: colunas ausentes: {missing}")

    out = pd.DataFrame({
        "numero_remessa": df[c_remessa].astype(str).str.strip(),
        "base": df[c_base].fillna("").astype(str).str.strip(),
        "codigo_base": df[c_codigo].map(norm_code),
        "recebimento": pd.to_datetime(df[c_receb], errors="coerce"),
        "entrega": pd.to_datetime(df[c_entrega], errors="coerce"),
    })
    out = out[out["recebimento"].notna() & out["codigo_base"].ne("")].copy()
    out["data"] = out["recebimento"].dt.date
    out["t0_ok"] = out["entrega"].notna() & (out["entrega"].dt.date == out["data"])
    out["arquivo_origem"] = Path(path).name
    return out


def excel_date_to_datetime(series: pd.Series) -> pd.Series:
    """Aceita datas reais, strings e serial numérico do Excel."""
    numeric = pd.to_numeric(series, errors="coerce")
    as_excel = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
    as_text = pd.to_datetime(series, errors="coerce", dayfirst=True)
    plausible = numeric.between(20000, 80000, inclusive="both")
    return as_text.where(~plausible, as_excel)


def read_t0_consolidado(path: str, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")

    c_data = pick_col(
        df,
        "Horário de término do prazo de coleta",
        "Data",
        "Dia",
        "Data T0",
    )
    c_codigo = pick_col(df, "Código da base")
    c_base = pick_col(df, "Nome da base", "Base")
    c_total = pick_col(df, "quantidade a entregar", "Qtd a entregar", "Total")
    c_ok = pick_col(df, "entregue", "Entregue T0", "T0 OK")
    c_taxa = pick_col(df, "T日签收率-签收率", "Taxa T0", "T0")

    missing = [
        nome for nome, col in [
            ("Data", c_data),
            ("Código da base", c_codigo),
            ("Nome da base", c_base),
            ("quantidade a entregar", c_total),
            ("entregue", c_ok),
        ] if col is None
    ]
    if missing:
        raise ValueError(f"{Path(path).name}/{sheet}: colunas ausentes: {missing}")

    out = pd.DataFrame({
        "data": excel_date_to_datetime(df[c_data]).dt.date,
        "codigo_base": df[c_codigo].map(norm_code),
        "base": df[c_base].fillna("").astype(str).str.strip(),
        "total_pedidos": pd.to_numeric(df[c_total], errors="coerce").fillna(0).astype(int),
        "t0_ok": pd.to_numeric(df[c_ok], errors="coerce").fillna(0).astype(int),
    })
    out = out[
        out["data"].notna()
        & out["codigo_base"].ne("")
        & out["total_pedidos"].gt(0)
    ].copy()
    out["t0_ok"] = out[["t0_ok", "total_pedidos"]].min(axis=1).astype(int)
    out["t0_perdido"] = out["total_pedidos"] - out["t0_ok"]
    out["taxa_t0"] = (out["t0_ok"] / out["total_pedidos"]).round(4)

    if c_taxa is not None:
        taxa_arquivo = pd.to_numeric(df.loc[out.index, c_taxa], errors="coerce")
        diff = (taxa_arquivo - out["taxa_t0"]).abs()
        out["taxa_divergente"] = diff.gt(0.005).fillna(False)
    else:
        out["taxa_divergente"] = False

    out["arquivo_origem"] = Path(path).name
    return out


def read_gestao(path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheet = "Responsáveis atuais" if "Responsáveis atuais" in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")

    required = ["Nome da base", "Estação No.", "Regional", "Estado(UF)", "Responsável da Região", "Coordenador", "Supervisor"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Gestão: colunas ausentes: {missing}")

    g = pd.DataFrame({
        "codigo_base": df["Estação No."].map(norm_code),
        "base_gestao": df["Nome da base"].fillna("").astype(str).str.strip(),
        "regional": df["Regional"].fillna("").astype(str).str.strip(),
        "uf": df["Estado(UF)"].fillna("").astype(str).str.strip(),
        "rm": df["Responsável da Região"].fillna("").astype(str).str.strip(),
        "coordenador": df["Coordenador"].fillna("").astype(str).str.strip(),
        "supervisor": df["Supervisor"].fillna("").astype(str).str.strip(),
        "status": df["Status atual"].fillna("").astype(str).str.strip() if "Status atual" in df.columns else "",
    })
    g = g[g["codigo_base"].ne("")].copy()
    g["sc"] = g["coordenador"].where(g["coordenador"].str.strip().ne(""), g["supervisor"])
    g["sc"] = g["sc"].replace("", "—")
    g["ativo_rank"] = g["status"].map(lambda x: 0 if "ATIV" in norm_text(x) or "OPERANDO" in norm_text(x) else 1)
    g = g.sort_values(["codigo_base", "ativo_rank"]).drop_duplicates("codigo_base", keep="first")
    return g.drop(columns=["ativo_rank"])


def enrich_and_filter(df: pd.DataFrame, gestao: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    base = df.merge(gestao, on="codigo_base", how="left")
    sem_match = int(base["rm"].isna().sum())

    base["rm"] = base["rm"].fillna("")
    base["sc"] = base["sc"].fillna("—")
    base["uf"] = base["uf"].fillna("")
    base["regional"] = base["regional"].fillna("")
    base["base_gestao"] = base["base_gestao"].fillna("")
    base["base"] = base["base_gestao"].where(base["base_gestao"].str.strip().ne(""), base["base"])

    regional = base[base["rm"].map(norm_text).eq(norm_text(RM_ALVO))].copy()
    return regional, sem_match


def build() -> tuple[pd.DataFrame, dict]:
    fontes, gestao_file = find_files()
    gestao = read_gestao(gestao_file)

    padrao_frames: list[pd.DataFrame] = []
    consol_frames: list[pd.DataFrame] = []
    tipos: list[dict] = []

    for path, tipo, sheet in fontes:
        tipos.append({"arquivo": path, "tipo": tipo, "aba": sheet})
        if tipo == "padrao":
            padrao_frames.append(read_t0_padrao(path, sheet))
        elif tipo == "consolidado":
            consol_frames.append(read_t0_consolidado(path, sheet))

    saidas: list[pd.DataFrame] = []
    sem_match_total = 0
    pedidos_unicos = 0
    pedidos_regional = 0
    divergencias_taxa = 0

    if padrao_frames:
        pedidos = pd.concat(padrao_frames, ignore_index=True)
        pedidos["has_entrega"] = pedidos["entrega"].notna().astype(int)
        pedidos = pedidos.sort_values(["numero_remessa", "has_entrega", "entrega"], na_position="first")
        pedidos = pedidos.drop_duplicates("numero_remessa", keep="last").drop(columns=["has_entrega"])
        pedidos_unicos = len(pedidos)

        regional, sem_match = enrich_and_filter(pedidos, gestao)
        sem_match_total += sem_match
        pedidos_regional = len(regional)

        agg_raw = (
            regional.groupby(["data", "codigo_base", "base", "regional", "uf", "rm", "sc"], dropna=False)
            .agg(total_pedidos=("numero_remessa", "nunique"), t0_ok=("t0_ok", "sum"))
            .reset_index()
        )
        agg_raw["t0_ok"] = agg_raw["t0_ok"].astype(int)
        agg_raw["t0_perdido"] = agg_raw["total_pedidos"] - agg_raw["t0_ok"]
        agg_raw["taxa_t0"] = (agg_raw["t0_ok"] / agg_raw["total_pedidos"]).round(4)
        agg_raw["prioridade_fonte"] = 2
        agg_raw["tipo_fonte"] = "padrao"
        saidas.append(agg_raw)

    if consol_frames:
        consolidado = pd.concat(consol_frames, ignore_index=True)
        divergencias_taxa = int(consolidado["taxa_divergente"].sum())
        consolidado = consolidado.drop_duplicates(["data", "codigo_base"], keep="last")
        regional_c, sem_match = enrich_and_filter(consolidado, gestao)
        sem_match_total += sem_match

        cols = [
            "data", "codigo_base", "base", "regional", "uf", "rm", "sc",
            "total_pedidos", "t0_ok", "t0_perdido", "taxa_t0"
        ]
        agg_con = regional_c[cols].copy()
        agg_con["prioridade_fonte"] = 1
        agg_con["tipo_fonte"] = "consolidado"
        saidas.append(agg_con)

    if not saidas:
        raise RuntimeError("Nenhuma linha T0 válida foi gerada.")

    final = pd.concat(saidas, ignore_index=True)
    antes = len(final)
    final = final.sort_values(["data", "codigo_base", "prioridade_fonte"])
    final = final.drop_duplicates(["data", "codigo_base"], keep="last")
    sobreposicoes = antes - len(final)
    final = final.drop(columns=["prioridade_fonte", "tipo_fonte"]).sort_values(["data", "base"]).reset_index(drop=True)

    info = {
        "fontes": tipos,
        "gestao": gestao_file,
        "pedidos_unicos": pedidos_unicos,
        "pedidos_regional": pedidos_regional,
        "sem_match_gestao": sem_match_total,
        "linhas_agregadas": len(final),
        "sobreposicoes": sobreposicoes,
        "divergencias_taxa": divergencias_taxa,
        "data_min": final["data"].min() if len(final) else None,
        "data_max": final["data"].max() if len(final) else None,
    }
    return final, info


def ensure_schema(conn):
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def upload(df: pd.DataFrame):
    from db import get_conn
    records = df.copy()
    records["data"] = pd.to_datetime(records["data"]).dt.date

    cols = [
        "data", "codigo_base", "base", "regional", "uf", "rm", "sc",
        "total_pedidos", "t0_ok", "t0_perdido", "taxa_t0"
    ]

    values = []
    for row in records[cols].itertuples(index=False, name=None):
        values.append(tuple(None if pd.isna(v) else v.item() if hasattr(v, "item") else v for v in row))

    statement = """
        insert into public.t0_diario (
            data, codigo_base, base, regional, uf, rm, sc,
            total_pedidos, t0_ok, t0_perdido, taxa_t0
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (data, codigo_base) do update set
            base = excluded.base,
            regional = excluded.regional,
            uf = excluded.uf,
            rm = excluded.rm,
            sc = excluded.sc,
            total_pedidos = excluded.total_pedidos,
            t0_ok = excluded.t0_ok,
            t0_perdido = excluded.t0_perdido,
            taxa_t0 = excluded.taxa_t0,
            atualizado_em = now()
    """

    with get_conn() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.executemany(statement, values)
        conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Importa automaticamente T0 padrão/lista + consolidado histórico + Gestão de colaboradores"
    )
    parser.add_argument("--dry-run", action="store_true", help="Processa e mostra resumo sem gravar no PostgreSQL")
    args = parser.parse_args()

    df, info = build()
    print("=" * 72)
    print("IMPORTAÇÃO T0 - J&T")
    print("=" * 72)
    print("Fontes T0 reconhecidas:")
    for item in info["fontes"]:
        print(f"  - [{item['tipo'].upper()}] {item['arquivo']} | aba: {item['aba']}")
    print(f"Gestão: {info['gestao']}")
    if info["pedidos_unicos"]:
        print(f"Pedidos únicos no(s) arquivo(s) padrão: {info['pedidos_unicos']:,}")
        print(f"Pedidos padrão da regional {RM_ALVO}: {info['pedidos_regional']:,}")
    print(f"Pedidos/linhas sem match na Gestão: {info['sem_match_gestao']:,}")
    print(f"Sobreposições data+base removidas: {info['sobreposicoes']:,}")
    if info["divergencias_taxa"]:
        print(f"ATENÇÃO: {info['divergencias_taxa']:,} linhas consolidadas têm taxa pronta divergente de entregue/total (>0,5 p.p.).")
    print(f"Período final: {info['data_min']} a {info['data_max']}")
    print(f"Linhas diárias/base geradas: {info['linhas_agregadas']:,}")
    if len(df):
        total = int(df["total_pedidos"].sum())
        ok = int(df["t0_ok"].sum())
        taxa = ok / total if total else 0
        print(f"T0 consolidado do período importado: {taxa:.2%} | Meta: {META_T0:.0%}")
    if args.dry_run:
        print("DRY-RUN: nada gravado no PostgreSQL.")
        return
    upload(df)
    print("Importação concluída com sucesso no PostgreSQL local.")


if __name__ == "__main__":
    main()
