"""POST /auth/register · /auth/login · /auth/logout   (RF-01)"""
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify

from ..db import get_conn
from ..errors import ApiError
from ..security import (
    create_access_token,
    hash_password,
    login_required,
    verify_password,
)
from ..utils import json_body, now_iso, validate

bp = Blueprint("auth", __name__, url_prefix="/auth")

USER_COLUMNS = "id_usuario, nombre_completo, email, rol, estado, fecha_registro"

REGISTER_SPEC = {
    "nombre_completo": {"required": True, "max": 150},
    "email": {"required": True, "email": True, "max": 254},
    "password": {"required": True, "password": True, "min": 8, "max": 128},
}
LOGIN_SPEC = {
    "email": {"required": True, "email": True},
    "password": {"required": True, "raw": True, "max": 128},
}


@bp.post("/register")
def register():
    data = validate(json_body(), REGISTER_SPEC)
    db = get_conn()
    if db.one("SELECT 1 AS x FROM usuarios WHERE email = %s", (data["email"],)):
        raise ApiError(409, "email_duplicado", "Ya existe una cuenta con ese correo.")

    user = db.one(
        f"INSERT INTO usuarios (nombre_completo, email, password_hash) VALUES (%s, %s, %s) "
        f"RETURNING {USER_COLUMNS}",
        (data["nombre_completo"], data["email"], hash_password(data["password"])),
    )
    current_app.extensions["mailer"].send(
        user["email"],
        "Bienvenido a AfterKey",
        f"Hola {user['nombre_completo']},\n\nTu cuenta en AfterKey fue creada correctamente. "
        "Ya puedes registrar tus cuentas digitales, designar responsables y definir tus "
        "instrucciones.\n\nAfterKey",
    )
    return jsonify(user), 201


@bp.post("/login")
def login():
    data = validate(json_body(), LOGIN_SPEC)
    db = get_conn()
    user = db.one("SELECT * FROM usuarios WHERE email = %s", (data["email"],))

    # Mismo mensaje (y trabajo de hash) si el correo no existe: evita enumerar usuarios.
    stored_hash = user["password_hash"] if user else hash_password("dummy-password-1")
    valid = verify_password(stored_hash, data["password"])
    if not user or not valid:
        raise ApiError(401, "credenciales_invalidas", "Correo o contraseña incorrectos.")
    if user["estado"] == "fallecido":
        raise ApiError(403, "usuario_fallecido", "La cuenta pertenece a un usuario fallecido.")

    token, exp = create_access_token(user)
    public = {k: user[k] for k in USER_COLUMNS.split(", ")}
    return jsonify(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": current_app.config["JWT_EXPIRES_MINUTES"] * 60,
            "usuario": public,
        }
    )


@bp.post("/logout")
@login_required
def logout():
    db = get_conn()
    exp = datetime.fromtimestamp(g.claims["exp"], tz=timezone.utc).isoformat()
    db.execute(
        "INSERT INTO tokens_revocados (jti, expira_en) VALUES (%s, %s)", (g.claims["jti"], exp)
    )
    db.execute("DELETE FROM tokens_revocados WHERE expira_en < %s", (now_iso(),))
    return jsonify({"mensaje": "Sesión cerrada correctamente."})
