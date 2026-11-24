"""AfterKey API - fábrica de la aplicación."""
import logging
from urllib.parse import urlsplit

import click
from flask import Flask, request

from . import db as database
from .config import load_config
from .errors import register_error_handlers
from .mailer import Mailer
from .utils import JSONProvider


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.update(load_config(overrides))
    app.json = JSONProvider(app)
    app.json.compact = False
    logging.basicConfig(level=logging.INFO)

    @app.after_request
    def allow_local_development_origins(response):
        origin = request.headers.get("Origin")
        if origin and app.config["APP_ENV"] != "production":
            try:
                parsed_origin = urlsplit(origin)
            except ValueError:
                parsed_origin = None
            if (
                parsed_origin
                and parsed_origin.scheme == "http"
                and parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}
                and not parsed_origin.username
                and not parsed_origin.password
                and parsed_origin.path in ("", "/")
                and not parsed_origin.query
                and not parsed_origin.fragment
            ):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = (
                    "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                )
                response.headers["Access-Control-Allow-Headers"] = (
                    "Authorization, Content-Type"
                )
                response.vary.add("Origin")
        return response

    database.init_app(app)
    app.extensions["mailer"] = Mailer(app)
    register_error_handlers(app)

    from .routes import (
        accounts, auth, beneficiaries, death, docs,
        establishments, instructions, notifications, users,
    )

    for module in (
        auth, users, accounts, beneficiaries, instructions,
        establishments, death, notifications, docs,
    ):
        app.register_blueprint(module.bp)

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("init-db")
    @click.option("--seed", is_flag=True, help="Cargar también el catálogo de establecimientos.")
    def init_db(seed):
        """Crea las tablas ejecutando database/schema.sql."""
        database.run_sql_file(app, "schema.sql")
        click.echo("Tablas creadas.")
        if seed:
            database.run_sql_file(app, "seed.sql")
            click.echo("Catálogo de establecimientos cargado.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--nombre", prompt="Nombre completo")
    @click.password_option()
    def create_admin(email, nombre, password):
        """Crea un usuario administrador (para validar defunciones y gestionar el catálogo)."""
        from .security import hash_password

        conn = database.Connection(app.extensions["db"])
        try:
            conn.execute(
                "INSERT INTO usuarios (nombre_completo, email, password_hash, rol) VALUES (%s, %s, %s, 'admin')",
                (nombre, email.strip().lower(), hash_password(password)),
            )
            conn.commit()
        finally:
            conn.close()
        click.echo(f"Administrador {email} creado.")
