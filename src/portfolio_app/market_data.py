from __future__ import annotations
import os,re
import pandas as pd
COINGECKO_IDS={"BTC":"bitcoin","BITCOIN":"bitcoin","ETH":"ethereum","ETHEREUM":"ethereum","SOL":"solana","SOLANA":"solana","ADA":"cardano","CARDANO":"cardano","XRP":"ripple","DOGE":"dogecoin","DOGECOIN":"dogecoin"}
class MarketDataError(RuntimeError): pass
def yahoo_symbol(ticker,asset_class,symbol_override=None):
    if symbol_override and symbol_override.strip(): return symbol_override.strip().upper()
    symbol=ticker.strip().upper()
    if asset_class=="Cripto": return symbol if "-" in symbol else f"{symbol}-USD"
    if asset_class in {"Ação","FII","ETF"} and re.fullmatch(r"[A-Z0-9]{4,6}",symbol) and not symbol.endswith(".SA"): return symbol+".SA"
    return symbol
def fetch_yahoo_history(ticker,asset_class,period="1y",symbol_override=None,currency="BRL"):
    try: import yfinance as yf
    except ImportError as e: raise MarketDataError("yfinance não instalado; dados locais continuam disponíveis.") from e
    symbol=yahoo_symbol(ticker,asset_class,symbol_override)
    if currency.upper()!="BRL" and not symbol_override: symbol=ticker.strip().upper()
    try: h=yf.Ticker(symbol).history(period=period,interval="1d",auto_adjust=False,actions=True,timeout=15)
    except Exception as e: raise MarketDataError(f"Falha ao consultar {symbol}: {e}") from e
    if h is None or h.empty: raise MarketDataError(f"Nenhum histórico para {symbol}.")
    close="Close" if "Close" in h.columns else "Adj Close"; adj="Adj Close" if "Adj Close" in h.columns else close
    f=pd.DataFrame({"data":pd.to_datetime(h.index).date.astype(str),"preco_original":pd.to_numeric(h[close],errors="coerce").to_numpy(),"preco_ajustado_original":pd.to_numeric(h[adj],errors="coerce").to_numpy(),"dividendo":pd.to_numeric(h["Dividends"],errors="coerce").fillna(0).to_numpy() if "Dividends" in h.columns else 0.0,"split":pd.to_numeric(h["Stock Splits"],errors="coerce").fillna(0).to_numpy() if "Stock Splits" in h.columns else 0.0,"fonte":"yfinance"}).dropna(subset=["preco_original"])
    curr=currency.upper(); f["moeda_original"]=curr; f["taxa_cambio"]=1.0
    if curr!="BRL":
        try:
            fx=yf.Ticker(f"{curr}BRL=X").history(period=period,interval="1d",auto_adjust=True,timeout=15)
            if fx is None or fx.empty: raise ValueError("histórico cambial ausente")
            series=pd.Series(pd.to_numeric(fx["Close"],errors="coerce").to_numpy(),index=pd.to_datetime(fx.index).date.astype(str))
            f["taxa_cambio"]=f["data"].map(series).ffill(); f=f.dropna(subset=["taxa_cambio"])
            if f.empty: raise ValueError("sem câmbio anterior")
            f["fonte"]=f"yfinance ({curr}/BRL)"
        except Exception as e: raise MarketDataError(f"Falha no câmbio {curr}/BRL: {e}") from e
    f["preco"]=f["preco_original"]*f["taxa_cambio"]; f["preco_ajustado"]=f["preco_ajustado_original"]*f["taxa_cambio"]; f["dividendo"]*=f["taxa_cambio"]
    f=f[(f["preco"]>0)&f["preco"].notna()].drop_duplicates("data",keep="last")
    if f.empty: raise MarketDataError(f"Preços inutilizáveis para {symbol}.")
    return f
def fetch_coingecko_history(coin_id,days=365):
    try: import requests
    except ImportError as e: raise MarketDataError("requests não instalado.") from e
    if not coin_id.strip(): raise MarketDataError("Informe ID CoinGecko.")
    headers={"accept":"application/json"}; key=os.environ.get("COINGECKO_DEMO_API_KEY","").strip()
    if key: headers["x-cg-demo-api-key"]=key
    try:
        r=requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id.strip().lower()}/market_chart",params={"vs_currency":"brl","days":str(days),"interval":"daily"},headers=headers,timeout=20); r.raise_for_status(); payload=r.json()
    except Exception as e: raise MarketDataError(f"CoinGecko indisponível ({coin_id}): {e}") from e
    if not payload.get("prices"): raise MarketDataError(f"CoinGecko sem histórico para {coin_id}.")
    f=pd.DataFrame(payload["prices"],columns=["ts","preco"]); f["data"]=pd.to_datetime(f["ts"],unit="ms",utc=True).dt.date.astype(str)
    f["preco_original"]=f["preco"]; f["preco_ajustado_original"]=f["preco"]; f["preco_ajustado"]=f["preco"]; f["moeda_original"]="BRL"; f["taxa_cambio"]=1.0; f["fonte"]="CoinGecko (BRL)"; f["dividendo"]=0.0; f["split"]=0.0
    return f.drop_duplicates("data",keep="last")
def fetch_history(ticker,asset_class,api_code=None,period="1y",currency="BRL"):
    if asset_class=="Cripto":
        coin=(api_code or "").strip().lower() or COINGECKO_IDS.get(ticker.strip().upper(),"")
        if not coin: raise MarketDataError("Informe ID CoinGecko; preços retornam BRL.")
        return fetch_coingecko_history(coin,365 if period in {"1y","max"} else 30)
    return fetch_yahoo_history(ticker,asset_class,period,api_code,currency)
def current_market_reference(ticker,asset_class,api_code=None):
    if asset_class=="Cripto":
        coin=(api_code or COINGECKO_IDS.get(ticker.strip().upper(),"")).strip()
        if coin: return f"CoinGecko: {coin} (BRL)"
    return f"Yahoo Finance: {yahoo_symbol(ticker,asset_class,api_code)}"
