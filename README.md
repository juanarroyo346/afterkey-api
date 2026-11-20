# AfterKey - Entrega final

## Contenido

- `Front/`: aplicativo móvil multiplataforma desarrollado con Expo, React Native y TypeScript.
- `Back/`: API REST desarrollada con Flask y Python.
- `BD/`: scripts DDL y datos iniciales de PostgreSQL.

## Requisitos

- Node.js 20 o superior.
- Expo CLI compatible con Expo SDK 54.
- Python 3.12 y PostgreSQL 14 o superior para el backend.

## Ejecutar backend

Desde `Back/`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask --app wsgi init-db --seed
flask --app wsgi run --port 8000
```

Configure `DATABASE_URL`, `SECRET_KEY` y `CREDENTIALS_KEY` en `.env`. Docker Compose es la opción recomendada:

```powershell
docker compose up --build
```

## Ejecutar frontend

Desde `Front/`:

```powershell
npm install
copy .env.example .env
npm start
```

Configure `EXPO_PUBLIC_API_URL` con la URL alcanzable desde el dispositivo. Si usa un teléfono físico, no use `localhost`; use la dirección IP de su equipo, por ejemplo `http://192.168.1.10:8000`.

Comandos útiles:

```powershell
npm run android
npm run ios
npm run web
npm run typecheck
```

## Base de datos

- `BD/schema.sql`: creación de tablas, índices y restricciones.
- `BD/seed.sql`: catálogo inicial de establecimientos.

## Flujo de prueba

1. Inicie el backend y PostgreSQL.
2. Abra el aplicativo móvil.
3. Cree una cuenta o registre un usuario.
4. Agregue cuentas digitales y responsables.
5. Cree instrucciones vinculando activos y responsables.
6. Consulte el perfil conectado al usuario autenticado.

La API utiliza JWT Bearer y protege los recursos por usuario. Swagger está disponible en `http://localhost:8000/docs`.
