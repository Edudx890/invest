from decimal import Decimal,InvalidOperation
from hashlib import sha256
from io import BytesIO
import re,pandas as pd
ASSET_CLASSES={"Ação","FII","ETF","Cripto","Renda Fixa","Outro"}
OPERATIONS={"compra":"Compra","buy":"Compra","aporte":"Aporte","venda":"Venda","sell":"Venda","retirada":"Retirada"}
ALIASES={"ticker":{"ticker","symbol","ativo"},"nome_ativo":{"nome_ativo","nome","name"},"classe_ativo":{"classe_ativo","classe","tipo"},"categoria_fundo_setor":{"categoria_fundo_setor","categoria","setor"},"tipo_operacao":{"tipo_operacao","operacao","operação"},"data_transacao":{"data_transacao","data","date"},"quantidade":{"quantidade","units","shares","cotas"},"preco_unitario":{"preco_unitario","preco","preço","unitprice"},"taxas_custos":{"taxas_custos","taxas","custos","fees"},"codigo_api":{"codigo_api","api_code","coingecko_id"},"moeda":{"moeda","currency"},"moeda_ativo":{"moeda_ativo","asset_currency"},"moeda_cotacao":{"moeda_cotacao","quote_currency"},"moeda_transacao":{"moeda_transacao","transaction_currency"},"taxa_cambio":{"taxa_cambio","cambio","fx_rate","exchange_rate"}}
def _headers(f):
 m={}
 for c in f.columns:
  key=str(c).strip().lower().replace(" ","_").replace("-","_")
  for name,aliases in ALIASES.items():
   if key in aliases: m[c]=name; break
 return f.rename(columns=m)
def _text(v,d=""):
 if v is None or pd.isna(v): return d
 v=str(v).strip(); return v if v else d
def _number(v):
 if v is None or pd.isna(v): raise ValueError("valor numérico ausente")
 s=str(v).strip().replace("R$","").replace("$","").replace(" ","")
 if "," in s and "." in s: s=s.replace(".","").replace(",",".") if s.rfind(",")>s.rfind(".") else s.replace(",","")
 elif "," in s: s=s.replace(",",".")
 try: n=Decimal(s)
 except InvalidOperation as e: raise ValueError("valor numérico inválido") from e
 if not n.is_finite(): raise ValueError("valor numérico deve ser finito")
 return n
def _date(v):
 if not _text(v): raise ValueError("data ausente")
 try:
  d=pd.to_datetime(v,dayfirst=True,errors="raise").date()
  if d.year<1900: raise ValueError()
  return d.isoformat()
 except Exception as e: raise ValueError("data inválida; use AAAA-MM-DD ou DD/MM/AAAA") from e
def _fingerprint(r):
 fields=(r["ticker"],r["tipo_operacao"],r["data_transacao"],str(r["quantidade"].normalize()),str(r["preco_unitario"].normalize()),str(r["taxas_custos"].normalize()),r["moeda_transacao"],str(r["taxa_cambio"] or ""))
 return sha256("|".join(fields).encode()).hexdigest()
