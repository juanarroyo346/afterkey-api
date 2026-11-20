"""Envío de correo.

MAIL_BACKEND=console  -> no envía nada; escribe el mensaje en el log y lo guarda
                         en ``outbox`` (ideal para desarrollo y pruebas).
MAIL_BACKEND=smtp     -> envía por SMTP con la configuración SMTP_*.
"""
import smtplib
from email.message import EmailMessage


class Mailer:
    def __init__(self, app):
        self.app = app
        self.outbox = []  # solo se usa con el backend "console"

    def send(self, to: str, subject: str, body: str):
        """Devuelve (ok: bool, detalle: str). Nunca lanza excepciones."""
        cfg = self.app.config
        try:
            if cfg["MAIL_BACKEND"] == "smtp":
                msg = EmailMessage()
                msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_FROM"], to, subject
                msg.set_content(body)
                with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
                    if cfg["SMTP_TLS"]:
                        smtp.starttls()
                    if cfg["SMTP_USER"]:
                        smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                    smtp.send_message(msg)
                return True, f"Enviado por SMTP a {to}"

            self.outbox.append({"to": to, "subject": subject, "body": body})
            del self.outbox[:-200]  # limita la memoria usada
            self.app.logger.info("[MAIL console] to=%s subject=%s", to, subject)
            return True, f"Registrado en consola para {to}"
        except Exception as exc:  # noqa: BLE001 - el correo nunca debe tumbar la petición
            self.app.logger.warning("Fallo enviando correo a %s: %s", to, exc)
            return False, f"Error enviando correo: {exc}"
