"""Validación de entrada, paginación y helpers compartidos por las rutas."""
import re
from datetime import date, datetime, timezone

from flask import request
from flask.json.provider import DefaultJSONProvider

from .errors import ApiError

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class JSONProvider(DefaultJSONProvider):
    """Fechas en ISO-8601, acentos sin escapar y orden de claves preservado."""

    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "cuerpo_invalido", "Se esperaba un cuerpo JSON (objeto).")
    return data


def validate(data: dict, spec: dict, partial: bool = False) -> dict:
    """Valida ``data`` contra ``spec`` y devuelve los valores limpios.

    Reglas por campo: type ('str'|'int'), required, nullable, max, min,
    enum, email, raw (no recorta espacios), password (raw + política: letras y números). Con ``partial=True`` (PUT) los campos son opcionales.
    Los campos desconocidos se rechazan.
    """
    errors, clean = [], {}

    for name in data:
        if name not in spec:
            errors.append({"campo": name, "mensaje": "campo no permitido"})

    for name, rule in spec.items():
        if name not in data:
            if rule.get("required") and not partial:
                errors.append({"campo": name, "mensaje": "es obligatorio"})
            continue

        value = data[name]
        if value is None:
            if rule.get("nullable"):
                clean[name] = None
            else:
                errors.append({"campo": name, "mensaje": "no puede ser nulo"})
            continue

        kind = rule.get("type", "str")
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append({"campo": name, "mensaje": "debe ser un entero"})
                continue
            if "min" in rule and value < rule["min"]:
                errors.append({"campo": name, "mensaje": f"debe ser >= {rule['min']}"})
                continue
            clean[name] = value
            continue

        # texto
        if not isinstance(value, str):
            errors.append({"campo": name, "mensaje": "debe ser texto"})
            continue
        if not (rule.get("raw") or rule.get("password")):
            value = value.strip()
        if value == "" and rule.get("required"):
            errors.append({"campo": name, "mensaje": "no puede estar vacío"})
            continue
        if value == "" and rule.get("nullable"):
            clean[name] = None
            continue
        if "max" in rule and len(value) > rule["max"]:
            errors.append({"campo": name, "mensaje": f"máximo {rule['max']} caracteres"})
            continue
        if "min" in rule and len(value) < rule["min"]:
            errors.append({"campo": name, "mensaje": f"mínimo {rule['min']} caracteres"})
            continue
        if rule.get("email"):
            if not EMAIL_RE.match(value):
                errors.append({"campo": name, "mensaje": "correo electrónico inválido"})
                continue
            value = value.lower()
        if rule.get("password") and not (
            re.search(r"[A-Za-z]", value) and re.search(r"\d", value)
        ):
            errors.append({"campo": name, "mensaje": "debe contener letras y números"})
            continue
        if "enum" in rule and value not in rule["enum"]:
            errors.append(
                {"campo": name, "mensaje": "valor inválido, use: " + ", ".join(rule["enum"])}
            )
            continue
        clean[name] = value

    if errors:
        raise ApiError(422, "validacion_fallida", "Los datos enviados no son válidos.", errors)
    return clean


def page_args():
    """Lee ?limit y ?offset (limit por defecto 50, máximo 200)."""

    def read(name, default, low, high):
        raw = request.args.get(name)
        if raw is None:
            return default
        if not raw.isdigit() or not low <= int(raw) <= high:
            raise ApiError(
                422, "paginacion_invalida", f"'{name}' debe ser un entero entre {low} y {high}."
            )
        return int(raw)

    return read("limit", 50, 1, 200), read("offset", 0, 0, 10**9)


def page(items, total, limit, offset):
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def update_row(db, table, pk_name, pk_value, fields: dict, touch_column=None):
    """UPDATE dinámico. Los nombres de columna provienen del código (nunca del cliente)."""
    if touch_column:
        fields = {**fields, touch_column: now_iso()}
    if not fields:
        return
    assignments = ", ".join(f"{col} = %s" for col in fields)
    db.execute(
        f"UPDATE {table} SET {assignments} WHERE {pk_name} = %s",
        [*fields.values(), pk_value],
    )
