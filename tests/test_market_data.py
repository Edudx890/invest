import pandas as pd
import pytest
import yfinance
from portfolio_app.market_data import MarketDataError,fetch_yahoo_history

def test_yahoo_close_and_adjusted_series_use_historical_fx(monkeypatch):
 dates=pd.to_datetime(["2025-01-02","2025-01-03"])
 stock=pd.DataFrame({"Close":[10.,11.],"Adj Close":[12.,13.],"Dividends":[0.,.2],"Stock Splits":[0.,0.]},index=dates)
 fx=pd.DataFrame({"Close":[5.]},index=pd.to_datetime(["2025-01-02"]))
 class Ticker:
  def __init__(self,symbol): self.symbol=symbol
  def history(self,**kwargs): return stock if self.symbol=="AAPL" else fx
 monkeypatch.setattr(yfinance,"Ticker",Ticker)
 frame=fetch_yahoo_history("AAPL","ETF",symbol_override="AAPL",currency="USD")
 assert list(frame["preco"])==[50.,55.]
 assert list(frame["preco_ajustado"])==[60.,65.]
 assert frame.iloc[1]["taxa_cambio"]==5
 assert "USD/BRL" in frame.iloc[0]["fonte"]

def test_market_failure_is_reported_not_fabricated(monkeypatch):
 class Broken:
  def __init__(self,symbol): pass
  def history(self,**kwargs): raise RuntimeError("offline")
 monkeypatch.setattr(yfinance,"Ticker",Broken)
 with pytest.raises(MarketDataError,match="Falha ao consultar"):
  fetch_yahoo_history("ABCD","ETF")
