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
    fixed_income_positions,
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
    fixed_rows = records(db.list_fixed_income())
    if fixed_rows:
        position_frame = pd.concat([position_frame, fixed_income_positions(fixed_rows)], ignore_index=True)
        total_value = position_frame['valor_mercado'].sum()
        position_frame['peso_pct'] = position_frame['valor_mercado'] / total_value * 100 if total_value else 0.0
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
                    float(quote.get("preco_original", quote["preco"])),
                    str(quote["fonte"]), manual=False,
                    original_currency=str(quote.get("moeda_original", "BRL")),
                    exchange_rate=quote.get("taxa_cambio", 1),
                    adjusted_price=quote.get("preco_ajustado_original", quote.get("preco_original", quote["preco"])),
                )
                currency = str(quote.get("moeda_original", "BRL"))
                if currency != "BRL" and quote.get("taxa_cambio"):
                    db.upsert_exchange_rate(currency, str(quote["data"]), quote["taxa_cambio"], str(quote["fonte"]))
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
                "preco_fechamento": quote_frame.get("preco_ajustado", quote_frame["preco_fechamento"]),
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


def render_metrics(position_frame,metrics,dividends,config):
    value=float(position_frame["valor_mercado"].sum()) if not position_frame.empty else 0.0
    cost=float(position_frame["custo_total"].sum()) if not position_frame.empty else 0.0
    realized=float(position_frame["resultado_realizado"].sum()) if not position_frame.empty else 0.0
    unrealized=float(position_frame["resultado_nao_realizado"].sum()) if not position_frame.empty else 0.0
    income=float(position_frame["proventos_total"].sum()) if not position_frame.empty else 0.0
    invested=float(position_frame["base_investida"].sum()) if not position_frame.empty else 0.0
    total=realized+unrealized+income; cols=st.columns(6)
    cols[0].metric("Patrimônio estimado (BRL)",fmt_brl(value)); cols[1].metric("Custo residual (BRL)",fmt_brl(cost))
    cols[2].metric("Resultado realizado (BRL)",fmt_brl(realized)); cols[3].metric("Resultado não realizado (BRL)",fmt_brl(unrealized))
    cols[4].metric("Proventos registrados (BRL)",fmt_brl(income)); cols[5].metric("Resultado total (BRL)",fmt_brl(total),fmt_pct(total/invested if invested else None))
    cols=st.columns(3); cols[0].metric("Retorno anualizado estimado",fmt_pct(metrics["retorno_anualizado"]))
    cols[1].metric("Volatilidade EWMA anual",fmt_pct(metrics["volatilidade_ewma"]))
    cols[2].metric("Sharpe anualizado","" if metrics["sharpe"] is None else f"{metrics['sharpe']:.2f}")
    if not config["risk_free_annual"].strip(): st.info("Informe a taxa Selic/CDI anual nas configurações para contextualizar o índice de Sharpe.")
    if not position_frame.empty: st.caption("Valores consolidados em BRL. Resultado total não é TWR/XIRR nem apuração fiscal.")
    if position_frame.empty: return
    yields=[]
    for row in position_frame.to_dict("records"):
        ratio=dividend_yield_12m(dividends,int(row["id_ativo"]),float(row["valor_mercado"])) if row["id_ativo"]>0 else None
        if ratio is not None: yields.append((float(row["peso_pct"])/100)*ratio)
    if yields: st.caption(f"Dividend yield ponderado registrado em 12 meses: {fmt_pct(sum(yields))}.")



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
        st.plotly_chart(fig, width="stretch")
    with right:
        by_category = position_frame.groupby("categoria_fundo_setor", as_index=False)["valor_mercado"].sum()
        fig = px.pie(by_category, names="categoria_fundo_setor", values="valor_mercado", hole=0.48, title="Alocação por setor/tipo")
        st.plotly_chart(fig, width="stretch")
    if len(portfolio_series) > 1:
        start_value = float(position_frame["valor_mercado"].sum())
        history = (1.0 + portfolio_series).cumprod() * start_value
        chart = px.line(
            x=pd.to_datetime(history.index),
            y=history.values,
            labels={"x": "Data", "y": "Índice do patrimônio (R$)"},
            title="Estimativa histórica reponderada pelos pesos atuais",
        )
        st.plotly_chart(chart, width="stretch")
        st.caption("Histórico reponderado pela composição atual; não reconstrói aportes e vendas passados.")
    manual_count = sum(int(row.get("is_manual_entry") or 0) for row in assets)
    st.caption(f"Ativos cadastrados: {len(assets)} · ativos com origem manual: {manual_count}")


