"""CRUD de /instructions  (RF-04)  -  qué hacer con cada activo tras el fallecimiento."""
from flask import Blueprint, g, jsonify, request

from ..db import get_conn
from ..errors import ApiError
from ..security import login_required
from ..utils import json_body, page, page_args, update_row, validate

bp = Blueprint("instructions", __name__, url_prefix="/instructions")

ACCIONES = ["Eliminar", "Transferir", "Conservar"]
CREATE_SPEC = {
    "id_activo": {"type": "int", "required": True, "min": 1},
    "id_beneficiario": {"type": "int", "min": 1, "nullable": True},
    "accion": {"required": True, "enum": ACCIONES},
    "detalle": {"max": 2000, "nullable": True},
}
# El activo de una instrucción no se puede cambiar: cree una instrucción nueva.
UPDATE_SPEC = {k: v for k, v in CREATE_SPEC.items() if k != "id_activo"}

SELECT = """
    SELECT i.id_instruccion, i.id_activo, a.nombre_activo, e.nombre_entidad AS establecimiento,
           i.id_beneficiario, b.nombre_completo AS beneficiario, i.accion, i.detalle, i.fecha_creacion
      FROM instrucciones i
      JOIN activos_digitales a          ON a.id_activo = i.id_activo
      JOIN establecimientos_afiliados e ON e.id_establecimiento = a.id_establecimiento
      LEFT JOIN beneficiarios b         ON b.id_beneficiario = i.id_beneficiario
"""


def _get_owned(db, instr_id):
    row = db.one(SELECT + " WHERE i.id_instruccion = %s AND a.id_usuario = %s", (instr_id, g.user["id_usuario"]))
    if row is None:
        raise ApiError(404, "no_encontrado", "Instrucción no encontrada.")
    return row


def _check_owned_refs(db, id_activo=None, id_beneficiario=None):
    """El activo y el responsable deben pertenecer al usuario autenticado."""
    uid = g.user["id_usuario"]
    if id_activo is not None and not db.one(
        "SELECT 1 AS x FROM activos_digitales WHERE id_activo = %s AND id_usuario = %s", (id_activo, uid)
    ):
        raise ApiError(
            422, "activo_invalido", "El activo no existe o no es suyo.",
            [{"campo": "id_activo", "mensaje": "no existe o no le pertenece"}],
        )
    if id_beneficiario is not None and not db.one(
        "SELECT 1 AS x FROM beneficiarios WHERE id_beneficiario = %s AND id_usuario_propietario = %s",
        (id_beneficiario, uid),
    ):
        raise ApiError(
            422, "responsable_invalido", "El responsable no existe o no es suyo.",
            [{"campo": "id_beneficiario", "mensaje": "no existe o no le pertenece"}],
        )


def _check_transfer_rule(accion, id_beneficiario):
    if accion == "Transferir" and id_beneficiario is None:
        raise ApiError(
            422, "responsable_requerido", "Para 'Transferir' debe indicar un responsable.",
            [{"campo": "id_beneficiario", "mensaje": "obligatorio cuando accion = Transferir"}],
        )


def _check_duplicate(db, id_activo, id_beneficiario, exclude_id=None):
    if id_beneficiario is None:
        return
    sql = "SELECT 1 AS x FROM instrucciones WHERE id_activo = %s AND id_beneficiario = %s"
    params = [id_activo, id_beneficiario]
    if exclude_id:
        sql += " AND id_instruccion <> %s"
        params.append(exclude_id)
    if db.one(sql, params):
        raise ApiError(409, "instruccion_duplicada", "Ese responsable ya tiene una instrucción sobre este activo.")


@bp.get("")
@login_required
def list_instructions():
    limit, offset = page_args()
    where, params = ["a.id_usuario = %s"], [g.user["id_usuario"]]
    if act := request.args.get("id_activo"):
        if not act.isdigit():
            raise ApiError(422, "filtro_invalido", "'id_activo' debe ser entero.")
        where.append("i.id_activo = %s")
        params.append(int(act))
    if accion := request.args.get("accion"):
        where.append("i.accion = %s")
        params.append(accion)
    clause = " AND ".join(where)

    db = get_conn()
    total = db.one(
        "SELECT COUNT(*) AS n FROM instrucciones i JOIN activos_digitales a ON a.id_activo = i.id_activo "
        f"WHERE {clause}",
        params,
    )["n"]
    items = db.all(f"{SELECT} WHERE {clause} ORDER BY i.id_instruccion LIMIT %s OFFSET %s", [*params, limit, offset])
    return jsonify(page(items, total, limit, offset))


@bp.get("/<int:instr_id>")
@login_required
def get_instruction(instr_id):
    return jsonify(_get_owned(get_conn(), instr_id))


@bp.post("")
@login_required
def create_instruction():
    data = validate(json_body(), CREATE_SPEC)
    db = get_conn()
    ben = data.get("id_beneficiario")
    _check_owned_refs(db, data["id_activo"], ben)
    _check_transfer_rule(data["accion"], ben)
    _check_duplicate(db, data["id_activo"], ben)
    new = db.one(
        "INSERT INTO instrucciones (id_activo, id_beneficiario, accion, detalle) "
        "VALUES (%s, %s, %s, %s) RETURNING id_instruccion",
        (data["id_activo"], ben, data["accion"], data.get("detalle")),
    )
    return jsonify(_get_owned(db, new["id_instruccion"])), 201


@bp.put("/<int:instr_id>")
@login_required
def update_instruction(instr_id):
    data = validate(json_body(), UPDATE_SPEC, partial=True)
    db = get_conn()
    current = _get_owned(db, instr_id)

    accion = data.get("accion", current["accion"])
    ben = data["id_beneficiario"] if "id_beneficiario" in data else current["id_beneficiario"]
    _check_owned_refs(db, None, data.get("id_beneficiario"))
    _check_transfer_rule(accion, ben)
    _check_duplicate(db, current["id_activo"], ben, exclude_id=instr_id)

    update_row(db, "instrucciones", "id_instruccion", instr_id, data)
    return jsonify(_get_owned(db, instr_id))


@bp.delete("/<int:instr_id>")
@login_required
def delete_instruction(instr_id):
    db = get_conn()
    _get_owned(db, instr_id)
    db.execute("DELETE FROM instrucciones WHERE id_instruccion = %s", (instr_id,))
    return "", 204
