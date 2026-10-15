"""Proceso de fallecimiento  (RF-05).

Flujo:
 1. Un responsable (X-Beneficiary-Email + X-Access-Code) reporta el fallecimiento
    con la referencia del certificado  ->  POST /death-notification   (queda "Pendiente")
 2. Un administrador valida la autenticidad del documento
                                         ->  PUT /death-notification/{id}/validate
 3. Si se "Aprobada": el titular pasa a 'fallecido' y se envían automáticamente
    las notificaciones a las empresas (RF-06).
"""
from flask import Blueprint, g, jsonify, request

from ..db import get_conn
from ..errors import ApiError
from ..security import admin_required, beneficiary_from_headers, get_actor
from ..services import dispatch_notifications
from ..utils import json_body, now_iso, page, page_args, update_row, validate

bp = Blueprint("death", __name__, url_prefix="/death-notification")

REPORT_SPEC = {
    "certificado_ref": {"required": True, "max": 255},
    "observaciones": {"max": 2000, "nullable": True},
}
VALIDATE_SPEC = {
    "estado_validacion": {"required": True, "enum": ["Aprobada", "Rechazada"]},
    "observaciones": {"max": 2000, "nullable": True},
}


@bp.post("")
def report_death():
    ben = beneficiary_from_headers()
    data = validate(json_body(), REPORT_SPEC)
    db = get_conn()

    owner = db.one("SELECT * FROM usuarios WHERE id_usuario = %s", (ben["id_usuario_propietario"],))
    if owner["estado"] == "fallecido":
        raise ApiError(409, "ya_fallecido", "El fallecimiento de este titular ya fue verificado.")

    existing = db.one("SELECT * FROM verificacion_defuncion WHERE id_usuario = %s", (owner["id_usuario"],))
    if existing and existing["estado_validacion"] != "Rechazada":
        raise ApiError(
            409, "proceso_en_curso",
            f"Ya existe una notificación de fallecimiento en estado '{existing['estado_validacion']}'.",
        )

    if existing:  # reintento tras un rechazo: la relación es 1:1, se reabre el mismo registro
        update_row(
            db, "verificacion_defuncion", "id_verificacion", existing["id_verificacion"],
            {
                "id_beneficiario_reportante": ben["id_beneficiario"],
                "certificado_ref": data["certificado_ref"],
                "observaciones": data.get("observaciones"),
                "estado_validacion": "Pendiente",
                "fecha_reporte": now_iso(),
                "fecha_validacion": None,
                "validado_por": None,
            },
        )
        ver_id = existing["id_verificacion"]
    else:
        ver_id = db.one(
            "INSERT INTO verificacion_defuncion (id_usuario, id_beneficiario_reportante, "
            "certificado_ref, observaciones) VALUES (%s, %s, %s, %s) RETURNING id_verificacion",
            (owner["id_usuario"], ben["id_beneficiario"], data["certificado_ref"], data.get("observaciones")),
        )["id_verificacion"]

    ver = db.one("SELECT * FROM verificacion_defuncion WHERE id_verificacion = %s", (ver_id,))
    return jsonify(ver), 201


@bp.get("/status")
def death_status():
    actor = get_actor()
    db = get_conn()
    uid = actor["id_usuario"]

    owner = db.one("SELECT id_usuario, nombre_completo, estado FROM usuarios WHERE id_usuario = %s", (uid,))
    if owner is None:
        raise ApiError(404, "no_encontrado", "Usuario inexistente.")
    ver = db.one("SELECT * FROM verificacion_defuncion WHERE id_usuario = %s", (uid,))
    counts = {"Pendiente": 0, "Enviado": 0, "Fallido": 0}
    for row in db.all(
        "SELECT l.estado, COUNT(*) AS n FROM logs_ejecucion l "
        "JOIN instrucciones i ON i.id_instruccion = l.id_instruccion "
        "JOIN activos_digitales a ON a.id_activo = i.id_activo "
        "WHERE a.id_usuario = %s GROUP BY l.estado",
        (uid,),
    ):
        counts[row["estado"]] = row["n"]

    return jsonify(
        {
            "id_usuario": owner["id_usuario"],
            "titular": owner["nombre_completo"],
            "estado_titular": owner["estado"],
            "estado_proceso": ver["estado_validacion"] if ver else "Sin notificar",
            "verificacion": ver,
            "notificaciones": counts,
        }
    )


@bp.get("")
@admin_required
def list_verifications():
    limit, offset = page_args()
    where, params = ["1 = 1"], []
    if estado := request.args.get("estado"):
        where.append("v.estado_validacion = %s")
        params.append(estado)
    clause = " AND ".join(where)
    db = get_conn()
    total = db.one(f"SELECT COUNT(*) AS n FROM verificacion_defuncion v WHERE {clause}", params)["n"]
    items = db.all(
        "SELECT v.*, u.nombre_completo AS titular, u.email AS email_titular "
        f"FROM verificacion_defuncion v JOIN usuarios u ON u.id_usuario = v.id_usuario "
        f"WHERE {clause} ORDER BY v.fecha_reporte DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return jsonify(page(items, total, limit, offset))


@bp.put("/<int:ver_id>/validate")
@admin_required
def validate_death(ver_id):
    data = validate(json_body(), VALIDATE_SPEC)
    db = get_conn()
    ver = db.one("SELECT * FROM verificacion_defuncion WHERE id_verificacion = %s", (ver_id,))
    if ver is None:
        raise ApiError(404, "no_encontrado", "Verificación no encontrada.")
    if ver["estado_validacion"] != "Pendiente":
        raise ApiError(409, "ya_resuelta", f"La verificación ya está '{ver['estado_validacion']}'.")

    fields = {
        "estado_validacion": data["estado_validacion"],
        "fecha_validacion": now_iso(),
        "validado_por": g.user["id_usuario"],
    }
    if "observaciones" in data:
        fields["observaciones"] = data["observaciones"]
    update_row(db, "verificacion_defuncion", "id_verificacion", ver_id, fields)

    resumen = None
    if data["estado_validacion"] == "Aprobada":
        update_row(db, "usuarios", "id_usuario", ver["id_usuario"], {"estado": "fallecido"})
        resumen = dispatch_notifications(ver["id_usuario"])  # RF-05: activación automática

    body = db.one("SELECT * FROM verificacion_defuncion WHERE id_verificacion = %s", (ver_id,))
    return jsonify({"verificacion": body, "notificaciones": resumen})
