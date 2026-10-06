from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from portfolio_app import db
from portfolio_app.calculations import (
    asset_returns,
    beta_against,
    build_positions,
    capm_expected_return,
    concentration_alerts,
    dividend_yield_12m,
    project_scenarios,
    risk_metrics,
    weighted_returns,
)
from portfolio_app.importers import parse_upload
from portfolio_app.market_data import MarketDataError, fetch_history, fetch_yahoo_history


st.set_page_config(
    page_title="Carteira Clara",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

ASSET_CLASSES = ["Ação", "FII", "ETF", "Cripto", "Renda Fixa", "Outro"]
OPERATIONS = ["Compra", "Venda", "Aporte", "Retirada"]
DEFAULTS = {
    "meta_mensal_1": "0.015",
    "meta_mensal_2": "0.020",
    "risk_free_annual": "",
    "fixed_income_reference": "0.40",
    "concentration_limit_pct": "25",
}


@st.cache_data(ttl=900, show_spinner=False)
def cached_market_history(
    ticker: str, asset_class: str, api_code: str, period: str = "1y", currency: str = "BRL"
) -> pd.DataFrame:
    return fetch_history(ticker, asset_class, api_code or None, period, currency)


@st.cache_resource
def initialize_database():
    db.init_db()
    return True


def settings() -> dict[str, str]:
    return {key: db.get_setting(key, default) for key, default in DEFAULTS.items()}


def risk_free_rate(config: dict[str, str]) -> float:
    try:
        return float(config["risk_free_annual"]) / 100.0
    except (TypeError, ValueError):
        return 0.0


def records(rows) -> list[dict]:
    return [dict(row) for row in rows]


def load_portfolio() -> tuple[pd.DataFrame, list[dict], list[dict], pd.DataFrame]:
    assets = records(db.list_assets())
    transactions = records(db.list_transactions())
    quotes = records(db.list_quotes())
    corporate_actions = records(db.list_dividends())
    latest = {int(asset_id): dict(row) for asset_id, row in db.latest_quotes().items()}
    position_frame = build_positions(assets, transactions, latest, corporate_actions)
    price_frame = pd.DataFrame()
    if quotes:
        price_frame = pd.DataFrame(quotes)
    return position_frame, assets, transactions, price_frame


def fmt_brl(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None or pd.isna(value) else f"{value * 100:.{digits}f}%"


def notify_refresh(assets: list[dict]) -> tuple[int, list[str]]:
    updated = 0
    failures: list[str] = []
    for asset in assets:
        try:
            history = cached_market_history(
                asset["ticker"],
                asset["classe_ativo"],
                asset.get("codigo_api") or "",
                "1y",
                asset.get("moeda", "BRL"),
            )
            for quote in history.to_dict("records"):
                db.upsert_quote(
                    int(asset["id_ativo"]),
                    str(quote["data"]),
                    float(quote["preco"]),
                    str(quote["fonte"]),
                    manual=False,
                )
                split_factor = float(quote.get("split") or 0.0)
                if split_factor > 0:
                    db.add_dividend(
                        int(asset["id_ativo"]),
                        "Split",
                        str(quote["data"]),
                        None,
                        split_factor,
                        0.0,
                        manual=False,
                    )
                dividend_per_unit = float(quote.get("dividendo") or 0.0)
                if dividend_per_unit > 0:
                    shares_on_date = db.quantity_as_of(int(asset["id_ativo"]), str(quote["data"]))
                    db.add_dividend(
                        int(asset["id_ativo"]),
                        "Dividendo",
                        str(quote["data"]),
                        str(quote["data"]),
                        dividend_per_unit,
                        dividend_per_unit * shares_on_date,
                        manual=False,
                    )
            updated += 1
        except Exception as exc:
            failures.append(f"{asset['ticker']}: {exc}")
    return updated, failures


def maybe_refresh_first_visit(assets: list[dict]) -> list[str]:
    """Fetch market data on the first portfolio view; the provider cache lasts 15 minutes."""
    if not assets or st.session_state.get("_first_market_refresh_done"):
        return []
    st.session_state["_first_market_refresh_done"] = True
    with st.spinner("Consultando cotações e guardando os dados disponíveis..."):
        _, failures = notify_refresh(assets)
    return failures


def current_analysis(position_frame: pd.DataFrame, quote_frame: pd.DataFrame, config: dict[str, str]):
    prices = pd.DataFrame()
    if not quote_frame.empty:
        prices = pd.DataFrame(
            {
                "id_ativo": quote_frame["id_ativo"],
                "ticker": quote_frame["ticker"],
                "data_cotacao": quote_frame["data_cotacao"],
                "preco_fechamento": quote_frame["preco_fechamento"],
            }
        )
    pivot = pd.DataFrame()
    returns = pd.DataFrame()
    portfolio_series = pd.Series(dtype=float, name="Carteira")
    metrics = risk_metrics(portfolio_series, risk_free_rate(config))
    if not prices.empty:
        pivot = prices.pivot_table(
            index="data_cotacao", columns="ticker", values="preco_fechamento", aggfunc="last"
        ).sort_index()
        returns = asset_returns(pivot)
        portfolio_series = weighted_returns(returns, position_frame)
        metrics = risk_metrics(portfolio_series, risk_free_rate(config))
    return pivot, returns, portfolio_series, metrics


def render_sidebar() -> str:
    with st.sidebar:
        st.title("Carteira Clara")
        st.caption("Análise pessoal de investimentos")
        choice = st.radio(
            "Navegação",
            [
                "Visão geral",
                "Estado atual",
                "Previsão",
                "Simular ativo",
                "Cadastro e importação",
                "Configurações e backup",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("Ferramenta analítica local. Não envia ordens e não recomenda compras ou vendas.")
        st.caption("Rentabilidade passada não representa garantia de rendimentos futuros.")
        st.caption(f"Banco local: {db.DB_PATH.name}")
    return choice


def render_metrics(position_frame: pd.DataFrame, metrics: dict, dividends: list[dict], config: dict[str, str]):
    value = float(position_frame["valor_mercado"].sum()) if not position_frame.empty else 0.0
    cost = float(position_frame["custo_total"].sum()) if not position_frame.empty else 0.0
    pnl = value - cost
    pnl_pct = pnl / cost if cost else None
    risk = metrics["volatilidade_ewma"]
    sharpe = metrics["sharpe"]
    cols = st.columns(5)
    cols[0].metric("Patrimônio estimado", fmt_brl(value))
    cols[1].metric("Resultado não realizado", fmt_brl(pnl), fmt_pct(pnl_pct))
    cols[2].metric("Retorno anualizado¹", fmt_pct(metrics["retorno_anualizado"]))
    cols[3].metric("Volatilidade EWMA anual", fmt_pct(risk))
    cols[4].metric("Sharpe anualizado", "—" if sharpe is None else f"{sharpe:.2f}")
    if not config["risk_free_annual"].strip():
        st.info("Informe a taxa Selic/CDI anual nas configurações para contextualizar o índice de Sharpe.")
    if position_frame.empty:
        return
    current_yields = []
    for row in position_frame.to_dict("records"):
        ratio = dividend_yield_12m(dividends, int(row["id_ativo"]), float(row["valor_mercado"]))
        if ratio is not None:
            current_yields.append((float(row["peso_pct"]) / 100.0) * ratio)
    if current_yields:
        st.caption(f"Dividend yield ponderado de proventos registrados em 12 meses: {fmt_pct(sum(current_yields))}.")
    st.caption("¹ Estimativa anualizada com os preços disponíveis e a composição atual da carteira.")


def render_overview(position_frame, assets, quote_frame, dividends, config):
    st.title("Visão geral")
    st.write("Resumo da carteira real. Projeções e ativos hipotéticos ficam em áreas separadas.")
    _, _, portfolio_series, metrics = current_analysis(position_frame, quote_frame, config)
    render_metrics(position_frame, metrics, dividends, config)
    if position_frame.empty:
        st.info("Cadastre sua primeira posição ou importe transações na seção Cadastro e importação.")
        return
    alerts = concentration_alerts(position_frame, float(config["concentration_limit_pct"]))
    for alert in alerts:
        st.warning("Concentração: " + alert)
    left, right = st.columns(2)
    with left:
        by_class = position_frame.groupby("classe_ativo", as_index=False)["valor_mercado"].sum()
        fig = px.pie(by_class, names="classe_ativo", values="valor_mercado", hole=0.48, title="Alocação por classe")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        by_category = position_frame.groupby("categoria_fundo_setor", as_index=False)["valor_mercado"].sum()
        fig = px.pie(by_category, names="categoria_fundo_setor", values="valor_mercado", hole=0.48, title="Alocação por setor/tipo")
        st.plotly_chart(fig, use_container_width=True)
    if len(portfolio_series) > 1:
        start_value = float(position_frame["valor_mercado"].sum())
        history = (1.0 + portfolio_series).cumprod() * start_value
        chart = px.line(
            x=pd.to_datetime(history.index),
            y=history.values,
            labels={"x": "Data", "y": "Índice do patrimônio (R$)"},
            title="Evolução indicativa com os pesos atuais",
        )
        st.plotly_chart(chart, use_container_width=True)
        st.caption("Histórico reponderado pela composição atual; não reconstrói aportes e vendas passados.")
    manual_count = sum(int(row.get("is_manual_entry") or 0) for row in assets)
    st.caption(f"Ativos cadastrados: {len(assets)} · ativos com origem manual: {manual_count}")


def render_current_state(position_frame, assets, quote_frame, dividends, config):
    st.title("Estado atual da carteira")
    st.write("Posições derivadas do histórico de compras, vendas e ajustes cadastrados.")
    refresh_col, help_col = st.columns([1, 3])
    with refresh_col:
        refresh_clicked = st.button("Atualizar cotações", type="primary", use_container_width=True)
    if refresh_clicked:
        cached_market_history.clear()
        updated, failures = notify_refresh(assets)
        if updated:
            st.success(f"Histórico atualizado para {updated} ativo(s).")
        if failures:
            st.warning("Algumas fontes falharam; as últimas cotações locais continuam disponíveis.")
            for failure in failures[:8]:
                st.caption(failure)
        st.rerun()
    if assets and not st.session_state.get("_first_market_refresh_loaded"):
        first_failures = maybe_refresh_first_visit(assets)
        if first_failures:
            st.warning("Algumas cotações não foram localizadas. O sistema mantém dados locais e permite digitação manual.")
            for failure in first_failures[:6]:
                st.caption(failure)
        position_frame, assets, transactions, quote_frame = load_portfolio()
        st.session_state["_first_market_refresh_loaded"] = True
    _, _, portfolio_series, metrics = current_analysis(position_frame, quote_frame, config)
    render_metrics(position_frame, metrics, dividends, config)
    if position_frame.empty:
        st.info("Sua carteira ainda não contém posições. Cadastre ou importe transações para começar.")
        return
    st.subheader("Posições")
    display = position_frame[
        [
            "ticker", "nome_ativo", "classe_ativo", "quantidade", "preco_medio",
            "ultimo_preco", "valor_mercado", "peso_pct", "resultado_nao_realizado",
            "fonte_cotacao", "data_cotacao",
        ]
    ].copy()
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "quantidade": st.column_config.NumberColumn("Quantidade", format="%.6f"),
            "preco_medio": st.column_config.NumberColumn("Preço médio", format="R$ %.2f"),
            "ultimo_preco": st.column_config.NumberColumn("Último preço", format="R$ %.2f"),
            "valor_mercado": st.column_config.NumberColumn("Valor de mercado", format="R$ %.2f"),
            "peso_pct": st.column_config.NumberColumn("Peso", format="%.2f%%"),
            "resultado_nao_realizado": st.column_config.NumberColumn("Resultado", format="R$ %.2f"),
        },
    )
    left, right = st.columns(2)
    with left:
        allocation = position_frame.groupby("classe_ativo", as_index=False)["valor_mercado"].sum()
        st.plotly_chart(px.pie(allocation, names="classe_ativo", values="valor_mercado", hole=0.4, title="Distribuição por classe"), use_container_width=True)
    with right:
        allocation = position_frame.groupby("categoria_fundo_setor", as_index=False)["valor_mercado"].sum()
        st.plotly_chart(px.bar(allocation, x="categoria_fundo_setor", y="valor_mercado", title="Exposição por setor/tipo"), use_container_width=True)
    for alert in concentration_alerts(position_frame, float(config["concentration_limit_pct"])):
        st.warning("Concentração: " + alert)
    if len(portfolio_series) > 1:
        value = float(position_frame["valor_mercado"].sum())
        series = (1.0 + portfolio_series).cumprod() * value
        st.plotly_chart(
            px.line(x=pd.to_datetime(series.index), y=series.values, labels={"x": "Data", "y": "R$"}, title="Evolução indicativa do patrimônio"),
            use_container_width=True,
        )
        st.caption("Série indicativa calculada com pesos atuais e cotações registradas; eventos de fluxo de caixa anteriores não são reconstruídos.")
    if dividends:
        st.subheader("Proventos registrados")
        dividend_frame = pd.DataFrame(dividends)
        st.dataframe(
            dividend_frame[["ticker", "tipo_provento", "data_com", "data_pagamento", "valor_por_acao", "valor_total", "is_manual_entry"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "valor_por_acao": st.column_config.NumberColumn("Valor por unidade", format="R$ %.4f"),
                "valor_total": st.column_config.NumberColumn("Total", format="R$ %.2f"),
                "is_manual_entry": st.column_config.CheckboxColumn("Entrada manual"),
            },
        )


def render_forecast(position_frame, quote_frame, config):
    st.title("Previsão de investimentos")
    st.write("Compare cenários determinísticos e uma faixa de incerteza baseada em volatilidade histórica.")
    st.info("Rentabilidade passada não representa garantia de rendimentos futuros.")
    initial = float(position_frame["valor_mercado"].sum()) if not position_frame.empty else 0.0
    _, _, portfolio_series, metrics = current_analysis(position_frame, quote_frame, config)
    ref1 = float(config["meta_mensal_1"])
    ref2 = float(config["meta_mensal_2"])
    left, mid, right = st.columns(3)
    with left:
        units = st.number_input("Prazo", min_value=1, max_value=600, value=36, step=1)
        horizon_unit = st.selectbox("Unidade do prazo", ["Meses", "Semestres", "Anos"])
    with mid:
        contribution = st.number_input("Aporte recorrente (R$)", min_value=0.0, value=2000.0, step=100.0)
        contribution_freq = st.selectbox("Frequência do aporte", ["Mensal", "Semestral", "Anual"])
    with right:
        selected_rate_pct = st.number_input("Taxa mensal do cenário escolhido (%)", min_value=-99.0, max_value=100.0, value=ref1 * 100, step=0.1)
        fallback_vol_pct = st.number_input("Volatilidade anual se não houver histórico (%)", min_value=0.0, max_value=300.0, value=20.0, step=1.0)
    if horizon_unit == "Semestres":
        months = int(units) * 6
    elif horizon_unit == "Anos":
        months = int(units) * 12
    else:
        months = int(units)
    contribution_period = {"Mensal": 1, "Semestral": 6, "Anual": 12}[contribution_freq]
    annual_vol = metrics["volatilidade_ewma"] if metrics["volatilidade_ewma"] is not None else fallback_vol_pct / 100.0
    monthly_vol = annual_vol / np.sqrt(12.0)
    if st.button("Calcular projeção", type="primary"):
        try:
            path, band = project_scenarios(
                starting_value=initial,
                monthly_contribution=float(contribution),
                months=months,
                selected_rate=float(selected_rate_pct) / 100.0,
                reference_rate=ref1,
                optimistic_rate=ref2,
                monthly_volatility=monthly_vol,
                contribution_every_months=contribution_period,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=band["Mês"], y=band["Percentil 10"], name="Percentil 10", line={"width": 0}, hovertemplate="%{y:,.2f}<extra></extra>"))
        figure.add_trace(go.Scatter(x=band["Mês"], y=band["Percentil 90"], name="Faixa de incerteza (10–90%)", fill="tonexty", line={"width": 0}, hovertemplate="%{y:,.2f}<extra></extra>"))
        for column in path.columns[1:]:
            figure.add_trace(go.Scatter(x=path["Mês"], y=path[column], mode="lines", name=column))
        figure.update_layout(title="Patrimônio projetado", xaxis_title="Mês", yaxis_title="Patrimônio (R$)", hovermode="x unified")
        st.plotly_chart(figure, use_container_width=True)
        st.subheader("Valores ao longo do tempo")
        st.dataframe(path.merge(band, on="Mês"), use_container_width=True, hide_index=True, column_config={
            column: st.column_config.NumberColumn(column, format="R$ %.2f")
            for column in path.columns[1:]
        })
        st.caption(f"Patrimônio inicial: {fmt_brl(initial)} · Volatilidade anual usada: {fmt_pct(annual_vol)} · {contribution_freq.lower()} de {fmt_brl(contribution)}.")
    else:
        st.caption(f"Patrimônio inicial vindo do Estado atual: {fmt_brl(initial)}.")


def _manual_asset_returns(monthly_return_pct: float, annual_vol_pct: float) -> pd.Series:
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=252)
    daily_mean = (1.0 + monthly_return_pct / 100.0) ** (12.0 / 252.0) - 1.0
    daily_vol = annual_vol_pct / 100.0 / np.sqrt(252.0)
    values = np.random.default_rng(940).normal(daily_mean, daily_vol, len(days))
    return pd.Series(values, index=days, name="Ativo simulado")


def render_asset_simulation(position_frame, quote_frame, config):
    st.title("Análise de outros investimentos")
    st.write("Estude um ativo fora da carteira e compare seu impacto hipotético em risco, retorno e alocação.")
    st.info("A simulação é analítica e não envia ordens nem constitui recomendação.")
    with st.form("asset_simulation_form"):
        a, b, c = st.columns(3)
        ticker = a.text_input("Ticker", value="BOVA11").strip().upper()
        asset_class = b.selectbox("Classe do ativo", ASSET_CLASSES, index=2)
        api_code = c.text_input("Código no provedor (Yahoo ou ID CoinGecko)", value="")
        currency = st.selectbox("Moeda do ativo antes da conversão", ["BRL", "USD"], index=0, disabled=asset_class == "Cripto")
        if asset_class == "Cripto":
            currency = "BRL"
        amount = st.number_input("Valor hipotético da compra (R$)", min_value=0.01, value=10000.0, step=100.0)
        manual_mode = st.checkbox("Usar premissas manuais se o provedor não encontrar o ativo")
        manual_price = st.number_input("Preço atual manual (R$)", min_value=0.0, value=0.0, step=0.1)
        manual_return = st.number_input("Retorno mensal esperado manual (%)", min_value=-99.0, max_value=100.0, value=1.0, step=0.1)
        manual_vol = st.number_input("Volatilidade anual manual (%)", min_value=0.0, max_value=300.0, value=25.0, step=1.0)
        manual_dy = st.number_input("Dividend yield anual manual (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        submitted = st.form_submit_button("Simular adição de ativo", type="primary")
    if not submitted:
        return
    if position_frame.empty:
        st.error("Cadastre ao menos uma posição antes de simular o efeito na carteira.")
        return
    current_total = float(position_frame["valor_mercado"].sum())
    if current_total <= 0:
        st.error("O patrimônio da carteira precisa ser maior que zero.")
        return
    quote_frame = quote_frame.copy()
    if quote_frame.empty:
        quote_frame = pd.DataFrame(columns=["id_ativo", "ticker", "data_cotacao", "preco_fechamento"])
    price_pivot = pd.DataFrame()
    if not quote_frame.empty:
        price_pivot = quote_frame.pivot_table(index="data_cotacao", columns="ticker", values="preco_fechamento", aggfunc="last").sort_index()
    returns = asset_returns(price_pivot)
    before = weighted_returns(returns, position_frame)
    external_history = None
    source_label = "Premissas manuais"
    try:
        external_history = cached_market_history(ticker, asset_class, api_code, "1y", currency)
        source_label = str(external_history["fonte"].iloc[-1])
    except Exception as exc:
        if not manual_mode:
            st.error(f"Não foi possível obter dados para {ticker}: {exc}. Ative a entrada manual para continuar.")
            return
        st.warning(f"Dados de mercado indisponíveis ({exc}). A simulação usará apenas as premissas informadas.")
    if external_history is not None and not external_history.empty:
        external_prices = external_history.set_index(pd.to_datetime(external_history["data"]))["preco"].astype(float)
        external_daily = external_prices.pct_change(fill_method=None).dropna()
        if manual_price <= 0:
            manual_price = float(external_prices.iloc[-1])
        external_annual_return = float((1.0 + external_daily.clip(lower=-0.999).mean()) ** 252 - 1.0) if len(external_daily) else manual_return / 100.0 * 12
        external_vol = float(external_daily.std(ddof=1) * np.sqrt(252)) if len(external_daily) > 1 else manual_vol / 100
        asset_series = external_daily
    else:
        external_annual_return = (1.0 + manual_return / 100.0) ** 12 - 1.0
        external_vol = manual_vol / 100.0
        asset_series = _manual_asset_returns(manual_return, manual_vol)
    risk_free = risk_free_rate(config)
    before_metrics = risk_metrics(before, risk_free)
    beta_value = None
    capm_return = None
    benchmark_label = "Indisponível"
    try:
        if asset_class == "Cripto":
            benchmark_symbol = "BTC-USD"
            benchmark_label = "Bitcoin (BTC-USD)"
        elif currency == "USD" or (api_code and not api_code.upper().endswith(".SA")):
            benchmark_symbol = "^GSPC"
            benchmark_label = "S&P 500"
        else:
            benchmark_symbol = "^BVSP"
            benchmark_label = "Ibovespa"
        benchmark_frame = fetch_yahoo_history(benchmark_symbol, "Outro", "1y")
        benchmark_prices = pd.Series(
            benchmark_frame["preco"].to_numpy(dtype=float),
            index=pd.to_datetime(benchmark_frame["data"]),
        )
        benchmark_series = benchmark_prices.pct_change(fill_method=None).dropna()
        beta_value = beta_against(asset_series, benchmark_series)
        benchmark_metrics = risk_metrics(benchmark_series, risk_free)
        capm_return = capm_expected_return(
            beta_value,
            risk_free,
            benchmark_metrics["retorno_anualizado"] or 0.0,
        )
    except Exception:
        beta_value = None
        capm_return = None
    amount_weight = float(amount) / (current_total + float(amount))
    scaled_weights = {
        str(row["ticker"]): float(row["valor_mercado"]) / (current_total + float(amount))
        for row in position_frame.to_dict("records")
    }
    scaled_weights[ticker] = scaled_weights.get(ticker, 0.0) + amount_weight
    asset_name = ticker
    asset_column = pd.DataFrame({asset_name: asset_series})
    combined_returns = pd.concat([returns, asset_column], axis=1) if not returns.empty else asset_column
    combined_returns = combined_returns.loc[:, ~combined_returns.columns.duplicated(keep="last")]
    aligned = combined_returns.dropna(how="all")
    available = [name for name in scaled_weights if name in aligned.columns]
    available_weight = sum(scaled_weights[name] for name in available)
    after_series = (
        aligned[available]
        .dropna(how="any")
        .mul(pd.Series({name: scaled_weights[name] / available_weight for name in available}), axis="columns")
        .sum(axis=1, min_count=1)
        .dropna()
        if available and available_weight > 0 else pd.Series(dtype=float)
    )
    after_metrics = risk_metrics(after_series, risk_free)
    st.subheader("Comparação de cenários")
    capm_col1, capm_col2, capm_col3 = st.columns(3)
    capm_col1.metric("Beta do ativo vs. benchmark", "—" if beta_value is None else f"{beta_value:.2f}")
    capm_col2.metric("Retorno esperado CAPM", fmt_pct(capm_return))
    capm_col3.metric("Benchmark", benchmark_label)
    col1, col2 = st.columns(2)
    for column, title, metric in (
        (col1, "Carteira atual", before_metrics),
        (col2, "Carteira com ativo simulado", after_metrics),
    ):
        with column:
            st.markdown(f"**{title}**")
            st.metric("Retorno anualizado", fmt_pct(metric["retorno_anualizado"]))
            st.metric("Volatilidade EWMA anual", fmt_pct(metric["volatilidade_ewma"]))
            st.metric("Sharpe", "—" if metric["sharpe"] is None else f"{metric['sharpe']:.2f}")
    compare = pd.DataFrame(
        [
            {"Indicador": "Retorno anualizado", "Atual": before_metrics["retorno_anualizado"], "Simulado": after_metrics["retorno_anualizado"]},
            {"Indicador": "Volatilidade EWMA", "Atual": before_metrics["volatilidade_ewma"], "Simulado": after_metrics["volatilidade_ewma"]},
            {"Indicador": "Sharpe", "Atual": before_metrics["sharpe"], "Simulado": after_metrics["sharpe"]},
        ]
    )
    chart_data = compare.melt(id_vars="Indicador", var_name="Carteira", value_name="Valor")
    st.plotly_chart(px.bar(chart_data, x="Indicador", y="Valor", color="Carteira", barmode="group", title="Métricas históricas indicativas"), use_container_width=True)
    class_mix = position_frame.groupby("classe_ativo")["valor_mercado"].sum().to_dict()
    class_mix[asset_class] = class_mix.get(asset_class, 0.0) + float(amount)
    mix_frame = pd.DataFrame([{"Classe": key, "Valor": value} for key, value in class_mix.items()])
    st.plotly_chart(px.pie(mix_frame, names="Classe", values="Valor", hole=0.4, title="Alocação hipotética por classe"), use_container_width=True)
    st.caption(f"{ticker}: fonte {source_label} · preço de referência {fmt_brl(manual_price)} · retorno anual estimado {fmt_pct(external_annual_return)} · volatilidade anual {fmt_pct(external_vol)} · dividend yield informado {manual_dy:.2f}%.")
    st.caption("A carteira combinada usa a série disponível e pesos proporcionais ao valor atual e ao aporte hipotético. Dados incompletos reduzem a comparabilidade.")
    if external_history is not None and not external_history.empty:
        st.dataframe(external_history.tail(15), use_container_width=True, hide_index=True)


def save_import_records(imported: list[dict]) -> int:
    saved = 0
    for row in imported:
        asset_id = db.add_asset(
            row["ticker"],
            row.get("nome_ativo", row["ticker"]),
            row.get("classe_ativo", "Outro"),
            row.get("categoria_fundo_setor", ""),
            manual=True,
            api_code=row.get("codigo_api", ""),
            currency=row.get("moeda", "BRL"),
        )
        db.add_transaction(
            asset_id,
            row["tipo_operacao"],
            row["data_transacao"],
            float(row["quantidade"]),
            float(row["preco_unitario"]),
            float(row.get("taxas_custos", 0.0)),
            manual=True,
        )
        saved += 1
    return saved


def render_capture(position_frame, assets):
    st.title("Cadastro e importação")
    tabs = st.tabs(["Transação manual", "Importar CSV/OFX", "Cotação manual", "Provento manual"])
    with tabs[0]:
        st.subheader("Registrar ativo e movimentação")
        with st.form("manual_transaction"):
            a, b, c = st.columns(3)
            ticker = a.text_input("Ticker", key="manual_ticker").strip().upper()
            name = b.text_input("Nome do ativo", key="manual_name")
            asset_class = c.selectbox("Classe", ASSET_CLASSES, key="manual_class")
            category = st.text_input("Setor ou categoria do fundo", key="manual_category")
            api_code = st.text_input("Código no provedor (Yahoo ou ID CoinGecko)", key="manual_api_code")
            currency = st.selectbox("Moeda de cotação antes da conversão", ["BRL", "USD"], key="manual_currency")
            d, e, f, g = st.columns(4)
            operation = d.selectbox("Operação", OPERATIONS)
            txn_date = e.date_input("Data", value=date.today())
            quantity = f.number_input("Quantidade", min_value=0.000001, value=1.0, format="%.6f")
            unit_price = g.number_input("Preço unitário (R$)", min_value=0.0, value=0.0, step=0.1)
            fees = st.number_input("Taxas e custos (R$)", min_value=0.0, value=0.0, step=0.01)
            save = st.form_submit_button("Salvar transação", type="primary")
        if save:
            try:
                if not ticker:
                    raise ValueError("Informe o ticker.")
                if asset_class == "Cripto":
                    currency = "BRL"
                asset_id = db.add_asset(ticker, name or ticker, asset_class, category, True, api_code, currency)
                db.add_transaction(asset_id, operation, txn_date.isoformat(), quantity, unit_price, fees, True)
                st.success("Transação registrada como entrada manual.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with tabs[1]:
        st.subheader("Importar histórico de transações")
        st.write("Envie um CSV no formato do arquivo exemplo ou um OFX de investimentos com ticker, data, quantidade e preço.")
        template_path = ROOT / "examples" / "exemplo_transacoes.csv"
        st.download_button(
            "Baixar modelo CSV",
            data=template_path.read_bytes(),
            file_name="modelo_transacoes.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader("Arquivo CSV ou OFX", type=["csv", "ofx"])
        if uploaded is not None:
            digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
            try:
                imported, import_errors = parse_upload(uploaded.name, uploaded.getvalue())
                st.write(f"Operações válidas encontradas: {len(imported)}")
                if imported:
                    st.dataframe(pd.DataFrame(imported).head(30), use_container_width=True, hide_index=True)
                for error in import_errors[:20]:
                    st.warning(error)
                if imported and st.button("Confirmar importação", type="primary", key=f"import_{digest}"):
                    count = save_import_records(imported)
                    st.success(f"{count} operação(ões) importada(s).")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))
        st.caption("A importação só aceita lançamentos de compra, venda, aporte e retirada. Revise as linhas antes de confirmar.")
    with tabs[2]:
        st.subheader("Registrar preço manual")
        asset_options = {f"{item['ticker']} — {item['nome_ativo']}": item for item in assets}
        if asset_options:
            with st.form("manual_quote"):
                selected = st.selectbox("Ativo", list(asset_options))
                quote_date = st.date_input("Data da cotação", value=date.today())
                price = st.number_input("Preço de fechamento (R$)", min_value=0.0001, value=1.0, step=0.1)
                save_quote = st.form_submit_button("Salvar cotação")
            if save_quote:
                try:
                    db.upsert_quote(int(asset_options[selected]["id_ativo"]), quote_date.isoformat(), price, "Manual", True)
                    st.success("Cotação salva com origem manual.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("Cadastre um ativo primeiro.")
    with tabs[3]:
        st.subheader("Registrar dividendo, JCP ou rendimento")
        asset_options = {f"{item['ticker']} — {item['nome_ativo']}": item for item in assets}
        if asset_options:
            with st.form("manual_dividend"):
                selected_dividend = st.selectbox("Ativo", list(asset_options), key="dividend_asset")
                kind = st.selectbox("Tipo", ["Dividendo", "JCP", "Rendimento"])
                ex_date = st.date_input("Data com", value=date.today())
                payment_date = st.date_input("Data de pagamento", value=date.today())
                per_unit = st.number_input("Valor por unidade (R$)", min_value=0.0, value=0.0, step=0.01)
                total = st.number_input("Valor total recebido (R$)", min_value=0.0, value=0.0, step=0.01)
                save_dividend = st.form_submit_button("Salvar provento")
            if save_dividend:
                try:
                    db.add_dividend(int(asset_options[selected_dividend]["id_ativo"]), kind, ex_date.isoformat(), payment_date.isoformat(), per_unit, total, True)
                    st.success("Provento registrado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("Cadastre um ativo primeiro.")


def render_settings():
    st.title("Configurações e backup")
    current = settings()
    st.write("Personalize referências de análise. Esses parâmetros não bloqueiam a alocação nem representam promessa de retorno.")
    with st.form("settings_form"):
        a, b, c = st.columns(3)
        target1 = a.number_input("Meta de referência 1 (% ao mês)", min_value=-50.0, max_value=100.0, value=float(current["meta_mensal_1"]) * 100, step=0.1)
        target2 = b.number_input("Meta de referência 2 (% ao mês)", min_value=-50.0, max_value=100.0, value=float(current["meta_mensal_2"]) * 100, step=0.1)
        rf = c.number_input("Selic/CDI anual acumulada (%)", min_value=-50.0, max_value=100.0, value=float(current["risk_free_annual"] or 0), step=0.1)
        d, e = st.columns(2)
        fixed_income = d.number_input("Referência de renda fixa (% da carteira)", min_value=0.0, max_value=100.0, value=float(current["fixed_income_reference"]) * 100, step=1.0)
        concentration = e.number_input("Alerta de concentração (%)", min_value=1.0, max_value=100.0, value=float(current["concentration_limit_pct"]), step=1.0)
        save = st.form_submit_button("Salvar preferências", type="primary")
    if save:
        db.set_setting("meta_mensal_1", str(target1 / 100))
        db.set_setting("meta_mensal_2", str(target2 / 100))
        db.set_setting("risk_free_annual", str(rf))
        db.set_setting("fixed_income_reference", str(fixed_income / 100))
        db.set_setting("concentration_limit_pct", str(concentration))
        st.success("Preferências salvas no banco local.")
        st.rerun()
    st.divider()
    st.subheader("Backup local")
    st.write("Uma cópia de segurança é criada ao iniciar a plataforma. Baixe uma cópia adicional antes de fazer alterações importantes.")
    if db.DB_PATH.exists():
        st.download_button("Baixar banco SQLite", data=db.DB_PATH.read_bytes(), file_name="investimentos-backup.db", mime="application/x-sqlite3")
    backups = sorted(db.BACKUP_DIR.glob("investimentos-*.db"), reverse=True) if db.BACKUP_DIR.exists() else []
    if backups:
        st.caption("Cópias automáticas locais (até 14):")
        st.dataframe(pd.DataFrame([{"Arquivo": p.name, "Tamanho (KB)": round(p.stat().st_size / 1024, 1)} for p in backups]), use_container_width=True, hide_index=True)
    restore_file = st.file_uploader("Restaurar banco SQLite de um arquivo de backup", type=["db", "sqlite", "sqlite3"])
    if restore_file is not None and st.button("Validar e restaurar backup", type="secondary"):
        try:
            db.restore_database(restore_file.getvalue())
            st.success("Backup restaurado. Atualize a página.")
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível restaurar o arquivo: {exc}")
    st.caption("A Fase 1 mantém o arquivo no computador local. A autenticação e o serviço em nuvem descritos como Fase 2 não fazem parte desta entrega.")


def main():
    try:
        initialize_database()
    except Exception as exc:
        st.error(f"Não foi possível abrir o banco local: {exc}")
        st.stop()
    page = render_sidebar()
    position_frame, assets, transactions, quote_frame = load_portfolio()
    dividends = records(db.list_dividends())
    config = settings()
    if page == "Visão geral":
        render_overview(position_frame, assets, quote_frame, dividends, config)
    elif page == "Estado atual":
        render_current_state(position_frame, assets, quote_frame, dividends, config)
    elif page == "Previsão":
        render_forecast(position_frame, quote_frame, config)
    elif page == "Simular ativo":
        render_asset_simulation(position_frame, quote_frame, config)
    elif page == "Cadastro e importação":
        render_capture(position_frame, assets)
    else:
        render_settings()


main()
