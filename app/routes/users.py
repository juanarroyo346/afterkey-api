"""GET/PUT/DELETE /users/me"""
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify

from ..db import get_conn
from ..errors import ApiError
from ..security import hash_password, login_required, verify_password
from ..utils import json_body, now_iso, update_row, validate
from .auth import USER_COLUMNS

bp = Blueprint("users", __name__, url_prefix="/users")

UPDATE_SPEC = {
    "nombre_completo": {"max": 150},
    "email": {"email": True, "max": 254},
    "password": {"password": True, "min": 8, "max": 128},  # contraseña nueva
    "password_actual": {"raw": True, "max": 128},
}
DELETE_SPEC = {"password": {"required": True, "raw": True, "max": 128}}


def _public(user_id):
    return get_conn().one(f"SELECT {USER_COLUMNS} FROM usuarios WHERE id_usuario = %s", (user_id,))


@bp.get("/me")
@login_required
def get_me():
    return jsonify(_public(g.user["id_usuario"]))


@bp.put("/me")
@login_required
def update_me():
    data = validate(json_body(), UPDATE_SPEC, partial=True)
    db = get_conn()
    fields = {}

    if "nombre_completo" in data:
        fields["nombre_completo"] = data["nombre_completo"]

    if "email" in data and data["email"] != g.user["email"]:
        taken = db.one(
            "SELECT 1 AS x FROM usuarios WHERE email = %s AND id_usuario <> %s",
            (data["email"], g.user["id_usuario"]),
        )
        if taken:
            raise ApiError(409, "email_duplicado", "Ya existe una cuenta con ese correo.")
        fields["email"] = data["email"]

    if "password" in data:
        if "password_actual" not in data or not verify_password(
            g.user["password_hash"], data["password_actual"]
        ):
            raise ApiError(
                403, "password_actual_incorrecta", "Para cambiar la contraseña indique la actual."
            )
        fields["password_hash"] = hash_password(data["password"])

    update_row(db, "usuarios", "id_usuario", g.user["id_usuario"], fields)
    return jsonify(_public(g.user["id_usuario"]))


@bp.delete("/me")
@login_required
def delete_me():
    """Elimina la cuenta y, en cascada, activos, beneficiarios, instrucciones y logs."""
    data = validate(json_body(), DELETE_SPEC)
    if not verify_password(g.user["password_hash"], data["password"]):
        raise ApiError(403, "password_incorrecta", "Contraseña incorrecta; la cuenta no fue eliminada.")

    db = get_conn()
    # Se revoca el token actual para que no pueda reutilizarse (el usuario ya no existirá).
    exp = datetime.fromtimestamp(g.claims["exp"], tz=timezone.utc).isoformat()
    db.execute("INSERT INTO tokens_revocados (jti, expira_en) VALUES (%s, %s)", (g.claims["jti"], exp))
    db.execute("DELETE FROM tokens_revocados WHERE expira_en < %s", (now_iso(),))
    db.execute("DELETE FROM usuarios WHERE id_usuario = %s", (g.user["id_usuario"],))
    return jsonify({"mensaje": "Cuenta eliminada correctamente."})
