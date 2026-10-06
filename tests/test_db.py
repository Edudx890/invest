import sqlite3
import pytest
from portfolio_app import db
@pytest.fixture
def database(tmp_path,monkeypatch):
 monkeypatch.setattr(db,"DATA_DIR",tmp_path); monkeypatch.setattr(db,"DB_PATH",tmp_path/"portfolio.db"); monkeypatch.setattr(db,"BACKUP_DIR",tmp_path/"backups"); db.init_db(); return db
def row(**x):
 r={"ticker":"ABC","nome_ativo":"ABC","classe_ativo":"Ação","moeda_ativo":"BRL","moeda_cotacao":"BRL","tipo_operacao":"Compra","data_transacao":"2025-01-01","quantidade":"10","preco_unitario":"30","taxas_custos":"1","moeda_transacao":"BRL"}; r.update(x); return r
def test_create_insert_read_and_update_settings(database):
 aid=database.add_asset("ABC","ABC","Ação"); tid=database.add_transaction(aid,"Compra","2025-01-01",10,30,1)
 assert database.list_transactions()[0]["id_transacao"]==tid and database.list_transactions()[0]["valor_total_brl"]=="300"
 database.set_setting("x","1"); database.set_setting("x","2"); assert database.get_setting("x","")=="2"
def test_currency_cache_and_usdt_not_usd(database):
 with pytest.raises(ValueError,match="USD/BRL"): database.add_transactions_batch([row(moeda_transacao="USD")])
 database.upsert_exchange_rate("USD","2025-01-01","6.1","manual"); database.add_transactions_batch([row(moeda_transacao="USD")])
 assert float(database.list_transactions()[0]["valor_total_brl"])==1830
 with pytest.raises(ValueError,match="USDT/BRL"): database.add_transactions_batch([row(moeda_transacao="USDT")])
 database.upsert_exchange_rate("USDT","2025-01-01","5.9","manual"); database.add_transactions_batch([row(ticker="BTC",moeda_transacao="USDT")])
 assert database.list_transactions()[-1]["taxa_cambio"]=="5.9"
def test_oversell_rolls_back_batch(database):
 with pytest.raises(ValueError,match="excede"): database.add_transactions_batch([row(),row(tipo_operacao="Venda",data_transacao="2025-01-02",quantidade="11")])
 assert not database.list_assets() and not database.list_transactions()
def test_import_duplicates_skipped_and_sales_kept(database):
 item=row(fingerprint="dup"); assert len(database.add_transactions_batch([item],False))==1
 assert database.add_transactions_batch([item],False)==[]
 database.add_transactions_batch([row(tipo_operacao="Venda",data_transacao="2025-02-01",quantidade="2")]); assert len(database.list_transactions())==2
def test_manual_fixed_income_update(database):
 i=database.save_fixed_income({"nome":"CDB","tipo":"CDB","valor_investido":"1000","valor_atualizado":"1010","taxa":"100","indexador":"CDI","vencimento":"2026-12-31"})
 database.save_fixed_income({"nome":"CDB","tipo":"CDB","valor_investido":"1000","valor_atualizado":"1020"},i); assert database.list_fixed_income()[0]["valor_atualizado"]=="1020"
def test_backup_restore_and_invalid_input(database):
 database.add_transactions_batch([row()])
 aid=database.list_transactions()[0]["id_ativo"]
 database.upsert_quote(aid,"2025-01-01","30","Manual",True)
 database.add_dividend(aid,"Dividendo","2025-01-01","2025-01-02","1","10")
 database.upsert_exchange_rate("USD","2025-01-01","6.1","manual")
 database.save_fixed_income({"nome":"Tesouro","tipo":"Tesouro","valor_investido":"500","valor_atualizado":"510"})
 backup=database.backup_database_bytes()
 database.set_setting("marker","later")
 database.save_fixed_income({"nome":"Tesouro","tipo":"Tesouro","valor_investido":"500","valor_atualizado":"520"},1)
 database.restore_database(backup)
 assert len(database.list_transactions())==1 and database.get_setting("marker","")==""
 assert len(database.list_quotes())==1 and len(database.list_dividends())==1
 assert database.list_fixed_income()[0]["valor_atualizado"]=="510"
 assert str(database.get_exchange_rate("USD","2025-01-01")["taxa_para_brl"])=="6.1"
 with pytest.raises(ValueError,match="integridade"): database.restore_database(b"not sqlite")
