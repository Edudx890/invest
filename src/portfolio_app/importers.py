from __future__ import annotations

from io import BytesIO
import re
import pandas as pd


ASSET_CLASSES = {"Ação", "FII", "ETF", "Cripto", "Renda Fixa", "Outro"}
OPERATIONS = {
    "compra": "Compra",
    "buy": "Compra",
    "aporte": "Aporte",
    "venda": "Venda",
    "sell": "Venda",
    "retirada": "Retirada",
}

HEADER_ALIASES = {
    "ticker": {"ticker", "symbol", "ativo", "codigo", "código"},
    "nome_ativo": {"nome_ativo", "nome", "name"},
    "classe_ativo": {"classe_ativo", "classe", "tipo_ativo", "tipo"},
    "categoria_fundo_setor": {"categoria_fundo_setor", "categoria", "setor"},
    "tipo_operacao": {"tipo_operacao", "operacao", "operação", "tipo_transacao"},
    "data_transacao": {"data_transacao", "data", "date"},
    "quantidade": {"quantidade", "units", "shares", "cotas"},
    "preco_unitario": {"preco_unitario", "preco", "preço", "unitprice", "valor_unitario"},
    "taxas_custos": {"taxas_custos", "taxas", "custos", "fees"},
    "codigo_api": {"codigo_api", "api_code", "coingecko_id"},
    "moeda": {"moeda", "currency"},
}


def _normalise_headers(frame: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for column in frame.columns:
        cleaned = str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for standard, aliases in HEADER_ALIASES.items():
            if cleaned in aliases:
                mapping[column] = standard
                break
    return frame.rename(columns=mapping)


def _text(value: object, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    cleaned = str(value).strip()
    return cleaned if cleaned else default


def parse_csv(data: bytes) -> tuple[list[dict], list[str]]:
    try:
        frame = pd.read_csv(BytesIO(data), sep=None, engine="python", dtype=str)
    except Exception as exc:
        raise ValueError(f"Não foi possível ler o CSV: {exc}") from exc
    frame = _normalise_headers(frame)
    required = {"ticker", "tipo_operacao", "data_transacao", "quantidade", "preco_unitario"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    records: list[dict] = []
    errors: list[str] = []
    for index, row in frame.iterrows():
        line = int(index) + 2
        try:
            ticker = str(row["ticker"]).strip().upper()
            operation_key = str(row["tipo_operacao"]).strip().lower()
            operation = OPERATIONS.get(operation_key)
            if not ticker or operation is None:
                raise ValueError("ticker vazio ou operação inválida")
            date = pd.to_datetime(row["data_transacao"], dayfirst=True, errors="raise").date().isoformat()
            quantity = _number(row["quantidade"])
            unit_price = _number(row["preco_unitario"])
            fee_value = row.get("taxas_custos", 0)
            fees = 0.0 if fee_value is None or pd.isna(fee_value) or not str(fee_value).strip() else _number(fee_value)
            if quantity <= 0 or unit_price < 0 or fees < 0:
                raise ValueError("quantidade/preço/taxas fora do intervalo permitido")
            asset_class = _text(row.get("classe_ativo"), "Outro").title()
            asset_class = {"Acao": "Ação", "Cripto": "Cripto"}.get(asset_class, asset_class)
            if asset_class not in ASSET_CLASSES:
                asset_class = "Outro"
            currency = _text(row.get("moeda"), "BRL").upper()
            if currency not in {"BRL", "USD"}:
                raise ValueError("moeda deve ser BRL ou USD")
            if asset_class == "Cripto":
                currency = "BRL"
            records.append(
                {
                    "ticker": ticker,
                    "nome_ativo": _text(row.get("nome_ativo"), ticker),
                    "classe_ativo": asset_class,
                    "categoria_fundo_setor": _text(row.get("categoria_fundo_setor")),
                    "tipo_operacao": operation,
                    "data_transacao": date,
                    "quantidade": quantity,
                    "preco_unitario": unit_price,
                    "taxas_custos": fees,
                    "codigo_api": _text(row.get("codigo_api")),
                    "moeda": currency,
                }
            )
        except Exception as exc:
            errors.append(f"Linha {line}: {exc}")
    return records, errors


def _number(value: object) -> float:
    if pd.isna(value):
        raise ValueError("valor numérico vazio")
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def _tag(block: str, name: str) -> str | None:
    match = re.search(rf"<{name}\b[^>]*>\s*([^<\r\n]+)", block, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_ofx(data: bytes) -> tuple[list[dict], list[str]]:
    """Read standard OFX investment buy/sell trade blocks where the security ID is a ticker."""
    text = data.decode("utf-8", errors="replace")
    transaction_pattern = re.compile(
        r"<(BUYSTOCK|SELLSTOCK|BUYMF|SELLMF|BUYOTHER|SELLOTHER)\b(.*?)(?=<(?:BUYSTOCK|SELLSTOCK|BUYMF|SELLMF|BUYOTHER|SELLOTHER)\b|</?INVTRANLIST\b|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    records: list[dict] = []
    errors: list[str] = []
    blocks = list(transaction_pattern.finditer(text))
    for index, match in enumerate(blocks, start=1):
        kind = match.group(1).upper()
        block = match.group(2)
        ticker = _tag(block, "UNIQUEID")
        ticker_type = (_tag(block, "UNIQUEIDTYPE") or "").lower()
        date_value = _tag(block, "DTTRADE") or _tag(block, "DTSETTLE")
        units_value = _tag(block, "UNITS")
        price_value = _tag(block, "UNITPRICE")
        try:
            if not ticker:
                raise ValueError("identificador do ativo ausente")
            if ticker_type and ticker_type not in {"ticker", "symbol"}:
                raise ValueError("o arquivo usa código que não é ticker; faça o vínculo pelo CSV")
            if not date_value or not units_value or not price_value:
                raise ValueError("data, quantidade ou preço unitário ausente")
            date = pd.to_datetime(date_value[:8], format="%Y%m%d", errors="raise").date().isoformat()
            operation = "Compra" if kind.startswith("BUY") else "Venda"
            asset_class = "FII" if re.fullmatch(r"[A-Z]{4}11", ticker.upper()) else "Ação"
            records.append(
                {
                    "ticker": ticker.upper(),
                    "nome_ativo": ticker.upper(),
                    "classe_ativo": asset_class,
                    "categoria_fundo_setor": "",
                    "tipo_operacao": operation,
                    "data_transacao": date,
                    "quantidade": abs(_number(units_value)),
                    "preco_unitario": abs(_number(price_value)),
                    "taxas_custos": 0.0,
                    "codigo_api": "",
                    "moeda": "BRL",
                }
            )
        except Exception as exc:
            errors.append(f"Operação OFX {index}: {exc}")
    if not blocks:
        errors.append("Nenhuma operação de compra/venda compatível foi encontrada no OFX.")
    return records, errors


def parse_upload(filename: str, data: bytes) -> tuple[list[dict], list[str]]:
    if filename.lower().endswith(".ofx"):
        return parse_ofx(data)
    return parse_csv(data)
