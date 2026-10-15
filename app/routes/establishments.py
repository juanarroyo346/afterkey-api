"""CRUD de /establishments (tabla maestra).

Lectura: cualquier usuario autenticado. Escritura: solo administradores.
"""
from flask import Blueprint, jsonify, request

from ..db import get_conn
from ..errors import ApiError
from ..security import admin_required, login_required
from ..utils import json_body, page, page_args, update_row, validate

bp = Blueprint("establishments", __name__, url_prefix="/establishments")

SECTORS = ["Banca", "RRSS", "Cloud", "Streaming", "Seguros", "Otro"]
SPEC = {
    "nombre_entidad": {"required": True, "max": 150},
    "email_soporte_legal": {"required": True, "email": True, "max": 254},
    "sector": {"required": True, "enum": SECTORS},
}


def _get_or_404(db, est_id):
    row = db.one("SELECT * FROM establecimientos_afiliados WHERE id_establecimiento = %s", (est_id,))
    if row is None:
        raise ApiError(404, "no_encontrado", "Establecimiento no encontrado.")
    return row


@bp.get("")
@login_required
def list_establishments():
    limit, offset = page_args()
    where, params = ["1 = 1"], []
    if sector := request.args.get("sector"):
        where.append("sector = %s")
        params.append(sector)
    if q := request.args.get("q"):
        where.append("LOWER(nombre_entidad) LIKE %s")
        params.append(f"%{q.strip().lower()}%")
    clause = " AND ".join(where)

    db = get_conn()
    total = db.one(f"SELECT COUNT(*) AS n FROM establecimientos_afiliados WHERE {clause}", params)["n"]
    items = db.all(
        f"SELECT * FROM establecimientos_afiliados WHERE {clause} "
        "ORDER BY nombre_entidad LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return jsonify(page(items, total, limit, offset))


@bp.get("/<int:est_id>")
@login_required
def get_establishment(est_id):
    return jsonify(_get_or_404(get_conn(), est_id))


@bp.post("")
@admin_required
def create_establishment():
    data = validate(json_body(), SPEC)
    db = get_conn()
    if db.one("SELECT 1 AS x FROM establecimientos_afiliados WHERE nombre_entidad = %s", (data["nombre_entidad"],)):
        raise ApiError(409, "nombre_duplicado", "Ya existe un establecimiento con ese nombre.")
    row = db.one(
        "INSERT INTO establecimientos_afiliados (nombre_entidad, email_soporte_legal, sector) "
        "VALUES (%s, %s, %s) RETURNING *",
        (data["nombre_entidad"], data["email_soporte_legal"], data["sector"]),
    )
    return jsonify(row), 201


@bp.put("/<int:est_id>")
@admin_required
def update_establishment(est_id):
    data = validate(json_body(), SPEC, partial=True)
    db = get_conn()
    _get_or_404(db, est_id)
    if "nombre_entidad" in data and db.one(
        "SELECT 1 AS x FROM establecimientos_afiliados WHERE nombre_entidad = %s AND id_establecimiento <> %s",
        (data["nombre_entidad"], est_id),
    ):
        raise ApiError(409, "nombre_duplicado", "Ya existe un establecimiento con ese nombre.")
    update_row(db, "establecimientos_afiliados", "id_establecimiento", est_id, data)
    return jsonify(_get_or_404(db, est_id))


@bp.delete("/<int:est_id>")
@admin_required
def delete_establishment(est_id):
    db = get_conn()
    _get_or_404(db, est_id)
    en_uso = db.one(
        "SELECT COUNT(*) AS n FROM activos_digitales WHERE id_establecimiento = %s", (est_id,)
    )["n"]
    if en_uso:
        raise ApiError(
            409, "establecimiento_en_uso", f"No se puede eliminar: {en_uso} activo(s) lo utilizan."
        )
    db.execute("DELETE FROM establecimientos_afiliados WHERE id_establecimiento = %s", (est_id,))
    return "", 204
