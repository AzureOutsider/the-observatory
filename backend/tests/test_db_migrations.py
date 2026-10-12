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
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id, amount, units, holding_cost_delta FROM transactions")).one() == (1, 80, 100, None)
    finally:
        engine.dispose()
