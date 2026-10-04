"""
API Factory Pro — FastAPI backend + modern SPA frontend
Run:  uvicorn app:app --host 0.0.0.0 --port 8501 --reload
"""
from __future__ import annotations

import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import config
from core.db_ops import get_named_config, list_columns, list_tables, test_db_conn
from core.services_mgr import (
    PM2_BIN,
    delete_service,
    generate_service_code,
    list_listening_ports,
    next_port,
    pm2_is_online,
    pm2_jlist,
    read_log,
    start_service,
    stop_service,
    sync_services_from_disk,
    update_service_port,
)
from core.storage import (
    load_db_configs,
    load_keys,
    load_status,
    save_db_configs,
    save_keys,
    save_status,
)

app = FastAPI(title="API Factory Pro", version="2.0.0")
STATIC = Path(__file__).parent / "static"

# simple token store
_TOKENS: Dict[str, float] = {}


def _init_analytics():
    try:
        conn = sqlite3.connect(config.ANALYTICS_DB)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT, endpoint TEXT, status INTEGER,
            duration REAL, size INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


_init_analytics()
sync_services_from_disk()


def require_auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")
    token = authorization.split(" ", 1)[1]
    exp = _TOKENS.get(token)
    if not exp or exp < time.time():
        _TOKENS.pop(token, None)
        raise HTTPException(401, "Session expired")
    return token


# ---------- models ----------
class BaleConfigIn(BaseModel):
    enabled: bool = False
    token: str = ""
    default_chat_id: str = ""
    notify_alarms: bool = True
    notify_service_down: bool = True
    allowed_chat_ids: list = []
    polling: bool = True
    panel_url: str = ""


class BaleTestIn(BaseModel):
    chat_id: str = ""
    text: str = "سلام از API Factory 👋"


class UserIn(BaseModel):

    username: str
    password: str
    role: str = "viewer"
    permissions: list = []


class LoginIn(BaseModel):

    username: str
    password: str


class DbConfigIn(BaseModel):
    label: str
    db_type: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str


class CreateServiceIn(BaseModel):
    db_label: str
    main_table: str
    joins: List[dict] = Field(default_factory=list)
    fields: List[str]
    filter_field: str = "بدون فیلتر"
    time_field: str = "غیرفعال"
    use_pagination: bool = True
    default_limit: int = 100
    default_offset: int = 0
    require_auth: bool = False
    name: str
    route: str = "/api/data"


class ManualServiceIn(BaseModel):
    name: str
    route_example: str = "/api/custom"
    code: str


class PortChangeIn(BaseModel):
    password: str
    port: int


class KeyIn(BaseModel):
    service: str
    key_name: str
    key_value: Optional[str] = None


# ---------- auth ----------
@app.post("/api/login")
def login(body: LoginIn):
    # built-in
    if body.username == config.LOGIN_USER and body.password == config.LOGIN_PASS:
        token = secrets.token_urlsafe(32)
        _TOKENS[token] = time.time() + 86400 * 7
        return {"token": token, "user": body.username, "role": "admin"}
    # users.json
    try:
        data = _load_users()
        for u in data.get("users", []):
            if u.get("username") == body.username and u.get("password") == body.password:
                token = secrets.token_urlsafe(32)
                _TOKENS[token] = time.time() + 86400 * 7
                return {"token": token, "user": body.username, "role": u.get("role", "viewer")}
    except Exception:
        pass
    raise HTTPException(401, "نام کاربری یا رمز اشتباه است")


@app.get("/api/me")
def me(_: str = Depends(require_auth)):
    return {"user": config.LOGIN_USER}


# ---------- dashboard ----------
@app.get("/api/summary")
def summary(_: str = Depends(require_auth)):
    status = sync_services_from_disk()
    active = sum(1 for f in status if pm2_is_online(f))
    total = len(status)
    reqs = 0
    try:
        conn = sqlite3.connect(config.ANALYTICS_DB)
        reqs = conn.execute("SELECT COUNT(*) FROM api_logs").fetchone()[0]
        conn.close()
    except Exception:
        pass
    return {
        "total_services": total,
        "active": active,
        "stopped": total - active,
        "requests": reqs,
        "pm2_bin": PM2_BIN,
        "interpreter": config.PM2_INTERPRETER,
        "services_dir": str(config.SERVICES_DIR),
        "server_ip": config.SERVER_IP,
    }


