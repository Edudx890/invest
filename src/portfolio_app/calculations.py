from __future__ import annotations

import math
import numpy as np
import pandas as pd


BUY_OPERATIONS = {"Compra", "Aporte"}
SELL_OPERATIONS = {"Venda", "Retirada"}
TRADING_DAYS = 252


def build_positions(
    assets: list[dict],
    transactions: list[dict],
    quote_by_asset: dict[int, dict],
    corporate_actions: list[dict] | None = None,
) -> pd.DataFrame:
    """Apply a moving-average cost method to the transaction ledger."""
    grouped: dict[int, dict] = {}
    for asset in assets:
        asset_id = int(asset["id_ativo"])
        grouped[asset_id] = {
            "id_ativo": asset_id,
            "ticker": asset["ticker"],
            "nome_ativo": asset["nome_ativo"],
            "classe_ativo": asset["classe_ativo"],
            "categoria_fundo_setor": asset.get("categoria_fundo_setor") or "Sem categoria",
            "quantidade": 0.0,
            "custo_total": 0.0,
            "ultimo_preco": 0.0,
            "fonte_cotacao": "Sem cotação",
            "data_cotacao": "",
        }
    events = []
    for txn in transactions:
        events.append((str(txn["data_transacao"]), 1, txn))
    for action in corporate_actions or []:
        if str(action.get("tipo_provento", "")).title() == "Split":
            events.append((str(action["data_com"]), 0, action))
    for _, _, event in sorted(events, key=lambda item: (item[0], item[1])):
        asset_id = int(event["id_ativo"])
        if asset_id not in grouped:
            continue
        current = grouped[asset_id]
        if "tipo_provento" in event:
            factor = float(event["valor_por_acao"])
            if factor > 0:
                current["quantidade"] *= factor
            continue
        quantity = float(event["quantidade"])
        unit_price = float(event["preco_unitario"])
        fees = float(event.get("taxas_custos") or 0.0)
        operation = event["tipo_operacao"].title()
        if operation in BUY_OPERATIONS:
            current["quantidade"] += quantity
            current["custo_total"] += quantity * unit_price + fees
        elif operation in SELL_OPERATIONS:
            if current["quantidade"] > 0:
                average_cost = current["custo_total"] / current["quantidade"]
                removed = min(quantity, current["quantidade"])
                current["quantidade"] -= removed
                current["custo_total"] -= removed * average_cost
    for asset_id, quote in quote_by_asset.items():
        if asset_id in grouped:
            grouped[asset_id]["ultimo_preco"] = float(quote["preco_fechamento"])
            grouped[asset_id]["fonte_cotacao"] = str(quote["fonte_dados"])
            grouped[asset_id]["data_cotacao"] = str(quote["data_cotacao"])
    records = []
    for row in grouped.values():
        if row["quantidade"] <= 1e-12:
            continue
        price = row["ultimo_preco"]
        if price <= 0:
            price = row["custo_total"] / row["quantidade"] if row["quantidade"] else 0.0
            row["fonte_cotacao"] = "Preço médio de aquisição"
        row["preco_medio"] = row["custo_total"] / row["quantidade"] if row["quantidade"] else 0.0
        row["ultimo_preco"] = price
        row["valor_mercado"] = row["quantidade"] * price
        row["resultado_nao_realizado"] = row["valor_mercado"] - row["custo_total"]
        records.append(row)
    columns = [
        "id_ativo", "ticker", "nome_ativo", "classe_ativo", "categoria_fundo_setor",
        "quantidade", "preco_medio", "ultimo_preco", "valor_mercado", "custo_total",
        "resultado_nao_realizado", "fonte_cotacao", "data_cotacao",
    ]
    frame = pd.DataFrame(records, columns=columns)
    if not frame.empty:
        total = frame["valor_mercado"].sum()
        frame["peso_pct"] = frame["valor_mercado"] / total * 100 if total else 0.0
    else:
        frame["peso_pct"] = pd.Series(dtype=float)
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
