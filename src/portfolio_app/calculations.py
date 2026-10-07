
from __future__ import annotations

import math
import numpy as np
import pandas as pd


BUY_OPERATIONS = {"Compra", "Aporte"}
SELL_OPERATIONS = {"Venda", "Retirada"}
TRADING_DAYS = 252


def build_positions(assets,transactions,quote_by_asset,corporate_actions=None):
    from decimal import Decimal
    from .financial import decimal_from_row,decimal_value
    groups={}
    for a in assets:
        aid=int(a["id_ativo"]); groups[aid]={"id_ativo":aid,"ticker":a["ticker"],"nome_ativo":a["nome_ativo"],"classe_ativo":a["classe_ativo"],"categoria_fundo_setor":a.get("categoria_fundo_setor") or "Sem categoria","moeda_ativo":a.get("moeda_ativo") or a.get("moeda") or "BRL","moeda_base":"BRL","q":Decimal(0),"_price_d":Decimal(0),"cost":Decimal(0),"realized":Decimal(0),"income":Decimal(0),"invested":Decimal(0),"fees":Decimal(0),"activity":False,"ultimo_preco":0.0,"fonte_cotacao":"Sem cotação","data_cotacao":""}
    events=[(str(t["data_transacao"]),1,int(t.get("id_transacao",0)),t) for t in transactions]
    for x in corporate_actions or []:
        if str(x.get("tipo_provento","")).title()=="Split": events.append((str(x["data_com"]),0,int(x.get("id_provento",0)),x))
    for _,kind,_,e in sorted(events,key=lambda x:x[:3]):
        aid=int(e["id_ativo"])
        if aid not in groups: continue
        r=groups[aid]; r["activity"]=True
        if kind==0:
            factor=decimal_value(e.get("valor_por_acao"))
            if factor>0: r["q"]*=factor
            continue
        q=decimal_value(e.get("quantidade_original",e["quantidade"])); op=str(e["tipo_operacao"]).title()
        currency=str(e.get("moeda_transacao") or "BRL").upper()
        if currency!="BRL" and e.get("valor_total_brl") in (None,"") and e.get("taxa_cambio") in (None,""):
            raise ValueError(f"Câmbio histórico pendente para {r['ticker']} em {e['data_transacao']} ({currency}); informe a taxa antes de consultar resultados.")
        fx=decimal_value(e.get("taxa_cambio"),Decimal(1))
        total=decimal_from_row(e,"valor_total_brl","valor_total_original")
        if e.get("valor_total_brl") in (None,""): total=q*decimal_from_row(e,"preco_unitario_original","preco_unitario")*fx
        if e.get("taxas_custos_brl") not in (None,""):
            fee=decimal_from_row(e,"taxas_custos_brl","taxas_custos_original")
        else:
            fee=decimal_from_row(e,"taxas_custos_original","taxas_custos")
            fee*=fx
        r["fees"]+=fee
        if op in BUY_OPERATIONS: r["q"]+=q; r["cost"]+=total+fee; r["invested"]+=total+fee
        elif op in SELL_OPERATIONS:
            if q>r["q"]: raise ValueError(f"Venda/retirada excede posição de {r['ticker']}.")
            basis=r["cost"]/r["q"]*q if r["q"] else Decimal(0)
            if op=="Venda": r["realized"]+=total-fee-basis
            r["q"]-=q; r["cost"]-=basis
    for e in corporate_actions or []:
        if str(e.get("tipo_provento","")).title()!="Split" and int(e["id_ativo"]) in groups:
            r=groups[int(e["id_ativo"])]; r["income"]+=decimal_from_row(e,"valor_total_brl","valor_total"); r["activity"]=True
    for aid,q in quote_by_asset.items():
        if aid in groups:
            groups[aid]["_price_d"]=decimal_value(q.get("preco_fechamento_decimal",q["preco_fechamento"])); groups[aid]["ultimo_preco"]=float(groups[aid]["_price_d"]); groups[aid]["fonte_cotacao"]=str(q.get("fonte_dados","Sem origem")); groups[aid]["data_cotacao"]=str(q.get("data_cotacao",""))
    rows=[]
    for r in groups.values():
        q,cost,realized,income,invested,fees=(r.pop(k) for k in ("q","cost","realized","income","invested","fees")); mark=r.pop("_price_d")
        if not r.pop("activity") and q==0: continue
        price=mark if mark>0 else cost/q if q else Decimal(0)
        if r["ultimo_preco"]<=0 and q: r["fonte_cotacao"]="Estimado pelo custo médio"
        market=q*price; unrl=market-cost; total=realized+unrl+income
        r.update({"quantidade":float(q),"preco_medio":float(cost/q) if q else 0.0,"ultimo_preco":float(price),"valor_mercado":float(market),"custo_total":float(cost),"base_investida":float(invested),"resultado_realizado":float(realized),"resultado_nao_realizado":float(unrl),"proventos_total":float(income),"resultado_total":float(total),"rentabilidade_pct":float(total/invested) if invested else None,"taxas_total":float(fees)})
        rows.append(r)
    cols=["id_ativo","ticker","nome_ativo","classe_ativo","categoria_fundo_setor","moeda_ativo","moeda_base","quantidade","preco_medio","ultimo_preco","valor_mercado","custo_total","base_investida","resultado_realizado","resultado_nao_realizado","proventos_total","resultado_total","rentabilidade_pct","taxas_total","fonte_cotacao","data_cotacao"]
    frame=pd.DataFrame(rows,columns=cols)
    if not frame.empty:
        total=frame["valor_mercado"].sum(); frame["peso_pct"]=frame["valor_mercado"]/total*100 if total else 0.0
    else: frame["peso_pct"]=pd.Series(dtype=float)
    return frame

