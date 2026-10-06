from decimal import Decimal
import pytest
from portfolio_app.calculations import build_positions,fixed_income_positions,project_scenarios
from portfolio_app.financial import transaction_amounts
ASSET={"id_ativo":1,"ticker":"ABC","nome_ativo":"ABC","classe_ativo":"Ação","categoria_fundo_setor":"Ações","moeda_ativo":"BRL"}
def tx(op,q,p,fee=0,day="2025-01-01",**extra):
 r={"id_ativo":1,"tipo_operacao":op,"quantidade":str(q),"preco_unitario":str(p),"taxas_custos":str(fee),"data_transacao":day}; r.update(extra); return r
def pos(rows,price=50,events=None): return build_positions([ASSET],rows,{1:{"preco_fechamento":price,"fonte_dados":"Manual"}},events or []).iloc[0]
def test_buy_multiple_and_weighted_average():
 r=pos([tx("Compra",10,30),tx("Compra",10,40,day="2025-02-01")]); assert (r.quantidade,r.custo_total,r.preco_medio)==(20,700,35)
def test_buy_market_value_unrealized_gain():
 r=pos([tx("Compra",10,30)],40); assert r.custo_total==300 and r.valor_mercado==400 and r.resultado_nao_realizado==100
def test_complete_buy_buy_appreciation_partial_sale_dividend():
 r=pos([tx("Compra",10,30),tx("Compra",10,40,day="2025-02-01"),tx("Venda",5,60,day="2025-03-01")],50,[{"id_ativo":1,"tipo_provento":"Rendimento","valor_total_brl":"12","valor_total":12}])
 assert r.quantidade==15 and r.custo_total==525 and r.resultado_realizado==125 and r.resultado_nao_realizado==225 and r.proventos_total==12 and r.resultado_total==362
@pytest.mark.parametrize("sale,expected",[(40,100),(20,-100)])
def test_full_sale_profit_and_loss(sale,expected):
 r=pos([tx("Compra",10,30),tx("Venda",10,sale,day="2025-02-01")]); assert r.quantidade==0 and r.resultado_realizado==expected and r.resultado_nao_realizado==0
def test_fees_and_rentability():
 r=pos([tx("Compra",10,30,3),tx("Venda",2,40,2,"2025-02-01")],40)
 assert r.taxas_total==5 and r.resultado_realizado==pytest.approx(17.4) and r.resultado_nao_realizado==pytest.approx(77.6)
 assert r.rentabilidade_pct==pytest.approx(95/303)
def test_split_preserves_basis():
 r=pos([tx("Compra",10,30)],events=[{"id_ativo":1,"tipo_provento":"Split","data_com":"2025-02-01","valor_por_acao":2}]); assert r.quantidade==20 and r.custo_total==300 and r.preco_medio==15
def test_usd_usdt_conversions_are_separate():
 usd=transaction_amounts("2","50","2","USD","1.5"); usdt=transaction_amounts("2","50","2","USDT","1.48")
 assert usd["valor_total_brl"]==Decimal("150.0") and usd["taxas_custos_brl"]==Decimal("3.0")
 assert usdt["valor_total_brl"]==Decimal("148.00") and usdt["valor_total_brl"]!=usdt["valor_total_original"]
def test_foreign_trade_and_market_value_in_brl():
 r=pos([tx("Compra",2,50,2,moeda_transacao="USD",taxa_cambio="1.5",valor_total_brl="150",taxas_custos_brl="3")],90)
 assert r.custo_total==153 and r.valor_mercado==180 and r.resultado_nao_realizado==27
def test_projection_and_manual_fixed_income():
 path,band=project_scenarios(1000,100,12,.01,.015,.02,.05); assert path.iloc[-1,1]>1000 and band.iloc[-1,2]<=band.iloc[-1,3]
 r=fixed_income_positions([{"id_renda_fixa":1,"nome":"CDB","tipo":"CDB","valor_investido":"1000","valor_atualizado":"1040"}]).iloc[0]
 assert r.valor_mercado==1040 and r.resultado_nao_realizado==40 and r.moeda_base=="BRL"
 precise=fixed_income_positions([{"id_renda_fixa":2,"nome":"LCI","tipo":"LCI/LCA","valor_investido":"0.1","valor_atualizado":"0.3"}]).iloc[0]
 assert precise.resultado_nao_realizado==0.2

def test_unresolved_foreign_legacy_cost_is_not_reported():
 with pytest.raises(ValueError,match="Câmbio histórico pendente"):
  pos([tx("Compra",2,10,moeda_transacao="USD")])
