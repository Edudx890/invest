from contextlib import contextmanager
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
import hashlib,os,sqlite3,tempfile
from .financial import currency_code,decimal_value,transaction_amounts
ROOT_DIR=Path(__file__).resolve().parents[2]; DATA_DIR=ROOT_DIR/"data"; DB_PATH=DATA_DIR/"investimentos.db"; BACKUP_DIR=DATA_DIR/"backups"; SCHEMA_VERSION=3
SCHEMA="""
CREATE TABLE IF NOT EXISTS Ativos(id_ativo INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT NOT NULL UNIQUE,nome_ativo TEXT NOT NULL,classe_ativo TEXT NOT NULL,categoria_fundo_setor TEXT,is_manual_entry INTEGER NOT NULL DEFAULT 0,data_cadastro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,codigo_api TEXT,moeda TEXT NOT NULL DEFAULT 'BRL',moeda_ativo TEXT NOT NULL DEFAULT 'BRL',moeda_base TEXT NOT NULL DEFAULT 'BRL');
CREATE TABLE IF NOT EXISTS Transacoes(id_transacao INTEGER PRIMARY KEY AUTOINCREMENT,id_ativo INTEGER NOT NULL,tipo_operacao TEXT NOT NULL,data_transacao TEXT NOT NULL,quantidade REAL NOT NULL,preco_unitario REAL NOT NULL,taxas_custos REAL NOT NULL DEFAULT 0,is_manual_entry INTEGER NOT NULL DEFAULT 0,quantidade_original TEXT,preco_unitario_original TEXT,valor_total_original TEXT,taxas_custos_original TEXT,moeda_transacao TEXT,moeda_base TEXT,taxa_cambio TEXT,preco_unitario_brl TEXT,valor_total_brl TEXT,taxas_custos_brl TEXT,fonte_cambio TEXT,fingerprint TEXT,FOREIGN KEY(id_ativo) REFERENCES Ativos(id_ativo));
CREATE TABLE IF NOT EXISTS Cotacoes_Historico(id_cotacao INTEGER PRIMARY KEY AUTOINCREMENT,id_ativo INTEGER NOT NULL,data_cotacao TEXT NOT NULL,preco_fechamento REAL NOT NULL,preco_fechamento_decimal TEXT,fonte_dados TEXT NOT NULL,is_manual_entry INTEGER NOT NULL DEFAULT 0,preco_original TEXT,moeda_original TEXT DEFAULT 'BRL',moeda_base TEXT DEFAULT 'BRL',taxa_cambio TEXT DEFAULT '1',preco_ajustado REAL,preco_ajustado_decimal TEXT,FOREIGN KEY(id_ativo) REFERENCES Ativos(id_ativo),UNIQUE(id_ativo,data_cotacao));
CREATE TABLE IF NOT EXISTS Proventos(id_provento INTEGER PRIMARY KEY AUTOINCREMENT,id_ativo INTEGER NOT NULL,tipo_provento TEXT NOT NULL,data_com TEXT NOT NULL,data_pagamento TEXT,valor_por_acao REAL NOT NULL,valor_total REAL NOT NULL,is_manual_entry INTEGER NOT NULL DEFAULT 0,valor_total_brl TEXT,moeda_provento TEXT DEFAULT 'BRL',taxa_cambio TEXT DEFAULT '1',fonte_dados TEXT DEFAULT 'Manual',FOREIGN KEY(id_ativo) REFERENCES Ativos(id_ativo));
CREATE TABLE IF NOT EXISTS Configuracoes(chave TEXT PRIMARY KEY,valor TEXT NOT NULL,atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS Taxas_Cambio(moeda TEXT NOT NULL,data_taxa TEXT NOT NULL,taxa_para_brl TEXT NOT NULL,fonte_dados TEXT NOT NULL,atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(moeda,data_taxa));
CREATE TABLE IF NOT EXISTS Renda_Fixa(id_renda_fixa INTEGER PRIMARY KEY AUTOINCREMENT,nome TEXT NOT NULL,tipo TEXT NOT NULL,emissor TEXT DEFAULT '',valor_investido TEXT NOT NULL,valor_atualizado TEXT NOT NULL,taxa TEXT DEFAULT '',indexador TEXT DEFAULT '',vencimento TEXT DEFAULT '',liquidez TEXT DEFAULT '',instituicao TEXT DEFAULT '',observacoes TEXT DEFAULT '',moeda_base TEXT DEFAULT 'BRL',is_manual_entry INTEGER DEFAULT 1,atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS Schema_Meta(chave TEXT PRIMARY KEY,valor TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_transacoes_ativo ON Transacoes(id_ativo);
CREATE INDEX IF NOT EXISTS idx_cotacoes_ativo_data ON Cotacoes_Historico(id_ativo,data_cotacao);
CREATE INDEX IF NOT EXISTS idx_proventos_ativo ON Proventos(id_ativo);
CREATE INDEX IF NOT EXISTS idx_transacoes_data ON Transacoes(data_transacao);
CREATE INDEX IF NOT EXISTS idx_fx_date ON Taxas_Cambio(moeda,data_taxa);
"""
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH,timeout=20); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=20000"); return c
@contextmanager
def session():
    c=connect()
    try: yield c; c.commit()
    except Exception: c.rollback(); raise
    finally: c.close()