# ---------- db configs ----------
@app.get("/api/db-configs")
def get_db_configs(_: str = Depends(require_auth)):
    raw = load_db_configs()
    safe = {}
    for k, v in raw.items():
        item = dict(v)
        if "password" in item:
            item["password"] = "••••••" if item["password"] else ""
        safe[k] = item
    return safe


@app.post("/api/db-configs")
def add_db_config(body: DbConfigIn, _: str = Depends(require_auth)):
    conf = {
        "db_type": "postgres" if body.db_type.lower().startswith("post") else "mysql",
        "host": body.host,
        "port": int(body.port),
        "user": body.user,
        "password": body.password,
        "database": body.database,
    }
    ok, msg = test_db_conn(conf)
    if not ok:
        raise HTTPException(400, msg)
    allc = load_db_configs()
    allc[body.label] = conf
    save_db_configs(allc)
    return {"ok": True, "message": msg}


@app.delete("/api/db-configs/{label}")
def del_db_config(label: str, _: str = Depends(require_auth)):
    allc = load_db_configs()
    allc.pop(label, None)
    save_db_configs(allc)
    return {"ok": True}


@app.get("/api/db-configs/{label}/tables")
def tables(label: str, _: str = Depends(require_auth)):
    from urllib.parse import unquote
    label = unquote(label)
    try:
        conf = get_named_config(label)
        tabs = list_tables(conf)
        return {"tables": tabs, "count": len(tabs), "label": label}
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, f"خطا در خواندن جداول: {e}")


@app.get("/api/db-configs/{label}/columns/{table}")
def columns(label: str, table: str, _: str = Depends(require_auth)):
    from urllib.parse import unquote
    label, table = unquote(label), unquote(table)
    try:
        conf = get_named_config(label)
        cols = list_columns(conf, table)
        return {"columns": cols, "count": len(cols), "table": table}
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, f"خطا در خواندن ستون‌ها: {e}")


@app.get("/api/db/meta")
def db_meta(label: str, table: str = "", _: str = Depends(require_auth)):
    """مسیر پایدار با querystring — برای نام‌های خاص."""
    try:
        conf = get_named_config(label)
        if table:
            return {"columns": list_columns(conf, table), "label": label, "table": table}
        return {"tables": list_tables(conf), "label": label}
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------- services ----------
@app.get("/api/services")
def services(_: str = Depends(require_auth)):
    status = sync_services_from_disk()
    pm2 = pm2_jlist()
    out = []
    for name, info in status.items():
        online = pm2_is_online(name)
        from core.services_mgr import pm2_name
        out.append(
            {
                "name": name,
                "port": info.get("port"),
                "url": info.get("url"),
                "active": online,
                "pid": info.get("pid"),
                "pm2": pm2.get(pm2_name(name)),
            }
        )
    return out


@app.post("/api/services/create")
def create_service(body: CreateServiceIn, _: str = Depends(require_auth)):
    if not body.name.strip():
        raise HTTPException(400, "نام سرویس لازم است")
    if not body.fields:
        raise HTTPException(400, "حداقل یک فیلد انتخاب کنید")
    conf = get_named_config(body.db_label)
    f_file = body.name if body.name.endswith(".py") else f"{body.name}.py"
    port = next_port()
    code = generate_service_code(
        db_conf=conf,
        main_table=body.main_table,
        joins=body.joins or [],
        selected_fields=body.fields,
        filter_field=body.filter_field,
        time_field=body.time_field,
        use_pagination=body.use_pagination,
        default_limit=body.default_limit,
        default_offset=body.default_offset,
        require_auth=body.require_auth,
        file_name=f_file,
        route=body.route or "/api/data",
        port=port,
    )
    path = config.SERVICES_DIR / f_file
    path.write_text(code, encoding="utf-8")
    status = load_status()
    preview = body.route or "/api/data"
    status[f_file] = {
        "port": port,
        "url": f"http://{config.SERVER_IP}:{port}{preview}",
        "pid": None,
        "active": False,
    }
    save_status(status)
    ok, msg = start_service(f_file)
    return {"ok": ok, "file": f_file, "port": port, "url": status[f_file]["url"], "message": msg}



