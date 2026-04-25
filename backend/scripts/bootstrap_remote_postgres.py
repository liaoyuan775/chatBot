from __future__ import annotations

import argparse
from urllib.parse import urlparse

import psycopg
from psycopg import sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create chatbot_dev/chatbot_prod and chatbot_app role on remote PostgreSQL.")
    parser.add_argument("--admin-dsn", required=True, help="postgresql://admin:pwd@host:port/postgres")
    parser.add_argument("--app-user", default="chatbot_app")
    parser.add_argument("--app-password", required=True)
    parser.add_argument("--dev-db", default="chatbot_dev")
    parser.add_argument("--prod-db", default="chatbot_prod")
    return parser.parse_args()


def ensure_not_default_db(name: str) -> None:
    if name in {"postgres", "template0", "template1"}:
        raise ValueError(f"Forbidden database name: {name}")


def main() -> None:
    args = parse_args()
    ensure_not_default_db(args.dev_db)
    ensure_not_default_db(args.prod_db)

    parsed = urlparse(args.admin_dsn)
    if parsed.path.lstrip("/") not in {"postgres", "chatbot_dev", "chatbot_prod"}:
        raise ValueError("Admin DSN should connect to a maintenance DB (usually postgres).")

    with psycopg.connect(args.admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", (args.app_user,))
            if not cur.fetchone():
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {};").format(
                        sql.Identifier(args.app_user),
                        sql.Literal(args.app_password),
                    )
                )

            for db_name in [args.dev_db, args.prod_db]:
                cur.execute(
                    sql.SQL("SELECT 1 FROM pg_database WHERE datname = {db};").format(db=sql.Literal(db_name))
                )
                exists = cur.fetchone()
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {} OWNER {};").format(sql.Identifier(db_name), sql.Identifier(args.app_user)))

            for db_name in [args.dev_db, args.prod_db]:
                db_dsn = args.admin_dsn.rsplit("/", 1)[0] + f"/{db_name}"
                with psycopg.connect(db_dsn, autocommit=True) as db_conn:
                    with db_conn.cursor() as db_cur:
                        db_cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                        db_cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                        db_cur.execute(
                            sql.SQL("GRANT CONNECT ON DATABASE {} TO {};").format(
                                sql.Identifier(db_name), sql.Identifier(args.app_user)
                            )
                        )
                        db_cur.execute(
                            sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {};").format(sql.Identifier(args.app_user))
                        )
                        db_cur.execute(
                            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {};").format(
                                sql.Identifier(args.app_user)
                            )
                        )

    print("Bootstrap finished. Created/verified role and databases:", args.dev_db, args.prod_db)


if __name__ == "__main__":
    main()