def _cols(c,t): return {r["name"] for r in c.execute(f"PRAGMA table_info({t})")}
def _add(c,t,n,d):
    if n in _cols(c,t): return False
    c.execute(f"ALTER TABLE {t} ADD COLUMN {n} {d}"); return True
def _migrate(c):
    c.executescript(SCHEMA)
    c.execute("BEGIN IMMEDIATE")
    try:
        added_currency=_add(c,"Ativos","moeda_ativo","TEXT")
        _add(c,"Ativos","moeda_base","TEXT")
        _add(c,"Ativos","codigo_api","TEXT")
        _add(c,"Ativos","moeda","TEXT")
        for n in ("quantidade_original","preco_unitario_original","valor_total_original","taxas_custos_original","moeda_transacao","moeda_base","taxa_cambio","preco_unitario_brl","valor_total_brl","taxas_custos_brl","fonte_cambio","fingerprint"):
            _add(c,"Transacoes",n,"TEXT")
        c.execute("UPDATE Transacoes SET quantidade_original=CAST(quantidade AS TEXT) WHERE quantidade_original IS NULL")
        added_quote=_add(c,"Cotacoes_Historico","preco_original","TEXT")
        for n,d in (("moeda_original","TEXT"),("moeda_base","TEXT"),("taxa_cambio","TEXT"),("preco_ajustado","REAL"),("preco_fechamento_decimal","TEXT"),("preco_ajustado_decimal","TEXT")):
            _add(c,"Cotacoes_Historico",n,d)
        added_div=_add(c,"Proventos","valor_total_brl","TEXT")
        for n in ("moeda_provento","taxa_cambio","fonte_dados"):
            _add(c,"Proventos",n,"TEXT")
        if added_currency:
            c.execute("UPDATE Ativos SET moeda_ativo=COALESCE(NULLIF(UPPER(moeda),''),'BRL')")
        c.execute("UPDATE Ativos SET moeda_base='BRL' WHERE moeda_base IS NULL OR moeda_base=''")
        for r in c.execute("""SELECT t.*,a.moeda_ativo,a.moeda FROM Transacoes t JOIN Ativos a ON a.id_ativo=t.id_ativo WHERE t.preco_unitario_brl IS NULL""").fetchall():
            q=decimal_value(r["quantidade_original"] or r["quantidade"])
            pv=decimal_value(r["preco_unitario"])
            f=decimal_value(r["taxas_custos"],Decimal(0)); total=q*pv
            curr=currency_code(r["moeda_ativo"] or r["moeda"] or "BRL")
            if curr=="BRL":
                rate,source=Decimal(1),"legado BRL"
            else:
                rate,source=_fx(c,curr,r["data_transacao"])
            if rate is None:
                c.execute("""UPDATE Transacoes SET quantidade_original=?,preco_unitario_original=?,valor_total_original=?,taxas_custos_original=?,moeda_transacao=?,moeda_base='BRL',taxa_cambio=NULL,preco_unitario_brl=NULL,valor_total_brl=NULL,taxas_custos_brl=NULL,fonte_cambio='pendente: informar taxa histórica' WHERE id_transacao=?""",(str(q),str(pv),str(total),str(f),curr,r["id_transacao"]))
            else:
                c.execute("""UPDATE Transacoes SET quantidade_original=?,preco_unitario_original=?,valor_total_original=?,taxas_custos_original=?,moeda_transacao=?,moeda_base='BRL',taxa_cambio=?,preco_unitario_brl=?,valor_total_brl=?,taxas_custos_brl=?,fonte_cambio=? WHERE id_transacao=?""",(str(q),str(pv),str(total),str(f),curr,str(rate),str(pv*rate),str(total*rate),str(f*rate),source,r["id_transacao"]))

        if added_quote:
            c.execute("""UPDATE Cotacoes_Historico SET preco_original=CAST(preco_fechamento AS TEXT),moeda_original='BRL',moeda_base='BRL',taxa_cambio='1',preco_ajustado=preco_fechamento,preco_fechamento_decimal=CAST(preco_fechamento AS TEXT),preco_ajustado_decimal=CAST(preco_fechamento AS TEXT)""")
        else:
            c.execute("""UPDATE Cotacoes_Historico SET preco_original=COALESCE(preco_original,CAST(preco_fechamento AS TEXT)),moeda_original=COALESCE(moeda_original,'BRL'),moeda_base=COALESCE(moeda_base,'BRL'),taxa_cambio=COALESCE(taxa_cambio,'1'),preco_ajustado=COALESCE(preco_ajustado,preco_fechamento),preco_fechamento_decimal=COALESCE(preco_fechamento_decimal,CAST(preco_fechamento AS TEXT)),preco_ajustado_decimal=COALESCE(preco_ajustado_decimal,CAST(COALESCE(preco_ajustado,preco_fechamento) AS TEXT))""")
        if added_div:
            c.execute("""UPDATE Proventos SET valor_total_brl=CAST(valor_total AS TEXT),moeda_provento='BRL',taxa_cambio='1',fonte_dados='legado'""")
        else:
            c.execute("""UPDATE Proventos SET valor_total_brl=COALESCE(valor_total_brl,CAST(valor_total AS TEXT)),moeda_provento=COALESCE(moeda_provento,'BRL'),taxa_cambio=COALESCE(taxa_cambio,'1'),fonte_dados=COALESCE(fonte_dados,'legado')""")
        c.execute("INSERT INTO Schema_Meta(chave,valor) VALUES('schema_version',?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(str(SCHEMA_VERSION),))
        c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        c.commit()
    except Exception:
        c.rollback()
        raise


def create_startup_backup():
    if not DB_PATH.exists() or not DB_PATH.stat().st_size: return None
    BACKUP_DIR.mkdir(parents=True,exist_ok=True); target=BACKUP_DIR/f"investimentos-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    try:
        src,dst=sqlite3.connect(DB_PATH),sqlite3.connect(target)
        try: src.backup(dst)
        finally: dst.close(); src.close()
        old=sorted(BACKUP_DIR.glob("investimentos-*.db"),key=lambda p:p.stat().st_mtime,reverse=True)
        for p in old[14:]: p.unlink(missing_ok=True)
        return target
    except sqlite3.DatabaseError: target.unlink(missing_ok=True); return None
def init_db():
    DATA_DIR.mkdir(parents=True,exist_ok=True); create_startup_backup()
    with session() as c: _migrate(c)
def fetch_all(sql,params=()):
    with session() as c: return list(c.execute(sql,params).fetchall())
def _date(v):
    try: return date.fromisoformat(str(v)).isoformat()
    except (TypeError,ValueError) as e: raise ValueError("Data inválida; use AAAA-MM-DD.") from e
def _asset(c,ticker,name,cls,category,manual,api,currency,quote):
    ticker=str(ticker or "").strip().upper()
    if not ticker: raise ValueError("Informe ticker.")
    currency,quote=currency_code(currency),currency_code(quote)
    r=c.execute("SELECT id_ativo FROM Ativos WHERE ticker=?",(ticker,)).fetchone()
    vals=(name or ticker,cls,category,api or None,currency,quote,ticker)
    if r:
        c.execute("""UPDATE Ativos SET nome_ativo=?,classe_ativo=?,categoria_fundo_setor=?,codigo_api=COALESCE(?,codigo_api),moeda_ativo=?,moeda=?,moeda_base='BRL' WHERE ticker=?""",vals); return int(r["id_ativo"])
    cur=c.execute("""INSERT INTO Ativos(ticker,nome_ativo,classe_ativo,categoria_fundo_setor,is_manual_entry,codigo_api,moeda,moeda_ativo,moeda_base) VALUES(?,?,?,?,?,?,?,?, 'BRL')""",(ticker,name or ticker,cls,category,int(manual),api or None,quote,currency)); return int(cur.lastrowid)
def add_asset(ticker,name,asset_class,category="",manual=True,api_code="",currency="BRL",quote_currency=None):
    with session() as c: return _asset(c,ticker,name,asset_class,category,manual,api_code,currency,quote_currency or currency)
def _fx(c,curr,day):
    if curr=="BRL": return Decimal(1),"identidade"
    r=c.execute("SELECT * FROM Taxas_Cambio WHERE moeda=? AND data_taxa<=? ORDER BY data_taxa DESC LIMIT 1",(curr,day)).fetchone()
    if not r or (date.fromisoformat(day)-date.fromisoformat(r["data_taxa"])).days>7: return None,None
    return decimal_value(r["taxa_para_brl"]),r["fonte_dados"]
def upsert_exchange_rate(currency,rate_date,rate,source):
    curr=currency_code(currency); day=_date(rate_date); rate=decimal_value(rate)
    if rate<=0: raise ValueError("Taxa deve ser positiva.")
    with session() as c: c.execute("""INSERT INTO Taxas_Cambio(moeda,data_taxa,taxa_para_brl,fonte_dados) VALUES(?,?,?,?) ON CONFLICT(moeda,data_taxa) DO UPDATE SET taxa_para_brl=excluded.taxa_para_brl,fonte_dados=excluded.fonte_dados,atualizado_em=CURRENT_TIMESTAMP""",(curr,day,str(rate),source))
def get_exchange_rate(currency,rate_date,max_age_days=7):
    curr=currency_code(currency); day=_date(rate_date)
    if curr=="BRL": return {"taxa_para_brl":Decimal(1),"data_taxa":day,"fonte_dados":"identidade"}
    rows=fetch_all("SELECT * FROM Taxas_Cambio WHERE moeda=? AND data_taxa<=? ORDER BY data_taxa DESC LIMIT 1",(curr,day))
    if not rows or (date.fromisoformat(day)-date.fromisoformat(rows[0]["data_taxa"])).days>max_age_days: return None
    r=rows[0]; return {"taxa_para_brl":Decimal(r["taxa_para_brl"]),"data_taxa":r["data_taxa"],"fonte_dados":r["fonte_dados"]}
def _fingerprint(ticker,op,day,a):
    s="|".join((ticker,op,day,str(a["quantidade"]),str(a["preco_unitario_original"]),str(a["taxas_custos_original"]),a["moeda_transacao"],str(a["taxa_cambio"])))
    return hashlib.sha256(s.encode()).hexdigest()
def _insert_tx(c, aid, transaction, manual=True):
    op = str(transaction["tipo_operacao"]).strip().title()
    day = _date(transaction["data_transacao"])
    currency = currency_code(transaction.get("moeda_transacao", "BRL"))
    if currency == "BRL":
        rate, fx_source = Decimal(1), "identidade"
    elif transaction.get("taxa_cambio") not in (None, ""):
        rate = decimal_value(transaction["taxa_cambio"])
        fx_source = transaction.get("fonte_cambio") or "manual"
    else:
        cached = _fx(c, currency, day)
        if cached[0] is None:
            raise ValueError(f"Taxa {currency}/BRL indisponível em {day}; informe o câmbio ou registre cache.")
        rate, fx_source = cached
    amount = transaction_amounts(
        transaction["quantidade"],
        transaction.get("preco_unitario_original", transaction.get("preco_unitario")),
        transaction.get("taxas_custos_original", transaction.get("taxas_custos", "0")),
        currency, rate
    )
    ticker_row=c.execute("SELECT ticker FROM Ativos WHERE id_ativo=?",(aid,)).fetchone()
    fingerprint=transaction.get("fingerprint") or _fingerprint(ticker_row["ticker"],op,day,{
        "quantidade":amount["quantidade"],"preco_unitario_original":amount["preco_unitario_original"],
        "taxas_custos_original":amount["taxas_custos_original"],"moeda_transacao":currency,
        "taxa_cambio":amount["taxa_cambio"]})
    if c.execute("SELECT 1 FROM Transacoes WHERE fingerprint=?",(fingerprint,)).fetchone():
        return None
    cur=c.execute(
        """INSERT INTO Transacoes(
            id_ativo,tipo_operacao,data_transacao,quantidade,preco_unitario,
            taxas_custos,is_manual_entry,quantidade_original,
            preco_unitario_original,valor_total_original,taxas_custos_original,
            moeda_transacao,moeda_base,taxa_cambio,preco_unitario_brl,
            valor_total_brl,taxas_custos_brl,fonte_cambio,fingerprint
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (aid,op,day,float(amount["quantidade"]),float(amount["preco_unitario_original"]),
         float(amount["taxas_custos_original"]),int(bool(manual)),str(amount["quantidade"]),
         str(amount["preco_unitario_original"]),str(amount["valor_total_original"]),
         str(amount["taxas_custos_original"]),currency,"BRL",str(amount["taxa_cambio"]),
         str(amount["preco_unitario_brl"]),str(amount["valor_total_brl"]),
         str(amount["taxas_custos_brl"]),fx_source,fingerprint)
    )
    return cur.lastrowid


def _validate_sells(c):
    for asset in c.execute("SELECT id_ativo FROM Ativos"):
        events=[]
        for r in c.execute("SELECT * FROM Transacoes WHERE id_ativo=?",(asset["id_ativo"],)): events.append((r["data_transacao"],1,r["id_transacao"],r))
        for r in c.execute("SELECT * FROM Proventos WHERE id_ativo=? AND tipo_provento='Split'",(asset["id_ativo"],)): events.append((r["data_com"],0,r["id_provento"],r))
        qty=Decimal(0)
        for _,kind,_,r in sorted(events,key=lambda x:x[:3]):
            if kind==0: qty*=decimal_value(r["valor_por_acao"]); continue
            n=decimal_value(r["quantidade_original"] or r["quantidade"]); op=str(r["tipo_operacao"]).title()
            if op in {"Compra","Aporte"}: qty+=n
            elif n>qty: raise ValueError(f"Venda excede posição disponível na data {r['data_transacao']}.")
            else: qty-=n
def add_transactions_batch(rows,manual=True):
    ids=[]
    with session() as c:
        c.execute("BEGIN IMMEDIATE")
        for row in rows:
            if row.get("id_ativo") is not None: aid=int(row["id_ativo"])
            else:
                curr=row.get("moeda_ativo",row.get("moeda","BRL")); quote=row.get("moeda_cotacao") or ("BRL" if row.get("classe_ativo")=="Cripto" else curr)
                aid=_asset(c,row.get("ticker"),row.get("nome_ativo"),row.get("classe_ativo","Outro"),row.get("categoria_fundo_setor",""),manual,row.get("codigo_api",""),curr,quote)
            rid=_insert_tx(c,aid,row,manual)
            if rid is not None: ids.append(rid)
        _validate_sells(c)
    return ids
def add_transaction(asset_id,operation,day,quantity,price,fees=0,manual=True,transaction_currency="BRL",exchange_rate=None):
    ids=add_transactions_batch([{"id_ativo":asset_id,"tipo_operacao":operation,"data_transacao":day,"quantidade":quantity,"preco_unitario":price,"taxas_custos":fees,"moeda_transacao":transaction_currency,"taxa_cambio":exchange_rate}],manual)
    if not ids: raise ValueError("Transação duplicada.")
    return ids[0]
def set_transaction_exchange_rate(transaction_id, rate, source="manual"):
    rate=decimal_value(rate)
    if rate<=0: raise ValueError("Taxa deve ser positiva.")
    with session() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT * FROM Transacoes WHERE id_transacao=?",(int(transaction_id),)).fetchone()
        if not row: raise ValueError("Transação não encontrada.")
        curr=currency_code(row["moeda_transacao"] or "BRL")
        if curr=="BRL": raise ValueError("Transações em BRL não precisam de câmbio.")
        amount=transaction_amounts(row["quantidade_original"] or row["quantidade"],row["preco_unitario_original"] or row["preco_unitario"],row["taxas_custos_original"] or row["taxas_custos"],curr,rate)
        c.execute("""UPDATE Transacoes SET taxa_cambio=?,preco_unitario_brl=?,valor_total_brl=?,taxas_custos_brl=?,fonte_cambio=? WHERE id_transacao=?""",(str(rate),str(amount["preco_unitario_brl"]),str(amount["valor_total_brl"]),str(amount["taxas_custos_brl"]),source,int(transaction_id)))
        _validate_sells(c)

def upsert_quote(asset_id, day, close, source, manual=False,
                 original_currency="BRL", exchange_rate=None, adjusted_price=None):
    day=_date(day)
    currency=currency_code(original_currency)
    original=decimal_value(close)
    if original<=0: raise ValueError("A cotação deve ser positiva.")
    if currency=="BRL":
        rate=Decimal(1)
    elif exchange_rate not in (None,""):
        rate=decimal_value(exchange_rate)
    else:
        cached=get_exchange_rate(currency,day)
        if not cached:
            raise ValueError(f"Taxa {currency}/BRL indisponível em {day}; informe o câmbio ou registre cache.")
        rate=cached["taxa_para_brl"]
    if rate<=0: raise ValueError("Taxa deve ser positiva.")
    close_brl=original*rate
    adjusted_original=original if adjusted_price is None else decimal_value(adjusted_price)
    if adjusted_original<=0: raise ValueError("A cotação ajustada deve ser positiva.")
    adjusted_brl=adjusted_original*rate
    with session() as c:
        c.execute(
            """INSERT INTO Cotacoes_Historico(
                id_ativo,data_cotacao,preco_fechamento,preco_fechamento_decimal,
                fonte_dados,is_manual_entry,preco_original,moeda_original,
                moeda_base,taxa_cambio,preco_ajustado,preco_ajustado_decimal
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id_ativo,data_cotacao) DO UPDATE SET
                preco_fechamento=excluded.preco_fechamento,
                preco_fechamento_decimal=excluded.preco_fechamento_decimal,
                fonte_dados=excluded.fonte_dados,
                is_manual_entry=excluded.is_manual_entry,
                preco_original=excluded.preco_original,
                moeda_original=excluded.moeda_original,
                moeda_base=excluded.moeda_base,
                taxa_cambio=excluded.taxa_cambio,
                preco_ajustado=excluded.preco_ajustado,
                preco_ajustado_decimal=excluded.preco_ajustado_decimal""",
            (asset_id,day,float(close_brl),str(close_brl),source,int(bool(manual)),
             str(original),currency,"BRL",str(rate),float(adjusted_brl),str(adjusted_brl))
        )


def add_dividend(aid,kind,day,pay,per,total,manual=True,source="Manual"):
    day=_date(day); pay=_date(pay) if pay else None; per,total=decimal_value(per),decimal_value(total)
    if per<0 or total<0: raise ValueError("Provento negativo.")
    with session() as c:
        old=c.execute("SELECT id_provento FROM Proventos WHERE id_ativo=? AND tipo_provento=? AND data_com=? AND ABS(valor_por_acao-?)<1e-9",(aid,kind,day,float(per))).fetchone()
        if old: return int(old["id_provento"])
        cur=c.execute("""INSERT INTO Proventos(id_ativo,tipo_provento,data_com,data_pagamento,valor_por_acao,valor_total,is_manual_entry,valor_total_brl,moeda_provento,taxa_cambio,fonte_dados) VALUES(?,?,?,?,?,?,?,?,'BRL','1',?)""",(aid,kind,day,pay,float(per),float(total),int(manual),str(total),source)); return int(cur.lastrowid)
def quantity_as_of(aid,day):
    q=Decimal(0)
    for r in fetch_all("SELECT tipo_operacao,quantidade,quantidade_original FROM Transacoes WHERE id_ativo=? AND data_transacao<=? ORDER BY data_transacao,id_transacao",(aid,day)):
        n=decimal_value(r["quantidade_original"] or r["quantidade"]); q+=n if r["tipo_operacao"].title() in {"Compra","Aporte"} else -min(n,q)
    for r in fetch_all("SELECT valor_por_acao FROM Proventos WHERE id_ativo=? AND tipo_provento='Split' AND data_com<=? ORDER BY data_com,id_provento",(aid,day)): q*=decimal_value(r["valor_por_acao"])
    return float(q)
def get_setting(key,default):
    rows=fetch_all("SELECT valor FROM Configuracoes WHERE chave=?",(key,)); return str(rows[0]["valor"]) if rows else default
def set_setting(key,value):
    with session() as c: c.execute("INSERT INTO Configuracoes(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,atualizado_em=CURRENT_TIMESTAMP",(key,value))
def list_assets(): return fetch_all("SELECT * FROM Ativos ORDER BY ticker")
def list_transactions(): return fetch_all("SELECT t.*,a.ticker,a.nome_ativo,a.moeda_ativo,a.moeda FROM Transacoes t JOIN Ativos a ON a.id_ativo=t.id_ativo ORDER BY t.data_transacao,t.id_transacao")
def list_unconverted_transactions():
    return fetch_all("""SELECT t.*,a.ticker,a.nome_ativo FROM Transacoes t JOIN Ativos a ON a.id_ativo=t.id_ativo WHERE t.moeda_transacao<>'BRL' AND (t.taxa_cambio IS NULL OR t.valor_total_brl IS NULL) ORDER BY t.data_transacao,t.id_transacao""")
def list_quotes(): return fetch_all("SELECT q.*,a.ticker FROM Cotacoes_Historico q JOIN Ativos a ON a.id_ativo=q.id_ativo ORDER BY q.data_cotacao")
def latest_quotes():
    rs=fetch_all("SELECT q.*,a.ticker FROM Cotacoes_Historico q JOIN Ativos a ON a.id_ativo=q.id_ativo JOIN (SELECT id_ativo,MAX(data_cotacao) d FROM Cotacoes_Historico GROUP BY id_ativo) m ON m.id_ativo=q.id_ativo AND m.d=q.data_cotacao")
    return {int(r["id_ativo"]):r for r in rs}
def list_dividends(): return fetch_all("SELECT p.*,a.ticker FROM Proventos p JOIN Ativos a ON a.id_ativo=p.id_ativo ORDER BY p.data_com DESC")
def save_fixed_income(r,record_id=None):
    name=str(r.get("nome","")).strip(); kind=str(r.get("tipo","Outro"))
    if not name: raise ValueError("Informe o nome.")
    if kind not in {"CDB","LCI/LCA","Tesouro","Outro"}: raise ValueError("Tipo inválido.")
    invested,current=decimal_value(r.get("valor_investido")),decimal_value(r.get("valor_atualizado"))
    if invested<=0 or current<0: raise ValueError("Valor de renda fixa inválido.")
    due=str(r.get("vencimento","") or "").strip()
    if due: due=_date(due)
    rate=str(r.get("taxa","") or "").strip()
    if rate: decimal_value(rate)
    vals=(name,kind,r.get("emissor",""),str(invested),str(current),rate,r.get("indexador",""),due,r.get("liquidez",""),r.get("instituicao",""),r.get("observacoes",""))
    with session() as c:
        if record_id:
            cur=c.execute("UPDATE Renda_Fixa SET nome=?,tipo=?,emissor=?,valor_investido=?,valor_atualizado=?,taxa=?,indexador=?,vencimento=?,liquidez=?,instituicao=?,observacoes=?,atualizado_em=CURRENT_TIMESTAMP WHERE id_renda_fixa=?",(*vals,int(record_id)))
            if not cur.rowcount: raise ValueError("Cadastro não encontrado.")
            return int(record_id)
        cur=c.execute("INSERT INTO Renda_Fixa(nome,tipo,emissor,valor_investido,valor_atualizado,taxa,indexador,vencimento,liquidez,instituicao,observacoes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",vals); return int(cur.lastrowid)
def list_fixed_income(): return fetch_all("SELECT * FROM Renda_Fixa ORDER BY nome")
def backup_database_bytes():
    if not DB_PATH.exists(): init_db()
    h=tempfile.NamedTemporaryFile(suffix=".db",dir=DATA_DIR,delete=False); p=Path(h.name); h.close()
    try:
        src,dst=sqlite3.connect(DB_PATH),sqlite3.connect(p)
        try: src.backup(dst)
        finally: src.close(); dst.close()
        return p.read_bytes()
    finally: p.unlink(missing_ok=True)
def restore_database(data):
    DATA_DIR.mkdir(parents=True,exist_ok=True); h=tempfile.NamedTemporaryFile(suffix=".db",dir=DATA_DIR,delete=False); p=Path(h.name); h.close(); p.write_bytes(data)
    try:
        c=sqlite3.connect(p); c.row_factory=sqlite3.Row
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("Falha na integridade SQLite.")
            tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"Ativos","Transacoes","Cotacoes_Historico","Proventos"}.issubset(tables): raise ValueError("Tabelas necessárias ausentes.")
            if int(c.execute("PRAGMA user_version").fetchone()[0] or 0)>SCHEMA_VERSION: raise ValueError("Schema mais novo.")
            c.execute("PRAGMA foreign_keys=ON")
            if c.execute("PRAGMA foreign_key_check").fetchall(): raise ValueError("Chaves estrangeiras inválidas.")
            _migrate(c)
        except sqlite3.DatabaseError as e: raise ValueError("Arquivo sem integridade SQLite válida.") from e
        finally: c.close()
        create_startup_backup(); os.replace(p,DB_PATH)
    finally: p.unlink(missing_ok=True)
