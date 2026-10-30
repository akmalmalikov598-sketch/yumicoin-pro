# -*- coding: utf-8 -*-
"""
TAP-TO-EARN Telegram Mini App  —  bitta fayl (bot + server + Mini App)
Render: Build = pip install -r requirements.txt | Start = python main.py
ENV: BOT_TOKEN, ADMIN_IDS, (BASE_URL), (DB_PATH), (COIN_NAME), (ADMIN_USERNAME), (ADSGRAM_BLOCK_ID)
"""
import os, time, json, hmac, hashlib, sqlite3, threading, random, math, logging, html as _html
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify, g, Response
from werkzeug.exceptions import HTTPException

# ───────────────────────── CONFIG ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE_URL = (os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
ADMINS = {int(i) for i in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if i.isdigit()}
DB_PATH = os.getenv("DB_PATH", "data.db")
COIN = os.getenv("COIN_NAME", "AkCoin")
CH = COIN[0].upper()
ADMIN_UN = os.getenv("ADMIN_USERNAME", "Akmaljon1100").lstrip("@")
ADSGRAM = os.getenv("ADSGRAM_BLOCK_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))
START_BONUS, REF_REWARD, REF_NEW = 1000, 1000, 500
MAXLVL = 12
UPBASE = {"tap": 500, "energy": 300, "regen": 400}
UPCOL = {"tap": "tap_lvl", "energy": "energy_lvl", "regen": "regen_lvl"}

# Boost xizmatlari: p = 1000 ta narxi (tanga), min = minimal miqdor
SERV = {
    "telegram": {"t": "Telegramda reklama chiqish", "i": "✈️", "s": {
        "sub": {"t": "Kanalga obunachi", "i": "👥", "p": 60000, "min": 100, "ph": "@kanal yoki t.me/kanal"},
        "view": {"t": "Kanal postiga prasmotr", "i": "👁", "p": 5000, "min": 100, "ph": "https://t.me/kanal/123"},
        "react": {"t": "Kanal postiga reaksiya", "i": "😍", "p": 9000, "min": 50, "ph": "https://t.me/kanal/123"}}},
    "instagram": {"t": "Instagramda reklama chiqish", "i": "📸", "s": {
        "follow": {"t": "Obunachi", "i": "👥", "p": 80000, "min": 100, "ph": "https://instagram.com/username"},
        "like": {"t": "Layk", "i": "❤️", "p": 20000, "min": 50, "ph": "https://instagram.com/p/..."},
        "view": {"t": "Reels prasmotr", "i": "👁", "p": 8000, "min": 100, "ph": "https://instagram.com/reel/..."}}},
    "tiktok": {"t": "TikTokda reklama chiqish", "i": "🎵", "s": {
        "follow": {"t": "Obunachi", "i": "👥", "p": 90000, "min": 100, "ph": "https://tiktok.com/@username"},
        "like": {"t": "Layk", "i": "❤️", "p": 20000, "min": 50, "ph": "https://tiktok.com/@u/video/..."},
        "view": {"t": "Prasmotr", "i": "👁", "p": 6000, "min": 100, "ph": "https://tiktok.com/@u/video/..."}}},
}
PAID = [["📢", "Reklama joylashtirish", "Bot va kanallarda reklama"],
        ["🤖", "Bot / Mini App buyurtma", "Sizga maxsus bot yasab beramiz"],
        ["💎", "Tanga sotib olish", "Tangani pul evaziga olish"]]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")

# ───────────────────────── DB ─────────────────────────
DB = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
DB.row_factory = sqlite3.Row
LK = threading.RLock()
DB.executescript("""
create table if not exists users(id integer primary key,name text,username text default '',balance integer default 0,
 energy real default 200,energy_ts real,tap_lvl integer default 0,energy_lvl integer default 0,regen_lvl integer default 0,
 ref_by integer,refs integer default 0,banned integer default 0,created real,last_seen real);
create table if not exists tasks(id integer primary key autoincrement,title text,kind text,url text default '',reward integer,
 chat_id text default '',daily_limit integer default 0,active integer default 1);
create table if not exists task_done(user_id integer,task_id integer,day text,cnt integer default 0,primary key(user_id,task_id,day));
create table if not exists auctions(id integer primary key autoincrement,title text,image text default '',price integer,ends real,
 done integer default 0,winner_id integer,winner_name text);
create table if not exists tickets(auction_id integer,user_id integer,cnt integer default 0,primary key(auction_id,user_id));
create table if not exists likes(auction_id integer,user_id integer,primary key(auction_id,user_id));
create table if not exists promos(code text primary key,reward integer,max_uses integer default 0,uses integer default 0);
create table if not exists promo_used(code text,user_id integer,primary key(code,user_id));
create table if not exists orders(id integer primary key autoincrement,user_id integer,plat text,svc text,link text,qty integer,
 cost integer,status text default 'pending',created real);
""")


def q(sql, a=(), one=False):
    with LK:
        r = DB.execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r


def x(sql, a=()):
    with LK:
        return DB.execute(sql, a).lastrowid


def get(uid):
    return q("select * from users where id=?", (uid,), True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ───────────────────────── TELEGRAM API ─────────────────────────
def tg(method, **p):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=p, timeout=40).json()
        if r.get("ok"):
            return r.get("result")
        if method not in ("getChatMember", "sendMessage", "getUpdates"):
            log.warning("tg %s: %s", method, r)
    except Exception as e:
        log.warning("tg %s err: %s", method, e)
    return None


def send(chat, text, markup=None):
    p = dict(chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True)
    if markup:
        p["reply_markup"] = markup
    return tg("sendMessage", **p)


def notify_admins(text, markup=None):
    for a in ADMINS:
        send(a, text, markup)


BOT_USER = ""

# ───────────────────────── GAME LOGIC ─────────────────────────
def maxe(u): return 200 + 100 * u["energy_lvl"]
def regen(u): return 1 + u["regen_lvl"]
def power(u): return 1 + u["tap_lvl"]
def cur_e(u, now): return min(maxe(u), u["energy"] + max(0, now - (u["energy_ts"] or now)) * regen(u))
def ucost(k, l): return None if l >= MAXLVL else int(UPBASE[k] * 1.9 ** l)


def state(u):
    now = time.time()
    return dict(id=u["id"], name=u["name"], username=u["username"], balance=u["balance"], refs=u["refs"],
                energy=int(cur_e(u, now)), max=maxe(u), regen=regen(u), power=power(u),
                lv={k: u[c] for k, c in UPCOL.items()},
                cost={k: ucost(k, u[c]) for k, c in UPCOL.items()})


def reg(uid, name, un, ref=None):
    with LK:
        u = get(uid)
        if u:
            if u["name"] != name or u["username"] != un:
                x("update users set name=?,username=? where id=?", (name, un, uid))
                u = get(uid)
            return u, False
        ok = bool(ref and ref != uid and get(ref))
        now = time.time()
        x("insert into users(id,name,username,balance,energy,energy_ts,ref_by,created,last_seen) values(?,?,?,?,?,?,?,?,?)",
          (uid, name, un, START_BONUS + (REF_NEW if ok else 0), 200, now, ref if ok else None, now, now))
        if ok:
            x("update users set balance=balance+?,refs=refs+1 where id=?", (REF_REWARD, ref))
    if ok:
        send(ref, f"🎉 <b>{_html.escape(name)}</b> sizning havolangiz orqali qo‘shildi! +{REF_REWARD} {COIN}")
    return get(uid), True


def verify(init):
    try:
        d = dict(parse_qsl(init, keep_blank_values=True))
        h = d.pop("hash", None)
        if not h:
            return None
        s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(key, s.encode(), hashlib.sha256).hexdigest(), h):
            return None
        if time.time() - int(d.get("auth_date", 0)) > 86400 * 7:
            return None
        return json.loads(d["user"]), d.get("start_param", "")
    except Exception:
        return None


