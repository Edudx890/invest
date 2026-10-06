from pathlib import Path
from streamlit.testing.v1 import AppTest
from portfolio_app import db
import yfinance
ROOT=Path(__file__).resolve().parents[1]
def test_routes_render_without_exceptions(tmp_path,monkeypatch):
 monkeypatch.setattr(db,"DATA_DIR",tmp_path); monkeypatch.setattr(db,"DB_PATH",tmp_path/"ui.db"); monkeypatch.setattr(db,"BACKUP_DIR",tmp_path/"backups")
 app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run(); assert not app.exception
 for page in ["Estado atual","Previsão","Simular ativo","Cadastro e importação","Configurações e backup","Visão geral"]:
  app.radio[0].set_value(page).run(); assert not app.exception,[e.message for e in app.exception]
 aid=db.add_asset("LEGACY","Legacy foreign","Ação",currency="USD",quote_currency="USD")
 with db.session() as c:
  c.execute("""INSERT INTO Transacoes(id_ativo,tipo_operacao,data_transacao,quantidade,preco_unitario,taxas_custos,is_manual_entry,quantidade_original,preco_unitario_original,valor_total_original,taxas_custos_original,moeda_transacao,moeda_base,fonte_cambio,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(aid,"Compra","2024-01-01",1.0,10.0,0.0,1,"1","10","10","0","USD","BRL","pendente: informar taxa histórica","legacy-ui"))
 app.radio[0].set_value("Cadastro e importação").run()
 assert not app.exception,[e.message for e in app.exception]

def test_manual_asset_simulation_with_market_failure(tmp_path,monkeypatch):
 monkeypatch.setattr(db,"DATA_DIR",tmp_path); monkeypatch.setattr(db,"DB_PATH",tmp_path/"sim.db"); monkeypatch.setattr(db,"BACKUP_DIR",tmp_path/"backups")
 class Offline:
  def __init__(self,symbol): pass
  def history(self,**kwargs): raise RuntimeError("offline")
 monkeypatch.setattr(yfinance,"Ticker",Offline)
 db.init_db()
 aid=db.add_asset("BASE","Base","Ação")
 db.add_transaction(aid,"Compra","2025-01-01","1","100")
 db.upsert_quote(aid,"2025-01-01","100","Manual",True)
 db.upsert_quote(aid,"2025-01-02","101","Manual",True)
 app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
 app.radio[0].set_value("Simular ativo").run()
 assert not app.exception,[e.message for e in app.exception]
 manual=next(x for x in app.checkbox if x.label=="Usar premissas manuais se o provedor não encontrar o ativo")
 manual.set_value(True)
 submit=next(x for x in app.button if x.label=="Simular adição de ativo")
 submit.click().run()
 assert not app.exception,[e.message for e in app.exception]
 assert any("Comparação de cenários" in x.value for x in app.subheader)
