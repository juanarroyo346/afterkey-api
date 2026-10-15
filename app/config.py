"""Configuración de la aplicación (12-factor: todo viene de variables de entorno)."""
import base64
import hashlib
import os

try:  # carga un archivo .env si python-dotenv está instalado
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def load_config(overrides=None):
    env = os.environ.get
    app_env = env("APP_ENV", "development")
    production = app_env == "production"

    secret_key = env("SECRET_KEY")
    if not secret_key:
        if production:
            raise RuntimeError("SECRET_KEY es obligatoria en producción")
        secret_key = "dev-only-insecure-secret-key-change-me"

    credentials_key = env("CREDENTIALS_KEY")
    if not credentials_key:
        if production:
            raise RuntimeError(
                "CREDENTIALS_KEY es obligatoria en producción. Genérela con: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        # Solo desarrollo: se deriva de SECRET_KEY para que funcione sin configurar nada.
        credentials_key = base64.urlsafe_b64encode(
            hashlib.sha256(secret_key.encode()).digest()
        ).decode()

    config = {
        "APP_ENV": app_env,
        "SECRET_KEY": secret_key,
        "CREDENTIALS_KEY": credentials_key,
        "DATABASE_URL": env(
            "DATABASE_URL", "postgresql://afterkey:afterkey@localhost:5432/afterkey"
        ),
        "DB_POOL_MAX": int(env("DB_POOL_MAX", "10")),
        "JWT_EXPIRES_MINUTES": int(env("JWT_EXPIRES_MINUTES", "60")),
        # Correo: "console" (solo registra en el log) o "smtp"
        "MAIL_BACKEND": env("MAIL_BACKEND", "console"),
        "MAIL_FROM": env("MAIL_FROM", "AfterKey <no-reply@afterkey.example.com>"),
        "SMTP_HOST": env("SMTP_HOST", "localhost"),
        "SMTP_PORT": int(env("SMTP_PORT", "587")),
        "SMTP_USER": env("SMTP_USER", ""),
        "SMTP_PASSWORD": env("SMTP_PASSWORD", ""),
        "SMTP_TLS": env("SMTP_TLS", "true").lower() == "true",
    }
    if overrides:
        config.update(overrides)
    return config