# ───────────────────────── FLASK API ─────────────────────────
app = Flask(__name__)


class Err(Exception):
    pass


@app.errorhandler(Err)
def _err(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(Exception)
def _exc(e):
    if isinstance(e, HTTPException):
        return e
    log.exception(e)
    return jsonify(error="Server xatosi"), 500


def auth(f):
    @wraps(f)
    def w(*a, **k):
        v = verify(request.headers.get("X-Init", ""))
        if not v:
            return jsonify(error="Avtorizatsiya xatosi"), 401
        tu, sp = v
        ref = int(sp[4:]) if sp.startswith("ref_") and sp[4:].isdigit() else None
        name = ((tu.get("first_name") or "") + " " + (tu.get("last_name") or "")).strip() or "User"
        u, _ = reg(tu["id"], name[:60], (tu.get("username") or "").lower(), ref)
        if u["banned"]:
            return jsonify(error="Siz bloklangansiz"), 403
        g.uid = u["id"]
        return f(*a, **k)
    return w


@app.get("/")
def index():
    return Response(HTML, mimetype="text/html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return "ok"


@app.post("/api/me")
@auth
def api_me():
    d = state(get(g.uid))
    d["cfg"] = dict(coin=COIN, ch=CH, bot=BOT_USER, admin=ADMIN_UN, ads=ADSGRAM, ref=REF_REWARD, paid=PAID)
    q("update users set last_seen=? where id=?", (time.time(), g.uid))
    return jsonify(d)


@app.post("/api/tap")
@auth
def api_tap():
    n = int((request.json or {}).get("n", 0))
    now = time.time()
    with LK:
        u = get(g.uid)
        e, p = cur_e(u, now), power(u)
        n = max(0, min(n, 80))
        n = min(n, int(max(0, now - (u["energy_ts"] or now)) * 25) + 40, int(e // p))
        gain = n * p
        x("update users set balance=balance+?,energy=?,energy_ts=? where id=?", (gain, e - gain, now, g.uid))
        return jsonify(state(get(g.uid)))


@app.post("/api/upgrade")
@auth
def api_upgrade():
    k = (request.json or {}).get("k")
    if k not in UPCOL:
        raise Err("Noto‘g‘ri so‘rov")
    col, now = UPCOL[k], time.time()
    with LK:
        u = get(g.uid)
        c = ucost(k, u[col])
        if c is None:
            raise Err("Maksimal daraja")
        if u["balance"] < c:
            raise Err("Tanga yetarli emas")
        e = cur_e(u, now)
        x(f"update users set balance=balance-?,{col}={col}+1,energy=?,energy_ts=? where id=?", (c, e, now, g.uid))
        return jsonify(state(get(g.uid)))


# ----- vazifalar -----
TS = {}
WAIT = {"link": 8, "youtube": 15, "ad": 3, "channel": 0}


def tdone(uid, t):
    d = today() if t["daily_limit"] > 0 else "once"
    r = q("select cnt from task_done where user_id=? and task_id=? and day=?", (uid, t["id"], d), True)
    return (r["cnt"] if r else 0), d


@app.get("/api/tasks")
@auth
def api_tasks():
    out = []
    for t in q("select * from tasks where active=1 order by id"):
        c, _ = tdone(g.uid, t)
        lim = t["daily_limit"]
        out.append(dict(id=t["id"], title=t["title"], kind=t["kind"], url=t["url"], reward=t["reward"], cnt=c,
                        limit=lim, done=c >= (lim if lim > 0 else 1), wait=WAIT.get(t["kind"], 5)))
    return jsonify(out)


@app.post("/api/task/<int:tid>/start")
@auth
def t_start(tid):
    TS[(g.uid, tid)] = time.time()
    return jsonify(ok=1)


@app.post("/api/task/<int:tid>/claim")
@auth
def t_claim(tid):
    t = q("select * from tasks where id=? and active=1", (tid,), True)
    if not t:
        raise Err("Vazifa topilmadi")
    c, d = tdone(g.uid, t)
    if c >= (t["daily_limit"] if t["daily_limit"] > 0 else 1):
        raise Err("Bu vazifa bajarilgan")
    st = TS.get((g.uid, tid))
    if not st or time.time() - st < WAIT.get(t["kind"], 5):
        raise Err("Avval vazifani bajaring")
    if t["kind"] == "channel":
        m = tg("getChatMember", chat_id=t["chat_id"], user_id=g.uid)
        if m is None:
            raise Err("Tekshirib bo‘lmadi (bot kanalda admin bo‘lishi kerak)")
        if m.get("status") not in ("member", "administrator", "creator"):
            raise Err("Avval kanalga obuna bo‘ling")
    with LK:
        c, d = tdone(g.uid, t)
        if c >= (t["daily_limit"] if t["daily_limit"] > 0 else 1):
            raise Err("Bu vazifa bajarilgan")
        x("insert into task_done values(?,?,?,1) on conflict(user_id,task_id,day) do update set cnt=cnt+1", (g.uid, tid, d))
        x("update users set balance=balance+? where id=?", (t["reward"], g.uid))
    TS.pop((g.uid, tid), None)
    return jsonify(reward=t["reward"])


# ----- auksion -----
@app.get("/api/auctions")
@auth
def api_auctions():
    sel = ("select a.*,(select count(*) from likes where auction_id=a.id) likes,"
           "(select count(*) from likes where auction_id=a.id and user_id=?) liked,"
           "(select coalesce(sum(cnt),0) from tickets where auction_id=a.id) total,"
           "(select coalesce(sum(cnt),0) from tickets where auction_id=a.id and user_id=?) mine from auctions a ")
    rows = q(sel + "where a.done=0 order by a.ends", (g.uid, g.uid)) + \
        q(sel + "where a.done=1 order by a.ends desc limit 3", (g.uid, g.uid))
    return jsonify([dict(r) for r in rows])


@app.post("/api/auction/<int:aid>/like")
@auth
def a_like(aid):
    with LK:
        if q("select 1 from likes where auction_id=? and user_id=?", (aid, g.uid), True):
            x("delete from likes where auction_id=? and user_id=?", (aid, g.uid))
        else:
            x("insert into likes values(?,?)", (aid, g.uid))
    return jsonify(ok=1)


@app.post("/api/auction/<int:aid>/buy")
@auth
def a_buy(aid):
    qty = int((request.json or {}).get("qty", 1))
    a = q("select * from auctions where id=?", (aid,), True)
    if not a or a["done"] or a["ends"] <= time.time():
        raise Err("Auksion yakunlangan")
    if not 1 <= qty <= 1000:
        raise Err("Noto‘g‘ri miqdor")
    cost = a["price"] * qty
    with LK:
        if get(g.uid)["balance"] < cost:
            raise Err("Tanga yetarli emas")
        x("update users set balance=balance-? where id=?", (cost, g.uid))
        x("insert into tickets values(?,?,?) on conflict(auction_id,user_id) do update set cnt=cnt+?", (aid, g.uid, qty, qty))
    return jsonify(state(get(g.uid)))


# ----- profil -----
@app.get("/api/rating")
@auth
def api_rating():
    top = q("select id,name,username,balance from users where banned=0 order by balance desc limit 50")
    me = get(g.uid)
    rank = q("select count(*)+1 c from users where balance>? and banned=0", (me["balance"],), True)["c"]
    return jsonify(top=[dict(r) for r in top], me=rank)


@app.post("/api/promo")
@auth
def api_promo():
    code = str((request.json or {}).get("code", "")).strip().upper()
    with LK:
        p = q("select * from promos where code=?", (code,), True)
        if not p:
            raise Err("Promokod topilmadi")
        if p["max_uses"] > 0 and p["uses"] >= p["max_uses"]:
            raise Err("Promokod tugagan")
        if q("select 1 from promo_used where code=? and user_id=?", (code, g.uid), True):
            raise Err("Siz bu promokodni ishlatgansiz")
        x("insert into promo_used values(?,?)", (code, g.uid))
        x("update promos set uses=uses+1 where code=?", (code,))
        x("update users set balance=balance+? where id=?", (p["reward"], g.uid))
    return jsonify(reward=p["reward"])


@app.post("/api/send")
@auth
def api_send():
    d = request.json or {}
    to = str(d.get("to", "")).strip().lstrip("@").lower()
    amt = int(d.get("amount", 0))
    if amt < 10:
        raise Err("Minimal miqdor: 10")
    with LK:
        u = get(g.uid)
        if u["balance"] < amt:
            raise Err("Tanga yetarli emas")
        r = get(int(to)) if to.isdigit() else q("select * from users where username=?", (to,), True)
        if not r:
            raise Err("Foydalanuvchi topilmadi")
        if r["id"] == g.uid:
            raise Err("O‘zingizga yubora olmaysiz")
        x("update users set balance=balance-? where id=?", (amt, g.uid))
        x("update users set balance=balance+? where id=?", (amt, r["id"]))
    send(r["id"], f"💸 <b>{_html.escape(u['name'])}</b> sizga {amt} {COIN} yubordi!")
    return jsonify(state(get(g.uid)))


# ----- boost xizmatlar -----
@app.get("/api/services")
@auth
def api_services():
    return jsonify(SERV)


@app.get("/api/orders")
@auth
def api_orders():
    out = []
    for o in q("select * from orders where user_id=? order by id desc limit 10", (g.uid,)):
        try:
            title = SERV[o["plat"]]["s"][o["svc"]]["t"]
        except KeyError:
            title = o["svc"]
        out.append(dict(id=o["id"], title=title, qty=o["qty"], cost=o["cost"], status=o["status"]))
    return jsonify(out)


@app.post("/api/order")
@auth
def api_order():
    d = request.json or {}
    k, s = d.get("k"), d.get("s")
    link = str(d.get("link", "")).strip()[:300]
    qty = int(d.get("qty", 0))
    it = SERV.get(k, {}).get("s", {}).get(s)
    if not it:
        raise Err("Xizmat topilmadi")
    if qty < it["min"] or qty > 1000000:
        raise Err("Noto‘g‘ri miqdor")
    if len(link) < 4:
        raise Err("Havolani kiriting")
    cost = math.ceil(qty * it["p"] / 1000)
    with LK:
        u = get(g.uid)
        if u["balance"] < cost:
            raise Err("Tanga yetarli emas")
        x("update users set balance=balance-? where id=?", (cost, g.uid))
        oid = x("insert into orders(user_id,plat,svc,link,qty,cost,created) values(?,?,?,?,?,?,?)",
                (g.uid, k, s, link, qty, cost, time.time()))
    notify_admins(f"🛒 <b>Yangi buyurtma #{oid}</b>\n👤 {_html.escape(u['name'])} (<code>{u['id']}</code>)\n"
                  f"📦 {SERV[k]['t']} → {it['t']}\n🔗 {_html.escape(link)}\n🔢 {qty} ta · 💰 {cost} {COIN}",
                  {"inline_keyboard": [[{"text": "✅ Bajarildi", "callback_data": f"ord:done:{oid}"},
                                        {"text": "❌ Bekor", "callback_data": f"ord:cancel:{oid}"}]]})
    return jsonify(state(get(g.uid)))


# ───────────────────────── BOT (long polling) ─────────────────────────
HELP = """<b>Admin buyruqlari</b>
/stats — statistika
/addtask tur|nom|mukofot|url|chat_id|kunlik_limit
  tur: link | channel | youtube | ad
  <code>/addtask channel|Kanalga obuna|100|https://t.me/kanal|@kanal|0</code>
  <code>/addtask ad|Reklama ko‘rish|50||0|20</code>
/tasks — vazifalar · /deltask ID
/addauction nom|bilet_narxi|kun|rasm_url
/auctions · /delauction ID
/addpromo KOD mukofot limit(0=cheksiz)
/give user_id miqdor · /ban id · /unban id
/orders — kutilayotgan buyurtmalar
/broadcast matn"""


def welcome(uid):
    send(uid, f"👋 <b>{COIN}</b> ga xush kelibsiz!\n\n👆 Tangani bosing, 🎯 vazifalar bajaring, 🏆 auksionda yuting, "
              f"🚀 xizmatlar buyurting.\n\nBoshlash uchun pastdagi tugmani bosing 👇",
         {"inline_keyboard": [[{"text": "🚀 O‘yinni ochish", "web_app": {"url": BASE_URL}}]]})


def on_msg(m):
    uid = m["from"]["id"]
    text = (m.get("text") or "").strip()
    if not text:
        return
    name = ((m["from"].get("first_name") or "") + " " + (m["from"].get("last_name") or "")).strip() or "User"
    if text.startswith("/start"):
        parts = text.split()
        ref = int(parts[1][4:]) if len(parts) > 1 and parts[1].startswith("ref_") and parts[1][4:].isdigit() else None
        reg(uid, name[:60], (m["from"].get("username") or "").lower(), ref)
        welcome(uid)
    elif uid in ADMINS and text.startswith("/"):
        admin_cmd(uid, text)


def admin_cmd(uid, text):
    cmd, _, arg = text.partition(" ")
    cmd, arg = cmd.split("@")[0].lower(), arg.strip()
    try:
        if cmd in ("/admin", "/help"):
            send(uid, HELP)
        elif cmd == "/stats":
            n = q("select count(*) c,coalesce(sum(balance),0) s from users", one=True)
            d = q("select count(*) c from users where created>?", (time.time() - 86400,), True)["c"]
            o = q("select count(*) c from orders where status='pending'", one=True)["c"]
            send(uid, f"📊 Foydalanuvchilar: <b>{n['c']}</b> (24 soat: +{d})\n💰 Jami tanga: <b>{n['s']}</b>\n🛒 Kutilayotgan buyurtma: <b>{o}</b>")
        elif cmd == "/addtask":
            p = [i.strip() for i in arg.split("|")] + [""] * 6
            if p[0] not in ("link", "channel", "youtube", "ad"):
                return send(uid, "Tur: link | channel | youtube | ad")
            tid = x("insert into tasks(title,kind,url,reward,chat_id,daily_limit) values(?,?,?,?,?,?)",
                    (p[1], p[0], p[3], int(p[2] or 0), p[4], int(p[5] or 0)))
            send(uid, f"✅ Vazifa #{tid} qo‘shildi")
        elif cmd == "/tasks":
            send(uid, "\n".join(f"#{t['id']} [{t['kind']}] {_html.escape(t['title'])} +{t['reward']}" for t in q("select * from tasks where active=1")) or "Yo‘q")
        elif cmd == "/deltask":
            x("update tasks set active=0 where id=?", (int(arg),)); send(uid, "🗑 O‘chirildi")
        elif cmd == "/addauction":
            p = [i.strip() for i in arg.split("|")] + [""] * 4
            aid = x("insert into auctions(title,price,ends,image) values(?,?,?,?)",
                    (p[0], int(p[1]), time.time() + float(p[2]) * 86400, p[3]))
            send(uid, f"✅ Auksion #{aid} qo‘shildi")
        elif cmd == "/auctions":
            send(uid, "\n".join(f"#{a['id']} {_html.escape(a['title'])} · {a['price']} · {'tugagan' if a['done'] else 'faol'}" for a in q("select * from auctions order by id desc limit 15")) or "Yo‘q")
        elif cmd == "/delauction":
            x("delete from auctions where id=?", (int(arg),)); send(uid, "🗑 O‘chirildi")
        elif cmd == "/addpromo":
            p = arg.split()
            x("insert or replace into promos(code,reward,max_uses) values(?,?,?)", (p[0].upper(), int(p[1]), int(p[2]) if len(p) > 2 else 0))
            send(uid, f"✅ Promokod <code>{p[0].upper()}</code> tayyor")
        elif cmd == "/give":
            a, b = arg.split()
            x("update users set balance=balance+? where id=?", (int(b), int(a))); send(uid, "✅ Berildi")
        elif cmd in ("/ban", "/unban"):
            x("update users set banned=? where id=?", (1 if cmd == "/ban" else 0, int(arg))); send(uid, "✅ Bajarildi")
        elif cmd == "/orders":
            rows = q("select * from orders where status='pending' order by id limit 20")
            if not rows:
                return send(uid, "Kutilayotgan buyurtma yo‘q")
            for o in rows:
                send(uid, f"🛒 <b>#{o['id']}</b> · {o['plat']}/{o['svc']}\n👤 <code>{o['user_id']}</code>\n🔗 {_html.escape(o['link'])}\n🔢 {o['qty']} · 💰 {o['cost']}",
                     {"inline_keyboard": [[{"text": "✅ Bajarildi", "callback_data": f"ord:done:{o['id']}"},
                                           {"text": "❌ Bekor", "callback_data": f"ord:cancel:{o['id']}"}]]})
        elif cmd == "/broadcast":
            if not arg:
                return send(uid, "/broadcast matn")
            threading.Thread(target=broadcast, args=(uid, arg), daemon=True).start()
    except Exception as e:
        send(uid, f"⚠️ Xato: {_html.escape(str(e))}\n\n/admin — yordam")


def broadcast(admin, text):
    ok = 0
    for r in q("select id from users where banned=0"):
        if send(r["id"], text, {"inline_keyboard": [[{"text": "🚀 Ochish", "web_app": {"url": BASE_URL}}]]}):
            ok += 1
        time.sleep(0.05)
    send(admin, f"📣 Yuborildi: {ok}")


def on_cb(c):
    uid, data = c["from"]["id"], c.get("data", "")
    if uid not in ADMINS or not data.startswith("ord:"):
        return tg("answerCallbackQuery", callback_query_id=c["id"])
    _, act, oid = data.split(":")
    with LK:
        o = q("select * from orders where id=?", (int(oid),), True)
        if not o or o["status"] != "pending":
            return tg("answerCallbackQuery", callback_query_id=c["id"], text="Allaqachon ishlangan")
        if act == "done":
            x("update orders set status='done' where id=?", (o["id"],))
            send(o["user_id"], f"✅ Buyurtmangiz #{o['id']} bajarildi!")
        else:
            x("update orders set status='cancel' where id=?", (o["id"],))
            x("update users set balance=balance+? where id=?", (o["cost"], o["user_id"]))
            send(o["user_id"], f"❌ Buyurtma #{o['id']} bekor qilindi. {o['cost']} {COIN} qaytarildi.")
    tg("answerCallbackQuery", callback_query_id=c["id"], text="Bajarildi")
    m = c.get("message")
    if m:
        tg("editMessageReplyMarkup", chat_id=m["chat"]["id"], message_id=m["message_id"], reply_markup={"inline_keyboard": []})


def poll():
    tg("deleteWebhook")
    off = 0
    while True:
        r = tg("getUpdates", offset=off, timeout=25, allowed_updates=["message", "callback_query"])
        if r is None:
            time.sleep(3)
            continue
        for up in r:
            off = up["update_id"] + 1
            try:
                if "message" in up:
                    on_msg(up["message"])
                elif "callback_query" in up:
                    on_cb(up["callback_query"])
            except Exception:
                log.exception("update")


def auction_loop():
    while True:
        try:
            for a in q("select * from auctions where done=0 and ends<=?", (time.time(),)):
                rows = q("select user_id,cnt from tickets where auction_id=?", (a["id"],))
                if rows:
                    w = random.choices([r["user_id"] for r in rows], weights=[r["cnt"] for r in rows])[0]
                    wu = get(w)
                    x("update auctions set done=1,winner_id=?,winner_name=? where id=?", (w, wu["name"], a["id"]))
                    send(w, f"🏆 <b>Tabriklaymiz!</b> Siz «{_html.escape(a['title'])}» auksionida g‘olib bo‘ldingiz!\nAdmin siz bilan bog‘lanadi: @{ADMIN_UN}")
                    notify_admins(f"🏆 Auksion #{a['id']} «{_html.escape(a['title'])}» g‘olibi: {_html.escape(wu['name'])} (<code>{w}</code>)")
                else:
                    x("update auctions set done=1 where id=?", (a["id"],))
        except Exception:
            log.exception("auction_loop")
        time.sleep(30)


def keepalive():
    while True:
        time.sleep(600)
        try:
            requests.get(BASE_URL + "/health", timeout=20)
        except Exception:
            pass


# ───────────────────────── MINI APP (frontend) ─────────────────────────
HTML = r"""<!DOCTYPE html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>App</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&display=swap" rel="stylesheet">
<style>
:root{--g1:#ffe27a;--g2:#f5a300;--glass:rgba(10,32,28,.58);--bd:rgba(255,255,255,.15);--mut:rgba(255,255,255,.62)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none;-webkit-user-select:none}
html,body{margin:0;height:100%;overflow:hidden;font-family:'Manrope',system-ui,sans-serif;color:#fff;background:#0b1f1a}
#bg{position:fixed;inset:0;background:linear-gradient(#2f93e6 0%,#7cc8f4 36%,#d3f0c6 60%,#5fae4f 100%);overflow:hidden}
#bg:after{content:'';position:absolute;inset:0;background:linear-gradient(rgba(0,20,40,.05),rgba(0,25,15,.5))}
.cl{position:absolute;height:56px;width:190px;border-radius:50px;background:rgba(255,255,255,.6);filter:blur(12px);animation:drift 46s linear infinite}
.c1{top:10%;left:-220px}.c2{top:26%;left:-220px;width:250px;animation-duration:70s;animation-delay:-25s}
@keyframes drift{to{transform:translateX(140vw)}}
.hills{position:absolute;bottom:0;left:0;width:100%;height:34%}
#view{position:fixed;inset:0;overflow-y:auto;padding:calc(env(safe-area-inset-top) + 12px) 14px 120px;-webkit-overflow-scrolling:touch}
#view::-webkit-scrollbar{display:none}
h3{margin:18px 4px 8px;font-size:17px;font-weight:800;display:flex;align-items:center;gap:8px}
small{font-size:12px;color:var(--mut);font-weight:600}.mut{color:var(--mut)}.c{text-align:center}
.card{background:var(--glass);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid var(--bd);border-radius:20px;padding:12px;margin-bottom:10px;box-shadow:0 8px 24px rgba(0,0,0,.18)}
.row{display:flex;align-items:center;gap:12px}.sp{justify-content:space-between}.gr{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
.gr b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.click:active{transform:scale(.98)}
.ic{width:44px;height:44px;border-radius:13px;background:rgba(0,0,0,.42);display:grid;place-items:center;font-size:21px;flex:none}
.btn{border:1px solid var(--bd);border-radius:13px;padding:10px 14px;font:800 13px 'Manrope',sans-serif;color:#fff;background:rgba(255,255,255,.14);cursor:pointer;white-space:nowrap}
.btn:active{transform:scale(.96)}.btn.sm{padding:7px 11px}.btn.wide{width:100%;padding:15px;font-size:15px;margin-top:4px}
.btn.gold{background:linear-gradient(135deg,var(--g1),var(--g2));color:#3d2700;border:0;box-shadow:0 4px 14px rgba(245,163,0,.4)}
.btn:disabled{opacity:.5;box-shadow:none}
.inp{width:100%;padding:15px;border-radius:14px;border:1px solid var(--bd);background:rgba(0,0,0,.4);color:#fff;font:700 15px 'Manrope',sans-serif;outline:0;user-select:text;-webkit-user-select:text}
.inp::placeholder{color:rgba(255,255,255,.4)}.inp:focus{border-color:var(--g1)}
.mc{display:inline-grid;place-items:center;width:1.15em;height:1.15em;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff0a0,#f5a300);color:#5a3300;font:900 .72em/1 'Manrope';font-style:normal;vertical-align:-.15em;box-shadow:inset 0 0 0 1.5px #ffd24a}
.top{display:flex;justify-content:center;margin-bottom:6px}
.pill{display:flex;align-items:center;gap:8px;padding:5px 14px 5px 5px;border-radius:30px;background:var(--glass);backdrop-filter:blur(14px);border:1px solid var(--bd);font-weight:800}
.av{width:30px;height:30px;border-radius:50%;object-fit:cover;background:#1d3d34;display:grid;place-items:center;font-weight:800}
.av.big{width:104px;height:104px;font-size:40px;border:3px solid var(--g1);box-shadow:0 0 0 5px rgba(255,226,122,.25),0 10px 30px rgba(0,0,0,.35)}
.badge{background:var(--g2);color:#3d2700;border-radius:20px;padding:1px 9px;font-size:12px}
.ok{color:#7dffb0;font-weight:800;font-size:13px}.bad{color:#ff8a8a}
.hd{display:flex;align-items:center;gap:12px;margin-bottom:14px;font-size:17px;font-weight:800}
.bk{width:42px;height:42px;border-radius:50%;border:1px solid var(--bd);background:rgba(255,255,255,.18);color:#fff;font-size:20px;backdrop-filter:blur(10px)}
/* tap */
.tapv{min-height:calc(100vh - 150px);display:flex;flex-direction:column;align-items:center;justify-content:space-between}
.bigbal{display:flex;align-items:center;gap:10px;font-size:46px;font-weight:800;text-shadow:0 4px 18px rgba(0,0,0,.4);margin-top:6px}
.bigbal .mc{font-size:36px}
.chips{display:flex;gap:8px;margin-top:6px}.chips span{padding:5px 12px;border-radius:20px;background:var(--glass);border:1px solid var(--bd);font-size:12px;font-weight:800}
#tz{flex:1;display:grid;place-items:center;width:100%;touch-action:none}
.coinw{animation:flo 4s ease-in-out infinite}@keyframes flo{50%{transform:translateY(-10px)}}
.coin{width:min(70vw,280px);aspect-ratio:1;border-radius:50%;display:grid;place-items:center;position:relative;overflow:hidden;transition:transform .09s ease-out;
background:radial-gradient(circle at 30% 22%,#fff6b8,#ffcb3d 34%,#e28b00 76%,#9c5200);
box-shadow:0 26px 50px rgba(0,0,0,.4),0 0 60px rgba(255,200,60,.35),inset 0 0 0 9px #f2ac12,inset 0 0 0 13px #ffe58f,inset 0 -14px 34px rgba(120,60,0,.55)}
.coin b{font-size:min(38vw,150px);font-weight:800;color:#fff6cc;text-shadow:0 5px 0 #c27a00,0 12px 20px rgba(0,0,0,.35)}
.coin:after{content:'';position:absolute;top:-30%;left:-60%;width:40%;height:160%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);transform:rotate(20deg);animation:sh 4.5s ease-in-out infinite}
@keyframes sh{0%,60%{left:-60%}100%{left:130%}}
.en{width:100%;margin-top:6px}.entx{text-align:right;font-weight:800;font-size:20px;padding-right:4px}.entx small{font-size:14px;opacity:.7}
.bar{height:16px;border-radius:10px;background:rgba(0,0,0,.4);border:1px solid var(--bd);overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;width:100%;border-radius:10px;background:linear-gradient(90deg,#ffd24a,#f5a300);transition:width .25s}
.fl{position:fixed;font-weight:800;font-size:30px;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.55);pointer-events:none;z-index:9;animation:up .85s ease-out forwards}
@keyframes up{from{transform:translate(-50%,-50%)}to{transform:translate(-50%,-220%);opacity:0}}
/* nav */
#nav{position:fixed;left:12px;right:12px;bottom:calc(env(safe-area-inset-bottom) + 12px);display:flex;gap:2px;padding:6px;border-radius:26px;background:rgba(10,32,28,.72);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);border:1px solid var(--bd);box-shadow:0 10px 30px rgba(0,0,0,.35);z-index:5}
#nav button{flex:1;border:0;background:transparent;color:var(--mut);padding:8px 0 6px;border-radius:20px;font:800 9.5px 'Manrope',sans-serif;display:flex;flex-direction:column;align-items:center;gap:3px;position:relative}
#nav svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
#nav button.on{color:#fff;background:rgba(255,255,255,.16)}#nav button.on svg{stroke:var(--g1)}
/* misc */
.img{height:150px;border-radius:15px;background:linear-gradient(135deg,#1e6f8c,#7b2ff7) center/cover;position:relative;overflow:hidden}.img.big{height:190px;margin-bottom:6px}
.hp{position:absolute;top:8px;left:8px;border:0;padding:6px 11px;border-radius:20px;background:rgba(0,0,0,.45);color:#fff;font:800 12px 'Manrope';backdrop-filter:blur(8px)}.hp.on{color:#ff6b8b}
.ended{position:absolute;right:8px;top:8px;background:rgba(0,0,0,.6);padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}
.au{padding:8px}.ai{padding:8px 6px 2px;display:flex;flex-direction:column;gap:6px}
.qrow{display:flex;gap:8px;margin:12px 0 8px}.qi{text-align:center;font-size:20px;padding:10px}
.chipsr{display:flex;gap:8px;flex-wrap:wrap}.chipsr .btn{flex:1}
.row2{display:flex;justify-content:space-between;padding:7px 2px;font-weight:700}.row2 span{color:var(--mut)}.row2+.row2{border-top:1px solid var(--bd)}
.stats{display:flex;gap:8px;margin:10px 0}.stats>div{flex:1;background:rgba(0,0,0,.3);border-radius:14px;padding:10px;display:flex;flex-direction:column;gap:3px;text-align:center}
.rk{width:30px;text-align:center}.meh{border-color:var(--g1);background:rgba(245,163,0,.18)}
.pf{display:flex;flex-direction:column;align-items:center;margin:14px 0 18px;gap:4px}.pf h2{margin:10px 0 0;font-size:24px}
.balc{display:flex;justify-content:center;align-items:center;gap:12px;font-size:40px;font-weight:800;padding:18px}.balc .mc{font-size:34px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.grid .card{margin:0;display:flex;flex-direction:column;gap:12px;padding:16px;font-weight:800;min-height:112px;justify-content:space-between}
#sheet{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:flex-end;z-index:20}#sheet.on{display:flex}
.sh{width:100%;max-height:88vh;overflow-y:auto;background:rgba(13,38,33,.97);border-radius:26px 26px 0 0;padding:20px 16px calc(env(safe-area-inset-bottom) + 20px);border-top:1px solid var(--bd);animation:sl .22s ease-out}
@keyframes sl{from{transform:translateY(60px);opacity:0}}
#toast{position:fixed;left:50%;top:calc(env(safe-area-inset-top) + 14px);transform:translate(-50%,-90px);background:rgba(10,32,28,.95);border:1px solid var(--bd);padding:12px 18px;border-radius:16px;font-weight:800;font-size:14px;z-index:50;transition:transform .3s;max-width:90vw;text-align:center}
#toast.on{transform:translate(-50%,0)}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<div id="bg"><div class="cl c1"></div><div class="cl c2"></div>
<svg class="hills" viewBox="0 0 400 160" preserveAspectRatio="none"><path d="M0 90Q100 30 200 80T400 60V160H0Z" fill="#4c9a40" opacity=".75"/><path d="M0 125Q120 75 240 118T400 104V160H0Z" fill="#2c7634"/></svg></div>
<div id="view"></div><nav id="nav"></nav><div id="sheet"><div class="sh" id="shc"></div></div><div id="toast"></div>
<script>
const tg=Telegram.WebApp;tg.ready();tg.expand();
try{tg.setHeaderColor('#1b4d3e');tg.setBackgroundColor('#0b1f1a');tg.disableVerticalSwipes&&tg.disableVerticalSwipes()}catch(e){}
const $=s=>document.querySelector(s);
const N=n=>Number(n).toLocaleString('en');
const K=n=>n>=1000?(n/1000).toFixed(1)+'K':N(n);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let S={},CFG={},tab='tap',pending=0,busy=false,SV={},ORD={},AU=[],AQ={},TK=[],TT={};
const USER=(tg.initDataUnsafe&&tg.initDataUnsafe.user)||{};
async function api(p,b){const r=await fetch(p,{method:b===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Init':tg.initData},body:b===undefined?undefined:JSON.stringify(b)});let j={};try{j=await r.json()}catch(e){}if(!r.ok)throw new Error(j.error||'Xatolik');return j}
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('on'),2300)};
const hap=(t='light')=>{try{tg.HapticFeedback.impactOccurred(t)}catch(e){}};
const ok=()=>{try{tg.HapticFeedback.notificationOccurred('success')}catch(e){}};
const mc=()=>`<i class="mc">${esc(CFG.ch)}</i>`;
const view=(h,keep)=>{const v=$('#view'),s=v.scrollTop;v.innerHTML=h;v.scrollTop=keep?s:0};
const av=cls=>USER.photo_url?`<img class="av ${cls}" src="${esc(USER.photo_url)}">`:`<div class="av ${cls}">${esc((S.name||'?')[0])}</div>`;
const tbar=()=>`<div class="top"><div class="pill">${av('')}<b id="tbal">${K(S.balance)}</b>${mc()}</div></div>`;
const hd=(t,fn)=>`<div class="hd"><button class="bk" onclick="${fn}">←</button><span>${t}</span></div>`;
const sheet=h=>{$('#shc').innerHTML=h;$('#sheet').classList.add('on')};
const closeSheet=()=>$('#sheet').classList.remove('on');
$('#sheet').addEventListener('click',e=>{if(e.target.id==='sheet')closeSheet()});
const refresh=async()=>{const r=await api('/api/me',{});S=r;CFG=r.cfg};
const cd=ts=>{let s=Math.max(0,Math.floor(ts-Date.now()/1000));const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d} kun ${h} soat ${m} daqiqa`:`${h} soat ${m} daqiqa ${s%60} soniya`};

/* NAV */
const IC={boost:'<path d="M12 3c3 2 5 6 4 11l-2 3h-4l-2-3c-1-5 1-9 4-11z"/><circle cx="12" cy="10" r="1.6"/><path d="M8 15l-3 3M16 15l3 3M10 20l2 2 2-2"/>',tasks:'<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',tap:'<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',auction:'<path d="M13 4l7 7-3 3-7-7zM9 8l-5 5 3 3 5-5M4 21h9"/>',profile:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>'};
const TABS=[['boost','Boost'],['tasks','Vazifalar'],['tap','Bosish'],['auction','Auksion'],['profile','Profil']];
const navR=()=>{$('#nav').innerHTML=TABS.map(([k,l])=>`<button class="${k===tab?'on':''}" onclick="go('${k}')"><svg viewBox="0 0 24 24">${IC[k]}</svg>${l}</button>`).join('')};
function go(t){flush();tab=t;navR();closeSheet();const f={tap:tapV,tasks:taskV,boost:boostV,auction:auV,profile:profV}[t];Promise.resolve().then(f).catch(e=>toast(e.message))}

/* TAP */
function tapV(){
 view(`<div class="tapv"><div style="text-align:center"><div class="bigbal">${mc().replace('class="mc"','class="mc"')}<b id="bb"></b></div><div class="chips"><span>👆 +${S.power}</span><span>⚡ +${S.regen}/s</span></div></div>
 <div id="tz"><div class="coinw"><div class="coin" id="coin"><b>${esc(CFG.ch)}</b></div></div></div>
 <div class="en"><div class="entx"><span id="et"></span></div><div class="bar"><i id="eb"></i></div></div></div>`);
 updTap();
 $('#tz').addEventListener('pointerdown',e=>{e.preventDefault();
  if(S.energy<S.power){try{tg.HapticFeedback.notificationOccurred('error')}catch(_){}return}
  const c=$('#coin'),r=c.getBoundingClientRect(),dx=(e.clientX-r.left-r.width/2)/r.width,dy=(e.clientY-r.top-r.height/2)/r.height;
  c.style.transform=`perspective(500px) rotateX(${-dy*28}deg) rotateY(${dx*28}deg) scale(.94)`;setTimeout(()=>c.style.transform='',100);
  S.energy-=S.power;S.balance+=S.power;pending++;updTap();hap();
  const s=document.createElement('span');s.className='fl';s.textContent='+'+S.power;s.style.left=e.clientX+'px';s.style.top=e.clientY+'px';document.body.appendChild(s);setTimeout(()=>s.remove(),900)})
}
function updTap(){const a=$('#bb');if(!a)return;a.textContent=N(S.balance);$('#et').innerHTML=`⚡ ${Math.floor(S.energy)}<small>/${S.max}</small>`;$('#eb').style.width=(S.energy/S.max*100)+'%'}
async function flush(){if(!pending||busy)return;const n=pending;pending=0;busy=true;
 try{const r=await api('/api/tap',{n});const p=pending*S.power;Object.assign(S,r);S.balance+=p;S.energy=Math.max(0,S.energy-p);updTap()}catch(e){pending+=n}busy=false}
setInterval(flush,900);
setInterval(()=>{if(S.max){S.energy=Math.min(S.max,S.energy+S.regen/4);if(tab==='tap')updTap()}},250);
document.addEventListener('visibilitychange',()=>{if(document.hidden)flush()});

/* VAZIFALAR */
const KI={link:'🔗',channel:'✈️',ad:'🎬',youtube:'▶️'},KL={ad:'Ko‘rish',channel:'Obuna',link:'Ochish',youtube:'O‘tish'};
const lbl=t=>{const s=TT[t.id];if(!s)return KL[t.kind]||'Bajarish';const r=Math.ceil((s.at-Date.now())/1000);return r>0?r+'s':(t.kind==='channel'?'Tekshirish':'Olish')};
async function taskV(){TK=await api('/api/tasks');trk()}
function trk(keep){const o=TK.filter(t=>!t.done).length,l=TK.slice().sort((a,b)=>a.done-b.done);
 view(tbar()+`<div class="card row"><div class="ic">👥</div><div class="gr"><b>Do‘stlarni taklif qiling</b><small>Har biri uchun +${N(CFG.ref)} ${mc()} · taklif qilingan: ${S.refs}</small></div><button class="btn gold" onclick="inv()">Taklif</button></div>
 <h3>Vazifalar <span class="badge">${o}</span></h3>`+(l.map(t=>`<div class="card row"><div class="ic">${KI[t.kind]||'⭐'}</div><div class="gr"><b>${esc(t.title)}</b><small>+${N(t.reward)} ${mc()}${t.limit?` · ${t.cnt}/${t.limit}`:''}</small></div>${t.done?'<span class="ok">✓ Bajarildi</span>':`<button class="btn" id="tk${t.id}" onclick="tdo(${t.id})">${lbl(t)}</button>`}</div>`).join('')||'<p class="mut c">Hozircha vazifa yo‘q</p>'),keep)}
function inv(){const l=`https://t.me/${CFG.bot}?start=ref_${S.id}`;tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(l)}&text=${encodeURIComponent('🎁 Tanga yig‘ing, auksionda sovg‘alar yuting! Qo‘shiling:')}`)}
let adsL=null;const loadAds=()=>adsL||(adsL=new Promise((res,rej)=>{const s=document.createElement('script');s.src='https://sad.adsgram.ai/js/sad.min.js';s.onload=res;s.onerror=rej;document.head.appendChild(s)}));
async function tdo(id){const t=TK.find(x=>x.id==id);
 if(TT[id]){if(Date.now()<TT[id].at)return toast('Biroz kuting…');
  try{const r=await api(`/api/task/${id}/claim`,{});delete TT[id];S.balance+=r.reward;ok();toast(`+${N(r.reward)} ${CFG.coin}`);TK=await api('/api/tasks');trk(1)}catch(e){toast(e.message)}return}
 try{
  if(t.kind==='ad'&&CFG.ads){await loadAds();await api(`/api/task/${id}/start`,{});await window.Adsgram.init({blockId:CFG.ads}).show();TT[id]={at:0};return tdo(id)}
  await api(`/api/task/${id}/start`,{});TT[id]={at:Date.now()+t.wait*1000};
  if(t.url){/^https:\/\/t\.me\//.test(t.url)?tg.openTelegramLink(t.url):tg.openLink(t.url)}
 }catch(e){toast(e.message||'Reklama topilmadi')}}
setInterval(()=>{for(const id in TT){const b=$('#tk'+id),t=TK.find(x=>x.id==id);if(b&&t){b.textContent=lbl(t);b.classList.toggle('gold',Date.now()>=TT[id].at)}}},500);

/* BOOST */
async function boostV(){
 const [sv,od]=await Promise.all([api('/api/services'),api('/api/orders')]);SV=sv;
 const up=[['tap','👆','Bosish kuchi',`+${S.power} → +${S.power+1}`],['energy','🔋','Energiya hajmi',`${S.max} → ${S.max+100}`],['regen','⚡','Tiklanish tezligi',`${S.regen}/s → ${S.regen+1}/s`]];
 view(tbar()+`<h3>Kuchaytirish</h3>`+up.map(([k,i,t,d])=>{const c=S.cost[k];return `<div class="card row"><div class="ic">${i}</div><div class="gr"><b>${t}</b><small>Daraja ${S.lv[k]} · ${c===null?'MAX':d}</small></div>${c===null?'':`<button class="btn gold" onclick="upg('${k}')">${N(c)} ${mc()}</button>`}</div>`}).join('')
 +`<h3>Xizmatlar</h3>`+Object.entries(SV).map(([k,p])=>`<div class="card row click" onclick="plat('${k}')"><div class="ic">${p.i}</div><b class="gr">${esc(p.t)}</b><span>›</span></div>`).join('')
 +(od.length?`<h3>Buyurtmalarim</h3>`+od.map(o=>`<div class="card row sp"><div class="gr"><b>#${o.id} ${esc(o.title)}</b><small>${N(o.qty)} ta · ${N(o.cost)} ${CFG.coin}</small></div><span class="${o.status==='done'?'ok':o.status==='cancel'?'bad':''}">${{pending:'⏳ Kutilmoqda',done:'✓ Bajarildi',cancel:'Bekor'}[o.status]}</span></div>`).join(''):''))}
async function upg(k){try{const r=await api('/api/upgrade',{k});Object.assign(S,r);ok();toast('Kuchaytirildi! 🔥');boostV()}catch(e){toast(e.message)}}
function plat(k){const p=SV[k];view(hd(esc(p.t),'boostV()')+Object.entries(p.s).map(([s,it])=>`<div class="card row click" onclick="svc('${k}','${s}')"><div class="ic">${it.i}</div><div class="gr"><b>${esc(it.t)}</b><small>1000 ta = ${N(it.p)} ${mc()}</small></div><span>›</span></div>`).join(''))}
function svc(k,s){const it=SV[k].s[s];ORD={k,s,min:it.min,p:it.p,qty:it.min};
 view(hd(esc(it.t),`plat('${k}')`)+`<small>Havolani kiriting:</small><input id="lk" class="inp" placeholder="${esc(it.ph)}" style="margin:8px 0 12px">
 <div class="card"><div class="row sp"><b>${esc(it.t)}</b><small>Min: ${it.min}</small></div><small>1000 ta = ${N(it.p)} ${mc()}</small>
 <div class="qrow"><button class="btn" onclick="qd(-1)">−${it.min}</button><input id="qn" class="inp qi" type="number" inputmode="numeric" value="${it.min}" oninput="qs(+this.value,1)"><button class="btn" onclick="qd(1)">+${it.min}</button></div>
 <div class="chipsr">${[1,5,10,50].map(m=>`<button class="btn sm" onclick="qs(${it.min*m})">${N(it.min*m)}</button>`).join('')}</div></div>
 <div class="card" id="sm"></div><button class="btn gold wide" id="ob" onclick="order()"></button>`);qs(it.min)}
function qs(n,inp){ORD.qty=Math.max(0,Math.floor(n)||0);if(!inp)$('#qn').value=ORD.qty;const c=Math.ceil(ORD.qty*ORD.p/1000);
 $('#sm').innerHTML=`<div class="row2"><span>Miqdor</span><b>${N(ORD.qty)} ta</b></div><div class="row2"><span>Jami</span><b>${N(c)} ${mc()}</b></div><div class="row2"><span>Balansingiz</span><b class="${S.balance<c?'bad':''}">${N(S.balance)} ${mc()}</b></div>`;
 const b=$('#ob');b.disabled=ORD.qty<ORD.min||S.balance<c;b.textContent=ORD.qty<ORD.min?`Minimal: ${ORD.min}`:S.balance<c?'Tanga yetarli emas':'Buyurtma berish'}
const qd=d=>qs(Math.max(ORD.min,ORD.qty+d*ORD.min));
async function order(){const link=$('#lk').value.trim();if(link.length<4)return toast('Havolani kiriting');
 try{const r=await api('/api/order',{k:ORD.k,s:ORD.s,link,qty:ORD.qty});Object.assign(S,r);ok();toast('Buyurtma qabul qilindi ✅');boostV()}catch(e){toast(e.message)}}

/* AUKSION */
async function auV(){AU=await api('/api/auctions');auR()}
function auR(keep){view(tbar()+(AU.map(a=>`<div class="card au click" onclick="auO(${a.id})"><div class="img" style="${a.image?`background-image:url('${esc(a.image)}')`:''}"><button class="hp ${a.liked?'on':''}" onclick="event.stopPropagation();lk(${a.id})">${a.liked?'♥':'♡'} ${a.likes}</button>${a.done?'<span class="ended">Yakunlangan</span>':''}</div><div class="ai"><b>${esc(a.title)}</b><div class="row sp"><span><b>${N(a.price)}</b> ${mc()} <small>/ bilet</small></span>${a.done?`<span class="ok">🏆 ${esc(a.winner_name||'—')}</span>`:`<span class="ok cd" data-e="${a.ends}">${cd(a.ends)}</span>`}</div></div></div>`).join('')||'<p class="mut c" style="margin-top:40px">Hozircha auksion yo‘q</p>'),keep)}
setInterval(()=>document.querySelectorAll('.cd').forEach(e=>e.textContent=cd(+e.dataset.e)),1000);
async function lk(id){const a=AU.find(x=>x.id==id);a.liked=a.liked?0:1;a.likes+=a.liked?1:-1;auR(1);hap();try{await api(`/api/auction/${id}/like`,{})}catch(e){}}
function auO(id){const a=AU.find(x=>x.id==id);AQ={id,q:1,price:a.price};
 sheet(`<div class="img big" style="${a.image?`background-image:url('${esc(a.image)}')`:''}"></div><h3 style="margin-top:8px">${esc(a.title)}</h3>
 <div class="stats"><div><small>Jami biletlar</small><b>${N(a.total)}</b></div><div><small>Sizning biletlaringiz</small><b>${N(a.mine)}</b></div><div><small>Imkoniyatingiz</small><b>${a.total?(a.mine/a.total*100).toFixed(1):0}%</b></div></div>`+
 (a.done?`<p class="c ok">🏆 G‘olib: ${esc(a.winner_name||'—')}</p>`:`<div class="qrow"><button class="btn" onclick="aq(-1)">−</button><input id="aqn" class="inp qi" type="number" inputmode="numeric" value="1" oninput="aq(0,+this.value)"><button class="btn" onclick="aq(1)">+</button></div>
 <div class="chipsr">${[1,5,10,50].map(m=>`<button class="btn sm" onclick="aq(0,${m})">${m}</button>`).join('')}</div><div class="card" id="asm" style="margin-top:12px"></div><button class="btn gold wide" id="abtn" onclick="abuy()"></button>`));if(!a.done)aq(0,1)}
function aq(d,v){AQ.q=Math.max(1,Math.min(1000,Math.floor(v!==undefined?v:AQ.q+d)||1));if(v===undefined)$('#aqn').value=AQ.q;const c=AQ.q*AQ.price;
 $('#asm').innerHTML=`<div class="row2"><span>Biletlar</span><b>${N(AQ.q)} ta</b></div><div class="row2"><span>Jami</span><b>${N(c)} ${mc()}</b></div><div class="row2"><span>Balansingiz</span><b class="${S.balance<c?'bad':''}">${N(S.balance)} ${mc()}</b></div>`;
 const b=$('#abtn');b.disabled=S.balance<c;b.textContent=S.balance<c?'Tanga yetarli emas':'Bilet olish'}
async function abuy(){try{const r=await api(`/api/auction/${AQ.id}/buy`,{qty:AQ.q});Object.assign(S,r);ok();closeSheet();toast('Bilet olindi! Omad 🍀');AU=await api('/api/auctions');auR(1)}catch(e){toast(e.message)}}

/* PROFIL */
function profV(){view(`<div class="pf">${av('big')}<h2>${esc(S.name)}</h2><small>${S.username?'@'+esc(S.username):'ID '+S.id}</small></div>
 <div class="card balc">${mc()}<b>${N(S.balance)}</b></div>
 <div class="grid"><div class="card click" onclick="promo()"><div class="ic">🎟</div>Promokod</div><div class="card click" onclick="sendV()"><div class="ic">📤</div>Tanga yuborish</div>
 <div class="card click" onclick="rate()"><div class="ic">📊</div>Reyting</div><div class="card click" onclick="paid()"><div class="ic">🏅</div>Pullik xizmatlar</div></div>`)}
function promo(){sheet(`<h3 style="margin-top:0">🎟 Promokod</h3><input id="pc" class="inp" placeholder="KODNI KIRITING" style="margin:8px 0 12px;text-transform:uppercase"><button class="btn gold wide" onclick="dopromo()">Faollashtirish</button>`)}
async function dopromo(){try{const r=await api('/api/promo',{code:$('#pc').value});S.balance+=r.reward;ok();closeSheet();toast(`+${N(r.reward)} ${CFG.coin} 🎉`);profV()}catch(e){toast(e.message)}}
function sendV(){sheet(`<h3 style="margin-top:0">📤 Tanga yuborish</h3><input id="st" class="inp" placeholder="@username yoki ID" style="margin:8px 0"><input id="sa" class="inp" type="number" inputmode="numeric" placeholder="Miqdor (min 10)" style="margin-bottom:12px"><button class="btn gold wide" onclick="dosend()">Yuborish</button>`)}
async function dosend(){try{const r=await api('/api/send',{to:$('#st').value,amount:+$('#sa').value});Object.assign(S,r);ok();closeSheet();toast('Yuborildi ✅');profV()}catch(e){toast(e.message)}}
async function rate(){const r=await api('/api/rating');view(hd('Reyting',`go('profile')`)+`<div class="card row sp meh"><b>Sizning o‘rningiz</b><b>#${r.me}</b></div>`+r.top.map((u,i)=>`<div class="card row ${u.id==S.id?'meh':''}"><b class="rk">${['🥇','🥈','🥉'][i]||i+1}</b><div class="gr"><b>${esc(u.name)}</b><small>${u.username?'@'+esc(u.username):''}</small></div><b>${K(u.balance)} ${mc()}</b></div>`).join(''))}
function paid(){view(hd('Pullik xizmatlar',`go('profile')`)+CFG.paid.map(p=>`<div class="card row"><div class="ic">${p[0]}</div><div class="gr"><b>${esc(p[1])}</b><small>${esc(p[2])}</small></div><button class="btn gold" onclick="tg.openTelegramLink('https://t.me/${esc(CFG.admin)}')">Bog‘lanish</button></div>`).join(''))}

(async()=>{try{await refresh()}catch(e){document.body.innerHTML='<p style="padding:40px;text-align:center">Ilovani Telegram ichida oching.</p>';return}go('tap')})();
</script></body></html>"""


# ───────────────────────── START ─────────────────────────
def main():
    global BOT_USER
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN kiritilmagan!")
    me = tg("getMe") or {}
    BOT_USER = me.get("username", "")
    if BASE_URL:
        tg("setChatMenuButton", menu_button={"type": "web_app", "text": "O‘ynash", "web_app": {"url": BASE_URL}})
        threading.Thread(target=keepalive, daemon=True).start()
    threading.Thread(target=poll, daemon=True).start()
    threading.Thread(target=auction_loop, daemon=True).start()
    log.info("Bot @%s ishga tushdi, port %s", BOT_USER, PORT)
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
