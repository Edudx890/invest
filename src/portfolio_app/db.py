from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "investimentos.db"
BACKUP_DIR = DATA_DIR / "backups"

SCHEMA = """
CREATE TABLE IF NOT EXISTS Ativos (
    id_ativo INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    nome_ativo TEXT NOT NULL,
    classe_ativo TEXT NOT NULL,
    categoria_fundo_setor TEXT,
    is_manual_entry INTEGER NOT NULL DEFAULT 0,
    data_cadastro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    codigo_api TEXT,
    moeda TEXT NOT NULL DEFAULT 'BRL'
);
CREATE TABLE IF NOT EXISTS Transacoes (
    id_transacao INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ativo INTEGER NOT NULL,
    tipo_operacao TEXT NOT NULL,
    data_transacao TEXT NOT NULL,
    quantidade REAL NOT NULL,
    preco_unitario REAL NOT NULL,
    taxas_custos REAL NOT NULL DEFAULT 0.0,
    is_manual_entry INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_ativo) REFERENCES Ativos(id_ativo)
);
CREATE TABLE IF NOT EXISTS Cotacoes_Historico (
    id_cotacao INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ativo INTEGER NOT NULL,
    data_cotacao TEXT NOT NULL,
    preco_fechamento REAL NOT NULL,
    fonte_dados TEXT NOT NULL,
    is_manual_entry INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_ativo) REFERENCES Ativos(id_ativo),
    UNIQUE (id_ativo, data_cotacao)
);
CREATE TABLE IF NOT EXISTS Proventos (
    id_provento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ativo INTEGER NOT NULL,
    tipo_provento TEXT NOT NULL,
    data_com TEXT NOT NULL,
    data_pagamento TEXT,
    valor_por_acao REAL NOT NULL,
    valor_total REAL NOT NULL,
    is_manual_entry INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_ativo) REFERENCES Ativos(id_ativo)
);
CREATE TABLE IF NOT EXISTS Configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_transacoes_ativo ON Transacoes(id_ativo);
CREATE INDEX IF NOT EXISTS idx_cotacoes_ativo_data ON Cotacoes_Historico(id_ativo, data_cotacao);
CREATE INDEX IF NOT EXISTS idx_proventos_ativo ON Proventos(id_ativo);
CREATE INDEX IF NOT EXISTS idx_transacoes_data ON Transacoes(data_transacao);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 20000")
    return connection


def create_startup_backup() -> Path | None:
    """Copy a valid existing database before schema changes or app startup."""
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"investimentos-{stamp}.db"
    try:
        source = sqlite3.connect(DB_PATH)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        backups = sorted(BACKUP_DIR.glob("investimentos-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[14:]:
            old.unlink(missing_ok=True)
        return target
    except sqlite3.DatabaseError:
        target.unlink(missing_ok=True)
        return None


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    create_startup_backup()
    with connect() as connection:
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(Ativos)")}
        if "codigo_api" not in columns:
            connection.execute("ALTER TABLE Ativos ADD COLUMN codigo_api TEXT")
        if "moeda" not in columns:
            connection.execute("ALTER TABLE Ativos ADD COLUMN moeda TEXT NOT NULL DEFAULT 'BRL'")
        connection.commit()


def fetch_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with connect() as connection:
        return list(connection.execute(sql, params).fetchall())


def execute(sql: str, params: tuple = ()) -> int:
    with connect() as connection:
        cursor = connection.execute(sql, params)
        connection.commit()
        return int(cursor.lastrowid or 0)


def add_asset(
    ticker: str,
    name: str,
    asset_class: str,
    category: str = "",
    manual: bool = True,
    api_code: str = "",
    currency: str = "BRL",
) -> int:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Informe o ticker do ativo.")
    existing = fetch_all("SELECT id_ativo FROM Ativos WHERE ticker = ?", (ticker,))
    if existing:
        execute(
            """UPDATE Ativos SET nome_ativo=?, classe_ativo=?, categoria_fundo_setor=?,
               codigo_api=COALESCE(NULLIF(?, ''), codigo_api), moeda=? WHERE ticker=?""",
            (name.strip() or ticker, asset_class, category.strip(), api_code.strip(), currency.upper(), ticker),
        )
        return int(existing[0]["id_ativo"])
    return execute(
        """INSERT INTO Ativos(ticker,nome_ativo,classe_ativo,categoria_fundo_setor,
           is_manual_entry,codigo_api,moeda) VALUES(?,?,?,?,?,?,?)""",
        (ticker, name.strip() or ticker, asset_class, category.strip(), int(manual), api_code.strip() or None, currency.upper()),
    )


def add_transaction(
    asset_id: int,
    operation: str,
    date: str,
    quantity: float,
    unit_price: float,
    fees: float = 0.0,
    manual: bool = True,
) -> int:
    if quantity <= 0 or unit_price < 0 or fees < 0:
        raise ValueError("Quantidade deve ser positiva; preço e custos não podem ser negativos.")
    operation = operation.strip().title()
    if operation not in {"Compra", "Venda", "Aporte", "Retirada"}:
        raise ValueError("Operação não reconhecida.")
    return execute(
        """INSERT INTO Transacoes(id_ativo,tipo_operacao,data_transacao,quantidade,
           preco_unitario,taxas_custos,is_manual_entry) VALUES(?,?,?,?,?,?,?)""",
        (asset_id, operation, date, float(quantity), float(unit_price), float(fees), int(manual)),
    )


def upsert_quote(
    asset_id: int,
    quote_date: str,
    price: float,
    source: str,
    manual: bool = False,
) -> None:
    if price <= 0:
        raise ValueError("A cotação deve ser maior que zero.")
    execute(
        """INSERT INTO Cotacoes_Historico(id_ativo,data_cotacao,preco_fechamento,
           fonte_dados,is_manual_entry) VALUES(?,?,?,?,?)
           ON CONFLICT(id_ativo,data_cotacao) DO UPDATE SET
           preco_fechamento=excluded.preco_fechamento,
           fonte_dados=excluded.fonte_dados,
           is_manual_entry=excluded.is_manual_entry""",
        (asset_id, quote_date, float(price), source, int(manual)),
    )


def add_dividend(
    asset_id: int,
    kind: str,
    ex_date: str,
    payment_date: str | None,
    per_unit: float,
    total: float,
    manual: bool = True,
) -> int:
    if per_unit < 0 or total < 0:
        raise ValueError("Os valores do provento não podem ser negativos.")
    duplicate = fetch_all(
        """SELECT id_provento FROM Proventos
           WHERE id_ativo=? AND tipo_provento=? AND data_com=?
             AND ABS(valor_por_acao-?) < 0.000000001""",
        (asset_id, kind, ex_date, float(per_unit)),
    )
    if duplicate:
        return int(duplicate[0]["id_provento"])
    return execute(
        """INSERT INTO Proventos(id_ativo,tipo_provento,data_com,data_pagamento,
           valor_por_acao,valor_total,is_manual_entry) VALUES(?,?,?,?,?,?,?)""",
        (asset_id, kind, ex_date, payment_date, per_unit, total, int(manual)),
    )


def quantity_as_of(asset_id: int, through_date: str) -> float:
    transactions = fetch_all(
        """SELECT tipo_operacao, quantidade FROM Transacoes
           WHERE id_ativo=? AND data_transacao<=? ORDER BY data_transacao,id_transacao""",
        (asset_id, through_date),
    )
    quantity = 0.0
    for txn in transactions:
        amount = float(txn["quantidade"])
        if txn["tipo_operacao"].title() in {"Compra", "Aporte"}:
            quantity += amount
        elif txn["tipo_operacao"].title() in {"Venda", "Retirada"}:
            quantity = max(0.0, quantity - amount)
    for action in fetch_all(
        """SELECT valor_por_acao FROM Proventos
           WHERE id_ativo=? AND tipo_provento='Split' AND data_com<=? ORDER BY data_com,id_provento""",
        (asset_id, through_date),
    ):
        quantity *= float(action["valor_por_acao"])
    return quantity


def get_setting(key: str, default: str) -> str:
    rows = fetch_all("SELECT valor FROM Configuracoes WHERE chave=?", (key,))
    return str(rows[0]["valor"]) if rows else default


def set_setting(key: str, value: str) -> None:
    execute(
        """INSERT INTO Configuracoes(chave,valor) VALUES(?,?)
           ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,
           atualizado_em=CURRENT_TIMESTAMP""",
        (key, value),
    )


def list_assets() -> list[sqlite3.Row]:
    return fetch_all("SELECT * FROM Ativos ORDER BY ticker")


def list_transactions() -> list[sqlite3.Row]:
    return fetch_all(
        """SELECT t.*, a.ticker, a.nome_ativo FROM Transacoes t
           JOIN Ativos a ON a.id_ativo=t.id_ativo
           ORDER BY t.data_transacao, t.id_transacao"""
    )


def list_quotes() -> list[sqlite3.Row]:
    return fetch_all(
        """SELECT q.*, a.ticker FROM Cotacoes_Historico q
           JOIN Ativos a ON a.id_ativo=q.id_ativo ORDER BY q.data_cotacao"""
    )


def latest_quotes() -> dict[int, sqlite3.Row]:
    rows = fetch_all(
        """SELECT q.*, a.ticker FROM Cotacoes_Historico q
           JOIN Ativos a ON a.id_ativo=q.id_ativo
           JOIN (SELECT id_ativo, MAX(data_cotacao) AS d FROM Cotacoes_Historico GROUP BY id_ativo) m
           ON m.id_ativo=q.id_ativo AND m.d=q.data_cotacao"""
    )
    return {int(row["id_ativo"]): row for row in rows}


def list_dividends() -> list[sqlite3.Row]:
    return fetch_all(
        """SELECT p.*, a.ticker FROM Proventos p JOIN Ativos a ON a.id_ativo=p.id_ativo
           ORDER BY p.data_com DESC"""
    )


def restore_database(uploaded_bytes: bytes) -> None:
    """Replace the local database only when the uploaded SQLite file is valid."""
    import os
    import tempfile

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = DATA_DIR / "restore-validation.db"
    temp_path.write_bytes(uploaded_bytes)
    try:
        with sqlite3.connect(temp_path) as candidate:
            result = candidate.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("O arquivo não passou na validação de integridade do SQLite.")
            required = {"Ativos", "Transacoes", "Cotacoes_Historico", "Proventos"}
            tables = {
                row[0] for row in candidate.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not required.issubset(tables):
                raise ValueError("O arquivo não possui as tabelas esperadas desta plataforma.")
        create_startup_backup()
        os.replace(temp_path, DB_PATH)
        init_db()
    finally:
        temp_path.unlink(missing_ok=True)