def fixed_income_positions(records):
    from .financial import decimal_value
    rows=[]
    for x in records:
        invested_d=decimal_value(x["valor_investido"]); current_d=decimal_value(x["valor_atualizado"]); result_d=current_d-invested_d
        invested=float(invested_d); current=float(current_d); result=float(result_d)
        rows.append({"id_ativo":-int(x["id_renda_fixa"]),"ticker":f"RF-{x['id_renda_fixa']}","nome_ativo":x["nome"],"classe_ativo":"Renda Fixa","categoria_fundo_setor":x.get("indexador") or x.get("tipo") or "Manual","moeda_ativo":"BRL","moeda_base":"BRL","quantidade":1.0,"preco_medio":invested,"ultimo_preco":current,"valor_mercado":current,"custo_total":invested,"base_investida":invested,"resultado_realizado":0.0,"resultado_nao_realizado":result,"proventos_total":0.0,"resultado_total":result,"rentabilidade_pct":float(result_d/invested_d) if invested_d else None,"taxas_total":0.0,"fonte_cotacao":"Manual","data_cotacao":str(x.get("atualizado_em","")),"peso_pct":0.0})
    frame=pd.DataFrame(rows)
    if not frame.empty:
        total=frame["valor_mercado"].sum(); frame["peso_pct"]=frame["valor_mercado"]/total*100 if total else 0.0
    return frame
def historical_prices(quote_rows: list[dict]) -> pd.DataFrame:
    if not quote_rows:
        return pd.DataFrame()
    frame = pd.DataFrame(quote_rows)
    frame["data_cotacao"] = pd.to_datetime(frame["data_cotacao"], errors="coerce")
    frame["preco_fechamento"] = pd.to_numeric(frame["preco_fechamento"], errors="coerce")
    frame = frame.dropna(subset=["data_cotacao", "preco_fechamento"])
    if frame.empty:
        return pd.DataFrame()
    pivot = frame.pivot_table(
        index="data_cotacao", columns="ticker", values="preco_fechamento", aggfunc="last"
    ).sort_index()
    return pivot


def asset_returns(price_frame: pd.DataFrame) -> pd.DataFrame:
    if price_frame.empty:
        return pd.DataFrame()
    return price_frame.sort_index().pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)


def weighted_returns(
    returns: pd.DataFrame,
    positions: pd.DataFrame,
    additional_weights: dict[str, float] | None = None,
) -> pd.Series:
    if returns.empty or positions.empty:
        return pd.Series(dtype=float, name="Carteira")
    total = float(positions["valor_mercado"].sum())
    if total <= 0:
        return pd.Series(dtype=float, name="Carteira")
    weights = {
        str(row["ticker"]): float(row["valor_mercado"]) / total
        for row in positions.to_dict("records")
        if row["ticker"] in returns.columns and float(row["valor_mercado"]) > 0
    }
    if additional_weights:
        weights.update(additional_weights)
    available = [ticker for ticker in weights if ticker in returns.columns]
    if not available:
        return pd.Series(dtype=float, name="Carteira")
    weight_total = sum(weights[ticker] for ticker in available)
    if weight_total <= 0:
        return pd.Series(dtype=float, name="Carteira")
    normalized = {ticker: weights[ticker] / weight_total for ticker in available}
    selected = returns[available].dropna(how="any")
    series = selected.mul(pd.Series(normalized), axis="columns").sum(axis=1, min_count=1)
    series = series.dropna()
    series.name = "Carteira"
    return series


def ewma_daily_volatility(returns: pd.Series, decay: float = 0.94) -> float | None:
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return None
    variance = float(np.var(values, ddof=1))
    for value in values[1:]:
        variance = decay * variance + (1.0 - decay) * float(value) ** 2
    return math.sqrt(max(variance, 0.0))


