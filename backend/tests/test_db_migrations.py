from sqlalchemy import create_engine, inspect, text

from app import db


def test_existing_transactions_receive_nullable_cost_delta_without_losing_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                operation VARCHAR(32) NOT NULL,
                trade_date DATE NOT NULL,
                amount NUMERIC(18, 4),
                units NUMERIC(18, 6),
                price NUMERIC(18, 6),
                fee NUMERIC(18, 4),
                reason TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        connection.execute(text("""
            INSERT INTO transactions (id, asset_id, operation, trade_date, amount, units, fee)
            VALUES (1, 1, 'buy', '2026-01-02', 80, 100, 0)
        """))
    monkeypatch.setattr(db, "engine", engine)
    try:
        db.init_db()
        db.init_db()
        assert "holding_cost_delta" in {column["name"] for column in inspect(engine).get_columns("transactions")}
        assert {"paper_assets", "paper_trades", "paper_price_snapshots"}.issubset(
            set(inspect(engine).get_table_names())
        )
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id, amount, units, holding_cost_delta FROM transactions")).one() == (1, 80, 100, None)
    finally:
        engine.dispose()


def test_existing_paper_trades_receive_nullable_idempotency_key_without_losing_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy-paper.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE paper_trades (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                operation VARCHAR(8) NOT NULL,
                trade_date DATE NOT NULL,
                amount NUMERIC(18, 4) NOT NULL,
                units NUMERIC(18, 6) NOT NULL,
                price NUMERIC(18, 6) NOT NULL,
                fee NUMERIC(18, 4) NOT NULL,
                reason TEXT,
                retracted_at DATETIME,
                retraction_reason TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        connection.execute(text("""
            INSERT INTO paper_trades (id, asset_id, operation, trade_date, amount, units, price, fee)
            VALUES (1, 1, 'buy', '2026-10-14', 100.1, 100, 1, 0.1)
        """))
    monkeypatch.setattr(db, "engine", engine)
    try:
        db.init_db()
        db.init_db()
        columns = {column["name"] for column in inspect(engine).get_columns("paper_trades")}
        assert "idempotency_key" in columns
        indexes = {index["name"] for index in inspect(engine).get_indexes("paper_trades")}
        assert "uq_paper_trades_idempotency_key" in indexes
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id, amount, idempotency_key FROM paper_trades")).one() == (1, 100.1, None)
    finally:
        engine.dispose()
