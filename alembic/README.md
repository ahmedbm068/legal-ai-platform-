# Alembic migrations

This directory holds database schema migrations for the Legal AI Platform.

## Why Alembic, when `schema_sync` already creates tables?

`backend/database/schema_sync.py` calls `Base.metadata.create_all()` and
applies a hand-rolled list of legacy patches at startup. That's fine for
local demos but is not a versioned, repeatable schema history. Alembic
gives us:

- A linear, reviewable history of schema changes (`alembic/versions/*.py`)
- Forward + backward migrations (`upgrade` / `downgrade`)
- `alembic upgrade head` as the single command for any environment
- Drift detection via `alembic check` / autogenerate

The `schema_sync` path remains as a convenience fallback for fresh local
databases until the team flips the production deployment to
`alembic upgrade head` exclusively.

## First-time setup against a fresh database

```bash
# 1. Install deps (alembic is already in requirements.txt)
pip install -r requirements.txt

# 2. Create the database (or let docker-compose do it)
docker compose up -d postgres

# 3. Apply all migrations
alembic upgrade head
```

## Workflow when you change a model

```bash
# 1. Edit a SQLAlchemy model in backend/models/*.py
# 2. Generate a migration (alembic diffs Base.metadata vs the live DB)
alembic revision --autogenerate -m "add foo column to bar"

# 3. Open alembic/versions/<hash>_add_foo_column_to_bar.py and review it.
#    Autogenerate is not perfect — check column types, indexes, server_default.

# 4. Apply locally
alembic upgrade head

# 5. Commit the migration file alongside the model change.
```

## The baseline migration

`versions/0001_baseline.py` is a no-op marker: it stamps an empty schema as
revision `0001_baseline` so existing databases (created via `schema_sync`)
can be brought under Alembic control without re-creating anything. Run:

```bash
alembic stamp 0001_baseline
```

on any database that was previously created via `schema_sync.py`. After
that, all subsequent changes go through normal `alembic revision` /
`alembic upgrade` flow.

## Common commands

| Command | What it does |
|---|---|
| `alembic current` | Show current revision in this DB |
| `alembic history` | Show full migration history |
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Roll back the last migration |
| `alembic revision --autogenerate -m "msg"` | Generate from model diff |
| `alembic stamp head` | Mark DB as up-to-date without running |
