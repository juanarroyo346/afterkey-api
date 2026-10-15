"""POST /notifications/send · GET /notifications   (RF-06)
   GET /reports/history · GET /reports/history.pdf  (RF-07)

Estos endpoints los pueden usar el titular, un administrador (?id_usuario=) o un
responsable (cabeceras X-Beneficiary-Email / X-Access-Code).
"""
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, jsonify, request, send_file

from ..db import get_conn
from ..errors import ApiError
from ..security import get_actor
from ..services import dispatch_notifications
from ..utils import now_iso, page, page_args

bp = Blueprint("notifications", __name__)

LOG_SELECT = """
    SELECT l.id_log, l.id_instruccion, l.fecha_ejecucion, l.estado, l.destinatario,
           l.resultado_peticion, e.nombre_entidad AS establecimiento,
           a.nombre_activo, i.accion
      FROM logs_ejecucion l
      JOIN instrucciones i              ON i.id_instruccion = l.id_instruccion
      JOIN activos_digitales a          ON a.id_activo = i.id_activo
      JOIN establecimientos_afiliados e ON e.id_establecimiento = a.id_establecimiento
"""


@bp.post("/notifications/send")
def send_notifications():
    """Genera y envía (o reintenta) las solicitudes a las empresas. Exige fallecimiento 'Aprobada'."""
    actor = get_actor()
    summary = dispatch_notifications(actor["id_usuario"])
    return jsonify(summary)


@bp.get("/notifications")
def list_notifications():
    actor = get_actor()
    limit, offset = page_args()
    where, params = ["a.id_usuario = %s"], [actor["id_usuario"]]
    if estado := request.args.get("estado"):
        where.append("l.estado = %s")
        params.append(estado)
    clause = " AND ".join(where)

    db = get_conn()
    total = db.one(
        "SELECT COUNT(*) AS n FROM logs_ejecucion l "
        "JOIN instrucciones i ON i.id_instruccion = l.id_instruccion "
        f"JOIN activos_digitales a ON a.id_activo = i.id_activo WHERE {clause}",
        params,
    )["n"]
    items = db.all(
        f"{LOG_SELECT} WHERE {clause} ORDER BY l.id_log DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return jsonify(page(items, total, limit, offset))


# ------------------------------------------------------------------- reportes
def _history(id_usuario):
    db = get_conn()
    owner = db.one("SELECT id_usuario, nombre_completo, email, estado FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    if owner is None:
        raise ApiError(404, "no_encontrado", "Usuario inexistente.")
    ver = db.one("SELECT * FROM verificacion_defuncion WHERE id_usuario = %s", (id_usuario,))
    logs = db.all(
        f"{LOG_SELECT} WHERE a.id_usuario = %s ORDER BY l.id_log", (id_usuario,)
    )
    return {"generado_en": now_iso(), "titular": owner, "verificacion": ver, "registros": logs}


@bp.get("/reports/history")
def history_json():
    return jsonify(_history(get_actor()["id_usuario"]))


@bp.get("/reports/history.pdf")
def history_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    h = _history(get_actor()["id_usuario"])
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    def p(text):
        return Paragraph(escape(str(text if text is not None else "-")), small)

    ver = h["verificacion"]
    story = [
        Paragraph("AfterKey - Historial de acciones y evidencias", styles["Title"]),
        Paragraph(
            escape(f"Titular: {h['titular']['nombre_completo']} ({h['titular']['email']}) - "
                   f"estado: {h['titular']['estado']}"),
            styles["BodyText"],
        ),
        Paragraph(escape(f"Generado: {h['generado_en']}"), styles["BodyText"]),
        Paragraph(
            escape(
                "Verificación de fallecimiento: "
                + (f"{ver['estado_validacion']} (reportada {ver['fecha_reporte']}, "
                   f"certificado: {ver['certificado_ref']})" if ver else "sin notificar")
            ),
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]

    rows = [[p(x) for x in ("Fecha", "Empresa", "Activo", "Acción", "Estado", "Destinatario", "Resultado")]]
    for r in h["registros"]:
        rows.append([p(r[k]) for k in (
            "fecha_ejecucion", "establecimiento", "nombre_activo", "accion",
            "estado", "destinatario", "resultado_peticion")])
    if len(rows) == 1:
        rows.append([p("Sin registros"), "", "", "", "", "", ""])

    table = Table(rows, repeatRows=1, colWidths=[85, 85, 90, 55, 50, 120, 270])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8ECF4")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)

    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=landscape(A4), title="Historial AfterKey").build(story)
    buffer.seek(0)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"historial_afterkey_{h['titular']['id_usuario']}.pdf",
    )