def test_additive_migration_preserves_legacy_data(tmp_path,monkeypatch):
 path=tmp_path/"legacy.db"; c=sqlite3.connect(path)
 c.executescript("""CREATE TABLE Ativos(id_ativo INTEGER PRIMARY KEY,ticker TEXT UNIQUE,nome_ativo TEXT,classe_ativo TEXT,categoria_fundo_setor TEXT,is_manual_entry INTEGER,data_cadastro TEXT,codigo_api TEXT,moeda TEXT);
 CREATE TABLE Transacoes(id_transacao INTEGER PRIMARY KEY,id_ativo INTEGER,tipo_operacao TEXT,data_transacao TEXT,quantidade REAL,preco_unitario REAL,taxas_custos REAL,is_manual_entry INTEGER);
 CREATE TABLE Cotacoes_Historico(id_cotacao INTEGER PRIMARY KEY,id_ativo INTEGER,data_cotacao TEXT,preco_fechamento REAL,fonte_dados TEXT,is_manual_entry INTEGER,UNIQUE(id_ativo,data_cotacao));
 CREATE TABLE Proventos(id_provento INTEGER PRIMARY KEY,id_ativo INTEGER,tipo_provento TEXT,data_com TEXT,data_pagamento TEXT,valor_por_acao REAL,valor_total REAL,is_manual_entry INTEGER);
 INSERT INTO Ativos VALUES(1,'ABC','ABC','ETF','','1','2025-01-01','','USD');
 INSERT INTO Transacoes VALUES(1,1,'Compra','2025-01-01',2,10,0,1);"""); c.commit(); c.close()
 monkeypatch.setattr(db,"DATA_DIR",tmp_path); monkeypatch.setattr(db,"DB_PATH",path); monkeypatch.setattr(db,"BACKUP_DIR",tmp_path/"backups")
 db.init_db(); tx=db.list_transactions()[0]
 assert tx["moeda_transacao"]=="USD" and tx["valor_total_brl"] is None
 assert len(db.list_unconverted_transactions())==1
 assert db.list_assets()[0]["moeda_ativo"]=="USD"
 db.set_transaction_exchange_rate(tx["id_transacao"],"6.1")
 tx=db.list_transactions()[0]
 from decimal import Decimal
 assert Decimal(tx["valor_total_brl"])==Decimal("122.000")
 assert tx["fonte_cambio"]=="manual" and not db.list_unconverted_transactions()

def test_decimal_fraction_quantity_and_quote_roundtrip(database):
 exact="0.123456789123456789"
 database.add_transactions_batch([row(ticker="BTC",classe_ativo="Cripto",moeda_ativo="BRL",moeda_cotacao="BRL",quantidade=exact,preco_unitario=exact,taxas_custos="0")])
 tx=database.list_transactions()[0]
 assert tx["quantidade_original"]==exact
 assert tx["preco_unitario_original"]==exact
 assert tx["valor_total_original"]=="0.01524157878067367851562262075"
 with pytest.raises(ValueError,match="cotação"): database.upsert_quote(int(tx["id_ativo"]),"2025-01-02","0","Manual",True)
 with pytest.raises(ValueError,match="Taxa"): database.upsert_quote(int(tx["id_ativo"]),"2025-01-02",exact,"Manual",True,"USD","0")
 database.upsert_quote(int(tx["id_ativo"]),"2025-01-02",exact,"Manual",True)
 quote=database.list_quotes()[0]
 assert quote["preco_fechamento_decimal"]==exact
 with database.session() as c: assert c.execute("PRAGMA user_version").fetchone()[0]==3
