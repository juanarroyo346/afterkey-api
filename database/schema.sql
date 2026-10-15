-- =====================================================================
-- AfterKey - Gestion de herencia digital
-- Esquema de base de datos (DDL) para PostgreSQL 14+
--
-- Ejecucion:  psql "$DATABASE_URL" -f database/schema.sql
-- Es idempotente: se puede ejecutar varias veces sin romper nada.
--
-- Nota: los "ENUM" del modelo conceptual se implementan con CHECK
-- sobre VARCHAR (mas faciles de evolucionar que CREATE TYPE ... ENUM).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. USUARIOS  (titulares de la herencia digital y administradores)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario       SERIAL PRIMARY KEY,
    nombre_completo  VARCHAR(150) NOT NULL,
    email            VARCHAR(254) NOT NULL UNIQUE,          -- siempre en minusculas
    password_hash    VARCHAR(255) NOT NULL,                 -- scrypt (nunca texto plano)
    rol              VARCHAR(10)  NOT NULL DEFAULT 'usuario'
                     CHECK (rol IN ('usuario', 'admin')),
    estado           VARCHAR(10)  NOT NULL DEFAULT 'vivo'
                     CHECK (estado IN ('vivo', 'fallecido')),
    fecha_registro   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- 2. ESTABLECIMIENTOS_AFILIADOS  (tabla maestra / catalogo de empresas)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS establecimientos_afiliados (
    id_establecimiento   SERIAL PRIMARY KEY,
    nombre_entidad       VARCHAR(150) NOT NULL UNIQUE,
    email_soporte_legal  VARCHAR(254) NOT NULL,
    sector               VARCHAR(20)  NOT NULL
                         CHECK (sector IN ('Banca', 'RRSS', 'Cloud', 'Streaming', 'Seguros', 'Otro'))
);

-- ---------------------------------------------------------------------
-- 3. ACTIVOS_DIGITALES  (cuentas, archivos y servicios del usuario)
--    Relación: usuarios 1:N activos_digitales
--              establecimientos_afiliados 1:N activos_digitales
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activos_digitales (
    id_activo              SERIAL PRIMARY KEY,
    id_usuario             INTEGER      NOT NULL
                           REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    id_establecimiento     INTEGER      NOT NULL
                           REFERENCES establecimientos_afiliados (id_establecimiento),
    tipo                   VARCHAR(10)  NOT NULL
                           CHECK (tipo IN ('Cuenta', 'Archivo', 'Servicio')),
    nombre_activo          VARCHAR(150) NOT NULL,
    notas                  TEXT,
    credenciales_cifradas  TEXT,                            -- Fernet (AES-128-CBC + HMAC); opcional
    fecha_creacion         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    fecha_actualizacion    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activos_usuario        ON activos_digitales (id_usuario);
CREATE INDEX IF NOT EXISTS idx_activos_establecimiento ON activos_digitales (id_establecimiento);

-- ---------------------------------------------------------------------
-- 4. BENEFICIARIOS  (responsables digitales designados por el usuario)
--    Relacion: usuarios 1:N beneficiarios
--    No son usuarios del sistema: se identifican con email + codigo de
--    acceso (se guarda solo el hash SHA-256 del codigo).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS beneficiarios (
    id_beneficiario         SERIAL PRIMARY KEY,
    id_usuario_propietario  INTEGER      NOT NULL
                            REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    nombre_completo         VARCHAR(150) NOT NULL,
    email_contacto          VARCHAR(254) NOT NULL,          -- siempre en minusculas
    telefono                VARCHAR(30),
    parentesco              VARCHAR(50),
    codigo_acceso_hash      CHAR(64)     NOT NULL,
    fecha_creacion          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_beneficiario_por_usuario UNIQUE (id_usuario_propietario, email_contacto)
);
CREATE INDEX IF NOT EXISTS idx_beneficiarios_email ON beneficiarios (email_contacto);

-- ---------------------------------------------------------------------
-- 5. INSTRUCCIONES  (testamento digital: quee hacer con cada activo)
--    Relacion: activos_digitales 1:N instrucciones
--              beneficiarios     1:N instrucciones
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS instrucciones (
    id_instruccion  SERIAL PRIMARY KEY,
    id_activo       INTEGER     NOT NULL
                    REFERENCES activos_digitales (id_activo) ON DELETE CASCADE,
    id_beneficiario INTEGER
                    REFERENCES beneficiarios (id_beneficiario),
    accion          VARCHAR(12) NOT NULL
                    CHECK (accion IN ('Eliminar', 'Transferir', 'Conservar')),
    detalle         TEXT,
    fecha_creacion  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Transferir exige un beneficiario que reciba el activo
    CONSTRAINT ck_transferir_requiere_beneficiario
        CHECK (accion <> 'Transferir' OR id_beneficiario IS NOT NULL),
    -- Un mismo beneficiario no puede tener dos instrucciones sobre el mismo activo
    CONSTRAINT uq_instruccion_activo_beneficiario UNIQUE (id_activo, id_beneficiario)
);
CREATE INDEX IF NOT EXISTS idx_instrucciones_activo       ON instrucciones (id_activo);
CREATE INDEX IF NOT EXISTS idx_instrucciones_beneficiario ON instrucciones (id_beneficiario);

-- ---------------------------------------------------------------------
-- 6. VERIFICACION_DEFUNCION  (disparador auditable del proceso)
--    Relacion: usuarios 1:1 verificacion_defuncion
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verificacion_defuncion (
    id_verificacion              SERIAL PRIMARY KEY,
    id_usuario                   INTEGER      NOT NULL UNIQUE
                                 REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    id_beneficiario_reportante   INTEGER
                                 REFERENCES beneficiarios (id_beneficiario) ON DELETE SET NULL,
    fecha_reporte                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    certificado_ref              VARCHAR(255) NOT NULL,     -- referencia/URL del acta de defunción
    estado_validacion            VARCHAR(10)  NOT NULL DEFAULT 'Pendiente'
                                 CHECK (estado_validacion IN ('Pendiente', 'Aprobada', 'Rechazada')),
    fecha_validacion             TIMESTAMPTZ,
    validado_por                 INTEGER
                                 REFERENCES usuarios (id_usuario) ON DELETE SET NULL,
    observaciones                TEXT
);

-- ---------------------------------------------------------------------
-- 7. LOGS_EJECUCION  (historial / evidencia de cada solicitud enviada)
--    Relacion: instrucciones 1:N logs_ejecucion
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_ejecucion (
    id_log              SERIAL PRIMARY KEY,
    id_instruccion      INTEGER      NOT NULL
                        REFERENCES instrucciones (id_instruccion) ON DELETE CASCADE,
    fecha_ejecucion     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    estado              VARCHAR(10)  NOT NULL DEFAULT 'Pendiente'
                        CHECK (estado IN ('Pendiente', 'Enviado', 'Fallido')),
    destinatario        VARCHAR(254),
    resultado_peticion  TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_instruccion ON logs_ejecucion (id_instruccion);

-- ---------------------------------------------------------------------
-- 8. TOKENS_REVOCADOS  (soporte de POST /auth/logout con JWT)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tokens_revocados (
    jti        VARCHAR(64)  PRIMARY KEY,
    expira_en  TIMESTAMPTZ  NOT NULL
);
