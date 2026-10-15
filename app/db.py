"""Acceso a base de datos con SQL puro y consultas parametrizadas.

* Producción / desarrollo: PostgreSQL vía psycopg2 (pool de conexiones).
* Pruebas automáticas: SQLite (DATABASE_URL=sqlite:///ruta.db), para poder
  ejecutar la suite sin levantar un servidor. El DDL oficial es PostgreSQL;
  para SQLite se traduce automáticamente (ver _to_sqlite).

Todas las consultas usan el estilo de parámetros ``%s`` y NUNCA se
concatenan valores del usuario dentro del SQL (previene inyección SQL).

Transacción por petición: se confirma (COMMIT) si la respuesta es < 400 y se
revierte (ROLLBACK) en cualquier otro caso.
"""
import re
import sqlite3
from pathlib import Path

from flask import current_app, g

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:  # pragma: no cover - solo ocurre si falta la dependencia
    psycopg2 = None

IntegrityError = (
    (sqlite3.IntegrityError, psycopg2.IntegrityError)
    if psycopg2
    else (sqlite3.IntegrityError,)
)

DATABASE_DIR = Path(__file__).resolve().parent.parent / "database"


def _to_sqlite(ddl: str) -> str:
    """Traduce el DDL de PostgreSQL a SQLite (solo para la suite de pruebas)."""
    ddl = re.sub(r"\bSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", ddl)
    ddl = ddl.replace("TIMESTAMPTZ", "TIMESTAMP").replace("NOW()", "CURRENT_TIMESTAMP")
    return ddl


class Database:
    """Fábrica de conexiones. El pool de PostgreSQL se crea de forma perezosa."""

    def __init__(self, url: str, pool_max: int = 10):
        self.url = url
        self.pool_max = pool_max
        self.is_sqlite = url.startswith("sqlite:")
        self._pool = None

    def acquire(self):
        if self.is_sqlite:
            raw = sqlite3.connect(self.url.replace("sqlite:///", "", 1))
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA foreign_keys = ON")
            return raw
        if psycopg2 is None:  # pragma: no cover
            raise RuntimeError("Falta instalar psycopg2-binary")
        if self._pool is None:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                1,
                self.pool_max,
                dsn=self.url,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
        return self._pool.getconn()

    def release(self, raw):
        if self.is_sqlite:
            raw.close()
        else:
            self._pool.putconn(raw)


class Connection:
    """Envoltorio mínimo sobre la conexión de la petición actual."""

    def __init__(self, database: Database):
        self.database = database
        self.raw = database.acquire()

    def _prepare(self, sql):
        return sql.replace("%s", "?") if self.database.is_sqlite else sql

    def _run(self, sql, params):
        cur = self.raw.cursor()
        cur.execute(self._prepare(sql), tuple(params))
        return cur

    def all(self, sql, params=()):
        cur = self._run(sql, params)
        rows = cur.fetchall() if cur.description else []
        return [dict(r) for r in rows]

    def one(self, sql, params=()):
        cur = self._run(sql, params)
        row = cur.fetchone() if cur.description else None
        return dict(row) if row else None

    def execute(self, sql, params=()):
        return self._run(sql, params).rowcount

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        try:
            self.raw.rollback()  # no-op si ya se hizo commit
        finally:
            self.database.release(self.raw)


def get_conn() -> Connection:
    if "conn" not in g:
        g.conn = Connection(current_app.extensions["db"])
    return g.conn


def init_app(app):
    app.extensions["db"] = Database(app.config["DATABASE_URL"], app.config["DB_POOL_MAX"])

    @app.after_request
    def finish_transaction(response):
        conn = g.pop("conn", None)
        if conn is not None:
            try:
                if response.status_code < 400:
                    conn.commit()
                else:
                    conn.rollback()
            finally:
                conn.close()
        return response

    @app.teardown_appcontext
    def close_on_error(exc):
        conn = g.pop("conn", None)  # solo queda si hubo una excepción sin respuesta
        if conn is not None:
            conn.close()


def run_sql_file(app, filename: str):
    """Ejecuta un script .sql de la carpeta database/ (usado por `flask init-db`)."""
    script = (DATABASE_DIR / filename).read_text(encoding="utf-8")
    database = app.extensions["db"]
    raw = database.acquire()
    try:
        if database.is_sqlite:
            raw.executescript(_to_sqlite(script))
        else:
            raw.cursor().execute(script)
        raw.commit()
    finally:
        database.release(raw)