def render_current_state(position_frame, assets, quote_frame, dividends, config):
    st.title("Estado atual da carteira")
    st.write("Posições derivadas do histórico de compras, vendas e ajustes cadastrados.")
    refresh_col, help_col = st.columns([1, 3])
    with refresh_col:
        refresh_clicked = st.button("Atualizar cotações", type="primary", width="stretch")
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
            "ticker", "nome_ativo", "classe_ativo", "moeda_ativo", "moeda_base", "quantidade", "preco_medio",
            "ultimo_preco", "valor_mercado", "peso_pct", "custo_total", "resultado_realizado",
            "resultado_nao_realizado", "proventos_total", "fonte_cotacao", "data_cotacao",
        ]
    ].copy()
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "quantidade": st.column_config.NumberColumn("Quantidade", format="%.6f"),
            "preco_medio": st.column_config.NumberColumn("Preço médio", format="R$ %.2f"),
            "ultimo_preco": st.column_config.NumberColumn("Último preço", format="R$ %.2f"),
            "valor_mercado": st.column_config.NumberColumn("Valor de mercado", format="R$ %.2f"),
            "peso_pct": st.column_config.NumberColumn("Peso", format="%.2f%%"),
            "custo_total": st.column_config.NumberColumn("Custo residual (BRL)",format="R$ %.2f"),
            "resultado_realizado": st.column_config.NumberColumn("Realizado (BRL)",format="R$ %.2f"),
            "resultado_nao_realizado": st.column_config.NumberColumn("Não realizado (BRL)",format="R$ %.2f"),
            "proventos_total": st.column_config.NumberColumn("Proventos (BRL)",format="R$ %.2f"),
        },
    )
    left, right = st.columns(2)
    with left:
        allocation = position_frame.groupby("classe_ativo", as_index=False)["valor_mercado"].sum()
        st.plotly_chart(px.pie(allocation, names="classe_ativo", values="valor_mercado", hole=0.4, title="Distribuição por classe"), width="stretch")
    with right:
        allocation = position_frame.groupby("categoria_fundo_setor", as_index=False)["valor_mercado"].sum()
        st.plotly_chart(px.bar(allocation, x="categoria_fundo_setor", y="valor_mercado", title="Exposição por setor/tipo"), width="stretch")
    for alert in concentration_alerts(position_frame, float(config["concentration_limit_pct"])):
        st.warning("Concentração: " + alert)
    if len(portfolio_series) > 1:
        value = float(position_frame["valor_mercado"].sum())
        series = (1.0 + portfolio_series).cumprod() * value
        st.plotly_chart(
            px.line(x=pd.to_datetime(series.index), y=series.values, labels={"x": "Data", "y": "R$"}, title="Estimativa histórica reponderada pelos pesos atuais"),
            width="stretch",
        )
        st.caption("Série indicativa calculada com pesos atuais e cotações registradas; eventos de fluxo de caixa anteriores não são reconstruídos.")
    if dividends:
        st.subheader("Proventos registrados")
        dividend_frame = pd.DataFrame(dividends)
        st.dataframe(
            dividend_frame[["ticker", "tipo_provento", "data_com", "data_pagamento", "valor_por_acao", "valor_total", "is_manual_entry"]],
            width="stretch",
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
        st.plotly_chart(figure, width="stretch")
        st.subheader("Valores ao longo do tempo")
        st.dataframe(path.merge(band, on="Mês"), width="stretch", hide_index=True, column_config={
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
    st.plotly_chart(px.bar(chart_data, x="Indicador", y="Valor", color="Carteira", barmode="group", title="Métricas históricas indicativas"), width="stretch")
    class_mix = position_frame.groupby("classe_ativo")["valor_mercado"].sum().to_dict()
    class_mix[asset_class] = class_mix.get(asset_class, 0.0) + float(amount)
    mix_frame = pd.DataFrame([{"Classe": key, "Valor": value} for key, value in class_mix.items()])
    st.plotly_chart(px.pie(mix_frame, names="Classe", values="Valor", hole=0.4, title="Alocação hipotética por classe"), width="stretch")
    st.caption(f"{ticker}: fonte {source_label} · preço de referência {fmt_brl(manual_price)} · retorno anual estimado {fmt_pct(external_annual_return)} · volatilidade anual {fmt_pct(external_vol)} · dividend yield informado {manual_dy:.2f}%.")
    st.caption("A carteira combinada usa a série disponível e pesos proporcionais ao valor atual e ao aporte hipotético. Dados incompletos reduzem a comparabilidade.")
    if external_history is not None and not external_history.empty:
        st.dataframe(external_history.tail(15), width="stretch", hide_index=True)


def save_import_records(imported):
    return len(db.add_transactions_batch(imported,manual=False))



def render_capture(position_frame,assets):
    st.title("Cadastro e importação")
    tabs=st.tabs(["Transação manual","Importar CSV/OFX","Cotação manual","Provento manual","Renda fixa manual","Câmbio legado"])
    with tabs[0]:
        with st.form("manual_transaction"):
            a,b,c=st.columns(3); ticker=a.text_input("Ticker").strip().upper(); name=b.text_input("Nome do ativo")
            cls=c.selectbox("Classe",ASSET_CLASSES); category=st.text_input("Setor/categoria"); api=st.text_input("Código Yahoo/CoinGecko")
            asset_currency=st.selectbox("Moeda/denominação do ativo",["BRL","USD","USDT","EUR","GBP","BTC","ETH"])
            tx_currency=st.selectbox("Moeda da transação",["BRL","USD","USDT","EUR","GBP"])
            op=st.selectbox("Operação",OPERATIONS); d,e,f,g=st.columns(4); day=d.date_input("Data",value=date.today())
            qty=e.number_input("Quantidade",min_value=.000001,value=1.0,format="%.8f")
            price=f.number_input("Preço unitário na moeda da transação",min_value=0.0,value=0.0,step=.01)
            fees=g.number_input("Taxas na moeda da transação",min_value=0.0,value=0.0,step=.01)
            fx=st.number_input("Câmbio para BRL (0 = usar cache)",min_value=0.0,value=1.0 if tx_currency=="BRL" else 0.0,step=.01)
            submit=st.form_submit_button("Salvar transação",type="primary")
        if submit:
            try:
                if not ticker: raise ValueError("Informe ticker.")
                db.add_transactions_batch([{"ticker":ticker,"nome_ativo":name or ticker,"classe_ativo":cls,"categoria_fundo_setor":category,"codigo_api":api,"moeda_ativo":asset_currency,"moeda_cotacao":"BRL" if cls=="Cripto" else asset_currency,"tipo_operacao":op,"data_transacao":day.isoformat(),"quantidade":qty,"preco_unitario":price,"taxas_custos":fees,"moeda_transacao":tx_currency,"taxa_cambio":fx if fx>0 else None}],manual=True)
                st.success("Transação gravada e histórico preservado."); st.rerun()
            except Exception as exc: st.error(str(exc))
    with tabs[1]:
        template=ROOT/"examples"/"exemplo_transacoes.csv"
        st.write("Preço e custos na moeda da operação; informe câmbio estrangeiro ou use cache.")
        st.download_button("Baixar modelo CSV",data=template.read_bytes(),file_name="modelo_transacoes.csv",mime="text/csv")
        upload=st.file_uploader("CSV/OFX",type=["csv","ofx"])
        if upload:
            digest=hashlib.sha256(upload.getvalue()).hexdigest()
            try:
                rows,errors=parse_upload(upload.name,upload.getvalue()); st.write(f"Operações válidas: {len(rows)}")
                if rows: st.dataframe(pd.DataFrame(rows).head(30),width="stretch",hide_index=True)
                for error in errors[:20]: st.warning(error)
                if rows and st.button("Confirmar importação atômica",type="primary",key=f"imp_{digest}"):
                    n=save_import_records(rows); st.success(f"{n} nova(s) operação(ões); duplicatas ignoradas."); st.rerun()
            except Exception as exc: st.error(str(exc))
    with tabs[2]:
        options={f"{x['ticker']}  {x['nome_ativo']}":x for x in assets}
        if options:
            with st.form("manual_quote"):
                label=st.selectbox("Ativo",list(options)); item=options[label]; curr=str(item.get("moeda","BRL"))
                day=st.date_input("Data",value=date.today()); price=st.number_input(f"Preço de fechamento ({curr})",min_value=.0001,value=1.0)
                fx=st.number_input("Câmbio para BRL (0 = cache)",min_value=0.0,value=1.0 if curr=="BRL" else 0.0)
                submit=st.form_submit_button("Salvar cotação")
            if submit:
                try:
                    if curr!="BRL" and fx<=0:
                        cached=db.get_exchange_rate(curr,day.isoformat())
                        if not cached: raise ValueError(f"Informe taxa {curr}/BRL ou registre cache.")
                        fx=float(cached["taxa_para_brl"])
                    db.upsert_quote(int(item["id_ativo"]),day.isoformat(),price,"Manual",True,curr,fx)
                    st.success("Cotação manual convertida para BRL."); st.rerun()
                except Exception as exc: st.error(str(exc))
        else: st.info("Cadastre um ativo primeiro.")
    with tabs[3]:
        options={f"{x['ticker']}  {x['nome_ativo']}":x for x in assets}
        if options:
            with st.form("manual_dividend"):
                label=st.selectbox("Ativo",list(options),key="div_asset"); kind=st.selectbox("Tipo",["Dividendo","JCP","Rendimento"])
                ex=st.date_input("Data com",value=date.today()); pay=st.date_input("Pagamento",value=date.today())
                per=st.number_input("Valor por unidade (BRL)",min_value=0.0,value=0.0); total=st.number_input("Total (BRL)",min_value=0.0,value=0.0)
                submit=st.form_submit_button("Salvar provento")
            if submit:
                try: db.add_dividend(int(options[label]["id_ativo"]),kind,ex.isoformat(),pay.isoformat(),per,total); st.success("Provento salvo em BRL."); st.rerun()
                except Exception as exc: st.error(str(exc))
        else: st.info("Cadastre um ativo primeiro.")
    with tabs[4]:
        fixed=records(db.list_fixed_income()); choices={"Novo investimento":None}
        choices.update({f"{x['nome']}  {x['tipo']}  ID {x['id_renda_fixa']}":x for x in fixed})
        label=st.selectbox("Criar/editar",list(choices),key="fixed_choice"); old=choices[label]
        with st.form("fixed_form"):
            name=st.text_input("Nome",value=old["nome"] if old else ""); kinds=["CDB","LCI/LCA","Tesouro","Outro"]
            kind=st.selectbox("Tipo",kinds,index=kinds.index(old["tipo"]) if old else 0)
            issuer=st.text_input("Emissor",value=old["emissor"] if old else ""); bank=st.text_input("Instituição",value=old["instituicao"] if old else "")
            invested=st.number_input("Valor investido BRL",min_value=0.0,value=float(old["valor_investido"]) if old else 0.0)
            updated=st.number_input("Valor atualizado manual BRL",min_value=0.0,value=float(old["valor_atualizado"]) if old else 0.0)
            rate=st.text_input("Taxa",value=old["taxa"] if old else ""); indexer=st.text_input("Indexador",value=old["indexador"] if old else "")
            maturity=st.text_input("Vencimento AAAA-MM-DD",value=old["vencimento"] if old else "")
            liquidity=st.text_input("Liquidez",value=old["liquidez"] if old else ""); notes=st.text_area("Observações",value=old["observacoes"] if old else "")
            submit=st.form_submit_button("Salvar renda fixa",type="primary")
        if submit:
            try:
                db.save_fixed_income({"nome":name,"tipo":kind,"emissor":issuer,"instituicao":bank,"valor_investido":invested,"valor_atualizado":updated,"taxa":rate,"indexador":indexer,"vencimento":maturity,"liquidez":liquidity,"observacoes":notes},int(old["id_renda_fixa"]) if old else None)
                st.success("Renda fixa manual salva em BRL."); st.rerun()
            except Exception as exc: st.error(str(exc))

    with tabs[5]:
        st.subheader("Regularizar câmbio das operações antigas")
        pending=db.list_unconverted_transactions()
        if pending:
            st.warning("Operações estrangeiras migradas sem câmbio histórico ficam fora dos resultados até informar uma taxa confiável.")
            st.dataframe(pd.DataFrame([{"ID":r["id_transacao"],"Ticker":r["ticker"],"Data":r["data_transacao"],"Moeda":r["moeda_transacao"],"Valor original":r["valor_total_original"],"Origem":r["fonte_cambio"]} for r in pending]),width="stretch",hide_index=True)
            with st.form("legacy_fx"):
                labels={f"#{r['id_transacao']} {r['ticker']}  {r['data_transacao']}  {r['moeda_transacao']}":r for r in pending}
                label=st.selectbox("Operação",list(labels))
                rate=st.number_input(f"Taxa {labels[label]['moeda_transacao']}/BRL",min_value=0.0,value=0.0,step=.01)
                submit=st.form_submit_button("Aplicar taxa manual")
            if submit:
                try:
                    if rate<=0: raise ValueError("Informe uma taxa positiva.")
                    db.set_transaction_exchange_rate(labels[label]["id_transacao"],rate)
                    st.success("Taxa aplicada à operação."); st.rerun()
                except Exception as exc: st.error(str(exc))
        else:
            st.info("Não há operações antigas aguardando câmbio.")

def render_settings():
    st.title("Configurações e backup"); current=settings()
    with st.form("settings_form"):
        a,b,c=st.columns(3); x=a.number_input("Meta mensal 1 (%)",min_value=-50.0,max_value=100.0,value=float(current["meta_mensal_1"])*100)
        y=b.number_input("Meta mensal 2 (%)",min_value=-50.0,max_value=100.0,value=float(current["meta_mensal_2"])*100)
        rf=c.number_input("Selic/CDI anual (%)",min_value=-50.0,max_value=100.0,value=float(current["risk_free_annual"] or 0))
        d,e=st.columns(2); fixed=d.number_input("Referência renda fixa (%)",min_value=0.0,max_value=100.0,value=float(current["fixed_income_reference"])*100)
        concentration=e.number_input("Alerta concentração (%)",min_value=1.0,max_value=100.0,value=float(current["concentration_limit_pct"]))
        save=st.form_submit_button("Salvar preferências")
    if save:
        for key,value in (("meta_mensal_1",x/100),("meta_mensal_2",y/100),("risk_free_annual",rf),("fixed_income_reference",fixed/100),("concentration_limit_pct",concentration)): db.set_setting(key,str(value))
        st.success("Preferências salvas."); st.rerun()
    st.divider(); st.subheader("Backup local"); st.write(f"Schema SQLite {db.SCHEMA_VERSION}; download usa snapshot consistente.")
    st.download_button("Baixar backup SQLite",data=db.backup_database_bytes(),file_name="investimentos-backup.db",mime="application/x-sqlite3")
    backups=sorted(db.BACKUP_DIR.glob("investimentos-*.db"),reverse=True) if db.BACKUP_DIR.exists() else []
    if backups: st.dataframe(pd.DataFrame([{"Arquivo":p.name,"KB":round(p.stat().st_size/1024,1)} for p in backups]),width="stretch",hide_index=True)
    upload=st.file_uploader("Restaurar banco SQLite",type=["db","sqlite","sqlite3"])
    if upload is not None and st.button("Validar e restaurar"):
        try: db.restore_database(upload.getvalue()); st.success("Backup restaurado."); st.rerun()
        except Exception as exc: st.error(f"Falha na restauração: {exc}")
    st.caption("Histórico com pesos atuais é estimativa, não rentabilidade real reconstruída.")



def main():
    try:
        initialize_database()
    except Exception as exc:
        st.error(f"Não foi possível abrir o banco local: {exc}")
        st.stop()
    page = render_sidebar()
    pending_fx=records(db.list_unconverted_transactions())
    if pending_fx and page!="Cadastro e importação":
        st.error(f"Há {len(pending_fx)} operação(ões) estrangeira(s) antiga(s) sem taxa histórica; nenhum resultado será calculado para evitar valores incorretos.")
        st.info("Abra Cadastro e importação / Câmbio legado e informe uma taxa de fonte confiável para cada operação.")
        st.stop()
    if pending_fx:
        position_frame=pd.DataFrame()
        assets=records(db.list_assets())
        transactions=records(db.list_transactions())
        quote_frame=pd.DataFrame(records(db.list_quotes()))
    else:
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