def risk_metrics(returns: pd.Series, risk_free_annual: float = 0.0) -> dict[str, float | None]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if len(values) < 2:
        return {
            "retorno_anualizado": None,
            "volatilidade_ewma": None,
            "sharpe": None,
            "retorno_acumulado": None,
        }
    clipped = values.clip(lower=-0.999999)
    cumulative = float((1.0 + clipped).prod() - 1.0)
    annualized_return = float((1.0 + cumulative) ** (TRADING_DAYS / len(clipped)) - 1.0) if cumulative > -1 else -1.0
    daily_vol = ewma_daily_volatility(clipped)
    annual_vol = daily_vol * math.sqrt(TRADING_DAYS) if daily_vol is not None else None
    sharpe = (
        (annualized_return - float(risk_free_annual)) / annual_vol
        if annual_vol is not None and annual_vol > 0
        else None
    )
    return {
        "retorno_anualizado": annualized_return,
        "volatilidade_ewma": annual_vol,
        "sharpe": sharpe,
        "retorno_acumulado": cumulative,
    }


def beta_against(asset_returns_series: pd.Series, market_returns_series: pd.Series) -> float | None:
    paired = pd.concat([asset_returns_series, market_returns_series], axis=1).dropna()
    if len(paired) < 20:
        return None
    market_variance = float(paired.iloc[:, 1].var(ddof=1))
    if market_variance <= 0:
        return None
    return float(paired.iloc[:, 0].cov(paired.iloc[:, 1]) / market_variance)


def capm_expected_return(
    beta: float | None, risk_free_annual: float, market_return_annual: float
) -> float | None:
    if beta is None:
        return None
    return float(risk_free_annual + beta * (market_return_annual - risk_free_annual))


def concentration_alerts(positions: pd.DataFrame, threshold_pct: float = 25.0) -> list[str]:
    if positions.empty:
        return []
    alerts: list[str] = []
    for field, label in (
        ("categoria_fundo_setor", "setor/tipo"),
        ("classe_ativo", "classe"),
    ):
        grouped = positions.groupby(field, dropna=False)["valor_mercado"].sum()
        total = float(grouped.sum())
        if total <= 0:
            continue
        for name, amount in grouped.items():
            share = float(amount) / total * 100
            if share > threshold_pct:
                alerts.append(f"{label.capitalize()} {name}: {share:.1f}% da carteira (limite de referência {threshold_pct:.0f}%).")
    return alerts


def project_scenarios(
    starting_value: float,
    monthly_contribution: float,
    months: int,
    selected_rate: float,
    reference_rate: float,
    optimistic_rate: float,
    monthly_volatility: float,
    contribution_every_months: int = 1,
    simulations: int = 800,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = int(months)
    if months < 1 or months > 600:
        raise ValueError("O horizonte deve estar entre 1 e 600 meses.")
    if starting_value < 0 or monthly_contribution < 0:
        raise ValueError("Patrimônio inicial e aporte não podem ser negativos.")
    if selected_rate <= -1 or reference_rate <= -1 or optimistic_rate <= -1:
        raise ValueError("As taxas mensais devem ser maiores que -100%.")
    contribution_every_months = max(1, int(contribution_every_months))

    def deterministic(rate: float) -> list[float]:
        balance = float(starting_value)
        values = [balance]
        for month in range(1, months + 1):
            balance *= 1.0 + rate
            if month % contribution_every_months == 0:
                balance += monthly_contribution
            values.append(balance)
        return values

    path = pd.DataFrame(
        {
            "Mês": np.arange(months + 1),
            "Taxa escolhida": deterministic(selected_rate),
            f"Referência {reference_rate * 100:.1f}% a.m.": deterministic(reference_rate),
            f"Meta {optimistic_rate * 100:.1f}% a.m.": deterministic(optimistic_rate),
        }
    )
    rng = np.random.default_rng(940)
    vol = max(0.0, float(monthly_volatility))
    matrix = np.zeros((simulations, months + 1), dtype=float)
    matrix[:, 0] = float(starting_value)
    for step in range(1, months + 1):
        shocks = rng.normal(0.0, vol, size=simulations)
        matrix[:, step] = np.maximum(0.0, matrix[:, step - 1] * (1.0 + selected_rate + shocks))
        if step % contribution_every_months == 0:
            matrix[:, step] += monthly_contribution
    band = pd.DataFrame(
        {
            "Mês": np.arange(months + 1),
            "Mediana": np.quantile(matrix, 0.50, axis=0),
            "Percentil 10": np.quantile(matrix, 0.10, axis=0),
            "Percentil 90": np.quantile(matrix, 0.90, axis=0),
        }
    )
    return path, band


def dividend_yield_12m(dividends: list[dict], asset_id: int, market_value: float) -> float | None:
    if market_value <= 0:
        return None
    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(months=12)
    total_paid = 0.0
    for row in dividends:
        if int(row["id_ativo"]) != int(asset_id):
            continue
        date = pd.to_datetime(row["data_pagamento"] or row["data_com"], errors="coerce")
        if pd.notna(date) and date >= cutoff:
            total_paid += float(row["valor_total"])
    return total_paid / market_value
