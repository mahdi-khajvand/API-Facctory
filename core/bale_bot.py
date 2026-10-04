"""Bale Messenger Bot — full control panel for API Factory.

Do NOT run this file directly:
  python -m uvicorn app:app --host 0.0.0.0 --port 8501

Polling starts automatically when Bale is enabled in the web panel.
Base API: https://tapi.bale.ai/bot<TOKEN>/<method>
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from core import config

BALE_API = "https://tapi.bale.ai/bot"
CONFIG_FILE = Path(config.BASE_DIR) / "bale_config.json"

_poll_stop = threading.Event()
_poll_thread: Optional[threading.Thread] = None
_offset = 0
_auth_sessions: dict = {}  # chat_id -> {"user": str, "ok": bool}
_auth_pending: dict = {}   # chat_id -> {"step": "user"|"pass", "username": str}
_seen_alarms: set = set()
_alert_stop = threading.Event()
_alert_thread = None

# Injected by app.py
_scan_alarms: Optional[Callable] = None
_list_services: Optional[Callable] = None
_start_svc: Optional[Callable] = None
_stop_svc: Optional[Callable] = None
_delete_svc: Optional[Callable] = None
_read_code: Optional[Callable] = None
_read_log: Optional[Callable] = None
_traffic_summary: Optional[Callable] = None


def bind_handlers(
    list_services,
    scan_alarms,
    start_svc,
    stop_svc,
    delete_svc,
    read_code,
    read_log,
    traffic_summary=None,
):
    global _list_services, _scan_alarms, _start_svc, _stop_svc, _delete_svc, _read_code, _read_log, _traffic_summary
    _list_services = list_services
    _scan_alarms = scan_alarms
    _start_svc = start_svc
    _stop_svc = stop_svc
    _delete_svc = delete_svc
    _read_code = read_code
    _read_log = read_log
    _traffic_summary = traffic_summary


def load_bale_config() -> dict:
    if not CONFIG_FILE.exists():
        return {
            "enabled": False,
            "token": "",
            "default_chat_id": "",
            "notify_alarms": True,
            "notify_service_down": True,
            "allowed_chat_ids": [],
            "polling": True,
            "panel_url": "",
        }
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {"enabled": False, "token": "", "default_chat_id": ""}
    data.setdefault("polling", True)
    return data


def save_bale_config(data: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _api(token: str, method: str, payload: Optional[dict] = None, timeout: int = 25) -> dict:
    url = f"{BALE_API}{token}/{method}"
    try:
        r = requests.post(url, json=payload or {}, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {"ok": False, "description": r.text[:300], "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def get_me(token: str) -> dict:
    return _api(token, "getMe", {})


def send_message(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "",
    reply_markup: Optional[dict] = None,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4000],
    }
    # Bale often shows raw HTML — only send parse_mode if explicitly requested
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _api(token, "sendMessage", payload)


def answer_callback(token: str, callback_query_id: str, text: str = "") -> dict:
    return _api(
        token,
        "answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text[:200]},
    )


def get_updates(token: str, offset: int = 0, timeout: int = 15) -> dict:
    return _api(token, "getUpdates", {"offset": offset, "timeout": timeout}, timeout=timeout + 10)


def notify(text: str, chat_id: Optional[str] = None) -> dict:
    cfg = load_bale_config()
    if not cfg.get("enabled") or not cfg.get("token"):
        return {"ok": False, "description": "Bale bot disabled or token missing"}
    cid = chat_id or cfg.get("default_chat_id")
    if not cid:
        return {"ok": False, "description": "chat_id missing"}
    return send_message(cfg["token"], cid, text)


# ---------- UI builders ----------

def panel_url() -> str:
    cfg = load_bale_config()
    return (cfg.get("panel_url") or "").strip()


def main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📋 سرویس‌ها", "callback_data": "menu:services"},
                {"text": "📊 ترافیک", "callback_data": "menu:traffic"},
            ],
            [
                {"text": "📈 داشبورد", "callback_data": "menu:dash"},
                {"text": "🚨 آلارم‌ها", "callback_data": "menu:alarms"},
            ],
            [
                {"text": "🔄 بروزرسانی", "callback_data": "menu:home"},
                {"text": "❓ راهنما", "callback_data": "menu:help"},
            ],
        ]
    }


def services_keyboard(services: list) -> dict:
    rows = []
    for s in services[:20]:
        name = s.get("name") or "?"
        flag = "🟢" if s.get("active") else "🔴"
        short = name if len(name) <= 40 else name[:37] + "..."
        rows.append([{"text": f"{flag} {short}", "callback_data": f"svc:{name}"}])
    rows.append([{"text": "🏠 منوی اصلی", "callback_data": "menu:home"}])
    return {"inline_keyboard": rows}


def service_actions_keyboard(name: str, active: bool) -> dict:
    toggle = (
        {"text": "⏹ توقف", "callback_data": f"stop:{name}"}
        if active
        else {"text": "▶️ اجرا", "callback_data": f"start:{name}"}
    )
    return {
        "inline_keyboard": [
            [toggle, {"text": "📄 کد", "callback_data": f"code:{name}"}],
            [
                {"text": "📋 لاگ", "callback_data": f"logs:{name}"},
                {"text": "🗑 حذف", "callback_data": f"delask:{name}"},
            ],
            [{"text": "⬅️ بازگشت به لیست", "callback_data": "menu:services"}],
        ]
    }


def delete_confirm_keyboard(name: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ بله، حذف شود", "callback_data": f"del:{name}"},
                {"text": "❌ انصراف", "callback_data": f"svc:{name}"},
            ]
        ]
    }


def home_text(services: list) -> str:
    on = sum(1 for s in services if s.get("active"))
    off = len(services) - on
    lines = [
        "⚡ API Factory Control",
        "",
        f"Total services: {len(services)}",
        f"🟢 Online: {on}   🔴 Stopped: {off}",
        "",
        "Choose from the menu below:",
    ]
    return "\n".join(lines)


def service_detail_text(s: dict) -> str:
    st = "🟢 Running" if s.get("active") else "🔴 Stopped"
    return (
        f"⚡ {s.get('name')}\n\n"
        f"Status: {st}\n"
        f"Port: {s.get('port') or '—'}\n"
        f"URL: {s.get('url') or '—'}\n"
    )


def text_bar(value: int, max_v: int, width: int = 12) -> str:
    if max_v <= 0:
        return "░" * width
    filled = int(round((value / max_v) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def traffic_text(summary: dict) -> str:
    t = summary.get("totals") or {}
    bys = summary.get("by_service") or []
    lines = [
        "📊 Traffic &amp; Latency",
        "",
        f"Requests: {t.get('requests', 0)}",
        f"Success: {t.get('success', 0)}   Fail: {t.get('fail', 0)}",
        f"Avg latency: {t.get('avg_ms', 0)} ms",
        "",
        "By service",
    ]
    max_c = max([x.get("count") or 0 for x in bys], default=1) or 1
    for x in bys[:12]:
        c = x.get("count") or 0
        lines.append(
            f"{text_bar(c, max_c)} {c}  "
            f"{x.get('service')}  "
            f"({x.get('avg_ms', '—')} ms)"
        )
    if not bys:
        lines.append("No traffic data yet")
    return "\n".join(lines)


def dash_text(services: list, summary: dict, alarms: list) -> str:
    on = sum(1 for s in services if s.get("active"))
    t = summary.get("totals") or {}
    return (
        "📈 Dashboard\n\n"
        f"Services: {len(services)} (🟢 {on} / 🔴 {len(services) - on})\n"
        f"Requests: {t.get('requests', 0)}\n"
        f"Success: {t.get('success', 0)} · Fail: {t.get('fail', 0)}\n"
        f"Avg latency: {t.get('avg_ms', 0)} ms\n"
        f"Open 5xx alarms: {len(alarms)}\n"
    )


def format_alarms(alarms: list) -> str:
    if not alarms:
        return "✅ No HTTP 5xx alarms found"
    lines = [f"🚨 Alarms ({len(alarms)})", ""]
    for a in alarms[:12]:
        lines.append(
            f"• {a.get('service')} · HTTP {a.get('code')} · {a.get('time') or '—'}\n"
            f"{(a.get('line') or '')[:100]}"
        )
    return "\n".join(lines)


def help_text() -> str:
    return (
        "❓ Help\n\n"
        "Use the buttons under messages, or type:\n"
        "/start — main menu\n"
        "/services — list APIs\n"
        "/status — same as services\n"
        "/alarms — HTTP 5xx\n"
        "/traffic — traffic chart (text)\n"
        "/dash — dashboard summary\n"
        "/help — this message\n"
    )


# ---------- command / callback handling ----------

def _find_service(name: str) -> Optional[dict]:
    if not _list_services:
        return None
    for s in _list_services() or []:
        if s.get("name") == name:
            return s
    return None


def _allowed(chat_id: Any, cfg: dict) -> bool:
    allowed = cfg.get("allowed_chat_ids") or []
    default_cid = str(cfg.get("default_chat_id") or "")
    if not allowed:
        return True
    return str(chat_id) in [str(x) for x in allowed] or str(chat_id) == default_cid


def send_home(token: str, chat_id: Any) -> None:
    services = (_list_services() if _list_services else []) or []
    send_message(token, chat_id, home_text(services), reply_markup=main_menu_keyboard())


def handle_text(token: str, chat_id: Any, text: str) -> None:
    low = (text or "").strip().lower()
    if low.startswith("/"):
        low = low.split("@", 1)[0].split()[0]

    if low in ("/start", "start", "/menu", "menu"):
        send_home(token, chat_id)
        return
    if low in ("/help", "help"):
        send_message(token, chat_id, help_text(), reply_markup=main_menu_keyboard())
        return
    if low in ("/services", "/status", "status", "services"):
        services = (_list_services() if _list_services else []) or []
        if not services:
            send_message(token, chat_id, "سرویسی ثبت نشده.", reply_markup=main_menu_keyboard())
            return
        send_message(
            token,
            chat_id,
            "📋 سرویس‌ها\nبرای مدیریت، یکی را انتخاب کنید:",
            reply_markup=services_keyboard(services),
        )
        return
    if low in ("/alarms", "alarms"):
        alarms = (_scan_alarms() if _scan_alarms else []) or []
        send_message(token, chat_id, format_alarms(alarms), reply_markup=main_menu_keyboard())
        return
    if low in ("/traffic", "traffic"):
        summary = (_traffic_summary() if _traffic_summary else {}) or {}
        send_message(token, chat_id, traffic_text(summary), reply_markup=main_menu_keyboard())
        return
    if low in ("/dash", "/dashboard", "dashboard"):
        services = (_list_services() if _list_services else []) or []
        summary = (_traffic_summary() if _traffic_summary else {}) or {}
        alarms = (_scan_alarms() if _scan_alarms else []) or []
        send_message(
            token,
            chat_id,
            dash_text(services, summary, alarms),
            reply_markup=main_menu_keyboard(),
        )
        return

    send_message(
        token,
        chat_id,
        "دستور ناشناخته. از منو استفاده کنید:",
        reply_markup=main_menu_keyboard(),
    )


def handle_callback(token: str, cq: dict) -> None:
    cq_id = cq.get("id")
    data = (cq.get("data") or "").strip()
    msg = cq.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id or not data:
        return

    def ack(txt: str = ""):
        if cq_id:
            answer_callback(token, cq_id, txt)

    if data == "menu:home":
        ack()
        send_home(token, chat_id)
        return
    if data == "menu:help":
        ack()
        send_message(token, chat_id, help_text(), reply_markup=main_menu_keyboard())
        return
    if data == "menu:services":
        ack()
        services = (_list_services() if _list_services else []) or []
        send_message(
            token,
            chat_id,
            "📋 سرویس‌ها\nیکی را انتخاب کنید:",
            reply_markup=services_keyboard(services),
        )
        return
    if data == "menu:alarms":
        ack()
        alarms = (_scan_alarms() if _scan_alarms else []) or []
        send_message(token, chat_id, format_alarms(alarms), reply_markup=main_menu_keyboard())
        return
    if data == "menu:traffic":
        ack()
        summary = (_traffic_summary() if _traffic_summary else {}) or {}
        send_message(token, chat_id, traffic_text(summary), reply_markup=main_menu_keyboard())
        return
    if data == "menu:dash":
        ack()
        services = (_list_services() if _list_services else []) or []
        summary = (_traffic_summary() if _traffic_summary else {}) or {}
        alarms = (_scan_alarms() if _scan_alarms else []) or []
        send_message(
            token,
            chat_id,
            dash_text(services, summary, alarms),
            reply_markup=main_menu_keyboard(),
        )
        return

    if data.startswith("svc:"):
        name = data[4:]
        s = _find_service(name)
        if not s:
            ack("Not found")
            send_message(token, chat_id, f"سرویس پیدا نشد: {name}")
            return
        ack()
        send_message(
            token,
            chat_id,
            service_detail_text(s),
            reply_markup=service_actions_keyboard(name, bool(s.get("active"))),
        )
        return

    if data.startswith("start:"):
        name = data[6:]
        if _start_svc:
            ok, msg_txt = _start_svc(name)
            ack("Started" if ok else "Failed")
            send_message(token, chat_id, f"{'✅' if ok else '❌'} اجرا: {name}\n{msg_txt}")
        s = _find_service(name) or {"name": name, "active": True}
        send_message(
            token,
            chat_id,
            service_detail_text(s),
            reply_markup=service_actions_keyboard(name, bool(s.get("active"))),
        )
        return

    if data.startswith("stop:"):
        name = data[5:]
        if _stop_svc:
            ok, msg_txt = _stop_svc(name)
            ack("Stopped" if ok else "Failed")
            send_message(token, chat_id, f"{'✅' if ok else '❌'} توقف: {name}\n{msg_txt}")
        s = _find_service(name) or {"name": name, "active": False}
        send_message(
            token,
            chat_id,
            service_detail_text(s),
            reply_markup=service_actions_keyboard(name, bool(s.get("active"))),
        )
        return

    if data.startswith("delask:"):
        name = data[7:]
        ack()
        send_message(
            token,
            chat_id,
            f"🗑 حذف شود؟\n{name}\nاین عمل برگشت‌ناپذیر است.",
            reply_markup=delete_confirm_keyboard(name),
        )
        return

    if data.startswith("del:"):
        name = data[4:]
        if _delete_svc:
            ok, msg_txt = _delete_svc(name)
            ack("Deleted" if ok else "Failed")
            send_message(token, chat_id, f"{'✅' if ok else '❌'} حذف: {name}\n{msg_txt}")
        services = (_list_services() if _list_services else []) or []
        send_message(
            token,
            chat_id,
            "📋 سرویس‌ها",
            reply_markup=services_keyboard(services),
        )
        return

    if data.startswith("code:"):
        name = data[5:]
        ack()
        if not _read_code:
            send_message(token, chat_id, "خواندن کد در دسترس نیست")
            return
        try:
            code = _read_code(name) or ""
        except Exception as e:
            send_message(token, chat_id, f"Error: {e}")
            return
        # Send in chunks (Bale message limit)
        header = f"📄 کد · {name}\n────────────────\n"
        chunk_size = 3500
        if len(code) <= chunk_size:
            send_message(
                token,
                chat_id,
                header + code[:3500],
                reply_markup=service_actions_keyboard(name, bool((_find_service(name) or {}).get("active"))),
            )
        else:
            send_message(token, chat_id, header + f"(حجم کد: {len(code)} کاراکتر — چند بخش ارسال می‌شود)")
            for i in range(0, min(len(code), chunk_size * 5), chunk_size):
                part = code[i : i + chunk_size]
                send_message(token, chat_id, part)
        return

    if data.startswith("logs:"):
        name = data[5:]
        ack()
        if not _read_log:
            send_message(token, chat_id, "خواندن لاگ در دسترس نیست")
            return
        try:
            logs = (_read_log(name) or "")[-3500:]
        except Exception as e:
            send_message(token, chat_id, f"Error: {e}")
            return
        send_message(
            token,
            chat_id,
            f"📋 لاگ · {name}\n────────────────\n{logs or '(خالی)'}",
            reply_markup=service_actions_keyboard(name, bool((_find_service(name) or {}).get("active"))),
        )
        return

    ack()


def _escape_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------- Bot login (username/password) ----------

SESSIONS_FILE = Path(config.BASE_DIR) / "bale_sessions.json"


def _load_sessions() -> dict:
    global _auth_sessions
    if SESSIONS_FILE.exists():
        try:
            _auth_sessions = {str(k): v for k, v in json.loads(SESSIONS_FILE.read_text(encoding="utf-8")).items()}
        except Exception:
            pass
    return _auth_sessions


def _save_sessions() -> None:
    try:
        SESSIONS_FILE.write_text(
            json.dumps(_auth_sessions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def is_authed(chat_id) -> bool:
    _load_sessions()
    s = _auth_sessions.get(str(chat_id))
    return bool(s and s.get("ok"))


def logout_chat(chat_id) -> None:
    _auth_sessions.pop(str(chat_id), None)
    _auth_pending.pop(str(chat_id), None)
    _save_sessions()


def verify_credentials(username: str, password: str) -> bool:
    try:
        if username == getattr(config, "LOGIN_USER", "admin") and password == getattr(config, "LOGIN_PASS", "admin"):
            return True
    except Exception:
        pass
    # users.json
    try:
        uf = Path(config.BASE_DIR) / "users.json"
        if uf.exists():
            data = json.loads(uf.read_text(encoding="utf-8"))
            for u in data.get("users", []):
                if u.get("username") == username and u.get("password") == password:
                    return True
    except Exception:
        pass
    return False


def ask_login(token: str, chat_id) -> None:
    _auth_pending[str(chat_id)] = {"step": "user", "username": ""}
    send_message(
        token,
        chat_id,
        "🔐 ورود به API Factory\n"
        "────────────────\n"
        "لطفاً نام کاربری را ارسال کنید.\n"
        "(همان یوزر پنل وب)",
    )


def handle_login_flow(token: str, chat_id, text: str) -> bool:
    """Return True if message consumed by login flow."""
    cid = str(chat_id)
    low = (text or "").strip().lower()
    if low in ("/logout", "logout", "خروج"):
        logout_chat(chat_id)
        send_message(token, chat_id, "خارج شدید. برای ورود دوباره /start بزنید.")
        return True

    if is_authed(chat_id):
        return False

    pending = _auth_pending.get(cid)
    if not pending:
        if low in ("/start", "start"):
            ask_login(token, chat_id)
            return True
        ask_login(token, chat_id)
        return True

    if pending.get("step") == "user":
        username = (text or "").strip()
        if not username or username.startswith("/"):
            send_message(token, chat_id, "نام کاربری معتبر بفرستید.")
            return True
        _auth_pending[cid] = {"step": "pass", "username": username}
        send_message(token, chat_id, f"کاربر: {username}\nحالا رمز عبور را بفرستید.")
        return True

    if pending.get("step") == "pass":
        password = (text or "").strip()
        username = pending.get("username") or ""
        if verify_credentials(username, password):
            _auth_sessions[cid] = {"ok": True, "user": username}
            _auth_pending.pop(cid, None)
            _save_sessions()
            send_message(token, chat_id, f"✅ خوش آمدید {username}")
            send_home(token, chat_id)
        else:
            _auth_pending[cid] = {"step": "user", "username": ""}
            send_message(token, chat_id, "❌ نام کاربری یا رمز اشتباه است.\nدوباره نام کاربری را بفرستید.")
        return True

    return True



def process_update(update: dict, *args, **kwargs) -> None:
    if args:
        global _scan_alarms, _list_services
        if len(args) >= 1 and args[0]:
            _scan_alarms = args[0]
        if len(args) >= 2 and args[1]:
            _list_services = args[1]

    cfg = load_bale_config()
    token = cfg.get("token") or ""
    if not token or not cfg.get("enabled"):
        return

    if update.get("callback_query"):
        cq = update["callback_query"]
        chat = ((cq.get("message") or {}).get("chat") or {})
        chat_id = chat.get("id")
        if not is_authed(chat_id):
            if cq.get("id"):
                answer_callback(token, cq["id"], "ابتدا وارد شوید")
            ask_login(token, chat_id)
            return
        if not _allowed(chat_id, cfg):
            if cq.get("id"):
                answer_callback(token, cq["id"], "Access denied")
            return
        handle_callback(token, cq)
        return

    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    if handle_login_flow(token, chat_id, text):
        return

    if not _allowed(chat_id, cfg):
        send_message(token, chat_id, "دسترسی مجاز نیست.")
        return
    handle_text(token, chat_id, text)



def _poll_loop() -> None:
    global _offset
    while not _poll_stop.is_set():
        cfg = load_bale_config()
        token = cfg.get("token") or ""
        if not cfg.get("enabled") or not token or not cfg.get("polling", True):
            time.sleep(3)
            continue
        res = get_updates(token, offset=_offset, timeout=12)
        if not res.get("ok"):
            time.sleep(3)
            continue
        for upd in res.get("result") or []:
            try:
                uid = int(upd.get("update_id") or 0)
                if uid >= _offset:
                    _offset = uid + 1
                process_update(upd)
            except Exception:
                pass


def _fingerprint(a: dict) -> str:
    return f"{a.get('service')}|{a.get('code')}|{a.get('line','')[:80]}|{a.get('time','')}"


def check_and_notify_alarms(force: bool = False) -> dict:
    """Scan alarms and push NEW ones to Bale (default chat + logged-in users)."""
    global _seen_alarms
    cfg = load_bale_config()
    if not cfg.get("enabled") or not cfg.get("token"):
        return {"ok": False, "message": "disabled"}
    if not cfg.get("notify_alarms", True) and not force:
        return {"ok": False, "message": "notify_alarms off"}

    alarms = (_scan_alarms() if _scan_alarms else []) or []
    new_ones = []
    for a in alarms:
        fp = _fingerprint(a)
        if fp not in _seen_alarms:
            _seen_alarms.add(fp)
            new_ones.append(a)

    # keep set bounded
    if len(_seen_alarms) > 5000:
        _seen_alarms = set(list(_seen_alarms)[-2000:])

    if not new_ones and not force:
        return {"ok": True, "sent": 0, "new": 0}

    to_send = new_ones if new_ones else alarms
    if not to_send:
        return {"ok": True, "sent": 0, "message": "no alarms"}

    text = "🚨 هشدار HTTP 5xx\n────────────────\n" + format_alarms(to_send)
    targets = set()
    if cfg.get("default_chat_id"):
        targets.add(str(cfg["default_chat_id"]))
    for cid, sess in _load_sessions().items():
        if sess.get("ok"):
            targets.add(str(cid))

    sent = 0
    for cid in targets:
        res = send_message(cfg["token"], cid, text)
        if res.get("ok"):
            sent += 1
    return {"ok": True, "sent": sent, "new": len(new_ones), "total": len(to_send)}


def _alert_loop() -> None:
    while not _alert_stop.is_set():
        try:
            cfg = load_bale_config()
            if cfg.get("enabled") and cfg.get("notify_alarms", True) and cfg.get("token"):
                check_and_notify_alarms(force=False)
        except Exception:
            pass
        # every 45 seconds
        _alert_stop.wait(45)


def start_alert_watcher() -> dict:
    global _alert_thread
    if _alert_thread and _alert_thread.is_alive():
        return {"ok": True, "running": True}
    _alert_stop.clear()
    _alert_thread = threading.Thread(target=_alert_loop, name="bale-alerts", daemon=True)
    _alert_thread.start()
    return {"ok": True, "running": True}


def start_polling(scan_alarms_fn=None, list_services_fn=None) -> dict:

    global _poll_thread, _scan_alarms, _list_services
    if scan_alarms_fn:
        _scan_alarms = scan_alarms_fn
    if list_services_fn:
        _list_services = list_services_fn
    if _poll_thread and _poll_thread.is_alive():
        return {"ok": True, "running": True, "message": "already running"}
    _poll_stop.clear()
    _poll_thread = threading.Thread(target=_poll_loop, name="bale-poll", daemon=True)
    _poll_thread.start()
    start_alert_watcher()
    return {"ok": True, "running": True, "message": "polling started"}


def stop_polling() -> dict:
    _poll_stop.set()
    return {"ok": True, "running": False}


def polling_status() -> dict:
    alive = bool(_poll_thread and _poll_thread.is_alive())
    return {"running": alive, "offset": _offset}


if __name__ == "__main__":
    print(
        "Do not run this file directly.\n"
        "Start the panel instead:\n"
        "  uvicorn app:app --host 0.0.0.0 --port 8501\n"
        "Then open Admin → Bale Bot and press «شروع گوش‌دادن»."
    )