@app.post("/api/services/create-manual")
def create_service_manual(body: ManualServiceIn, _: str = Depends(require_auth)):
    import re
    from urllib.parse import urlparse

    if not body.name.strip():
        raise HTTPException(400, "نام سرویس لازم است")
    if not (body.code or "").strip():
        raise HTTPException(400, "کد خالی است")
    f_file = body.name if body.name.endswith(".py") else f"{body.name}.py"
    port = next_port()
    example = (body.route_example or "/api/custom").strip()
    if example.startswith(("http://", "https://")):
        parsed = urlparse(example)
    else:
        if not example.startswith("/"):
            example = "/" + example
        parsed = urlparse(example)
    route_path = parsed.path or "/"
    query = parsed.query
    final_url = f"http://{config.SERVER_IP}:{port}{route_path}"
    if query:
        final_url += f"?{query}"

    code = body.code
    code = re.sub(
        r'if\s+__name__\s*==\s*[\'\"]__main__[\'\"]\s*:\s*[\r\n]+(?:[ \t]+.*[\r\n]*)*',
        "",
        code,
        flags=re.MULTILINE,
    )
    code = re.sub(r"app\.run\s*\([^\)]*\)", "", code, flags=re.MULTILINE | re.DOTALL)
    final_code = code.rstrip() + f"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port={port})
