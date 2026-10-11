#!/usr/bin/env python3
"""12306 Desktop Backend — HTTP JSON API wrapping client.KyfwClient.

Run: python server.py --port 37891 [--cookie-file PATH]
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sys
import threading
import time
import traceback
from datetime import datetime
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from client import KyfwClient  # noqa: E402

SEAT_LABELS: dict[str, str] = {
    "9": "商务座", "P": "特等座", "D": "优选一等座", "M": "一等座", "O": "二等座",
    "S": "二等包座", "6": "高级软卧", "A": "高级动卧", "4": "软卧", "F": "动卧",
    "I": "一等卧", "3": "硬卧", "J": "二等卧", "2": "软座", "1": "硬座",
    "W": "无座", "H": "其他",
}
SEAT_ROW_FIELDS: dict[str, str] = {
    "9": "business", "P": "special_class", "D": "premium_first_class",
    "M": "first_class", "O": "second_class", "S": "second_class_compartment",
    "6": "deluxe_soft_sleeper", "4": "soft_sleeper", "F": "dynamic_sleeper",
    "3": "hard_sleeper", "2": "soft_seat", "1": "hard_seat",
    "W": "no_seat", "H": "other",
}
MAX_LOGS = 300

_lock = threading.RLock()
_client_opts: dict = {"cookie_file": "", "timeout": 15}

MAX_ACCOUNTS = 6
MAX_GRAB_WORKERS = 180  # 6 账号 × 30 线程
_accounts: list[dict] = []
_clients: dict[str, KyfwClient] = {}
_primary_id: str = ""
_accounts_file: Path | None = None
_acct_status_cache: dict[str, tuple[float, dict]] = {}
_qr_sessions: dict[str, str] = {}

_watch: dict = {
    "running": False,
    "status": "idle",  # idle | running | ordered | stopped | error
    "config": None,
    "logs": [],
    "rows": [],
    "result": None,
    "started_at": None,
    "last_check_at": None,
    "checks": 0,
    "thread": None,
}

_grab: dict = {
    "running": False,
    "status": "idle",  # idle | waiting | running | success | dry_done | stopped | timeout | error
    "config": None,
    "logs": [],
    "result": None,
    "warning": None,
    "started_at": None,
    "fired_at": None,
    "finished_at": None,
    "countdown": None,
    "server_offset": None,
    "attempts": 0,
    "errors": 0,
    "threads": 0,
}
_grab_lock = threading.RLock()
_grab_stop = threading.Event()


def load_accounts(cookie_file: str) -> None:
    global _accounts, _primary_id, _accounts_file
    _accounts_file = Path(cookie_file).resolve().parent / "accounts.json"
    loaded: list[dict] = []
    primary = ""
    if _accounts_file.exists():
        try:
            data = json.loads(_accounts_file.read_text(encoding="utf-8"))
            loaded = [a for a in (data.get("accounts") or []) if a.get("id") and a.get("cookie_file")]
            primary = str(data.get("primary") or "")
        except Exception:  # noqa: BLE001
            loaded = []
    if not loaded:
        loaded = [{"id": "a1", "name": "账号1", "cookie_file": str(Path(cookie_file).resolve())}]
    if primary not in {a["id"] for a in loaded}:
        primary = loaded[0]["id"]
    _accounts = loaded
    _primary_id = primary
    save_accounts()


def save_accounts() -> None:
    if not _accounts_file:
        return
    try:
        _accounts_file.write_text(
            json.dumps({"accounts": _accounts, "primary": _primary_id},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


def find_account(acc_id: str) -> dict:
    for a in _accounts:
        if a["id"] == acc_id:
            return a
    raise RuntimeError(f"账号不存在: {acc_id}")


def account_client(acc_id: str) -> KyfwClient:
    with _lock:
        c = _clients.get(acc_id)
        if c is None:
            acc = find_account(acc_id)
            c = KyfwClient(
                timeout=int(_client_opts.get("timeout") or 15),
                cookie_file=str(acc["cookie_file"]),
            )
            _clients[acc_id] = c
        return c


def get_client() -> KyfwClient:
    if not _accounts:
        raise RuntimeError("backend not initialized")
    return account_client(_primary_id)


def probe_account(acc_id: str, force: bool = False) -> dict:
    nowts = time.time()
    cached = _acct_status_cache.get(acc_id)
    if not force and cached and nowts - cached[0] < 15:
        return cached[1]
    try:
        st = ensure_login(account_client(acc_id))
        out: dict = {"logged_in": True, "user": st.get("user"), "error": None}
    except Exception as e:  # noqa: BLE001
        out = {"logged_in": False, "user": None, "error": str(e)}
    _acct_status_cache[acc_id] = (nowts, out)
    return out


def promote_primary() -> None:
    global _primary_id
    online = [
        a["id"] for a in _accounts
        if _acct_status_cache.get(a["id"], (0, {"logged_in": False}))[1].get("logged_in")
    ]
    if online and _primary_id not in online:
        _primary_id = online[0]
        save_accounts()


def accounts_state(refresh: bool = False) -> dict:
    items = []
    for a in _accounts:
        st = probe_account(a["id"], force=refresh)
        items.append({
            "id": a["id"],
            "name": a["name"],
            "primary": a["id"] == _primary_id,
            "logged_in": bool(st.get("logged_in")),
            "user": st.get("user"),
            "error": st.get("error"),
        })
    promote_primary()
    for it in items:
        it["primary"] = it["id"] == _primary_id
    return {
        "accounts": items,
        "primary": _primary_id,
        "online": sum(1 for i in items if i["logged_in"]),
    }


def ensure_any_login() -> dict:
    """Login via primary account, falling back to any other logged-in account."""
    global _primary_id
    try:
        return ensure_login(get_client())
    except Exception as first_err:  # noqa: BLE001
        for a in list(_accounts):
            if a["id"] == _primary_id:
                continue
            try:
                st = ensure_login(account_client(a["id"]))
                _primary_id = a["id"]
                save_accounts()
                _acct_status_cache.pop(a["id"], None)
                return st
            except Exception:  # noqa: BLE001
                continue
        raise first_err


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(level: str, msg: str) -> None:
    _watch["logs"].append({"ts": now_iso(), "level": level, "msg": msg})
    if len(_watch["logs"]) > MAX_LOGS:
        del _watch["logs"][: len(_watch["logs"]) - MAX_LOGS]
    print(f"[{level}] {msg}", flush=True)


def ensure_login(client: KyfwClient) -> dict:
    """Return login status, refreshing the otn session via uamtk when needed."""

    def probe() -> tuple[bool, dict]:
        try:
            st = client.check_login_status()
            cu = client.check_user()
            data = cu.get("data") if isinstance(cu, dict) else None
            flag = data.get("flag") if isinstance(data, dict) else None
            if flag is True:
                return True, st
            if not st.get("logged_in") or flag is False:
                return False, st
            return True, st
        except Exception as e:  # noqa: BLE001
            return False, {"error": str(e)}

    good, st = probe()
    if good:
        return st
    try:
        tk = client._request(
            "POST", "/passport/web/auth/uamtk", data={"appid": "otn"},
            referer="/otn/passport?redirect=/otn/login/userLogin",
        )
        if str(tk.get("result_code")) == "0":
            apptk = tk.get("newapptk") or tk.get("apptk")
            if apptk:
                client._request(
                    "POST", "/otn/uamauthclient", data={"tk": apptk},
                    referer="/otn/passport?redirect=/otn/login/userLogin",
                )
                client._save_cookies()
    except Exception:  # noqa: BLE001
        pass
    good, st = probe()
    if not good:
        err = st.get("error") if isinstance(st, dict) else None
        raise RuntimeError(err or "登录已失效，请重新扫码登录。")
    return st


def seat_value_state(value: str) -> str:
    v = str(value or "").strip()
    if v in ("有", "是"):
        return "available"
    if v.isdigit():
        return "available" if int(v) > 0 else "sold_out"
    if v in ("", "--", "-"):
        return "not_offered"
    if v in ("无", "*", "0"):
        return "sold_out"
    if "候补" in v:
        return "waitlist"
    return v


def row_seat_summary(row: dict) -> dict:
    out: dict[str, str] = {}
    for code, field in SEAT_ROW_FIELDS.items():
        label = SEAT_LABELS.get(code, code)
        out[label] = str(row.get(field, "--"))
    return out


def row_has_seat(row: dict, seat_code: str) -> bool:
    field = SEAT_ROW_FIELDS.get(seat_code)
    if not field:
        return False
    return seat_value_state(row.get(field, "")) == "available"


def resolve_seat(seat: str) -> str:
    return KyfwClient.resolve_seat_code(seat)


def translate_book_seat(row: dict, code: str) -> str:
    """Map the requested seat code to one accepted by the booking flow.

    12306 sells 无座 on 普速 trains under seat code 1 (硬座) and on G/D trains
    under O (二等座); the query row's seat_types string is the authoritative list.
    """
    seat_types = str(row.get("seat_types") or "")
    if not seat_types or code in seat_types:
        return code
    if code == "W":
        for cand in ("W", "1", "O", "2", "6", "4"):
            if cand in seat_types:
                return cand
    raise RuntimeError(
        f"车次 {row.get('train_code')} 不支持所选席别 {SEAT_LABELS.get(code, code)}。"
        f"可用席别代码: {seat_types}"
    )


def find_row(rows: list[dict], train_code: str) -> dict | None:
    norm = train_code.strip().upper()
    matches = [r for r in rows if str(r.get("train_code", "")).upper() == norm]
    if not matches:
        return None
    buyable = [r for r in matches if str(r.get("can_web_buy", "")).upper() == "Y"]
    return buyable[0] if buyable else matches[0]


def do_book(
    *,
    date: str,
    from_station: str,
    to_station: str,
    train_code: str,
    seat: str,
    passengers: list[str],
    choose_seats: str = "",
    berth: str = "",
    purpose: str = "ADULT",
    endpoint: str = "queryG",
    dry_run: bool = False,
    max_wait_seconds: int = 30,
    poll_interval: float = 1.5,
) -> dict:
    if not passengers:
        raise RuntimeError("至少选择一位乘车人。")
    seat_code = KyfwClient.resolve_seat_code(seat)
    with _lock:
        client = get_client()
        ensure_login(client)
        data = client.query_left_ticket(
            train_date=date, from_station=from_station, to_station=to_station,
            purpose_codes=purpose, endpoint=endpoint,
        )
        row = find_row(data.get("rows") or [], train_code)
        if not row:
            raise RuntimeError(f"未找到车次 {train_code}。")
        book_seat = translate_book_seat(row, seat_code)
        if book_seat != seat_code:
            print(f"[book] seat translated {seat_code} -> {book_seat} "
                  f"for {row.get('train_code')}", flush=True)
        result = client.book_ticket(
            train_date=date,
            from_station=from_station,
            to_station=to_station,
            train_code=train_code,
            seat=book_seat,
            passenger_names=passengers,
            purpose_codes=purpose,
            endpoint=endpoint,
            choose_seats=choose_seats,
            berth=berth,
            max_wait_seconds=max_wait_seconds,
            poll_interval=poll_interval,
            dry_run=dry_run,
        )
    return result


def watch_loop(cfg: dict) -> None:
    interval = max(2.0, float(cfg.get("interval") or 3))
    seat_code = str(cfg.get("_seat_code") or "")
    train_code = str(cfg.get("train_code") or "").strip().upper()
    auto_book = bool(cfg.get("auto_book", True))
    from_station = cfg["from"]
    to_station = cfg["to"]
    date = cfg["date"]
    endpoint = cfg.get("endpoint") or "queryG"
    purpose = cfg.get("purpose") or "ADULT"
    passengers = cfg.get("passengers") or []

    log("info", f"监控开始: {date} {from_station}->{to_station} "
                f"车次={train_code or '任意'} 席别={SEAT_LABELS.get(seat_code, seat_code)} "
                f"间隔={interval}s 乘客={','.join(passengers)}")
    if seat_code not in SEAT_ROW_FIELDS:
        log("warn", f"席别代码 {seat_code} 无法解析余票字段，仅能查询不能自动检测，请手动下单。")

    while _watch["running"]:
        _watch["last_check_at"] = now_iso()
        _watch["checks"] += 1
        try:
            with _lock:
                client = get_client()
                data = client.query_left_ticket(
                    train_date=date, from_station=from_station,
                    to_station=to_station, purpose_codes=purpose, endpoint=endpoint,
                )
            rows = data.get("rows") or []
            brief = []
            hits = []
            for row in rows:
                if train_code and str(row.get("train_code", "")).upper() != train_code:
                    continue
                seats = row_seat_summary(row)
                has = row_has_seat(row, seat_code)
                brief.append({
                    "train_code": row.get("train_code"),
                    "start_time": row.get("start_time"),
                    "arrive_time": row.get("arrive_time"),
                    "can_web_buy": row.get("can_web_buy"),
                    "seats": seats,
                    "target_has_seat": has,
                })
                if has and str(row.get("can_web_buy", "")).upper() == "Y":
                    hits.append(row)
            _watch["rows"] = brief[:50]
            label = SEAT_LABELS.get(seat_code, seat_code)
            if hits:
                codes = ",".join(str(r.get("train_code")) for r in hits[:6])
                log("info", f"发现余票: {codes} {label}有票" + ("，准备下单" if auto_book else ""))
            elif _watch["checks"] % 10 == 1:
                log("info", f"第{_watch['checks']}次检查: 暂无 {label} 余票")

            if hits and auto_book and _watch["running"]:
                target = hits[0]
                code = str(target.get("train_code"))
                try:
                    result = do_book(
                        date=date, from_station=from_station, to_station=to_station,
                        train_code=code, seat=seat_code, passengers=passengers,
                        choose_seats=str(cfg.get("choose_seats") or ""),
                        berth=str(cfg.get("berth") or ""),
                        purpose=purpose, endpoint=endpoint,
                        max_wait_seconds=int(cfg.get("max_wait_seconds") or 120),
                        poll_interval=float(cfg.get("poll_interval") or 1.5),
                    )
                    if result.get("berth_note"):
                        log("warn", str(result["berth_note"]))
                    order_id = result.get("order_id")
                    if order_id:
                        _watch["status"] = "ordered"
                        _watch["result"] = {
                            "order_id": order_id,
                            "train_code": code,
                            "passengers": passengers,
                            "seat": SEAT_LABELS.get(seat_code, seat_code),
                            "at": now_iso(),
                        }
                        log("info", f"下单成功！订单号 {order_id}，请尽快支付（20分钟内）。")
                        _watch["running"] = False
                        break
                    log("error", "下单返回中未找到订单号: " + json.dumps(
                        {k: v for k, v in result.items() if k in ("step",)}, ensure_ascii=False))
                except Exception as e:  # noqa: BLE001
                    log("error", f"下单失败（继续监控）: {e}")
        except Exception as e:  # noqa: BLE001
            log("error", f"查询失败: {e}")
        if _watch["running"]:
            time.sleep(interval)

    if _watch["status"] == "running":
        _watch["status"] = "stopped"
        log("info", "监控已停止。")


def start_watch(cfg: dict) -> dict:
    if _watch.get("running"):
        raise RuntimeError("已有监控在运行，请先停止。")
    required = ("date", "from", "to", "seat")
    missing = [k for k in required if not str(cfg.get(k) or "").strip()]
    if missing:
        raise RuntimeError("缺少参数: " + ",".join(missing))
    seat_code = resolve_seat(str(cfg["seat"]))
    cfg["_seat_code"] = seat_code
    cfg["interval"] = max(2.0, float(cfg.get("interval") or 3))
    if cfg.get("auto_book", True) and not (cfg.get("passengers") or []):
        raise RuntimeError("自动下单需要至少一位乘车人。")
    with _lock:
        get_client()  # initialized check
    _watch["running"] = True
    _watch["status"] = "running"
    _watch["config"] = {k: v for k, v in cfg.items() if not k.startswith("_") or k == "_seat_code"}
    _watch["logs"] = []
    _watch["rows"] = []
    _watch["result"] = None
    _watch["started_at"] = now_iso()
    _watch["last_check_at"] = None
    _watch["checks"] = 0
    t = threading.Thread(target=watch_loop, args=(cfg,), daemon=True)
    _watch["thread"] = t
    t.start()
    return watch_state()


def stop_watch() -> dict:
    if _watch.get("running"):
        _watch["running"] = False
        log("info", "停止请求已发送。")
    return watch_state()


def watch_state() -> dict:
    return {
        "running": bool(_watch.get("running")),
        "status": _watch.get("status"),
        "config": _watch.get("config"),
        "logs": _watch.get("logs", []),
        "rows": _watch.get("rows", []),
        "result": _watch.get("result"),
        "started_at": _watch.get("started_at"),
        "last_check_at": _watch.get("last_check_at"),
        "checks": _watch.get("checks", 0),
    }


def grab_log(level: str, msg: str) -> None:
    _grab["logs"].append({"ts": now_iso(), "level": level, "msg": msg})
    if len(_grab["logs"]) > MAX_LOGS:
        del _grab["logs"][: len(_grab["logs"]) - MAX_LOGS]
    print(f"[grab:{level}] {msg}", flush=True)


def fetch_server_offset() -> float | None:
    """server_epoch - local_epoch from the 12306 HTTP Date header, or None."""
    try:
        import requests

        r = requests.get(
            "https://kyfw.12306.cn/otn/leftTicket/init",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
            },
            timeout=6,
        )
        hdr = r.headers.get("Date")
        if not hdr:
            return None
        return parsedate_to_datetime(hdr).timestamp() - time.time()
    except Exception:  # noqa: BLE001
        return None


def row_seat_enough(row: dict, seat_code: str, need: int) -> bool:
    if not row_has_seat(row, seat_code):
        return False
    field = SEAT_ROW_FIELDS.get(seat_code)
    v = str(row.get(field, "")).strip()
    if v.isdigit():
        return int(v) >= need
    return True


def assess_sale_state(
    rows: list[dict], seat_code: str, need: int, train_code: str
) -> tuple[str, str] | None:
    """开售后的余票/停售判定。返回 None=继续等待, (reason, msg)=判定失败。"""
    label = SEAT_LABELS.get(seat_code, seat_code)
    if train_code:
        row = find_row(rows, train_code)
        if row is None:
            return ("not_found", f"未找到车次 {train_code}（可能停运/停售/未开行），无法抢购")
        web = str(row.get("can_web_buy", "")).upper()
        if web == "IS_TIME_NOT_BUY":
            return None  # 未到开售时刻，继续等待（由超时兜底）
        if web != "Y":
            return ("stopped", f"车次 {train_code} 当前不可预订（已停售/未开售），无法抢购")
        if not row_seat_enough(row, seat_code, need):
            v = str(row.get(SEAT_ROW_FIELDS.get(seat_code, ""), "") or "").strip()
            state = seat_value_state(v)
            if state == "not_offered":
                return ("no_seat", f"车次 {train_code} 不提供{label}，无法抢购")
            if state == "available":
                return ("no_tickets", f"{train_code} {label}余票不足（{v} < {need}人），无法抢购")
            return ("no_tickets", f"{train_code} {label}已无余票（{v or '无'}），无法抢购")
        return None
    candidates = [
        r for r in rows
        if str(r.get("can_web_buy", "")).upper() == "Y" and row_seat_enough(r, seat_code, need)
    ]
    if candidates:
        return None
    if not rows:
        return ("not_found", "查询结果为空（可能停运/停售），无法抢购")
    if any(str(r.get("can_web_buy", "")).upper() == "IS_TIME_NOT_BUY" for r in rows):
        return None  # 存在未开售车次，继续等待
    buyable = any(str(r.get("can_web_buy", "")).upper() == "Y" for r in rows)
    if not buyable:
        return ("stopped", "当前线路车次均不可预订（已停售/未开售），无法抢购")
    return ("no_tickets", f"所有车次 {label} 均无足够余票（需 {need} 人），无法抢购")


def grab_pause(ctx: dict, base: float) -> None:
    ctx["stop"].wait(base + random.uniform(0.0, 0.25))


def grab_worker(idx: int, ctx: dict, cfg: dict, opts: dict) -> None:
    ids = cfg["_account_ids"]
    acc_id = ids[(idx - 1) % len(ids)]
    acc_name = str(cfg["_account_names"].get(acc_id, acc_id))
    tag = f"[{acc_name}·T{idx}]"
    client = KyfwClient(
        timeout=int(opts.get("timeout") or 15),
        cookie_file=str(cfg["_account_cookies"].get(acc_id) or opts.get("cookie_file") or "") or None,
    )
    seat_code = cfg["_seat_code"]
    train_code = cfg["train_code"]
    pax = list(cfg.get("_account_pax", {}).get(acc_id) or cfg["passengers"])
    need = max(1, len(pax))
    if idx > 1:
        ctx["stop"].wait(0.12 * ((idx - 1) % max(1, ctx["n_accounts"]) + 1))
    while not ctx["stop"].is_set():
        if acc_id in ctx["dead"]:
            return
        try:
            with ctx["lock"]:
                ctx["attempts"] += 1
                attempt_no = ctx["attempts"]
            data = client.query_left_ticket(
                train_date=cfg["date"], from_station=cfg["from"], to_station=cfg["to"],
                purpose_codes=cfg["purpose"], endpoint=cfg["endpoint"],
            )
            rows = data.get("rows") or []
            if train_code:
                row = find_row(rows, train_code)
                if row is None:
                    if attempt_no % 20 == 1:
                        grab_log(
                            "info",
                            f"{tag} 未找到车次 {train_code}（可能未开售/未开行），继续重试",
                        )
                    grab_pause(ctx, 0.4)
                    continue
            else:
                candidates = [
                    r for r in rows
                    if str(r.get("can_web_buy", "")).upper() == "Y"
                    and row_seat_enough(r, seat_code, need)
                ]
                if not candidates:
                    grab_pause(ctx, 0.35)
                    continue
                row = candidates[0]
            if str(row.get("can_web_buy", "")).upper() != "Y":
                grab_pause(ctx, 0.3)
                continue
            if not row_seat_enough(row, seat_code, need):
                grab_pause(ctx, 0.4)
                continue
            if ctx["stop"].is_set():
                break
            book_seat = translate_book_seat(row, seat_code)
            code = str(row.get("train_code"))
            acc_lock = ctx["acc_locks"].setdefault(acc_id, threading.Lock())
            if not acc_lock.acquire(timeout=0.3):
                # 同账号另一线程正在提交/排队，避免并发提交挤掉会话
                grab_pause(ctx, 0.35)
                continue
            entered_queue = False
            try:
                if ctx["stop"].is_set():
                    break

                def _on_queued() -> None:
                    nonlocal entered_queue
                    entered_queue = True
                    with ctx["lock"]:
                        ctx["queued_count"] += 1
                    grab_log("info", f"{tag} 已提交并进入排队，等待出票结果…")

                result = client.book_ticket(
                    train_date=cfg["date"], from_station=cfg["from"], to_station=cfg["to"],
                    train_code=code, seat=book_seat, passenger_names=pax,
                    purpose_codes=cfg["purpose"], endpoint=cfg["endpoint"],
                    choose_seats=str(cfg.get("choose_seats") or ""),
                    berth=str(cfg.get("berth") or ""),
                    max_wait_seconds=int(cfg.get("max_wait_seconds") or 180),
                    poll_interval=float(cfg.get("poll_interval") or 1.5),
                    dry_run=bool(cfg.get("dry_run")),
                    stop_event=ctx["stop"],
                    on_queued=_on_queued,
                )
            finally:
                if entered_queue:
                    with ctx["lock"]:
                        ctx["queued_count"] = max(0, ctx["queued_count"] - 1)
                acc_lock.release()
            if result.get("berth_note"):
                grab_log("warn", f"{tag} {result['berth_note']}")
            got_order = str(result.get("order_id") or "")
            checked = str(result.get("step") or "") == "checked"
            if got_order or checked:
                with ctx["lock"]:
                    if ctx["result"] is None:
                        ctx["result"] = {
                            "order_id": got_order or None,
                            "step": result.get("step"),
                            "train_code": code,
                            "seat": SEAT_LABELS.get(book_seat, book_seat),
                            "passengers": list(pax),
                            "thread": idx,
                            "attempts": attempt_no,
                            "at": now_iso(),
                        }
                        ctx["reason"] = "success" if got_order else "dry"
                if got_order:
                    grab_log(
                        "info",
                        f"{tag} 下单成功！订单号 {got_order}（{code}），请尽快支付。",
                    )
                else:
                    grab_log("info", f"{tag} 试运行完成：{code} 全链路检查通过（未生成订单）")
                ctx["stop"].set()
                return
            grab_pause(ctx, 0.3)
        except Exception as e:  # noqa: BLE001
            if ctx["stop"].is_set() or _grab_stop.is_set():
                # 已停止：不再计数/刷失败日志（含排队等待被中止的提示）
                return
            msg = str(e)
            with ctx["lock"]:
                ctx["errors"] += 1
                err_no = ctx["errors"]
            if "登录" in msg or "未登录" in msg or "checkUser" in msg:
                with ctx["lock"]:
                    newly_dead = acc_id not in ctx["dead"]
                    ctx["dead"].add(acc_id)
                    all_dead = len(ctx["dead"]) >= ctx["n_accounts"]
                    if all_dead and ctx["reason"] is None:
                        ctx["reason"] = "error"
                        ctx["error"] = f"所有账号登录已失效: {msg[:200]}"
                if newly_dead:
                    remain = ctx["n_accounts"] - len(ctx["dead"])
                    grab_log(
                        "error",
                        f"{tag} 登录已失效，该账号退出: {msg[:150]}"
                        + ("（全部账号失效，任务结束）" if all_dead else f"（剩余可用账号 {remain} 个）"),
                    )
                if all_dead:
                    ctx["stop"].set()
                return
            # 检测"未处理的订单"：说明此前某次排队已实际生成订单
            if "未处理的订单" in msg or "未完成订单" in msg:
                grab_log(
                    "warn",
                    f"{tag} 检测到未处理订单（说明此前排队已出票）：{msg[:150]}",
                )
                grab_log("warn", "抢购任务停止，请到订单页查看待支付订单。")
                with ctx["lock"]:
                    if ctx["reason"] is None:
                        ctx["reason"] = "success"
                        ctx["result"] = {
                            "order_id": None,
                            "step": "order_exists",
                            "train_code": cfg.get("train_code"),
                            "seat": SEAT_LABELS.get(cfg["_seat_code"], cfg["_seat_code"]),
                            "passengers": list(pax),
                            "thread": idx,
                            "attempts": attempt_no,
                            "at": now_iso(),
                            "note": "检测到账号存在未完成订单，抢购自动停止",
                        }
                ctx["stop"].set()
                return
            if err_no <= 6 or err_no % 20 == 0:
                grab_log("error", f"{tag} 第{err_no}次失败: {msg[:180]}")
            grab_pause(ctx, 0.4)


def grab_coordinator(cfg: dict, opts: dict) -> None:
    acc_ids: list[str] = list(cfg["_account_ids"])
    acc_names: dict[str, str] = dict(cfg["_account_names"])

    def preflight() -> None:
        dead: list[str] = []
        with _lock:
            for aid in acc_ids:
                try:
                    ensure_login(account_client(aid))
                    _acct_status_cache.pop(aid, None)
                except Exception:  # noqa: BLE001
                    dead.append(acc_names.get(aid, aid))
        if not dead:
            _grab["warning"] = None
        elif len(dead) >= len(acc_ids):
            _grab["warning"] = "所有账号登录已失效，请重新扫码登录。"
            grab_log("error", "所有账号登录已失效（抢购将无法下单），请到“登录”页扫码。")
        else:
            _grab["warning"] = "登录失效: " + "、".join(dead)
            grab_log(
                "warn",
                f"账号登录失效: {'、'.join(dead)}（共 {len(dead)}/{len(acc_ids)}，"
                f"将仅用其余 {len(acc_ids) - len(dead)} 个账号抢购）",
            )

    try:
        preflight()

        start_dt = datetime.strptime(cfg["start_at"], "%Y-%m-%d %H:%M:%S")
        offset = fetch_server_offset()
        if offset is None:
            offset = 0.0
            grab_log("warn", "无法获取12306服务器时间，按本机时间触发（请确保本机时间准确）")
        else:
            grab_log("info", f"服务器时间偏差 {offset:+.1f}s，将以12306服务器时间为准触发")

        lead = float(cfg.get("lead_sec", 3) or 0)
        last_calib = 0.0
        milestone: set[int] = set()
        while not _grab_stop.is_set():
            nowt = time.time()
            if nowt - last_calib > 30:
                new_off = fetch_server_offset()
                if new_off is not None:
                    offset = new_off
                last_calib = nowt
            remaining = start_dt.timestamp() - offset - time.time()
            _grab["server_offset"] = round(offset, 2)
            _grab["countdown"] = round(remaining, 1)
            for m in (60, 30, 10, 5):
                if m not in milestone and lead < remaining <= m:
                    milestone.add(m)
                    grab_log("info", f"距开售 {m}s …")
                    break
            if remaining <= lead:
                break
            time.sleep(min(0.5, max(0.1, remaining - lead)))
        if _grab_stop.is_set():
            _grab["status"] = "stopped"
            _grab["finished_at"] = now_iso()
            grab_log("info", "抢购任务已停止（开售前）。")
            return

        preflight()

        _grab["fired_at"] = now_iso()
        _grab["status"] = "running"
        _grab["countdown"] = 0.0
        grab_log(
            "info",
            f"开售触发！{len(acc_ids)} 账号 × {cfg['threads']} 线程 = 并发 "
            f"{len(acc_ids) * int(cfg['threads'])} 抢购中… "
            f"车次={cfg['train_code'] or '自动选票'} "
            f"席别={SEAT_LABELS.get(cfg['_seat_code'], cfg['_seat_code'])} "
            "乘车人=" + "；".join(
                f"{acc_names.get(aid, aid)}:{'/'.join(ns)}"
                for aid, ns in cfg["_account_pax"].items()
            ),
        )

        ctx: dict = {
            "stop": threading.Event(),
            "lock": threading.Lock(),
            "attempts": 0,
            "errors": 0,
            "result": None,
            "reason": None,
            "error": None,
            "fail_reason": None,
            "dead": set(),
            "n_accounts": len(acc_ids),
            "acc_locks": {},
            "queued_count": 0,
        }
        total_threads = int(cfg["threads"]) * len(acc_ids)
        worker_threads: list[threading.Thread] = []
        for i in range(1, total_threads + 1):
            t = threading.Thread(
                target=grab_worker, args=(i, ctx, cfg, opts), daemon=True
            )
            t.start()
            worker_threads.append(t)

        deadline = time.time() + int(cfg["timeout_sec"])
        open_ts = start_dt.timestamp() - offset
        last_ticket_check = 0.0
        while time.time() < deadline:
            if ctx["stop"].is_set() or _grab_stop.is_set():
                break
            nowt2 = time.time()
            if (
                nowt2 >= open_ts + 15
                and nowt2 - last_ticket_check >= 4
                and ctx["reason"] is None
                and int(ctx.get("queued_count") or 0) <= 0
            ):
                last_ticket_check = nowt2
                verdict: tuple[str, str] | None = None
                try:
                    with _lock:
                        data = get_client().query_left_ticket(
                            train_date=cfg["date"], from_station=cfg["from"],
                            to_station=cfg["to"], purpose_codes=cfg["purpose"],
                            endpoint=cfg["endpoint"],
                        )
                    verdict = assess_sale_state(
                        data.get("rows") or [], cfg["_seat_code"],
                        max(1, int(cfg.get("_max_need") or 0), len(cfg["passengers"])),
                        cfg["train_code"],
                    )
                except Exception:  # noqa: BLE001
                    verdict = None  # 查询异常不判负，下轮再试
                if verdict:
                    fail_reason, fail_msg = verdict
                    grab_log("error", fail_msg)
                    grab_log("warn", "抢购失败：建议转入“抢票监控”，余票出现时自动下单。")
                    with ctx["lock"]:
                        ctx["reason"] = "failed"
                        ctx["error"] = fail_msg
                        ctx["fail_reason"] = fail_reason
                    ctx["stop"].set()
                    break
            _grab["attempts"] = ctx["attempts"]
            _grab["errors"] = ctx["errors"]
            time.sleep(0.2)
        ctx["stop"].set()
        # 收割已提交的排队结果：停止/超时/误判失败后订单仍可能生成，等 worker 结束再定论
        r0 = ctx.get("reason")
        in_queue = int(ctx.get("queued_count") or 0) > 0
        if r0 not in ("success", "dry") and (r0 is None or in_queue):
            if r0 is None:
                if _grab_stop.is_set():
                    grab_log(
                        "info",
                        "已请求停止：等待已提交的排队结果（≤45s，用于捕获可能已生成的订单）…",
                    )
                else:
                    grab_log("info", "超时结束：等待已提交的排队结果（≤45s）…")
            drain_until = time.time() + 60.0
            for wt in worker_threads:
                remain = drain_until - time.time()
                if remain <= 0:
                    break
                wt.join(timeout=remain)
        _grab["attempts"] = ctx["attempts"]
        _grab["errors"] = ctx["errors"]
        _grab["countdown"] = None

        reason = ctx.get("reason")
        # 成功/试运行完成：立即停止所有工作线程，不等待排队收割
        if reason in ("success", "dry"):
            ctx["stop"].set()  # 双重保险
            if reason == "success":
                _grab["status"] = "success"
                _grab["result"] = ctx["result"]
                grab_log(
                    "info",
                    f"抢购成功！订单号 {ctx['result'].get('order_id')}，请在订单页支付。",
                )
            else:
                _grab["status"] = "dry_done"
                _grab["result"] = ctx["result"]
                grab_log("info", "试运行完成：多账号多线程全链路验证通过（未生成订单）。")
        else:
            # 失败/超时/手动停止：等待排队结果收割（最多 60s）
            r0 = ctx.get("reason")
            in_queue = int(ctx.get("queued_count") or 0) > 0
            if r0 not in ("success", "dry") and (r0 is None or in_queue):
                if r0 is None:
                    if _grab_stop.is_set():
                        grab_log(
                            "info",
                            "已请求停止：等待已提交的排队结果（≤60s，用于捕获可能已生成的订单）…",
                        )
                    else:
                        grab_log("info", "超时结束：等待已提交的排队结果（≤60s）…")
                drain_until = time.time() + 60.0
                for wt in worker_threads:
                    remain = drain_until - time.time()
                    if remain <= 0:
                        break
                    wt.join(timeout=remain)
            _grab["attempts"] = ctx["attempts"]
            _grab["errors"] = ctx["errors"]
            _grab["countdown"] = None

            reason = ctx.get("reason")
            if reason == "failed":
                _grab["status"] = "failed"
                _grab["result"] = {"error": ctx.get("error"), "fail_reason": ctx.get("fail_reason")}
            elif reason == "error":
                _grab["status"] = "error"
                _grab["result"] = {"error": ctx.get("error")}
                grab_log("error", "抢购失败: " + str(ctx.get("error")))
            elif _grab_stop.is_set():
                _grab["status"] = "stopped"
                grab_log(
                    "info",
                    "抢购任务已手动停止（宽限期内未捕获到新订单；若曾进入排队，"
                    "请到订单页核对待支付订单，以免漏单）。",
                )
            else:
                _grab["status"] = "timeout"
                grab_log("warn", f"超时（{cfg['timeout_sec']}s）未成功，任务已结束。")
                grab_log("warn", "建议转入“抢票监控”，余票出现时自动下单。")
        _grab["finished_at"] = now_iso()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _grab["status"] = "error"
        grab_log("error", f"抢购任务异常: {e}")
        _grab["finished_at"] = now_iso()
    finally:
        _grab["running"] = False
        _grab["countdown"] = None


def start_grab(body: dict) -> dict:
    with _grab_lock:
        if _grab.get("running"):
            raise RuntimeError("已有抢购任务在运行，请先停止。")
        src = {
            k: str(body.get(k) or "").strip()
            for k in ("date", "from", "to", "train_code", "seat", "start_at")
        }
        missing = [k for k in ("date", "from", "to", "seat", "start_at") if not src[k]]
        if missing:
            raise RuntimeError("缺少参数: " + ",".join(missing))
        passengers = [str(x) for x in (body.get("passengers") or []) if str(x).strip()]
        pax_by_account: dict[str, list[str]] = {}
        raw_pax = body.get("pax_by_account")
        if isinstance(raw_pax, dict):
            for k, v in raw_pax.items():
                if isinstance(v, list):
                    names = [str(x).strip() for x in v if str(x).strip()]
                    if names:
                        pax_by_account[str(k)] = names
        if not passengers and not pax_by_account:
            raise RuntimeError("至少选择一位乘车人。")
        seat_code = resolve_seat(src["seat"])
        start_at = src["start_at"].replace("T", " ")
        if len(start_at) == 16:
            start_at += ":00"
        try:
            start_dt = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise RuntimeError("开售时间格式应为 YYYY-MM-DD HH:MM:SS。") from exc
        if start_dt.timestamp() < time.time() + 2:
            raise RuntimeError("开售时间已过，请重新设置。")
        try:
            lead_sec = float(body.get("lead_sec"))
        except (TypeError, ValueError):
            lead_sec = 3.0
        lead_sec = max(0.0, min(60.0, lead_sec))
        try:
            threads = int(body.get("threads") or 2)
        except (TypeError, ValueError):
            threads = 2
        threads = max(1, min(30, threads))
        try:
            timeout_sec = int(body.get("timeout_sec") or 600)
        except (TypeError, ValueError):
            timeout_sec = 600
        timeout_sec = max(30, min(7200, timeout_sec))
        with _lock:
            accs = [
                a for a in list(_accounts)
                if probe_account(a["id"], force=False).get("logged_in")
            ]
        if not accs:
            raise RuntimeError("没有已登录的账号，请先到“登录”页扫码登录（支持多账号）。")
        account_pax: dict[str, list[str]] = {}
        for a in accs:
            names = pax_by_account.get(a["id"])
            if names:
                account_pax[a["id"]] = list(names)
        if not account_pax:
            if passengers:
                account_pax = {a["id"]: list(passengers) for a in accs}
            else:
                raise RuntimeError("至少为一个账号选择乘车人。")
        if not passengers:
            union: list[str] = []
            for names in account_pax.values():
                for n in names:
                    if n not in union:
                        union.append(n)
            passengers = union
        accs = [a for a in accs if a["id"] in account_pax]
        acc_ids = [a["id"] for a in accs]
        while threads * len(acc_ids) > MAX_GRAB_WORKERS and threads > 1:
            threads -= 1
        cfg = {
            "date": src["date"],
            "from": src["from"],
            "to": src["to"],
            "train_code": src["train_code"].upper(),
            "seat": src["seat"],
            "_seat_code": seat_code,
            "start_at": start_at,
            "lead_sec": lead_sec,
            "threads": threads,
            "timeout_sec": timeout_sec,
            "dry_run": bool(body.get("dry_run")),
            "passengers": passengers,
            "purpose": str(body.get("purpose") or "ADULT"),
            "endpoint": str(body.get("endpoint") or "queryG"),
            "choose_seats": str(body.get("choose_seats") or ""),
            "berth": str(body.get("berth") or ""),
            "max_wait_seconds": int(body.get("max_wait_seconds") or 180),
            "poll_interval": float(body.get("poll_interval") or 1.5),
            "_account_ids": acc_ids,
            "_account_cookies": {a["id"]: a["cookie_file"] for a in accs},
            "_account_names": {a["id"]: a["name"] for a in accs},
            "_account_pax": account_pax,
            "_max_need": max(len(v) for v in account_pax.values()),
        }
        total_threads = threads * len(acc_ids)
        _grab_stop.clear()
        _grab.update(
            {
                "running": True,
                "status": "waiting",
                "config": cfg,
                "logs": [],
                "result": None,
                "warning": None,
                "started_at": now_iso(),
                "fired_at": None,
                "finished_at": None,
                "countdown": None,
                "server_offset": None,
                "attempts": 0,
                "errors": 0,
                "threads": threads,
                "accounts": [{"id": a["id"], "name": a["name"]} for a in accs],
                "total_threads": total_threads,
            }
        )
        grab_log(
            "info",
            f"抢购任务已创建: {start_at} 开售（提前 {lead_sec:g}s 启动），"
            f"{len(acc_ids)} 账号 × {threads} 线程 = 并发 {total_threads}，超时 {timeout_sec}s"
            + ("（试运行，不生成订单）" if cfg["dry_run"] else "（真实下单）"),
        )
        opts = {
            "cookie_file": _client_opts.get("cookie_file"),
            "timeout": _client_opts.get("timeout"),
        }
        t = threading.Thread(target=grab_coordinator, args=(cfg, opts), daemon=True)
        t.start()
    return grab_state()


def stop_grab() -> dict:
    with _grab_lock:
        if _grab.get("running"):
            _grab_stop.set()
            grab_log("info", "已发送停止请求…")
        return grab_state()


def grab_state() -> dict:
    cfg = _grab.get("config")
    pub_cfg = None
    if isinstance(cfg, dict):
        pub_cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    return {
        "running": bool(_grab.get("running")),
        "status": _grab.get("status"),
        "config": pub_cfg,
        "logs": list(_grab.get("logs") or []),
        "result": _grab.get("result"),
        "warning": _grab.get("warning"),
        "started_at": _grab.get("started_at"),
        "fired_at": _grab.get("fired_at"),
        "finished_at": _grab.get("finished_at"),
        "countdown": _grab.get("countdown"),
        "server_offset": _grab.get("server_offset"),
        "attempts": _grab.get("attempts", 0),
        "errors": _grab.get("errors", 0),
        "threads": _grab.get("threads", 0),
        "accounts": list(_grab.get("accounts") or []),
        "total_threads": _grab.get("total_threads", 0),
        "fail_reason": (res.get("fail_reason") if isinstance(res := _grab.get("result"), dict) else None),
    }


def orders_summary(resp: dict) -> list[dict]:
    data = resp.get("data") if isinstance(resp, dict) else None
    order_list = data.get("orderDBList") if isinstance(data, dict) else None
    out = []
    for od in order_list or []:
        tickets = []
        for t in od.get("tickets") or []:
            st = t.get("stationTrainDTO") or {}
            pax = t.get("passengerDTO") or {}
            tickets.append({
                "passenger": pax.get("passenger_name"),
                "train": st.get("station_train_code"),
                "from": st.get("from_station_name"),
                "to": st.get("to_station_name"),
                "seat_name": t.get("seat_name"),
                "price": t.get("str_ticket_price_page"),
                "status": t.get("ticket_status_name"),
                "pay_limit_time": t.get("pay_limit_time"),
                "start": t.get("start_train_date_page"),
            })
        out.append({
            "sequence_no": od.get("sequence_no"),
            "order_date": od.get("order_date"),
            "pay_flag": od.get("pay_flag"),
            "total_price": od.get("ticket_total_price_page"),
            "tickets": tickets,
        })
    return out


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "TrainBackend/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quiet
        pass

    # -- helpers ---------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, **kw) -> None:
        self._json({"ok": True, **kw})

    def _err(self, msg: str, status: int = 400) -> None:
        self._json({"ok": False, "error": str(msg)}, status=status)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path
        try:
            if path == "/api/ping":
                self._ok(pong=True)
            elif path == "/api/status":
                with _lock:
                    try:
                        st = ensure_any_login()
                        self._ok(logged_in=bool(st.get("logged_in")), user=st.get("user"))
                    except Exception as e:  # noqa: BLE001
                        self._ok(logged_in=False, user=None, warning=str(e))
            elif path == "/api/accounts":
                refresh = (qs.get("refresh") or ["0"])[0] in ("1", "true")
                with _lock:
                    self._ok(**accounts_state(refresh=refresh))
            elif path == "/api/qr/check":
                uuid = (qs.get("uuid") or [""])[0]
                if not uuid:
                    self._err("uuid 参数缺失")
                    return
                acc_param = (qs.get("account") or [""])[0].strip()
                acc_id = acc_param or _qr_sessions.get(uuid) or _primary_id
                with _lock:
                    find_account(acc_id)
                    client = account_client(acc_id)
                    result = client.check_qr_login(uuid=uuid, appid="otn", finalize=True)
                    if result.get("step") == "logged_in":
                        client._save_cookies()
                        _qr_sessions.pop(uuid, None)
                        _acct_status_cache.pop(acc_id, None)
                payload = {
                    "step": result.get("step"),
                    "qr_status": result.get("qr_status"),
                    "result_code": result.get("result_code"),
                    "result_message": result.get("result_message"),
                    "account": acc_id,
                }
                login_status = result.get("login_status") or {}
                if isinstance(login_status, dict):
                    payload["user"] = login_status.get("user")
                    payload["logged_in"] = bool(login_status.get("logged_in"))
                if result.get("warning"):
                    payload["warning"] = result.get("warning")
                self._ok(**payload)
            elif path == "/api/query":
                date = (qs.get("date") or [""])[0]
                from_station = (qs.get("from") or [""])[0]
                to_station = (qs.get("to") or [""])[0]
                endpoint = (qs.get("endpoint") or ["queryG"])[0]
                purpose = (qs.get("purpose") or ["ADULT"])[0]
                if not (date and from_station and to_station):
                    self._err("缺少 date/from/to 参数")
                    return
                with _lock:
                    client = get_client()
                    data = client.query_left_ticket(
                        train_date=date, from_station=from_station,
                        to_station=to_station, purpose_codes=purpose, endpoint=endpoint,
                    )
                rows = []
                for row in data.get("rows") or []:
                    item = dict(row)
                    item.pop("secret_str", None)
                    item.pop("yp_info", None)
                    item["seats"] = row_seat_summary(row)
                    item["has_target_hint"] = None
                    rows.append(item)
                self._ok(query=data.get("query"), rows=rows)
            elif path == "/api/passengers":
                acc_id = (qs.get("account") or [""])[0]
                with _lock:
                    client = account_client(acc_id) if acc_id else get_client()
                    ensure_login(client)
                    resp = client.query_passengers()
                rows = resp.get("passengers") or []
                passengers = [{
                    "name": p.get("passenger_name"),
                    "id_type": p.get("passenger_id_type_code"),
                    "id_type_name": p.get("passenger_id_type_name"),
                    "id_no": p.get("passenger_id_no"),
                    "type": p.get("passenger_type"),
                    "type_name": p.get("passenger_type_name"),
                    "mobile": p.get("mobile_no"),
                    "masked_id_no": (str(p.get("passenger_id_no") or "")[:6] + "********"
                                     + str(p.get("passenger_id_no") or "")[-4:])
                    if len(str(p.get("passenger_id_no") or "")) > 10 else p.get("passenger_id_no"),
                } for p in rows]
                self._ok(passengers=passengers, source=resp.get("source"))
            elif path == "/api/watch":
                self._ok(watch=watch_state())
            elif path == "/api/grab":
                self._ok(grab=grab_state())
            elif path == "/api/orders/uncomplete":
                with _lock:
                    client = get_client()
                    ensure_login(client)
                    resp = client.query_my_order_no_complete()
                self._ok(summary=orders_summary(resp), raw=resp)
            elif path == "/api/qr/image":
                p = (qs.get("path") or [""])[0]
                fp = Path(p)
                if not fp.is_absolute() or not fp.exists() or fp.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    self._err("非法图片路径")
                    return
                b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
                mime = "image/png" if fp.suffix.lower() == ".png" else "image/jpeg"
                self._ok(data_url=f"data:{mime};base64,{b64}")
            else:
                self._err("not found", status=404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._err(e, status=500)

    def do_POST(self) -> None:  # noqa: N802
        global _primary_id
        path = urlparse(self.path).path
        try:
            body = self._read_body()
            if path == "/api/qr/create":
                acc_id = str(body.get("account") or "").strip() or _primary_id
                with _lock:
                    find_account(acc_id)
                    client = account_client(acc_id)
                    result = client.create_qr_login(appid="otn")
                    uuid = str(result.get("uuid") or "")
                    if uuid:
                        _qr_sessions[uuid] = acc_id
                image = str(result.get("image") or "")
                self._ok(uuid=uuid, account=acc_id,
                         image="data:image/jpg;base64," + image if image else "")
            elif path == "/api/accounts/add":
                with _lock:
                    if _grab.get("running"):
                        raise RuntimeError("抢购任务运行中，暂不能修改账号。")
                    if len(_accounts) >= MAX_ACCOUNTS:
                        raise RuntimeError(f"最多支持 {MAX_ACCOUNTS} 个账号。")
                    name = str(body.get("name") or "").strip() or f"账号{len(_accounts) + 1}"
                    nums = [int(a["id"][1:]) for a in _accounts
                            if a["id"].startswith("a") and a["id"][1:].isdigit()]
                    nid = f"a{max(nums or [0]) + 1}"
                    base_dir = _accounts_file.parent if _accounts_file else SCRIPT_DIR
                    cookie_path = str(base_dir / f"kyfw_cookies_{nid}.json")
                    _accounts.append({"id": nid, "name": name, "cookie_file": cookie_path})
                    save_accounts()
                    out = accounts_state(refresh=False)
                    out["new_id"] = nid
                    self._ok(**out)
            elif path == "/api/accounts/remove":
                acc_id = str(body.get("id") or "").strip()
                with _lock:
                    if _grab.get("running"):
                        raise RuntimeError("抢购任务运行中，暂不能修改账号。")
                    if len(_accounts) <= 1:
                        raise RuntimeError("至少保留一个账号。")
                    acc = find_account(acc_id)
                    _accounts.remove(acc)
                    if _primary_id == acc_id and _accounts:
                        _primary_id = _accounts[0]["id"]
                    save_accounts()
                    _clients.pop(acc_id, None)
                    _acct_status_cache.pop(acc_id, None)
                    try:
                        Path(acc["cookie_file"]).unlink(missing_ok=True)
                    except Exception:  # noqa: BLE001
                        pass
                    self._ok(**accounts_state(refresh=False))
            elif path == "/api/book":
                try:
                    result = do_book(
                        date=str(body.get("date") or ""),
                        from_station=str(body.get("from") or ""),
                        to_station=str(body.get("to") or ""),
                        train_code=str(body.get("train_code") or ""),
                        seat=str(body.get("seat") or ""),
                        passengers=[str(x) for x in (body.get("passengers") or []) if str(x).strip()],
                        choose_seats=str(body.get("choose_seats") or ""),
                        berth=str(body.get("berth") or ""),
                        purpose=str(body.get("purpose") or "ADULT"),
                        endpoint=str(body.get("endpoint") or "queryG"),
                        dry_run=bool(body.get("dry_run")),
                        max_wait_seconds=int(body.get("max_wait_seconds") or 120),
                        poll_interval=float(body.get("poll_interval") or 1.5),
                    )
                except Exception as e:  # noqa: BLE001
                    self._err(e)
                    return
                summary = {
                    "step": result.get("step"),
                    "order_id": result.get("order_id"),
                    "seat_code": result.get("seat_code"),
                    "seat_detail_type": result.get("seat_detail_type"),
                    "berth_note": result.get("berth_note"),
                    "selected_passengers": result.get("selected_passengers"),
                    "train": {
                        "train_code": (result.get("train") or {}).get("train_code"),
                        "start_time": (result.get("train") or {}).get("start_time"),
                        "arrive_time": (result.get("train") or {}).get("arrive_time"),
                        "from_station": (result.get("train") or {}).get("from_station"),
                        "to_station": (result.get("train") or {}).get("to_station"),
                    } if isinstance(result.get("train"), dict) else None,
                }
                self._ok(result=summary)
            elif path == "/api/watch/start":
                try:
                    state = start_watch(body)
                except Exception as e:  # noqa: BLE001
                    self._err(e)
                    return
                self._ok(watch=state)
            elif path == "/api/watch/stop":
                self._ok(watch=stop_watch())
            elif path == "/api/grab/start":
                try:
                    state = start_grab(body)
                except Exception as e:  # noqa: BLE001
                    self._err(e)
                    return
                self._ok(grab=state)
            elif path == "/api/grab/stop":
                self._ok(grab=stop_grab())
            elif path == "/api/pay":
                channel = str(body.get("channel") or "")
                with _lock:
                    client = get_client()
                    ensure_login(client)
                    import client as client_mod
                    try:
                        result = client_mod.fetch_common_order_payment(client, pay_channel=channel)
                    except Exception as e:  # noqa: BLE001
                        self._err(e)
                        return
                payment = result.get("payment") or {}
                self._ok(
                    order=result.get("selected_order"),
                    payment=payment,
                    pay_channel=result.get("pay_channel"),
                    pay_qr_url=result.get("pay_qr_url"),
                    pay_qr_image_file=result.get("pay_qr_image_file"),
                    pay_qr_error=result.get("pay_qr_error"),
                )
            else:
                self._err("not found", status=404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._err(e, status=500)


def main() -> int:
    global _client_opts
    parser = argparse.ArgumentParser(description="12306 desktop backend")
    parser.add_argument("--port", type=int, default=37891)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--cookie-file", default=None)
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    cookie_file = args.cookie_file or str(SCRIPT_DIR / "cache" / "kyfw_12306_cookies.json")
    _client_opts = {"cookie_file": cookie_file, "timeout": args.timeout}
    load_accounts(cookie_file)
    print(f"[backend] accounts={len(_accounts)} primary={_primary_id} cookie_file={cookie_file}", flush=True)

    httpd = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"[backend] listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _watch["running"] = False
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
