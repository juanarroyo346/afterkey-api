"""Pruebas de integración de la API de AfterKey.

Ejecutar:   python -m unittest discover -s tests -v

La suite usa SQLite (archivo temporal) para no requerir un servidor; el DDL de
PostgreSQL se traduce automáticamente (ver app/db.py::_to_sqlite).
"""
import os
import re
import sqlite3
import tempfile
import unittest

import yaml

from app import create_app
from app.db import run_sql_file
from app.security import decrypt_secret, hash_password

PASSWORD = "Clave12345"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DATABASE_URL": f"sqlite:///{self.db_path}", "TESTING": True})
        run_sql_file(self.app, "schema.sql")
        run_sql_file(self.app, "seed.sql")
        self.client = self.app.test_client()
        self.mailer = self.app.extensions["mailer"]

    def tearDown(self):
        os.remove(self.db_path)

    # ------------------------------------------------------------ helpers
    def sql(self, query, params=()):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in con.execute(query, params).fetchall()]
            con.commit()
            return rows
        finally:
            con.close()

    def register(self, email="ana@example.com", nombre="Ana Gómez"):
        r = self.client.post(
            "/auth/register", json={"nombre_completo": nombre, "email": email, "password": PASSWORD}
        )
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def login(self, email="ana@example.com"):
        r = self.client.post("/auth/login", json={"email": email, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["access_token"]}

    def new_user(self, email="ana@example.com", nombre="Ana Gómez"):
        self.register(email, nombre)
        return self.login(email)

    def new_admin(self, email="admin@example.com"):
        self.sql(
            "INSERT INTO usuarios (nombre_completo, email, password_hash, rol) VALUES (?, ?, ?, 'admin')",
            ("Admin", email, hash_password(PASSWORD)),
        )
        return self.login(email)

    def est_id(self, nombre):
        return self.sql("SELECT id_establecimiento AS i FROM establecimientos_afiliados WHERE nombre_entidad = ?", (nombre,))[0]["i"]

    def make_account(self, h, est="Bancolombia", nombre="Cuenta ahorros", **extra):
        body = {"id_establecimiento": self.est_id(est), "tipo": "Cuenta", "nombre_activo": nombre, **extra}
        r = self.client.post("/accounts", json=body, headers=h)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def make_beneficiary(self, h, email="luis@example.com", nombre="Luis Gómez"):
        r = self.client.post(
            "/beneficiaries", json={"nombre_completo": nombre, "email_contacto": email}, headers=h
        )
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def make_instruction(self, h, id_activo, accion="Eliminar", id_beneficiario=None, **extra):
        body = {"id_activo": id_activo, "accion": accion, **extra}
        if id_beneficiario:
            body["id_beneficiario"] = id_beneficiario
        r = self.client.post("/instructions", json=body, headers=h)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()


# ======================================================================= docs
class DocsTests(ApiTestCase):
    def test_health_and_swagger(self):
        self.assertEqual(self.client.get("/health").get_json()["estado"], "ok")
        self.assertIn("swagger-ui", self.client.get("/docs").get_data(as_text=True))
        spec = self.client.get("/openapi.json").get_json()
        self.assertEqual(spec["openapi"], "3.0.3")

    def test_every_route_is_documented_and_vice_versa(self):
        with open("docs/openapi.yaml", encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)
        documented = {
            (m.upper(), path)
            for path, item in spec["paths"].items()
            for m in item
            if m in ("get", "post", "put", "delete", "patch")
        }
        implemented = set()
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint == "static" or rule.rule in ("/", "/docs", "/openapi.json", "/openapi.yaml"):
                continue
            path = re.sub(r"<int:\w+>", "{id}", rule.rule)
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                implemented.add((method, path))
        self.assertEqual(implemented - documented, set(), "Rutas sin documentar")
        self.assertEqual(documented - implemented, set(), "Documentadas pero no implementadas")


# ======================================================================= auth
class AuthTests(ApiTestCase):
    def test_register_login_me(self):
        user = self.register()
        self.assertEqual(user["email"], "ana@example.com")
        self.assertNotIn("password_hash", user)
        self.assertEqual(self.mailer.outbox[-1]["subject"], "Bienvenido a AfterKey")
        h = self.login()
        me = self.client.get("/users/me", headers=h).get_json()
        self.assertEqual(me["nombre_completo"], "Ana Gómez")
        # la contraseña jamás se guarda en claro
        stored = self.sql("SELECT password_hash FROM usuarios")[0]["password_hash"]
        self.assertNotIn(PASSWORD, stored)

    def test_register_validation_and_duplicates(self):
        bad = self.client.post("/auth/register", json={"nombre_completo": "A", "email": "x", "password": "corta"})
        self.assertEqual(bad.status_code, 422)
        campos = {d["campo"] for d in bad.get_json()["error"]["detalles"]}
        self.assertEqual(campos, {"email", "password"})
        weak = self.client.post("/auth/register", json={"nombre_completo": "A", "email": "a@b.co", "password": "soloLetrasAqui"})
        self.assertEqual(weak.status_code, 422)
        self.register()
        dup = self.client.post("/auth/register", json={"nombre_completo": "Otra", "email": "ANA@example.com", "password": PASSWORD})
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(self.client.post("/auth/register", data="no json").status_code, 400)

    def test_login_failures_are_generic(self):
        self.register()
        wrong = self.client.post("/auth/login", json={"email": "ana@example.com", "password": "Otra12345"})
        ghost = self.client.post("/auth/login", json={"email": "nadie@example.com", "password": PASSWORD})
        self.assertEqual((wrong.status_code, ghost.status_code), (401, 401))
        self.assertEqual(wrong.get_json(), ghost.get_json())

    def test_logout_revokes_token(self):
        h = self.new_user()
        self.assertEqual(self.client.post("/auth/logout", headers=h).status_code, 200)
        r = self.client.get("/users/me", headers=h)
        self.assertEqual((r.status_code, r.get_json()["error"]["codigo"]), (401, "token_revocado"))

    def test_protected_endpoints_require_token(self):
        self.assertEqual(self.client.get("/users/me").status_code, 401)
        r = self.client.get("/accounts", headers={"Authorization": "Bearer basura"})
        self.assertEqual(r.get_json()["error"]["codigo"], "token_invalido")

    def test_update_me_and_change_password(self):
        h = self.new_user()
        self.register("otra@example.com")
        conflict = self.client.put("/users/me", json={"email": "otra@example.com"}, headers=h)
        self.assertEqual(conflict.status_code, 409)
        ok = self.client.put("/users/me", json={"nombre_completo": "Ana María"}, headers=h)
        self.assertEqual(ok.get_json()["nombre_completo"], "Ana María")
        no_current = self.client.put("/users/me", json={"password": "Nueva12345"}, headers=h)
        self.assertEqual(no_current.status_code, 403)
        done = self.client.put("/users/me", json={"password": "Nueva12345", "password_actual": PASSWORD}, headers=h)
        self.assertEqual(done.status_code, 200)
        relog = self.client.post("/auth/login", json={"email": "ana@example.com", "password": "Nueva12345"})
        self.assertEqual(relog.status_code, 200)

    def test_delete_me_cascades(self):
        h = self.new_user()
        acc = self.make_account(h)
        self.make_instruction(h, acc["id_activo"])
        self.assertEqual(self.client.delete("/users/me", json={"password": "mala"}, headers=h).status_code, 403)
        self.assertEqual(self.client.delete("/users/me", json={"password": PASSWORD}, headers=h).status_code, 200)
        for table in ("usuarios", "activos_digitales", "instrucciones"):
            self.assertEqual(self.sql(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 0, table)
        self.assertEqual(self.client.get("/users/me", headers=h).status_code, 401)


# ===================================================================== cuentas
class AccountTests(ApiTestCase):
    def test_crud(self):
        h = self.new_user()
        acc = self.make_account(h, notas="Principal")
        self.assertEqual(acc["establecimiento"], "Bancolombia")
        self.assertFalse(acc["tiene_credenciales"])
        got = self.client.get(f"/accounts/{acc['id_activo']}", headers=h).get_json()
        self.assertEqual(got["nombre_activo"], "Cuenta ahorros")
        upd = self.client.put(
            f"/accounts/{acc['id_activo']}", json={"nombre_activo": "Ahorros 2", "tipo": "Servicio"}, headers=h
        ).get_json()
        self.assertEqual((upd["nombre_activo"], upd["tipo"], upd["notas"]), ("Ahorros 2", "Servicio", "Principal"))
        self.assertEqual(self.client.delete(f"/accounts/{acc['id_activo']}", headers=h).status_code, 204)
        self.assertEqual(self.client.get(f"/accounts/{acc['id_activo']}", headers=h).status_code, 404)

    def test_credentials_are_encrypted_and_never_returned(self):
        h = self.new_user()
        acc = self.make_account(h, credenciales="MiClaveSecreta!")
        self.assertTrue(acc["tiene_credenciales"])
        self.assertNotIn("MiClaveSecreta", str(self.client.get("/accounts", headers=h).get_json()))
        stored = self.sql("SELECT credenciales_cifradas AS c FROM activos_digitales")[0]["c"]
        self.assertNotIn("MiClaveSecreta", stored)
        with self.app.app_context():
            self.assertEqual(decrypt_secret(stored), "MiClaveSecreta!")
        cleared = self.client.put(f"/accounts/{acc['id_activo']}", json={"credenciales": None}, headers=h)
        self.assertFalse(cleared.get_json()["tiene_credenciales"])

    def test_isolation_between_users(self):
        a = self.new_user("a@example.com")
        b = self.new_user("b@example.com")
        acc = self.make_account(a)
        self.assertEqual(self.client.get(f"/accounts/{acc['id_activo']}", headers=b).status_code, 404)
        self.assertEqual(self.client.put(f"/accounts/{acc['id_activo']}", json={"notas": "x"}, headers=b).status_code, 404)
        self.assertEqual(self.client.delete(f"/accounts/{acc['id_activo']}", headers=b).status_code, 404)
        self.assertEqual(self.client.get("/accounts", headers=b).get_json()["total"], 0)

    def test_validation_filters_and_pagination(self):
        h = self.new_user()
        bad = self.client.post("/accounts", json={"id_establecimiento": 9999, "tipo": "Cuenta", "nombre_activo": "x"}, headers=h)
        self.assertEqual(bad.get_json()["error"]["codigo"], "establecimiento_inexistente")
        worse = self.client.post("/accounts", json={"tipo": "Otro", "nombre_activo": "", "extra": 1}, headers=h)
        self.assertEqual(worse.status_code, 422)
        self.make_account(h, "Bancolombia", "A")
        self.make_account(h, "Netflix", "B")
        self.client.post("/accounts", json={"id_establecimiento": self.est_id("Dropbox"), "tipo": "Archivo", "nombre_activo": "C"}, headers=h)
        self.assertEqual(self.client.get("/accounts?tipo=Archivo", headers=h).get_json()["total"], 1)
        page = self.client.get("/accounts?limit=2&offset=2", headers=h).get_json()
        self.assertEqual((page["total"], len(page["items"])), (3, 1))
        self.assertEqual(self.client.get("/accounts?limit=0", headers=h).status_code, 422)


# ================================================================ responsables
class BeneficiaryTests(ApiTestCase):
    def test_crud_and_access_code_shown_once(self):
        h = self.new_user()
        ben = self.make_beneficiary(h)
        self.assertTrue(ben["codigo_acceso"].startswith("AK-"))
        listed = self.client.get("/beneficiaries", headers=h).get_json()
        self.assertNotIn("codigo_acceso", str(listed))
        self.assertNotIn(ben["codigo_acceso"], self.sql("SELECT codigo_acceso_hash AS c FROM beneficiarios")[0]["c"])
        dup = self.client.post("/beneficiaries", json={"nombre_completo": "Otro", "email_contacto": "LUIS@example.com"}, headers=h)
        self.assertEqual(dup.status_code, 409)
        upd = self.client.put(f"/beneficiaries/{ben['id_beneficiario']}", json={"telefono": "123", "parentesco": "Hermano"}, headers=h)
        self.assertEqual(upd.get_json()["parentesco"], "Hermano")
        self.assertEqual(self.client.delete(f"/beneficiaries/{ben['id_beneficiario']}", headers=h).status_code, 204)

    def test_regenerate_code_invalidates_old_one(self):
        h = self.new_user()
        ben = self.make_beneficiary(h)
        old = ben["codigo_acceso"]
        new = self.client.post(f"/beneficiaries/{ben['id_beneficiario']}/regenerate-code", headers=h).get_json()["codigo_acceso"]
        status = lambda code: self.client.get(
            "/death-notification/status",
            headers={"X-Beneficiary-Email": "luis@example.com", "X-Access-Code": code},
        ).status_code
        self.assertEqual((status(old), status(new)), (401, 200))

    def test_cannot_delete_beneficiary_in_use(self):
        h = self.new_user()
        acc, ben = self.make_account(h), self.make_beneficiary(h)
        self.make_instruction(h, acc["id_activo"], "Transferir", ben["id_beneficiario"])
        r = self.client.delete(f"/beneficiaries/{ben['id_beneficiario']}", headers=h)
        self.assertEqual((r.status_code, r.get_json()["error"]["codigo"]), (409, "responsable_en_uso"))


# ================================================================ instrucciones
class InstructionTests(ApiTestCase):
    def test_rules(self):
        h = self.new_user()
        other = self.new_user("otro@example.com")
        acc, ben = self.make_account(h), self.make_beneficiary(h)
        foreign_acc = self.make_account(other)

        no_ben = self.client.post("/instructions", json={"id_activo": acc["id_activo"], "accion": "Transferir"}, headers=h)
        self.assertEqual(no_ben.get_json()["error"]["codigo"], "responsable_requerido")
        foreign = self.client.post("/instructions", json={"id_activo": foreign_acc["id_activo"], "accion": "Eliminar"}, headers=h)
        self.assertEqual(foreign.get_json()["error"]["codigo"], "activo_invalido")
        bad_action = self.client.post("/instructions", json={"id_activo": acc["id_activo"], "accion": "Vender"}, headers=h)
        self.assertEqual(bad_action.status_code, 422)

        ins = self.make_instruction(h, acc["id_activo"], "Transferir", ben["id_beneficiario"], detalle="Para mi hermano")
        self.assertEqual((ins["beneficiario"], ins["establecimiento"]), ("Luis Gómez", "Bancolombia"))
        dup = self.client.post(
            "/instructions",
            json={"id_activo": acc["id_activo"], "id_beneficiario": ben["id_beneficiario"], "accion": "Conservar"},
            headers=h,
        )
        self.assertEqual(dup.status_code, 409)

        # no se puede dejar una instrucción 'Transferir' sin responsable
        broken = self.client.put(f"/instructions/{ins['id_instruccion']}", json={"id_beneficiario": None}, headers=h)
        self.assertEqual(broken.status_code, 422)
        ok = self.client.put(f"/instructions/{ins['id_instruccion']}", json={"accion": "Conservar", "id_beneficiario": None}, headers=h)
        self.assertEqual(ok.get_json()["accion"], "Conservar")

        self.assertEqual(self.client.get(f"/instructions?id_activo={acc['id_activo']}", headers=h).get_json()["total"], 1)
        self.assertEqual(self.client.get(f"/instructions/{ins['id_instruccion']}", headers=other).status_code, 404)
        self.assertEqual(self.client.delete(f"/instructions/{ins['id_instruccion']}", headers=h).status_code, 204)


# ======================================================== tabla maestra (catálogo)
class EstablishmentTests(ApiTestCase):
    def test_read_for_users_write_for_admins(self):
        user, admin = self.new_user(), self.new_admin()
        self.assertGreaterEqual(self.client.get("/establishments", headers=user).get_json()["total"], 10)
        self.assertEqual(self.client.get("/establishments?sector=Banca", headers=user).get_json()["total"], 3)
        self.assertEqual(self.client.get("/establishments?q=netf", headers=user).get_json()["total"], 1)
        body = {"nombre_entidad": "Nuevo Banco", "email_soporte_legal": "legal@nuevo.example.com", "sector": "Banca"}
        self.assertEqual(self.client.post("/establishments", json=body, headers=user).status_code, 403)
        created = self.client.post("/establishments", json=body, headers=admin)
        self.assertEqual(created.status_code, 201)
        eid = created.get_json()["id_establecimiento"]
        self.assertEqual(self.client.post("/establishments", json=body, headers=admin).status_code, 409)
        upd = self.client.put(f"/establishments/{eid}", json={"sector": "Seguros"}, headers=admin)
        self.assertEqual(upd.get_json()["sector"], "Seguros")
        self.assertEqual(self.client.delete(f"/establishments/{eid}", headers=admin).status_code, 204)
        self.assertEqual(self.client.get(f"/establishments/{eid}", headers=user).status_code, 404)

    def test_cannot_delete_establishment_in_use(self):
        user, admin = self.new_user(), self.new_admin()
        self.make_account(user, "Netflix")
        r = self.client.delete(f"/establishments/{self.est_id('Netflix')}", headers=admin)
        self.assertEqual((r.status_code, r.get_json()["error"]["codigo"]), (409, "establecimiento_en_uso"))


# ======================================================= proceso de fallecimiento
class DeathFlowTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.new_user("ana@example.com", "Ana Gómez")
        self.admin = self.new_admin()
        self.ben = self.make_beneficiary(self.owner)
        self.bh = {"X-Beneficiary-Email": "luis@example.com", "X-Access-Code": self.ben["codigo_acceso"]}
        self.bank = self.make_account(self.owner, "Bancolombia", "Ahorros", credenciales="Cl4veSuperSecreta")
        self.nflx = self.make_account(self.owner, "Netflix", "Netflix familiar")
        self.make_account(self.owner, "Dropbox", "Fotos sin instrucción")
        self.make_instruction(self.owner, self.bank["id_activo"], "Transferir", self.ben["id_beneficiario"], detalle="Para mi hermano")
        self.make_instruction(self.owner, self.nflx["id_activo"], "Eliminar")
        self.uid = self.bank["id_usuario"]
        self.mailer.outbox.clear()

    def report(self, ref="https://actas.example.com/1.pdf"):
        return self.client.post("/death-notification", json={"certificado_ref": ref}, headers=self.bh)

    def test_full_flow(self):
        # credenciales de responsable inválidas
        bad = self.client.post("/death-notification", json={"certificado_ref": "x"},
                               headers={"X-Beneficiary-Email": "luis@example.com", "X-Access-Code": "AK-mal"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.client.post("/death-notification", json={"certificado_ref": "x"}).status_code, 401)

        # aún no verificado: no se puede notificar
        early = self.client.post("/notifications/send", headers=self.bh)
        self.assertEqual((early.status_code, early.get_json()["error"]["codigo"]), (409, "defuncion_no_verificada"))

        # 1) el responsable reporta
        rep = self.report()
        self.assertEqual((rep.status_code, rep.get_json()["estado_validacion"]), (201, "Pendiente"))
        self.assertEqual(self.report().status_code, 409)
        status = self.client.get("/death-notification/status", headers=self.bh).get_json()
        self.assertEqual((status["estado_proceso"], status["estado_titular"]), ("Pendiente", "vivo"))
        self.assertEqual(self.client.get("/death-notification/status", headers=self.owner).get_json()["estado_proceso"], "Pendiente")

        # 2) solo un admin valida
        ver_id = rep.get_json()["id_verificacion"]
        self.assertEqual(self.client.put(f"/death-notification/{ver_id}/validate", json={"estado_validacion": "Aprobada"}, headers=self.owner).status_code, 403)
        self.assertEqual(self.client.get("/death-notification", headers=self.owner).status_code, 403)
        pending = self.client.get("/death-notification?estado=Pendiente", headers=self.admin).get_json()
        self.assertEqual((pending["total"], pending["items"][0]["titular"]), (1, "Ana Gómez"))

        # rechazo -> el titular sigue vivo y el responsable puede reintentar (relación 1:1 se reabre)
        rej = self.client.put(f"/death-notification/{ver_id}/validate",
                              json={"estado_validacion": "Rechazada", "observaciones": "Ilegible"}, headers=self.admin)
        self.assertEqual(rej.get_json()["verificacion"]["estado_validacion"], "Rechazada")
        self.assertEqual(self.sql("SELECT estado FROM usuarios WHERE id_usuario = ?", (self.uid,))[0]["estado"], "vivo")
        self.assertEqual(self.mailer.outbox, [])
        again = self.report("https://actas.example.com/2.pdf")
        self.assertEqual((again.status_code, again.get_json()["estado_validacion"]), (201, "Pendiente"))
        self.assertEqual(again.get_json()["id_verificacion"], ver_id)

        # 3) aprobación -> titular fallecido + envío automático
        ok = self.client.put(f"/death-notification/{ver_id}/validate", json={"estado_validacion": "Aprobada"}, headers=self.admin).get_json()
        self.assertEqual(ok["notificaciones"], {"enviadas": 2, "fallidas": 0, "omitidas_ya_enviadas": 0, "activos_sin_instruccion": 1})
        self.assertEqual(self.sql("SELECT estado FROM usuarios WHERE id_usuario = ?", (self.uid,))[0]["estado"], "fallecido")

        to_companies = [m for m in self.mailer.outbox if m["to"].endswith(".example.com")]
        self.assertEqual({m["to"] for m in to_companies}, {"soporte-legal@bancolombia.example.com", "legal@netflix.example.com"})
        self.assertEqual(len([m for m in self.mailer.outbox if m["to"] == "luis@example.com"]), 1)
        for m in self.mailer.outbox:
            self.assertNotIn("Cl4veSuperSecreta", m["body"])
        bank_mail = next(m for m in to_companies if "bancolombia" in m["to"])
        self.assertIn("TRANSFERIR", bank_mail["body"])
        self.assertIn("Luis Gómez", bank_mail["body"])

        # el titular fallecido ya no puede entrar y su token deja de servir
        self.assertEqual(self.client.post("/auth/login", json={"email": "ana@example.com", "password": PASSWORD}).status_code, 403)
        self.assertEqual(self.client.get("/users/me", headers=self.owner).status_code, 403)
        self.assertEqual(self.client.put(f"/death-notification/{ver_id}/validate", json={"estado_validacion": "Rechazada"}, headers=self.admin).status_code, 409)
        self.assertEqual(self.report().status_code, 409)

        # 4) historial, idempotencia y reportes
        logs = self.client.get("/notifications", headers=self.bh).get_json()
        self.assertEqual((logs["total"], {i["estado"] for i in logs["items"]}), (2, {"Enviado"}))
        resend = self.client.post("/notifications/send", headers=self.bh).get_json()
        self.assertEqual((resend["enviadas"], resend["omitidas_ya_enviadas"]), (0, 2))
        self.assertEqual(self.client.get("/notifications", headers=self.admin).status_code, 422)  # falta id_usuario
        by_admin = self.client.get(f"/notifications?id_usuario={self.uid}&estado=Enviado", headers=self.admin).get_json()
        self.assertEqual(by_admin["total"], 2)
        final = self.client.get("/death-notification/status", headers=self.bh).get_json()
        self.assertEqual((final["estado_proceso"], final["notificaciones"]["Enviado"]), ("Aprobada", 2))

        hist = self.client.get("/reports/history", headers=self.bh).get_json()
        self.assertEqual((len(hist["registros"]), hist["verificacion"]["estado_validacion"]), (2, "Aprobada"))
        pdf = self.client.get("/reports/history.pdf", headers=self.bh)
        self.assertEqual((pdf.status_code, pdf.mimetype), (200, "application/pdf"))
        self.assertTrue(pdf.data.startswith(b"%PDF"))

    def test_failed_emails_are_retried(self):
        self.report()
        original = self.mailer.send
        self.mailer.send = lambda to, s, b: (False, "SMTP caído") if "netflix" in to else original(to, s, b)
        ver_id = self.sql("SELECT id_verificacion AS i FROM verificacion_defuncion")[0]["i"]
        res = self.client.put(f"/death-notification/{ver_id}/validate", json={"estado_validacion": "Aprobada"}, headers=self.admin).get_json()
        self.assertEqual((res["notificaciones"]["enviadas"], res["notificaciones"]["fallidas"]), (1, 1))
        failed = self.client.get("/notifications?estado=Fallido", headers=self.bh).get_json()
        self.assertEqual((failed["total"], failed["items"][0]["resultado_peticion"]), (1, "SMTP caído"))

        self.mailer.send = original  # el servicio se recupera
        retry = self.client.post("/notifications/send", headers=self.bh).get_json()
        self.assertEqual((retry["enviadas"], retry["fallidas"], retry["omitidas_ya_enviadas"]), (1, 0, 1))
        counts = self.client.get("/death-notification/status", headers=self.bh).get_json()["notificaciones"]
        self.assertEqual((counts["Enviado"], counts["Fallido"]), (2, 1))  # el historial conserva el intento fallido


if __name__ == "__main__":
    unittest.main()
