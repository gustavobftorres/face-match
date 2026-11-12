"""Apply numbered SQL migrations atomically, once, using a dedicated owner URL."""
import os
from pathlib import Path

import psycopg


def migrate(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(759346182)")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            for path in sorted((Path(__file__).parent / 'migrations').glob('[0-9]*.sql')):
                if connection.execute('SELECT 1 FROM schema_migrations WHERE name = %s', (path.name,)).fetchone():
                    continue
                connection.execute(path.read_text())
                connection.execute('INSERT INTO schema_migrations (name) VALUES (%s)', (path.name,))


if __name__ == '__main__':
    migrate(os.environ['DATABASE_URL'])
