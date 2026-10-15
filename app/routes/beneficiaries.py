"""CRUD de /beneficiaries  (RF-03)  -  responsables digitales del usuario.

Al crear un responsable (o regenerar su código) la API devuelve el
``codigo_acceso`` UNA sola vez; en base de datos solo queda su hash. El titular
debe entregárselo al responsable: con ese código y su correo podrá iniciar el
proceso de fallecimiento (ver /death-notification).
"""
from flask import Blueprint, g, jsonify

from ..db import get_conn
from ..errors import ApiError
from ..security import hash_access_code, login_required, new_access_code
from ..utils import json_body, page, page_args, update_row, validate

bp = Blueprint("beneficiaries", __name__, url_prefix="/beneficiaries")

SPEC = {
    "nombre_completo": {"required": True, "max": 150},
    "email_contacto": {"required": True, "email": True, "max": 254},
    "telefono": {"max": 30, "nullable": True},
    "parentesco": {"max": 50, "nullable": True},
}
COLUMNS = (
    "id_beneficiario, id_usuario_propietario, nombre_completo, email_contacto, "
    "telefono, parentesco, fecha_creacion"
)


def _get_owned(db, ben_id):
    row = db.one(
        f"SELECT {COLUMNS} FROM beneficiarios WHERE id_beneficiario = %s AND id_usuario_propietario = %s",
        (ben_id, g.user["id_usuario"]),
    )
    if row is None:
        raise ApiError(404, "no_encontrado", "Responsable no encontrado.")
    return row


def _email_taken(db, email, exclude_id=None):
    sql = "SELECT 1 AS x FROM beneficiarios WHERE id_usuario_propietario = %s AND email_contacto = %s"
    params = [g.user["id_usuario"], email]
    if exclude_id:
        sql += " AND id_beneficiario <> %s"
        params.append(exclude_id)
    return db.one(sql, params) is not None


@bp.get("")
@login_required
def list_beneficiaries():
    limit, offset = page_args()
    db = get_conn()
    uid = g.user["id_usuario"]
    total = db.one("SELECT COUNT(*) AS n FROM beneficiarios WHERE id_usuario_propietario = %s", (uid,))["n"]
    items = db.all(
        f"SELECT {COLUMNS} FROM beneficiarios WHERE id_usuario_propietario = %s "
        "ORDER BY id_beneficiario LIMIT %s OFFSET %s",
        (uid, limit, offset),
    )
    return jsonify(page(items, total, limit, offset))


@bp.get("/<int:ben_id>")
@login_required
def get_beneficiary(ben_id):
    return jsonify(_get_owned(get_conn(), ben_id))


@bp.post("")
@login_required
def create_beneficiary():
    data = validate(json_body(), SPEC)
    db = get_conn()
    if _email_taken(db, data["email_contacto"]):
        raise ApiError(409, "responsable_duplicado", "Ya registró un responsable con ese correo.")

    code = new_access_code()
    new = db.one(
        "INSERT INTO beneficiarios (id_usuario_propietario, nombre_completo, email_contacto, "
        "telefono, parentesco, codigo_acceso_hash) VALUES (%s, %s, %s, %s, %s, %s) "
        "RETURNING id_beneficiario",
        (
            g.user["id_usuario"],
            data["nombre_completo"],
            data["email_contacto"],
            data.get("telefono"),
            data.get("parentesco"),
            hash_access_code(code),
        ),
    )
    body = _get_owned(db, new["id_beneficiario"])
    body["codigo_acceso"] = code  # se muestra una única vez
    return jsonify(body), 201


@bp.put("/<int:ben_id>")
@login_required
def update_beneficiary(ben_id):
    data = validate(json_body(), SPEC, partial=True)
    db = get_conn()
    _get_owned(db, ben_id)
    if "email_contacto" in data and _email_taken(db, data["email_contacto"], ben_id):
        raise ApiError(409, "responsable_duplicado", "Ya registró un responsable con ese correo.")
    update_row(db, "beneficiarios", "id_beneficiario", ben_id, data)
    return jsonify(_get_owned(db, ben_id))


@bp.post("/<int:ben_id>/regenerate-code")
@login_required
def regenerate_code(ben_id):
    """Genera un código nuevo e invalida el anterior (p. ej. si se filtró o se perdió)."""
    db = get_conn()
    _get_owned(db, ben_id)
    code = new_access_code()
    update_row(db, "beneficiarios", "id_beneficiario", ben_id, {"codigo_acceso_hash": hash_access_code(code)})
    body = _get_owned(db, ben_id)
    body["codigo_acceso"] = code
    return jsonify(body)


@bp.delete("/<int:ben_id>")
@login_required
def delete_beneficiary(ben_id):
    db = get_conn()
    _get_owned(db, ben_id)
    en_uso = db.one("SELECT COUNT(*) AS n FROM instrucciones WHERE id_beneficiario = %s", (ben_id,))["n"]
    if en_uso:
        raise ApiError(
            409,
            "responsable_en_uso",
            f"No se puede eliminar: {en_uso} instrucción(es) lo usan. Reasígnelas o elimínelas primero.",
        )
    db.execute("DELETE FROM beneficiarios WHERE id_beneficiario = %s", (ben_id,))
    return "", 204
