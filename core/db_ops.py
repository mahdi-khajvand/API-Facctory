from typing import List, Tuple

from .storage import load_db_configs


def get_db_type(conf: dict) -> str:
    return (conf.get("db_type") or "mysql").lower()


def conf_for_connector(conf: dict) -> dict:
    clean = {k: v for k, v in conf.items() if k != "db_type"}
    if get_db_type(conf) == "postgres":
        if "database" in clean and "dbname" not in clean:
            clean = dict(clean)
            clean["dbname"] = clean.pop("database")
    return clean


def test_db_conn(conf: dict) -> Tuple[bool, str]:
    try:
        if get_db_type(conf) == "postgres":
            import psycopg2

            c = psycopg2.connect(**conf_for_connector(conf))
            c.close()
        else:
            import mysql.connector

            c = mysql.connector.connect(**conf_for_connector(conf))
            c.close()
        return True, "اتصال موفق"
    except Exception as e:
        return False, str(e)


def list_tables(conf: dict) -> List[str]:
    if get_db_type(conf) == "postgres":
        import psycopg2

        c = psycopg2.connect(**conf_for_connector(conf))
        cur = c.cursor()
        cur.execute(
            """
            SELECT table_schema || '.' || table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """
        )
        raw = [r[0] for r in cur.fetchall()]
        # اگر همه public هستند، نام ساده برگردان
        rows = []
        for name in raw:
            if name.startswith("public."):
                rows.append(name.split(".", 1)[1])
            else:
                rows.append(name)
        cur.close()
        c.close()
        return rows
    import mysql.connector

    c = mysql.connector.connect(**conf_for_connector(conf))
    cur = c.cursor()
    cur.execute("SHOW TABLES")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    c.close()
    return rows


def list_columns(conf: dict, table: str) -> List[str]:
    schema = None
    tname = table
    if "." in table and get_db_type(conf) == "postgres":
        schema, tname = table.split(".", 1)

    if get_db_type(conf) == "postgres":
        import psycopg2

        c = psycopg2.connect(**conf_for_connector(conf))
        cur = c.cursor()
        if schema:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, tname),
            )
        else:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (tname,),
            )
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        c.close()
        return rows
    import mysql.connector

    c = mysql.connector.connect(**conf_for_connector(conf))
    cur = c.cursor()
    # escape backticks in table name
    safe = str(tname).replace("`", "``")
    cur.execute(f"SHOW COLUMNS FROM `{safe}`")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    c.close()
    return rows


def get_named_config(name: str) -> dict:
    confs = load_db_configs()
    if name not in confs:
        raise KeyError(f"دیتابیس «{name}» یافت نشد")
    return confs[name]
