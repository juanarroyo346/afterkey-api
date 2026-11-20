"""Lógica de negocio del proceso post-fallecimiento (RF-05 y RF-06)."""
from flask import current_app

from .db import get_conn
from .errors import ApiError

ACCION_TEXTO = {
    "Eliminar": "ELIMINAR / CERRAR la cuenta o servicio",
    "Transferir": "TRANSFERIR la cuenta o servicio al beneficiario indicado",
    "Conservar": "CONSERVAR la cuenta o servicio sin cambios (solo registrar el fallecimiento)",
}


def _compose_company_email(owner, ver, row):
    lines = [
        f"Estimado equipo de soporte legal de {row['nombre_entidad']}:",
        "",
        "Le informamos, a través de la plataforma AfterKey, del fallecimiento del titular "
        f"{owner['nombre_completo']} ({owner['email']}).",
        "",
        f"Activo afectado : {row['nombre_activo']} (tipo: {row['tipo']})",
        f"Instrucción     : {ACCION_TEXTO[row['accion']]}",
    ]
    if row["detalle"]:
        lines.append(f"Detalle         : {row['detalle']}")
    if row["b_nombre"]:
        contacto = f"{row['b_nombre']} <{row['b_email']}>"
        if row["b_tel"]:
            contacto += f", tel. {row['b_tel']}"
        lines.append(f"Responsable     : {contacto}")
    lines += [
        f"Certificado de defunción (referencia): {ver['certificado_ref']}",
        "",
        "Esta solicitud no sustituye los procedimientos internos de su entidad ni constituye "
        "un trámite legal de sucesión. Por favor contacte al responsable indicado para "
        "continuar el proceso.",
        "",
        "AfterKey - Gestión de herencia digital",
    ]
    return "\n".join(lines)


def dispatch_notifications(id_usuario: int) -> dict:
    """Envía a cada empresa la solicitud de cada instrucción pendiente y registra la evidencia.

    * Exige una verificación de defunción *Aprobada*.
    * Es reintentable: omite instrucciones que ya tienen un log 'Enviado' y
      vuelve a intentar las que quedaron 'Fallido'.
    * NUNCA incluye credenciales en los correos.
    """
    db = get_conn()
    mailer = current_app.extensions["mailer"]

    owner = db.one("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    if owner is None:
        raise ApiError(404, "no_encontrado", "Usuario inexistente.")
    ver = db.one("SELECT * FROM verificacion_defuncion WHERE id_usuario = %s", (id_usuario,))
    if ver is None or ver["estado_validacion"] != "Aprobada":
        raise ApiError(
            409,
            "defuncion_no_verificada",
            "Solo se pueden enviar notificaciones cuando el fallecimiento fue verificado (Aprobada).",
        )

    pendientes = db.all(
        """
        SELECT i.id_instruccion, i.accion, i.detalle,
               a.nombre_activo, a.tipo,
               e.nombre_entidad, e.email_soporte_legal,
               b.nombre_completo AS b_nombre, b.email_contacto AS b_email, b.telefono AS b_tel
          FROM instrucciones i
          JOIN activos_digitales a            ON a.id_activo = i.id_activo
          JOIN establecimientos_afiliados e   ON e.id_establecimiento = a.id_establecimiento
          LEFT JOIN beneficiarios b           ON b.id_beneficiario = i.id_beneficiario
         WHERE a.id_usuario = %s
           AND NOT EXISTS (SELECT 1 FROM logs_ejecucion l
                            WHERE l.id_instruccion = i.id_instruccion AND l.estado = 'Enviado')
         ORDER BY i.id_instruccion
        """,
        (id_usuario,),
    )

    enviadas = fallidas = 0
    for row in pendientes:
        ok, detalle = mailer.send(
            row["email_soporte_legal"],
            f"Notificación de fallecimiento de titular - {owner['nombre_completo']}",
            _compose_company_email(owner, ver, row),
        )
        db.execute(
            "INSERT INTO logs_ejecucion (id_instruccion, estado, destinatario, resultado_peticion) "
            "VALUES (%s, %s, %s, %s)",
            (row["id_instruccion"], "Enviado" if ok else "Fallido", row["email_soporte_legal"], detalle),
        )
        enviadas += ok
        fallidas += not ok

    total_instrucciones = db.one(
        "SELECT COUNT(*) AS n FROM instrucciones i JOIN activos_digitales a "
        "ON a.id_activo = i.id_activo WHERE a.id_usuario = %s",
        (id_usuario,),
    )["n"]
    sin_instruccion = db.one(
        "SELECT COUNT(*) AS n FROM activos_digitales a WHERE a.id_usuario = %s "
        "AND NOT EXISTS (SELECT 1 FROM instrucciones i WHERE i.id_activo = a.id_activo)",
        (id_usuario,),
    )["n"]

    summary = {
        "enviadas": enviadas,
        "fallidas": fallidas,
        "omitidas_ya_enviadas": total_instrucciones - len(pendientes),
        "activos_sin_instruccion": sin_instruccion,
    }

    # RF-06: notificar el estado a los responsables
    if enviadas or fallidas:
        for ben in db.all(
            "SELECT nombre_completo, email_contacto FROM beneficiarios WHERE id_usuario_propietario = %s",
            (id_usuario,),
        ):
            mailer.send(
                ben["email_contacto"],
                "AfterKey: estado de las notificaciones enviadas",
                f"Hola {ben['nombre_completo']},\n\n"
                f"Se procesaron las solicitudes de {owner['nombre_completo']}: "
                f"{enviadas} enviadas, {fallidas} fallidas.\n"
                "Puede consultar el detalle en el historial de notificaciones.\n\nAfterKey",
            )
    return summary