"""
    path = config.SERVICES_DIR / f_file
    path.write_text(final_code, encoding="utf-8")
    status = load_status()
    status[f_file] = {"port": port, "url": final_url, "pid": None, "active": False}
    save_status(status)
    ok, msg = start_service(f_file)
    return {"ok": ok, "file": f_file, "port": port, "url": final_url, "message": msg}


@app.post("/api/services/{name}/start")
def svc_start(name: str, _: str = Depends(require_auth)):
    ok, msg = start_service(name)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@app.post("/api/services/{name}/stop")
def svc_stop(name: str, _: str = Depends(require_auth)):
    ok, msg = stop_service(name)
    return {"ok": ok, "message": msg}


@app.delete("/api/services/{name}")
def svc_delete(name: str, _: str = Depends(require_auth)):
    ok, msg = delete_service(name)
    return {"ok": ok, "message": msg}


@app.get("/api/services/{name}/logs")
def svc_logs(name: str, _: str = Depends(require_auth)):
    return {"logs": read_log(name)}


@app.get("/api/services/{name}/code")
def svc_code(name: str, _: str = Depends(require_auth)):
    path = config.SERVICES_DIR / name
    if not path.exists():
        raise HTTPException(404, "یافت نشد")
    return {"code": path.read_text(encoding="utf-8", errors="ignore")}


class SaveCodeIn(BaseModel):
    code: str


@app.put("/api/services/{name}/code")
def svc_save_code(name: str, body: SaveCodeIn, _: str = Depends(require_auth)):
    path = config.SERVICES_DIR / name
    if not path.exists():
        raise HTTPException(404, "یافت نشد")
    path.write_text(body.code or "", encoding="utf-8")
    ok, msg = start_service(name)
    return {"ok": ok, "message": msg}


@app.post("/api/services/{name}/port")
def svc_port(name: str, body: PortChangeIn, _: str = Depends(require_auth)):
    if body.password != config.PORT_CHANGE_PASSWORD:
        raise HTTPException(403, "رمز اشتباه است")
    stop_service(name)
    ok = update_service_port(name, int(body.port))
    status = load_status()
    status.setdefault(name, {})
    old_url = status[name].get("url") or ""
    status[name]["port"] = int(body.port)
    if old_url:
        import re

        status[name]["url"] = re.sub(r":\d+", f":{int(body.port)}", old_url, count=1)
    else:
        status[name]["url"] = f"http://{config.SERVER_IP}:{int(body.port)}/"
    status[name]["active"] = False
    status[name]["pid"] = None
    save_status(status)
    return {"ok": ok, "port": body.port}


# ---------- ports ----------
@app.get("/api/ports")
def ports(_: str = Depends(require_auth)):
    listening = list_listening_ports()
    status = load_status()
    service_by_port = {}
    for fname, info in status.items():
        try:
            p = int(info.get("port") or 0)
        except Exception:
            continue
        if p:
            service_by_port[p] = fname
    used = sorted({p for p, _, _ in listening} | set(service_by_port.keys()))
    free = [p for p in range(5000, 5101) if p not in used]
    rows = []
    listen_map = {p: (pid, pname) for p, pid, pname in listening}
    for port in sorted(set(listen_map) | set(service_by_port)):
        pid, pname = listen_map.get(port, ("", ""))
        svc = service_by_port.get(port)
        rows.append(
            {
                "port": port,
                "status": "LISTEN" if port in listen_map else "registered",
                "pid": pid or None,
                "process": pname or None,
                "service": svc,
                "url": f"http://{config.SERVER_IP}:{port}/" if svc else None,
            }
        )
    return {"rows": rows, "free": free[:60], "free_count": len(free)}


# ---------- keys ----------
@app.get("/api/keys")
def get_keys(_: str = Depends(require_auth)):
    return load_keys()


@app.post("/api/keys")
def add_key(body: KeyIn, _: str = Depends(require_auth)):
    keys = load_keys()
    keys.setdefault(body.service, {})
    val = body.key_value or secrets.token_urlsafe(24)
    keys[body.service][body.key_name] = val
    save_keys(keys)
    return {"ok": True, "key": val}


@app.delete("/api/keys/{service}/{key_name}")
def del_key(service: str, key_name: str, _: str = Depends(require_auth)):
    keys = load_keys()
    if service in keys:
        keys[service].pop(key_name, None)
        if not keys[service]:
            keys.pop(service, None)
        save_keys(keys)
    return {"ok": True}


# ---------- analytics ----------
@app.get("/api/analytics")
def analytics(_: str = Depends(require_auth)):
    try:
        conn = sqlite3.connect(config.ANALYTICS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM api_logs ORDER BY id DESC LIMIT 500"
        ).fetchall()
        conn.close()
        data = [dict(r) for r in rows]
    except Exception:
        data = []
    return {"logs": data}


# ---------- proxy fetch for BI ----------
@app.get("/api/proxy-fetch")
def proxy_fetch(url: str, api_key: str = "", _: str = Depends(require_auth)):
    try:
        headers = {"X-API-Key": api_key} if api_key else {}
        r = requests.get(url, headers=headers, timeout=30)
        return {"status": r.status_code, "data": r.json() if r.ok else r.text}
    except Exception as e:
        raise HTTPException(400, str(e))




# ---------- users ----------
def _load_users():
    path = config.USERS_FILE
    if not path.exists():
        default = {
            "users": [
                {"username": config.LOGIN_USER, "password": config.LOGIN_PASS, "role": "admin", "permissions": ["*"]}
            ]
        }
        path.write_text(__import__("json").dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
        return default
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def _save_users(data):
    import json
    config.USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/api/users")
def list_users(_: str = Depends(require_auth)):
    data = _load_users()
    safe = []
    for u in data.get("users", []):
        safe.append({
            "username": u.get("username"),
            "role": u.get("role", "viewer"),
            "permissions": u.get("permissions") or [],
        })
    return {"users": safe}


@app.post("/api/users")
def create_user(body: UserIn, _: str = Depends(require_auth)):
    username = (body.username or "").strip()
    password = body.password or ""
    role = (body.role or "viewer").strip()
    permissions = body.permissions or []
    if not username or not password:
        raise HTTPException(400, "username و password لازم است")
    data = _load_users()
    if any(u.get("username") == username for u in data.get("users", [])):
        raise HTTPException(400, "این کاربر وجود دارد")
    data.setdefault("users", []).append({
        "username": username,
        "password": password,
        "role": role,
        "permissions": permissions if isinstance(permissions, list) else [permissions],
    })
    _save_users(data)
    return {"ok": True, "message": "کاربر ساخته شد"}


@app.delete("/api/users/{username}")
def delete_user(username: str, _: str = Depends(require_auth)):
    data = _load_users()
    users = data.get("users") or []
    if username == config.LOGIN_USER:
        raise HTTPException(400, "کاربر پیش‌فرض سیستم قابل حذف نیست")
    data["users"] = [u for u in users if u.get("username") != username]
    _save_users(data)
    return {"ok": True}


@app.get("/api/analytics/summary")
def analytics_summary(_: str = Depends(require_auth)):
    return _analytics_summary_data()






# ---------- Bale bot ----------
from core import bale_bot as bale


@app.get("/api/bale/config")
def bale_get_config(_: str = Depends(require_auth)):
    cfg = bale.load_bale_config()
    token = cfg.get("token") or ""
    masked = (token[:6] + "…" + token[-4:]) if len(token) > 12 else ("••••" if token else "")
    out = dict(cfg)
    out["token_masked"] = masked
    out["token_set"] = bool(token)
    out.pop("token", None)
    return out


@app.post("/api/bale/config")
def bale_save_config(body: BaleConfigIn, _: str = Depends(require_auth)):
    prev = bale.load_bale_config()
    data = body.dict()
    if not (data.get("token") or "").strip():
        data["token"] = prev.get("token") or ""
    bale.save_bale_config(data)
    return {"ok": True, "message": "تنظیمات بله ذخیره شد"}


@app.post("/api/bale/test")
def bale_test(body: BaleTestIn, _: str = Depends(require_auth)):
    cfg = bale.load_bale_config()
    token = cfg.get("token") or ""
    if not token:
        raise HTTPException(400, "ابتدا توکن ربات را ذخیره کنید")
    chat_id = (body.chat_id or cfg.get("default_chat_id") or "").strip()
    if not chat_id:
        raise HTTPException(400, "chat_id لازم است")
    res = bale.send_message(token, chat_id, body.text or "سلام از API Factory")
    if not res.get("ok"):
        raise HTTPException(400, res.get("description") or str(res))
    return {"ok": True, "result": res}


@app.post("/api/bale/verify")
def bale_verify(_: str = Depends(require_auth)):
    cfg = bale.load_bale_config()
    token = cfg.get("token") or ""
    if not token:
        raise HTTPException(400, "توکن خالی است")
    res = bale.get_me(token)
    if not res.get("ok"):
        raise HTTPException(400, res.get("description") or "توکن نامعتبر")
    return {"ok": True, "bot": res.get("result")}



def _scan_http5xx_alarms():
    """Find real HTTP 5xx from text logs AND analytics.db."""
    import re as _re
    import sqlite3
    from core.services_mgr import sync_services_from_disk

    alarms = []
    pat = _re.compile(
        r"(?:"
        r"HTTP/\d\.\d[\"'\s]+(5\d\d)\b"
        r"|status[=:\s\"']+(5\d\d)\b"
        r"|(5\d\d)\s+(?:Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout|ERROR)"
        r"|\"(?:GET|POST|PUT|DELETE|PATCH)\s+[^\"]+\"\s+(5\d\d)\b"
        r"|\b(5\d\d)\s+ERROR\b"
        r"|ERROR.*?status\D+(5\d\d)"
        r")",
        _re.I,
    )
    ts_pat = _re.compile(
        r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
        r"|\d{2}/\w{3}/\d{4}[ :]\d{2}:\d{2}:\d{2}"
        r"|\d{2}:\d{2}:\d{2})"
    )

    try:
        status = sync_services_from_disk()
    except Exception:
        status = {}

    for name in list(status.keys()):
        try:
            candidates = [
                config.LOGS_DIR / f"{name}.log",
                config.LOGS_DIR / name,
                config.LOGS_DIR / str(name).replace(".py", ".log"),
            ]
            logs = ""
            for log_path in candidates:
                if log_path.exists():
                    logs = log_path.read_text(encoding="utf-8", errors="ignore")
                    break
            for ln in logs.splitlines()[-800:]:
                m = pat.search(ln)
                if not m:
                    continue
                code = next((g for g in m.groups() if g and str(g).startswith("5")), "500")
                tm = "—"
                tsm = ts_pat.search(ln)
                if tsm:
                    tm = tsm.group(1)
                alarms.append({
                    "service": name,
                    "code": str(code),
                    "time": tm,
                    "line": ln.strip()[:220],
                    "source": "log",
                })
        except Exception:
            pass

    try:
        conn = sqlite3.connect(str(config.ANALYTICS_DB))
        try:
            rows = conn.execute(
                "SELECT service, endpoint, status, ts FROM api_logs "
                "WHERE CAST(status AS INTEGER) >= 500 ORDER BY id DESC LIMIT 100"
            ).fetchall()
        except Exception:
            try:
                rows = conn.execute(
                    "SELECT service, endpoint, status, id FROM api_logs "
                    "WHERE CAST(status AS INTEGER) >= 500 ORDER BY id DESC LIMIT 100"
                ).fetchall()
            except Exception:
                rows = []
        for r in rows:
            try:
                svc, ep, st = r[0], r[1], r[2]
                tm = str(r[3]) if len(r) > 3 and r[3] is not None else "—"
                alarms.append({
                    "service": svc or "unknown",
                    "code": str(st),
                    "time": tm,
                    "line": f"status={st} endpoint={ep}",
                    "source": "db",
                })
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    seen = set()
    out = []
    for item in alarms:
        key = (item.get("service"), item.get("code"), item.get("line"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out



@app.post("/api/bale/webhook")
async def bale_webhook(request: Request):
    """Inbound updates from Bale (if webhook is set)."""
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")
    bale.process_update(update, _scan_http5xx_alarms, _list_services_for_bale)
    return {"ok": True}


def _list_services_for_bale():
    from core.services_mgr import sync_services_from_disk, pm2_is_online
    status = sync_services_from_disk()
    out = []
    for name, info in status.items():
        out.append({
            "name": name,
            "port": info.get("port"),
            "url": info.get("url"),
            "active": pm2_is_online(name),
        })
    return out


@app.post("/api/bale/polling/start")
def bale_poll_start(_: str = Depends(require_auth)):
    _bind_bale_handlers()
    return bale.start_polling(_scan_http5xx_alarms, _list_services_for_bale)


@app.post("/api/bale/polling/stop")
def bale_poll_stop(_: str = Depends(require_auth)):
    return bale.stop_polling()


@app.get("/api/bale/polling/status")
def bale_poll_status(_: str = Depends(require_auth)):
    return bale.polling_status()


@app.post("/api/bale/notify-alarms")
def bale_notify_alarms(_: str = Depends(require_auth)):
    _bind_bale_handlers()
    return bale.check_and_notify_alarms(force=True)






def _analytics_summary_data():
    """Shared traffic summary for web + Bale bot."""
    import sqlite3
    out = {
        "by_service": [],
        "by_status": [],
        "timeline": [],
        "totals": {"requests": 0, "success": 0, "fail": 0, "avg_ms": 0},
    }
    try:
        conn = sqlite3.connect(config.ANALYTICS_DB)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT COUNT(*) c, AVG(duration_ms) avg_ms, "
                "SUM(CASE WHEN status < 400 THEN 1 ELSE 0 END) ok, "
                "SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) fail FROM api_logs"
            ).fetchone()
            if rows:
                out["totals"] = {
                    "requests": rows["c"] or 0,
                    "success": rows["ok"] or 0,
                    "fail": rows["fail"] or 0,
                    "avg_ms": round(rows["avg_ms"] or 0, 1),
                }
        except Exception:
            pass
        try:
            for r in conn.execute(
                "SELECT service, COUNT(*) c, AVG(duration_ms) avg_ms, "
                "SUM(CASE WHEN status < 400 THEN 1 ELSE 0 END) ok, "
                "SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) fail "
                "FROM api_logs GROUP BY service ORDER BY c DESC LIMIT 20"
            ):
                out["by_service"].append({
                    "service": r[0] or "unknown",
                    "count": r[1],
                    "avg_ms": round(r[2] or 0, 1),
                    "ok": r[3] or 0,
                    "fail": r[4] or 0,
                })
        except Exception:
            pass
        try:
            for r in conn.execute(
                "SELECT status, COUNT(*) c FROM api_logs GROUP BY status ORDER BY c DESC"
            ):
                out["by_status"].append({"status": r[0], "count": r[1]})
        except Exception:
            pass
        conn.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def _bind_bale_handlers():
    from core.services_mgr import start_service, stop_service, delete_service, read_log

    def _read_code(name: str) -> str:
        path = config.SERVICES_DIR / name
        if not path.exists() and not name.endswith(".py"):
            path = config.SERVICES_DIR / f"{name}.py"
        if not path.exists():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8", errors="ignore")

    bale.bind_handlers(
        list_services=_list_services_for_bale,
        scan_alarms=_scan_http5xx_alarms,
        start_svc=start_service,
        stop_svc=stop_service,
        delete_svc=delete_service,
        read_code=_read_code,
        read_log=read_log,
        traffic_summary=_analytics_summary_data,
    )


@app.on_event("startup")
def _bale_autostart_polling():
    try:
        _bind_bale_handlers()
        cfg = bale.load_bale_config()
        if cfg.get("enabled") and cfg.get("token") and cfg.get("polling", True):
            bale.start_polling(_scan_http5xx_alarms, _list_services_for_bale)
        if cfg.get("enabled") and cfg.get("token") and cfg.get("notify_alarms", True):
            bale.start_alert_watcher()
    except Exception:
        pass


# ---------- static SPA ----------
# ---------- static SPA ----------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8501, reload=True)
