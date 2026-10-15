"""Formato de error uniforme:  {"error": {"codigo": ..., "mensaje": ..., "detalles": ...}}"""
from flask import jsonify
from werkzeug.exceptions import HTTPException

from .db import IntegrityError


class ApiError(Exception):
    def __init__(self, status, codigo, mensaje, detalles=None):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles


def _response(status, codigo, mensaje, detalles=None):
    body = {"error": {"codigo": codigo, "mensaje": mensaje}}
    if detalles:
        body["error"]["detalles"] = detalles
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return _response(e.status, e.codigo, e.mensaje, e.detalles)

    def handle_integrity(e):
        # Red de seguridad ante condiciones de carrera (duplicados / registros en uso).
        app.logger.warning("Violación de integridad: %s", e)
        return _response(
            409,
            "conflicto_integridad",
            "La operación viola una restricción de integridad "
            "(registro duplicado o en uso por otros datos).",
        )

    for exc_class in IntegrityError:  # una clase por driver (sqlite3 / psycopg2)
        app.register_error_handler(exc_class, handle_integrity)

    @app.errorhandler(HTTPException)
    def handle_http(e):
        codes = {
            400: "solicitud_invalida",
            404: "no_encontrado",
            405: "metodo_no_permitido",
            415: "tipo_no_soportado",
        }
        return _response(e.code, codes.get(e.code, "error_http"), e.description)

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        app.logger.exception("Error no controlado")
        return _response(500, "error_interno", "Error interno del servidor.")
