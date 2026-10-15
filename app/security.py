"""Autenticación, autorización y criptografía.

* Contraseñas: scrypt (werkzeug), nunca en texto plano.
* Sesiones: JWT HS256 con ``jti``; el logout lo agrega a ``tokens_revocados``.
* Credenciales de activos: cifradas con Fernet (AES + HMAC) antes de guardarlas.
  La API NUNCA las devuelve; solo expone ``tiene_credenciales``.
* Beneficiarios: no son usuarios; se identifican con email + código de acceso
  (cabeceras X-Beneficiary-Email / X-Access-Code). Solo se guarda el SHA-256
  del código (es aleatorio y de alta entropía, por eso basta un hash rápido).
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from cryptography.fernet import Fernet
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_conn
from .errors import ApiError


# ----------------------------------------------------------------- contraseñas
def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


# --------------------------------------------------------- cifrado de secretos
def _fernet() -> Fernet:
    return Fernet(current_app.config["CREDENTIALS_KEY"])


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


# ---------------------------------------------------------------------- JWT
def create_access_token(user: dict):
    """Devuelve (token, fecha_expiracion)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=current_app.config["JWT_EXPIRES_MINUTES"])
    payload = {
        "sub": str(user["id_usuario"]),
        "rol": user["rol"],
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token, exp


def _user_from_bearer() -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError(401, "no_autenticado", "Falta la cabecera 'Authorization: Bearer <token>'.")
    token = header[7:].strip()
    try:
        claims = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token_expirado", "El token expiró; inicie sesión de nuevo.")
    except jwt.InvalidTokenError:
        raise ApiError(401, "token_invalido", "Token inválido.")

    db = get_conn()
    if db.one("SELECT 1 AS x FROM tokens_revocados WHERE jti = %s", (claims.get("jti"),)):
        raise ApiError(401, "token_revocado", "La sesión fue cerrada; inicie sesión de nuevo.")
    user = db.one("SELECT * FROM usuarios WHERE id_usuario = %s", (int(claims["sub"]),))
    if user is None:
        raise ApiError(401, "token_invalido", "El usuario del token ya no existe.")
    if user["estado"] == "fallecido":
        raise ApiError(403, "usuario_fallecido", "La cuenta pertenece a un usuario fallecido.")
    g.claims = claims
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_bearer()
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_bearer()
        if g.user["rol"] != "admin":
            raise ApiError(403, "prohibido", "Se requiere rol de administrador.")
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------- beneficiarios
def new_access_code() -> str:
    return "AK-" + secrets.token_urlsafe(18)


def hash_access_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def authenticate_beneficiary(email: str, code: str) -> dict:
    candidates = get_conn().all(
        "SELECT * FROM beneficiarios WHERE email_contacto = %s", (email.strip().lower(),)
    )
    wanted = hash_access_code(code.strip())
    for candidate in candidates:
        if hmac.compare_digest(candidate["codigo_acceso_hash"], wanted):
            return candidate
    # Mensaje genérico: no revela si falló el correo o el código.
    raise ApiError(401, "credenciales_beneficiario_invalidas", "Correo o código de acceso inválidos.")


def beneficiary_from_headers() -> dict:
    email = request.headers.get("X-Beneficiary-Email")
    code = request.headers.get("X-Access-Code")
    if not email or not code:
        raise ApiError(
            401,
            "no_autenticado",
            "Envíe 'Authorization: Bearer <token>' o bien las cabeceras "
            "'X-Beneficiary-Email' y 'X-Access-Code'.",
        )
    return authenticate_beneficiary(email, code)


def get_actor() -> dict:
    """Identifica quién llama en endpoints compartidos (titular, admin o beneficiario).

    Devuelve {tipo, usuario, beneficiario, id_usuario} donde ``id_usuario`` es
    el titular cuyos datos se consultan.
    """
    if request.headers.get("Authorization"):
        user = _user_from_bearer()
        g.user = user
        if user["rol"] == "admin":
            raw = request.args.get("id_usuario", "")
            if not raw.isdigit():
                raise ApiError(
                    422, "falta_id_usuario", "Los administradores deben indicar ?id_usuario=<id>."
                )
            return {"tipo": "admin", "usuario": user, "beneficiario": None, "id_usuario": int(raw)}
        return {"tipo": "titular", "usuario": user, "beneficiario": None, "id_usuario": user["id_usuario"]}

    ben = beneficiary_from_headers()
    return {
        "tipo": "beneficiario",
        "usuario": None,
        "beneficiario": ben,
        "id_usuario": ben["id_usuario_propietario"],
    }
