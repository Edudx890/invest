from decimal import Decimal,InvalidOperation,getcontext
import re
getcontext().prec=28
def decimal_value(value,default=None):
    if value is None or value=="":
        if default is not None: return default
        raise ValueError("Valor numérico obrigatório.")
    try: result=value if isinstance(value,Decimal) else Decimal(str(value).strip())
    except (InvalidOperation,ValueError,TypeError) as exc: raise ValueError(f"Valor numérico inválido: {value}") from exc
    if not result.is_finite(): raise ValueError("O valor deve ser finito.")
    return result
def currency_code(value):
    code=str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,6}",code): raise ValueError("Moeda/código inválido.")
    return code
def transaction_amounts(quantity,unit_price,fees,currency,exchange_rate):
    quantity=decimal_value(quantity); unit_price=decimal_value(unit_price); fees=decimal_value(fees,Decimal("0"))
    currency=currency_code(currency); rate=Decimal("1") if currency=="BRL" else decimal_value(exchange_rate)
    if quantity<=0 or unit_price<0 or fees<0 or rate<=0: raise ValueError("Quantidade, preço, taxas ou câmbio inválido.")
    total=quantity*unit_price
    return {"quantidade":quantity,"preco_unitario_original":unit_price,"valor_total_original":total,
    "taxas_custos_original":fees,"moeda_transacao":currency,"moeda_base":"BRL","taxa_cambio":rate,
    "preco_unitario_brl":unit_price*rate,"valor_total_brl":total*rate,"taxas_custos_brl":fees*rate}
def decimal_from_row(row,explicit,legacy,default="0"):
    value=row.get(explicit)
    return decimal_value(value) if value not in (None,"") else decimal_value(row.get(legacy),Decimal(default))
