from __future__ import annotations

import os
import re
import pandas as pd


COINGECKO_IDS = {
    "BTC": "bitcoin",
    "BITCOIN": "bitcoin",
    "ETH": "ethereum",
    "ETHEREUM": "ethereum",
    "SOL": "solana",
    "SOLANA": "solana",
    "ADA": "cardano",
    "CARDANO": "cardano",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "DOGECOIN": "dogecoin",
}


class MarketDataError(RuntimeError):
    pass


def yahoo_symbol(ticker: str, asset_class: str, symbol_override: str | None = None) -> str:
    if symbol_override and symbol_override.strip():
        return symbol_override.strip().upper()
    symbol = ticker.strip().upper()
    if asset_class == "Cripto":
        return symbol if "-" in symbol else f"{symbol}-USD"
    if asset_class in {"Ação", "FII", "ETF"} and re.fullmatch(r"[A-Z0-9]{4,6}", symbol) and not symbol.endswith(".SA"):
        return f"{symbol}.SA"
    return symbol


def fetch_yahoo_history(
    ticker: str,
    asset_class: str,
    period: str = "1y",
    symbol_override: str | None = None,
    currency: str = "BRL",
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataError("yfinance não está instalado. Instale as dependências do projeto.") from exc
    symbol = yahoo_symbol(ticker, asset_class, symbol_override)
    if currency.upper() != "BRL" and not symbol_override:
        symbol = ticker.strip().upper()
    try:
        history = yf.Ticker(symbol).history(
            period=period, interval="1d", auto_adjust=False, actions=True, timeout=15
        )
    except Exception as exc:
        raise MarketDataError(f"Falha ao consultar {symbol}: {exc}") from exc
    if history is None or history.empty:
        raise MarketDataError(f"Nenhum histórico foi localizado para {symbol}.")
    price_column = "Adj Close" if "Adj Close" in history.columns else "Close"
    result = pd.DataFrame(
        {
            "data": pd.to_datetime(history.index).date.astype(str),
            "preco": pd.to_numeric(history[price_column], errors="coerce").to_numpy(),
            "dividendo": pd.to_numeric(history["Dividends"], errors="coerce").fillna(0).to_numpy()
            if "Dividends" in history.columns else 0.0,
            "split": pd.to_numeric(history["Stock Splits"], errors="coerce").fillna(0).to_numpy()
            if "Stock Splits" in history.columns else 0.0,
            "fonte": "yfinance",
        }
    ).dropna(subset=["preco"])
    currency = currency.upper()
    if currency != "BRL":
        fx_symbol = f"{currency}BRL=X"
        try:
            fx_history = yf.Ticker(fx_symbol).history(
                period=period, interval="1d", auto_adjust=True, timeout=15
            )
            fx_prices = pd.Series(
                pd.to_numeric(fx_history["Close"], errors="coerce").to_numpy(dtype=float),
                index=pd.to_datetime(fx_history.index).date.astype(str),
            ).replace([float("inf"), float("-inf")], pd.NA)
            result["fx"] = result["data"].map(fx_prices)
            result["fx"] = result["fx"].ffill().bfill()
            if result["fx"].isna().any():
                raise ValueError("cotação cambial ausente em parte do histórico")
            result["preco"] = result["preco"] * result["fx"]
            result["dividendo"] = result["dividendo"] * result["fx"]
            result["fonte"] = f"yfinance ({currency}/BRL)"
            result = result.drop(columns=["fx"])
        except Exception as exc:
            raise MarketDataError(f"Não foi possível converter {currency} para BRL: {exc}") from exc
    result = result[result["preco"] > 0].drop_duplicates("data", keep="last")
    if result.empty:
        raise MarketDataError(f"O provedor não devolveu preços utilizáveis para {symbol}.")
    return result


def fetch_coingecko_history(coin_id: str, days: int = 365) -> pd.DataFrame:
    try:
        import requests
    except ImportError as exc:
        raise MarketDataError("requests não está instalado. Instale as dependências do projeto.") from exc
    if not coin_id.strip():
        raise MarketDataError("Informe o identificador da moeda no CoinGecko.")
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id.strip().lower()}/market_chart"
    headers = {"accept": "application/json"}
    api_key = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    try:
        response = requests.get(
            url,
            params={"vs_currency": "brl", "days": str(days), "interval": "daily"},
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise MarketDataError(f"CoinGecko indisponível para {coin_id}: {exc}") from exc
    points = payload.get("prices", [])
    if not points:
        raise MarketDataError(f"O CoinGecko não devolveu histórico para {coin_id}.")
    frame = pd.DataFrame(points, columns=["timestamp_ms", "preco"])
    frame["data"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    frame["fonte"] = "CoinGecko"
    frame["dividendo"] = 0.0
    frame["split"] = 0.0
    return frame[["data", "preco", "fonte", "dividendo", "split"]].drop_duplicates("data", keep="last")


def fetch_history(
    ticker: str,
    asset_class: str,
    api_code: str | None = None,
    period: str = "1y",
    currency: str = "BRL",
) -> pd.DataFrame:
    if asset_class == "Cripto":
        coin_id = (api_code or "").strip().lower()
        if not coin_id:
            coin_id = COINGECKO_IDS.get(ticker.strip().upper(), "")
        if not coin_id:
            raise MarketDataError("Informe um ID CoinGecko para esta criptomoeda; a fonte é convertida para BRL.")
        return fetch_coingecko_history(coin_id, days=365 if period in {"1y", "max"} else 30)
    return fetch_yahoo_history(
        ticker, asset_class, period=period, symbol_override=api_code, currency=currency
    )


def current_market_reference(ticker: str, asset_class: str, api_code: str | None = None) -> str:
    if asset_class == "Cripto":
        coin_id = (api_code or COINGECKO_IDS.get(ticker.strip().upper(), "")).strip()
        if coin_id:
            return f"CoinGecko: {coin_id}"
    return f"Yahoo Finance: {yahoo_symbol(ticker, asset_class, api_code)}"
