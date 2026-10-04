import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .db_ops import conf_for_connector, get_db_type
from .storage import load_status, save_status


def pm2_name(file_name: str) -> str:
    base = Path(file_name).stem
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", base)
    return f"api_{safe}"


def _resolve_pm2_bin() -> str:
    env = os.environ.get("API_FACTORY_PM2_BIN", "").strip()
    candidates = []
    if env:
        candidates.append(env)
    candidates.append("/usr/local/bin/pm2")
    candidates.append("/home/datalake/.nvm/versions/node/v18.17.1/bin/pm2")
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        try:
            for d in sorted(nvm_root.iterdir(), reverse=True):
                candidates.append(str(d / "bin" / "pm2"))
        except Exception:
            pass
    candidates.extend(["/usr/local/bin/pm2", "/usr/bin/pm2", str(Path.home() / ".nvm/versions/node"), "pm2"])
    for c in candidates:
        if c == "pm2":
            try:
                r = subprocess.run(
                    ["bash", "-lc", "command -v pm2"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                path = (r.stdout or "").strip()
                if path and Path(path).exists():
                    return path
            except Exception:
                pass
            continue
        if Path(c).exists():
            return c
    return env or "pm2"


PM2_BIN = _resolve_pm2_bin()


def _run_pm2(args, timeout=30) -> Tuple[bool, str, str]:
    global PM2_BIN
    bin_path = PM2_BIN
    if not bin_path or bin_path == "pm2" or not Path(str(bin_path)).exists():
        bin_path = _resolve_pm2_bin()
        PM2_BIN = bin_path
    env = os.environ.copy()
    node_bin = str(Path(bin_path).parent) if bin_path and bin_path != "pm2" else ""
    if node_bin:
        env["PATH"] = node_bin + os.pathsep + env.get("PATH", "")
    cmd = [bin_path] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(config.SERVICES_DIR),
            env=env,
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode == 0, out.strip(), proc.stderr or ""
    except FileNotFoundError:
        return False, "", f"pm2 پیدا نشد ({bin_path})"
    except Exception as e:
        return False, "", str(e)


def pm2_jlist() -> dict:
    ok, out, _ = _run_pm2(["jlist"])
    try:
        start = out.find("[")
        end = out.rfind("]")
        data = json.loads(out[start : end + 1] if start >= 0 else (out or "[]"))
    except Exception:
        return {}
    result = {}
    for item in data if isinstance(data, list) else []:
        name = item.get("name")
        if not name:
            continue
        env = item.get("pm2_env") or {}
        result[name] = {
            "pm_id": item.get("pm_id"),
            "name": name,
            "status": env.get("status"),
            "pid": env.get("pid") or item.get("pid"),
            "restart_time": env.get("restart_time"),
            "pm_uptime": env.get("pm_uptime"),
        }
    return result


def pm2_is_online(file_name: str) -> bool:
    info = pm2_jlist().get(pm2_name(file_name)) or {}
    return (info.get("status") or "").lower() == "online"


def start_service(file_name: str) -> Tuple[bool, str]:
    script_path = str((config.SERVICES_DIR / file_name).resolve())
    if not (config.SERVICES_DIR / file_name).exists():
        return False, "فایل سرویس وجود ندارد"
    name = pm2_name(file_name)
    interpreter = config.resolve_pm2_interpreter()
    if not Path(interpreter).exists() and interpreter != "python3":
        return False, f"مفسر پایتون پیدا نشد: {interpreter}. export API_FACTORY_PM2_INTERPRETER=$(which python3)"
    # اگر از قبل آنلاین است، نیازی به خطای دوباره نیست
    if pm2_is_online(file_name):
        status = load_status()
        status.setdefault(file_name, {})
        info = pm2_jlist().get(name) or {}
        status[file_name]["pid"] = info.get("pid")
        status[file_name]["active"] = True
        save_status(status)
        return True, "سرویس از قبل در حال اجراست (PM2 online)"

    _run_pm2(["delete", name])
    ok, out, err = _run_pm2(
        [
            "start",
            script_path,
            "--name",
            name,
            "--interpreter",
            interpreter,
        ]
    )
    time.sleep(0.6)
    # گاهی PM2 خروجی خطا می‌دهد ولی پروسه بالا می‌آید
    online = pm2_is_online(file_name)
    status = load_status()
    status.setdefault(file_name, {})
    info = pm2_jlist().get(name) or {}
    if ok or online:
        status[file_name]["pid"] = info.get("pid")
        status[file_name]["active"] = True
        save_status(status)
        if online and not ok:
            return True, "سرویس اجرا شد (با هشدار PM2)"
        return True, "سرویس با PM2 اجرا شد"
    status[file_name]["active"] = False
    save_status(status)
    detail = (err or out or "خطا در اجرای PM2").strip()
    return False, detail + f" | interpreter={interpreter}"


def stop_service(file_name: str) -> Tuple[bool, str]:
    ok, out, err = _run_pm2(["stop", pm2_name(file_name)])
    status = load_status()
    if file_name in status:
        status[file_name]["active"] = False
        status[file_name]["pid"] = None
        save_status(status)
    return ok, out or err


def delete_service(file_name: str) -> Tuple[bool, str]:
    _run_pm2(["delete", pm2_name(file_name)])
    status = load_status()
    status.pop(file_name, None)
    save_status(status)
    path = config.SERVICES_DIR / file_name
    if path.exists():
        path.unlink()
    log_path = config.LOGS_DIR / f"{file_name}.log"
    if log_path.exists():
        log_path.unlink()
    return True, "حذف شد"


def sync_services_from_disk():
    status = load_status()
    changed = False
    if config.SERVICES_DIR.exists():
        for f in config.SERVICES_DIR.glob("*.py"):
            if f.name not in status:
                port = _extract_port(f.read_text(encoding="utf-8", errors="ignore"))
                status[f.name] = {
                    "port": port,
                    "url": f"http://{config.SERVER_IP}:{port}/" if port else "",
                    "pid": None,
                    "active": False,
                }
                changed = True
    if changed:
        save_status(status)
    return status


def _extract_port(code: str) -> Optional[int]:
    m = re.search(r"port\s*=\s*(\d+)", code)
    return int(m.group(1)) if m else None


def next_port() -> int:
    status = load_status()
    ports = [int(s.get("port") or 0) for s in status.values()]
    return max(ports + [5000]) + 1


def list_listening_ports() -> List[tuple]:
    rows = []
    try:
        out = subprocess.check_output(["ss", "-tulnp"], stderr=subprocess.DEVNULL).decode(
            errors="ignore"
        )
    except Exception:
        try:
            out = subprocess.check_output(
                ["netstat", "-tulnp"], stderr=subprocess.DEVNULL
            ).decode(errors="ignore")
        except Exception:
            return []
    for line in out.splitlines():
        if "LISTEN" not in line.upper():
            continue
        port = None
        for token in line.split():
            m = re.search(r":(\d+)$", token)
            if m:
                port = int(m.group(1))
        if port is None:
            continue
        pid = ""
        pname = ""
        m_pid = re.search(r"pid=(\d+)", line)
        if m_pid:
            pid = m_pid.group(1)
        m_name = re.search(r'"([^"]+)",pid=', line)
        if m_name:
            pname = m_name.group(1)
        rows.append((port, pid, pname))
    seen = {}
    for port, pid, pname in rows:
        if port not in seen:
            seen[port] = (port, pid, pname)
    return sorted(seen.values(), key=lambda x: x[0])


def update_service_port(file_name: str, new_port: int) -> bool:
    path = config.SERVICES_DIR / file_name
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    text2, n = re.subn(r"(app\.run\s*\([^)]*?port\s*=\s*)\d+", rf"\g<1>{int(new_port)}", text, count=1)
    if n == 0:
        text2, n = re.subn(r"(port\s*=\s*)\d+(\s*\))", rf"\g<1>{int(new_port)}\2", text, count=1)
    if n:
        path.write_text(text2, encoding="utf-8")
        return True
    return False


def read_log(file_name: str, lines: int = 200) -> str:
    path = config.LOGS_DIR / f"{file_name}.log"
    if path.exists():
        content = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(content[-lines:])
    ok, out, err = _run_pm2(["logs", pm2_name(file_name), "--nostream", "--lines", str(lines)])
    return out or err or "لاگی نیست"


def generate_service_code(
    *,
    db_conf: dict,
    main_table: str,
    joins: list,
    selected_fields: list,
    filter_field: str,
    time_field: str,
    use_pagination: bool,
    default_limit: int,
    default_offset: int,
    require_auth: bool,
    file_name: str,
    route: str,
    port: int,
) -> str:
    db_type = get_db_type(db_conf)

    def q_id(name):
        if db_type == "postgres":
            return '"' + str(name).replace('"', '""') + '"'
        return "`" + str(name).replace("`", "``") + "`"

    select_parts = []
    for fs in selected_fields:
        tb, c = fs.split(".", 1)
        alias = f"{tb}_{c}"
        select_parts.append(f"{q_id(tb)}.{q_id(c)} AS {q_id(alias)}")
    selected_sql = ", ".join(select_parts)
    from_sql = q_id(main_table)
    for j in joins:
        from_sql += (
            f" {j['type']} {q_id(j['table'])} ON "
            f"{q_id(main_table)}.{q_id(j['left_col'])} = "
            f"{q_id(j['table'])}.{q_id(j['right_col'])}"
        )
    select_stmt_lit = repr(f"SELECT {selected_sql} FROM {from_sql}")

    auth_code = ""
    if require_auth:
        auth_code = f"""
    key = request.headers.get('X-API-Key')
    k_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'api_keys.json')
    try:
        with open(k_path, 'r', encoding='utf-8') as f:
            all_keys = json.load(f)
            service_keys = all_keys.get("{file_name}", {{}})
        if key not in service_keys:
            return jsonify({{"error": "Unauthorized"}}), 401
    except Exception:
        return jsonify({{"error": "Security check failed"}}), 500
"""

    where_logic = []
    if filter_field and filter_field != "بدون فیلتر":
        if "." in filter_field:
            ft, fc = filter_field.split(".", 1)
        else:
            ft, fc = main_table, filter_field
        param_name = f"{ft}_{fc}"
        cond_lit = repr(f"{q_id(ft)}.{q_id(fc)}=%s")
        where_logic.append(
            f"if request.args.get({param_name!r}): cond.append({cond_lit}); p.append(request.args.get({param_name!r}))"
        )
    if time_field and time_field != "غیرفعال":
        if "." in time_field:
            tt, tc = time_field.split(".", 1)
        else:
            tt, tc = main_table, time_field
        cond_start = repr(f"{q_id(tt)}.{q_id(tc)}>=%s")
        cond_end = repr(f"{q_id(tt)}.{q_id(tc)}<=%s")
        where_logic.append(
            f"if request.args.get('start'): cond.append({cond_start}); p.append(request.args.get('start'))"
        )
        where_logic.append(
            f"if request.args.get('end'): cond.append({cond_end}); p.append(request.args.get('end'))"
        )
    where_code = "\n        ".join(where_logic)
    pagination_logic = ""
    if use_pagination:
        pagination_logic = f"""
        limit = request.args.get('limit', default={default_limit}, type=int)
        offset = request.args.get('offset', default={default_offset}, type=int)
        q += f' LIMIT {{limit}} OFFSET {{offset}}'
"""
    connect_conf = conf_for_connector(db_conf)
    if db_type == "postgres":
        imports = "import psycopg2\nfrom psycopg2.extras import RealDictCursor\nimport os, json, time, sqlite3"
        connect_block = f"""        c = psycopg2.connect(**{connect_conf})
        cur = c.cursor(cursor_factory=RealDictCursor)"""
    else:
        imports = "import mysql.connector, os, json, time, sqlite3"
        connect_block = f"""        c = mysql.connector.connect(**{connect_conf})
        cur = c.cursor(dictionary=True)"""

    return f'''from flask import Flask, jsonify, request, g
{imports}

app = Flask(__name__)

@app.before_request
def start_timer():
    g.start_time = time.time()

@app.after_request
def log_and_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    try:
        duration = (time.time() - g.start_time) * 1000
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'analytics.db')
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO api_logs (service, endpoint, status, duration, size) VALUES (?, ?, ?, ?, ?)',
            ("{file_name}", request.path, response.status_code, duration, len(response.data))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return response

@app.route("{route}")
def h():
{auth_code}
    try:
{connect_block}
        cond, p = [], []
        {where_code}
        q = {select_stmt_lit}
        if cond:
            q += " WHERE " + " AND ".join(cond)
{pagination_logic}
        cur.execute(q, tuple(p))
        res = cur.fetchall()
        cur.close()
        c.close()
        return jsonify(res)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port={port})
'''
