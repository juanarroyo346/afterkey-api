"""CRUD de /accounts  (RF-02)  -  activos digitales del usuario autenticado.

Cada consulta filtra por ``id_usuario`` del token: un usuario nunca ve ni toca
los activos de otro (se responde 404, no 403, para no revelar que existen).
"""
from flask import Blueprint, g, jsonify, request

from ..db import get_conn
from ..errors import ApiError
from ..security import encrypt_secret, login_required
from ..utils import json_body, page, page_args, update_row, validate

bp = Blueprint("accounts", __name__, url_prefix="/accounts")

TIPOS = ["Cuenta", "Archivo", "Servicio"]
SPEC = {
    "id_establecimiento": {"type": "int", "required": True, "min": 1},
    "tipo": {"required": True, "enum": TIPOS},
    "nombre_activo": {"required": True, "max": 150},
    "notas": {"max": 2000, "nullable": True},
    # Solo escritura: se cifra antes de guardar y jamás se devuelve.
    "credenciales": {"max": 2000, "nullable": True, "raw": True},
}

SELECT = """
    SELECT a.id_activo, a.id_usuario, a.id_establecimiento,
           e.nombre_entidad AS establecimiento, a.tipo, a.nombre_activo, a.notas,
           (a.credenciales_cifradas IS NOT NULL) AS tiene_credenciales,
           a.fecha_creacion, a.fecha_actualizacion
      FROM activos_digitales a
      JOIN establecimientos_afiliados e ON e.id_establecimiento = a.id_establecimiento
"""


def _present(row):
    row["tiene_credenciales"] = bool(row["tiene_credenciales"])
    return row


def _get_owned(db, account_id):
    row = db.one(SELECT + " WHERE a.id_activo = %s AND a.id_usuario = %s", (account_id, g.user["id_usuario"]))
    if row is None:
        raise ApiError(404, "no_encontrado", "Cuenta no encontrada.")
    return _present(row)


def _ensure_establishment(db, est_id):
    if not db.one("SELECT 1 AS x FROM establecimientos_afiliados WHERE id_establecimiento = %s", (est_id,)):
        raise ApiError(
            422,
            "establecimiento_inexistente",
            "El establecimiento indicado no existe en el catálogo.",
            [{"campo": "id_establecimiento", "mensaje": "no existe"}],
        )


@bp.get("")
@login_required
def list_accounts():
    limit, offset = page_args()
    where, params = ["a.id_usuario = %s"], [g.user["id_usuario"]]
    if tipo := request.args.get("tipo"):
        where.append("a.tipo = %s")
        params.append(tipo)
    if est := request.args.get("id_establecimiento"):
        if not est.isdigit():
            raise ApiError(422, "filtro_invalido", "'id_establecimiento' debe ser entero.")
        where.append("a.id_establecimiento = %s")
        params.append(int(est))
    clause = " AND ".join(where)

    db = get_conn()
    total = db.one(f"SELECT COUNT(*) AS n FROM activos_digitales a WHERE {clause}", params)["n"]
    items = db.all(
        f"{SELECT} WHERE {clause} ORDER BY a.id_activo LIMIT %s OFFSET %s", [*params, limit, offset]
    )
    return jsonify(page([_present(i) for i in items], total, limit, offset))


@bp.get("/<int:account_id>")
@login_required
def get_account(account_id):
    return jsonify(_get_owned(get_conn(), account_id))


@bp.post("")
@login_required
def create_account():
    data = validate(json_body(), SPEC)
    db = get_conn()
    _ensure_establishment(db, data["id_establecimiento"])
    creds = data.get("credenciales")
    new = db.one(
        "INSERT INTO activos_digitales "
        "(id_usuario, id_establecimiento, tipo, nombre_activo, notas, credenciales_cifradas) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_activo",
        (
            g.user["id_usuario"],
            data["id_establecimiento"],
            data["tipo"],
            data["nombre_activo"],
            data.get("notas"),
            encrypt_secret(creds) if creds else None,
        ),
    )
    return jsonify(_get_owned(db, new["id_activo"])), 201


@bp.put("/<int:account_id>")
@login_required
def update_account(account_id):
    data = validate(json_body(), SPEC, partial=True)
    db = get_conn()
    _get_owned(db, account_id)
    if "id_establecimiento" in data:
        _ensure_establishment(db, data["id_establecimiento"])

    fields = {k: v for k, v in data.items() if k != "credenciales"}
    if "credenciales" in data:
        creds = data["credenciales"]
        fields["credenciales_cifradas"] = encrypt_secret(creds) if creds else None
    update_row(db, "activos_digitales", "id_activo", account_id, fields, touch_column="fecha_actualizacion")
    return jsonify(_get_owned(db, account_id))


@bp.delete("/<int:account_id>")
@login_required
def delete_account(account_id):
    """Elimina el activo y, en cascada, sus instrucciones y logs."""
    db = get_conn()
    _get_owned(db, account_id)
    db.execute("DELETE FROM activos_digitales WHERE id_activo = %s", (account_id,))
    return "", 204
