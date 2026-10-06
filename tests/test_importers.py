from decimal import Decimal
import pytest
from portfolio_app.importers import parse_csv,parse_upload
def b(s): return s.encode()
def test_valid_csv_preserves_transaction_currency_and_fx():
 rows,e=parse_csv(b("ticker,tipo_operacao,data_transacao,quantidade,preco_unitario,moeda_ativo,moeda_transacao,taxa_cambio\nAAPL,Compra,2025-01-02,2,50,USD,USD,6.1\n"))
 assert not e and rows[0]["moeda_transacao"]=="USD" and rows[0]["taxa_cambio"]==Decimal("6.1")
def test_missing_required_fields():
 with pytest.raises(ValueError,match="Colunas obrigatórias"): parse_csv(b("ticker,data\nABC,2025-01-01"))
@pytest.mark.parametrize("row,msg",[("ABC,Compra,,1,10","data ausente"),("ABC,Compra,31/02/2025,1,10","data inválida"),("ABC,Compra,2025-01-01,x,10","valor numérico inválido")])
def test_invalid_rows(row,msg):
 _,e=parse_csv(b("ticker,tipo_operacao,data_transacao,quantidade,preco_unitario\n"+row)); assert msg in e[0]
def test_invalid_currency_rate():
 _,e=parse_csv(b("ticker,tipo_operacao,data_transacao,quantidade,preco_unitario,moeda_transacao,taxa_cambio\nA,Compra,2025-01-01,1,2,USDT,0")); assert "câmbio" in e[0]
def test_duplicate_and_usdt():
 rows,e=parse_csv(b("ticker,tipo_operacao,data_transacao,quantidade,preco_unitario,moeda,moeda_transacao\nBTC,Compra,2025-01-01,1,20,USDT,USDT\nBTC,Compra,2025-01-01,1,20,USDT,USDT\n"))
 assert len(rows)==1 and "duplicada" in e[0] and rows[0]["moeda_ativo"]=="USDT"
def test_supported_ofx_defaults_brl():
 rows,e=parse_upload("trades.ofx",b"<BUYSTOCK><UNIQUEID>AAPL</UNIQUEID><DTTRADE>20250101</DTTRADE><UNITS>1</UNITS><UNITPRICE>10</UNITPRICE></BUYSTOCK>"); assert not e and rows[0]["moeda_transacao"]=="BRL"