def parse_csv(data):
 try: f=_headers(pd.read_csv(BytesIO(data),sep=None,engine="python",dtype=str,keep_default_na=False))
 except Exception as e: raise ValueError(f"CSV inválido: {e}") from e
 required={"ticker","tipo_operacao","data_transacao","quantidade","preco_unitario"}; missing=sorted(required-set(f.columns))
 if missing: raise ValueError("Colunas obrigatórias ausentes: "+", ".join(missing))
 rows=[]; errors=[]; seen=set()
 for i,r in f.iterrows():
  try:
   ticker=_text(r["ticker"]).upper(); op=OPERATIONS.get(_text(r["tipo_operacao"]).lower())
   if not ticker or not op: raise ValueError("ticker vazio ou operação inválida")
   day=_date(r["data_transacao"]); qty,price=_number(r["quantidade"]),_number(r["preco_unitario"])
   fee=_number(r.get("taxas_custos","0")) if _text(r.get("taxas_custos")) else Decimal(0)
   if qty<=0 or price<0 or fee<0: raise ValueError("quantidade/preço/taxas fora do intervalo")
   cls=_text(r.get("classe_ativo"),"Outro").title(); cls={"Acao":"Ação"}.get(cls,cls)
   if cls not in ASSET_CLASSES: raise ValueError("classe de ativo inválida")
   asset_cur=_text(r.get("moeda_ativo"),_text(r.get("moeda"),"BRL")).upper()
   tx_cur=_text(r.get("moeda_transacao"),"BRL").upper(); quote=_text(r.get("moeda_cotacao")).upper()
   if any(not re.fullmatch("[A-Z0-9]{3,6}",c) for c in (asset_cur,tx_cur)) or (quote and not re.fullmatch("[A-Z0-9]{3,6}",quote)): raise ValueError("moeda inválida")
   fx=_number(r.get("taxa_cambio")) if _text(r.get("taxa_cambio")) else None
   if fx is not None and fx<=0: raise ValueError("taxa de câmbio deve ser positiva")
   item={"ticker":ticker,"nome_ativo":_text(r.get("nome_ativo"),ticker),"classe_ativo":cls,"categoria_fundo_setor":_text(r.get("categoria_fundo_setor")),"tipo_operacao":op,"data_transacao":day,"quantidade":qty,"preco_unitario":price,"taxas_custos":fee,"codigo_api":_text(r.get("codigo_api")),"moeda_ativo":asset_cur,"moeda_cotacao":quote or ("BRL" if cls=="Cripto" else asset_cur),"moeda_transacao":tx_cur,"taxa_cambio":fx}
   item["fingerprint"]=_fingerprint(item)
   if item["fingerprint"] in seen: raise ValueError("transação duplicada neste arquivo")
   seen.add(item["fingerprint"]); rows.append(item)
  except Exception as e: errors.append(f"Linha {int(i)+2}: {e}")
 return rows,errors
def _tag(block,name):
 m=re.search(rf"<{name}\b[^>]*>\s*([^<\r\n]+)",block,re.I); return m.group(1).strip() if m else None
def parse_ofx(data):
 text=data.decode("utf-8",errors="replace"); pat=re.compile(r"<(BUYSTOCK|SELLSTOCK|BUYMF|SELLMF|BUYOTHER|SELLOTHER)\b(.*?)(?=<(?:BUYSTOCK|SELLSTOCK|BUYMF|SELLMF|BUYOTHER|SELLOTHER)\b|</?INVTRANLIST\b|$)",re.I|re.S)
 rows=[]; errors=[]; blocks=list(pat.finditer(text))
 for i,m in enumerate(blocks,1):
  kind,block=m.group(1).upper(),m.group(2); ticker=_tag(block,"UNIQUEID"); typ=(_tag(block,"UNIQUEIDTYPE") or "").lower(); day=_tag(block,"DTTRADE") or _tag(block,"DTSETTLE")
  try:
   if not ticker: raise ValueError("identificador ausente")
   if typ and typ not in {"ticker","symbol"}: raise ValueError("identificador não é ticker")
   if not day or not _tag(block,"UNITS") or not _tag(block,"UNITPRICE"): raise ValueError("data, quantidade ou preço ausente")
   rows.append({"ticker":ticker.upper(),"nome_ativo":ticker.upper(),"classe_ativo":"FII" if re.fullmatch("[A-Z]{4}11",ticker.upper()) else "Ação","categoria_fundo_setor":"","tipo_operacao":"Compra" if kind.startswith("BUY") else "Venda","data_transacao":pd.to_datetime(day[:8],format="%Y%m%d",errors="raise").date().isoformat(),"quantidade":abs(_number(_tag(block,"UNITS"))),"preco_unitario":abs(_number(_tag(block,"UNITPRICE"))),"taxas_custos":Decimal(0),"codigo_api":"","moeda_ativo":"BRL","moeda_cotacao":"BRL","moeda_transacao":"BRL","taxa_cambio":None})
  except Exception as e: errors.append(f"Operação OFX {i}: {e}")
 if not blocks: errors.append("Nenhuma operação compatível encontrada.")
 return rows,errors
def parse_upload(filename,data): return parse_ofx(data) if filename.lower().endswith(".ofx") else parse_csv(data)
