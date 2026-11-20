"""/docs (Swagger UI) · /openapi.json · /openapi.yaml · /health"""
from pathlib import Path

import yaml
from flask import Blueprint, Response, jsonify, redirect

from ..db import get_conn

bp = Blueprint("docs", __name__)

SPEC_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "openapi.yaml"

SWAGGER_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>AfterKey API - Swagger UI</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      persistAuthorization: true,
      tryItOutEnabled: true
    });
  </script>
</body>
</html>"""


@bp.get("/")
def index():
    return redirect("/docs")


@bp.get("/docs")
def swagger_ui():
    return Response(SWAGGER_HTML, mimetype="text/html")


@bp.get("/openapi.yaml")
def openapi_yaml():
    return Response(SPEC_PATH.read_text(encoding="utf-8"), mimetype="application/yaml")


@bp.get("/openapi.json")
def openapi_json():
    return jsonify(yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8")))


@bp.get("/health")
def health():
    """Comprueba que la API responde y que la base de datos es alcanzable."""
    get_conn().one("SELECT 1 AS ok")
    return jsonify({"estado": "ok", "base_de_datos": "ok"})
