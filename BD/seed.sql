-- =====================================================================
-- AfterKey - Datos semilla del catalogo de Establecimientos Afiliados
-- Los correos usan el dominio reservado example.com a proposito, para
-- que en desarrollo NUNCA se escriba a empresas reales.
-- Ejecucion:  psql "$DATABASE_URL" -f database/seed.sql
-- =====================================================================
INSERT INTO establecimientos_afiliados (nombre_entidad, email_soporte_legal, sector) VALUES
    ('Bancolombia',       'soporte-legal@bancolombia.example.com', 'Banca'),
    ('Davivienda',        'soporte-legal@davivienda.example.com',  'Banca'),
    ('Nequi',             'soporte-legal@nequi.example.com',       'Banca'),
    ('Facebook',          'legal@facebook.example.com',            'RRSS'),
    ('Instagram',         'legal@instagram.example.com',           'RRSS'),
    ('X (Twitter)',       'legal@x.example.com',                   'RRSS'),
    ('LinkedIn',          'legal@linkedin.example.com',            'RRSS'),
    ('Google (Gmail/Drive)', 'legal@google.example.com',           'Cloud'),
    ('Apple iCloud',      'legal@icloud.example.com',              'Cloud'),
    ('Dropbox',           'legal@dropbox.example.com',             'Cloud'),
    ('Microsoft OneDrive','legal@onedrive.example.com',            'Cloud'),
    ('Netflix',           'legal@netflix.example.com',             'Streaming'),
    ('Spotify',           'legal@spotify.example.com',             'Streaming'),
    ('Suramericana',      'legal@suramericana.example.com',        'Seguros')
ON CONFLICT (nombre_entidad) DO NOTHING;
