# -*- coding: utf-8 -*-
"""
TAP-TO-EARN Telegram Mini App  —  bitta fayl: bot + server + Mini App + ADMIN PANEL
Render: Build = pip install -r requirements.txt | Start = python main.py
ENV: BOT_TOKEN, ADMIN_IDS (vergul bilan), DB_PATH (ixtiyoriy, masalan /data/data.db)
Qolgan hamma narsa (nom, mukofot, vazifa, auksion, xizmat, narx, matn...) — Mini App ichidagi Admin paneldan.
"""
import os, re, time, json, hmac, hashlib, sqlite3, threading, random, math, logging, html as _html
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify, g, Response, abort
from werkzeug.exceptions import HTTPException

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE_URL = (os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
ADMINS = {int(i) for i in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if i.isdigit()}
DB_PATH = os.getenv("DB_PATH", "data.db")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")

# (kalit, nomi, standart, tur, guruh)
SETDEF = [
    ("coin_name", "Tanga nomi", os.getenv("COIN_NAME", "AkCoin"), "text", "Asosiy"),
    ("coin_char", "Tanga belgisi (1-2 harf)", "A", "text", "Asosiy"),
    ("admin_username", "Admin username (aloqa uchun)", os.getenv("ADMIN_USERNAME", "Akmaljon1100"), "text", "Asosiy"),
    ("announce", "Bosh sahifa e’loni (bo‘sh = yo‘q)", "", "text", "Asosiy"),
    ("maintenance", "Texnik ishlar rejimi", "0", "sel01", "Asosiy"),
    ("start_bonus", "Yangi foydalanuvchi bonusi", "1000", "int", "Mukofotlar"),
    ("ref_reward", "Do‘st taklif qilgan uchun mukofot", "1000", "int", "Mukofotlar"),
    ("ref_new", "Taklif orqali kelgan do‘stga qo‘shimcha", "500", "int", "Mukofotlar"),
    ("daily_base", "Kunlik bonus — 1-kun", "100", "int", "Mukofotlar"),
    ("daily_step", "Kunlik bonus — har kunga qo‘shimcha", "100", "int", "Mukofotlar"),
    ("base_energy", "Boshlang‘ich energiya", "200", "int", "O‘yin"),
    ("energy_step", "Energiya upgrade qadami", "100", "int", "O‘yin"),
    ("max_lvl", "Upgrade maksimal darajasi", "12", "int", "O‘yin"),
    ("up_tap", "Bosish kuchi — boshlang‘ich narx", "500", "int", "O‘yin"),
    ("up_energy", "Energiya — boshlang‘ich narx", "300", "int", "O‘yin"),
    ("up_regen", "Tiklanish — boshlang‘ich narx", "400", "int", "O‘yin"),
    ("up_growth", "Narx o‘sish koeffitsiyenti", "1.9", "float", "O‘yin"),
    ("lvl_bronze", "Bronza darajasi chegarasi", "5000", "int", "Darajalar"),
    ("lvl_silver", "Kumush darajasi chegarasi", "25000", "int", "Darajalar"),
    ("lvl_gold", "Oltin darajasi chegarasi", "100000", "int", "Darajalar"),
    ("lvl_platinum", "Platina darajasi chegarasi", "500000", "int", "Darajalar"),
    ("lvl_diamond", "Brilliant darajasi chegarasi", "2000000", "int", "Darajalar"),
    ("lvl_legend", "Afsona darajasi chegarasi", "10000000", "int", "Darajalar"),
    ("wait_link", "Havola vazifasi kutish vaqti (soniya)", "8", "int", "Vazifalar"),
    ("wait_youtube", "YouTube vazifasi kutish vaqti (soniya)", "15", "int", "Vazifalar"),
    ("wait_ad", "Reklama vazifasi kutish vaqti (soniya)", "3", "int", "Vazifalar"),
    ("wait_channel", "Kanal obunasi kutish vaqti (soniya)", "0", "int", "Vazifalar"),
    ("min_send", "Tanga yuborish minimumi", "10", "int", "O‘yin"),
    ("send_fee", "Yuborish komissiyasi (%)", "0", "int", "O‘yin"),
    ("welcome", "/start xabari ({name} va {coin} ishlatish mumkin, HTML bor)",
     "👋 <b>{coin}</b> ga xush kelibsiz, {name}!\n\n👆 Tanga bosing · 🎯 vazifa bajaring · 🏆 auksionda yuting · 🚀 xizmat buyurtma qiling\n\nBoshlash uchun pastdagi tugmani bosing 👇",
     "area", "Matnlar"),
    ("adsgram", "Adsgram Block ID (reklama daromadi)", os.getenv("ADSGRAM_BLOCK_ID", ""), "text", "Integratsiya"),
    ("smm_url", "SMM panel API manzili (ixtiyoriy)", "", "text", "Integratsiya"),
    ("smm_key", "SMM panel API kaliti", "", "text", "Integratsiya"),
]
DEFV = {k: d for k, _, d, _, _ in SETDEF}
UPCOL = {"tap": "tap_lvl", "energy": "energy_lvl", "regen": "regen_lvl"}
def level_table():
    return [(0, "Yangi"), (si("lvl_bronze"), "Bronza"), (si("lvl_silver"), "Kumush"),
            (si("lvl_gold"), "Oltin"), (si("lvl_platinum"), "Platina"),
            (si("lvl_diamond"), "Brilliant"), (si("lvl_legend"), "Afsona")]

SEED_SERV = [
    ("telegram", "Telegramda reklama chiqish", "✈️", [
        ("sub", "Kanalga obunachi", "👥", 60000, 100, "@kanal yoki t.me/kanal"),
        ("view", "Kanal postiga prasmotr", "👁", 5000, 100, "https://t.me/kanal/123"),
        ("react", "Kanal postiga reaksiya", "😍", 9000, 50, "https://t.me/kanal/123")]),
    ("instagram", "Instagramda reklama chiqish", "📸", [
        ("follow", "Obunachi", "👥", 80000, 100, "https://instagram.com/username"),
        ("like", "Layk", "❤️", 20000, 50, "https://instagram.com/p/..."),
        ("view", "Reels prasmotr", "👁", 8000, 100, "https://instagram.com/reel/...")]),
    ("tiktok", "TikTokda reklama chiqish", "🎵", [
        ("follow", "Obunachi", "👥", 90000, 100, "https://tiktok.com/@username"),
        ("like", "Layk", "❤️", 20000, 50, "https://tiktok.com/@u/video/..."),
        ("view", "Prasmotr", "👁", 6000, 100, "https://tiktok.com/@u/video/...")]),
]
SEED_PAID = [("📢", "Reklama joylashtirish", "Bot va kanallarda reklama"),
             ("🤖", "Bot / Mini App buyurtma", "Sizga maxsus bot yasab beramiz"),
             ("💎", "Tanga sotib olish", "Tangani pul evaziga olish")]

# ───────────────────────── DB ─────────────────────────
DB = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
DB.row_factory = sqlite3.Row
LK = threading.RLock()
ST, ADMSET = {}, set(ADMINS)


def q(sql, a=(), one=False):
    with LK:
        r = DB.execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r


def x(sql, a=()):
    with LK:
        return DB.execute(sql, a).lastrowid


def one(sql, a=()):
    return q(sql, a, True)[0]


def get(uid):
    return q("select * from users where id=?", (uid,), True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def init_db():
    with LK:
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
create table if not exists settings(k text primary key,v text);
create table if not exists admins(id integer primary key,note text default '');
create table if not exists paid(id integer primary key autoincrement,icon text default '⭐',title text,descr text default '',sort integer default 0,active integer default 1);
create table if not exists plats(slug text primary key,title text,icon text default '✨',sort integer default 0,active integer default 1);
create table if not exists svcs(id integer primary key autoincrement,plat text,slug text,title text,icon text default '✨',price integer,minq integer default 100,ph text default '',smm_id text default '',sort integer default 0,active integer default 1);
""")
        for t, c, d in [("users", "earned", "integer default 0"), ("users", "daily_day", "text default ''"),
                        ("users", "streak", "integer default 0"), ("tasks", "sort", "integer default 0"),
                        ("orders", "ext", "text default ''")]:
            try:
                DB.execute(f"alter table {t} add column {c} {d}")
            except sqlite3.OperationalError:
                pass
        DB.execute("update users set earned=balance where earned=0 or earned is null")
        for k, _, d, _, _ in SETDEF:
            DB.execute("insert or ignore into settings values(?,?)", (k, d))
        if not DB.execute("select 1 from plats").fetchone():
            for i, (pk, pt, pi, items) in enumerate(SEED_SERV):
                DB.execute("insert into plats(slug,title,icon,sort) values(?,?,?,?)", (pk, pt, pi, i))
                for j, (s, t, ic, p, m, ph) in enumerate(items):
                    DB.execute("insert into svcs(plat,slug,title,icon,price,minq,ph,sort) values(?,?,?,?,?,?,?,?)", (pk, s, t, ic, p, m, ph, j))
        if not DB.execute("select 1 from paid").fetchone():
            for i, (ic, t, d) in enumerate(SEED_PAID):
                DB.execute("insert into paid(icon,title,descr,sort) values(?,?,?,?)", (ic, t, d, i))
    reload_st()
    reload_adm()


def reload_st():
    ST.clear()
    for r in q("select k,v from settings"):
        ST[r["k"]] = r["v"]


def reload_adm():
    ADMSET.clear()
    ADMSET.update(ADMINS)
    ADMSET.update(r["id"] for r in q("select id from admins"))


def sv(k):
    return ST.get(k, DEFV.get(k, ""))


def si(k):
    try:
        return int(float(sv(k)))
    except Exception:
        return int(float(DEFV[k]))


def sf(k):
    try:
        return float(sv(k))
    except Exception:
        return float(DEFV[k])


def coin():
    return sv("coin_name") or "Coin"


def ch():
    return (sv("coin_char") or coin()[0]).upper()[:2]


def is_admin(uid):
    return uid in ADMSET


init_db()

# ───────────────────────── TELEGRAM ─────────────────────────
BOT_USER = ""


def tg(method, **p):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=p, timeout=40).json()
        if r.get("ok"):
            return r.get("result")
        if method not in ("getChatMember", "sendMessage", "sendPhoto", "getUpdates"):
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
    for a in list(ADMSET):
        send(a, text, markup)


# ───────────────────────── O‘YIN MANTIQI ─────────────────────────
def maxe(u): return si("base_energy") + si("energy_step") * u["energy_lvl"]
def regen(u): return 1 + u["regen_lvl"]
def power(u): return 1 + u["tap_lvl"]
def cur_e(u, now): return min(maxe(u), u["energy"] + max(0, now - (u["energy_ts"] or now)) * regen(u))


def ucost(k, l):
    return None if l >= si("max_lvl") else int(si("up_" + k) * sf("up_growth") ** l)


def gain(uid, amt):
    x("update users set balance=balance+?,earned=earned+? where id=?", (amt, max(amt, 0), uid))


def lvl_info(e):
    lvls = level_table()
    i = max(j for j, (t, _) in enumerate(lvls) if e >= t)
    nx = lvls[i + 1] if i + 1 < len(lvls) else None
    return dict(i=i, name=lvls[i][1], next=nx[1] if nx else None, lo=lvls[i][0], hi=nx[0] if nx else None)


def daily_info(u):
    t = today()
    y = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    last, st = u["daily_day"] or "", u["streak"] or 0
    avail = last != t
    if avail and last != y:
        st = 0
    b, s = si("daily_base"), si("daily_step")
    rw = [b + s * i for i in range(6)] + [2 * (b + s * 6)]
    dn = (st % 7) if avail else (((st - 1) % 7) + 1 if st else 0)
    return dict(avail=avail, streak=st, done=dn, rewards=rw)


def state(u):
    now = time.time()
    return dict(id=u["id"], name=u["name"], username=u["username"], balance=u["balance"], earned=u["earned"], refs=u["refs"],
                energy=int(cur_e(u, now)), max=maxe(u), regen=regen(u), power=power(u), estep=si("energy_step"), maxl=si("max_lvl"),
                lv={k: u[c] for k, c in UPCOL.items()}, cost={k: ucost(k, u[c]) for k, c in UPCOL.items()},
                lvl=lvl_info(u["earned"]), daily=daily_info(u))


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
        b = si("start_bonus") + (si("ref_new") if ok else 0)
        x("insert into users(id,name,username,balance,earned,energy,energy_ts,ref_by,created,last_seen) values(?,?,?,?,?,?,?,?,?,?)",
          (uid, name, un, b, b, si("base_energy"), now, ref if ok else None, now, now))
        if ok:
            gain(ref, si("ref_reward"))
            x("update users set refs=refs+1 where id=?", (ref,))
    if ok:
        send(ref, f"🎉 <b>{_html.escape(name)}</b> havolangiz orqali qo‘shildi! +{si('ref_reward')} {coin()}")
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


def finish_auction(aid):
    with LK:
        a = q("select * from auctions where id=?", (aid,), True)
        if not a or a["done"]:
            return None
        rows = q("select user_id,cnt from tickets where auction_id=?", (aid,))
        if not rows:
            x("update auctions set done=1 where id=?", (aid,))
            return {}
        w = random.choices([r["user_id"] for r in rows], weights=[r["cnt"] for r in rows])[0]
        wu = get(w)
        x("update auctions set done=1,winner_id=?,winner_name=?,ends=? where id=?", (w, wu["name"], min(a["ends"], time.time()), aid))
    send(w, f"🏆 <b>Tabriklaymiz!</b> Siz «{_html.escape(a['title'])}» auksionida g‘olib bo‘ldingiz!\nAdmin bog‘lanadi: @{sv('admin_username').lstrip('@')}")
    notify_admins(f"🏆 Auksion #{aid} «{_html.escape(a['title'])}» g‘olibi: {_html.escape(wu['name'])} (<code>{w}</code>)")
    return dict(id=w, name=wu["name"])


def order_act(oid, act):
    with LK:
        o = q("select * from orders where id=?", (oid,), True)
        if not o or o["status"] not in ("pending", "processing"):
            return False
        if act == "done":
            x("update orders set status='done' where id=?", (oid,))
            msg = f"✅ Buyurtmangiz #{oid} bajarildi!"
        else:
            x("update orders set status='cancel' where id=?", (oid,))
            x("update users set balance=balance+? where id=?", (o["cost"], o["user_id"]))
            msg = f"❌ Buyurtma #{oid} bekor qilindi. {o['cost']} {coin()} qaytarildi."
    send(o["user_id"], msg)
    return True


def smm(action, **p):
    try:
        return requests.post(sv("smm_url"), data=dict(key=sv("smm_key"), action=action, **p), timeout=25).json()
    except Exception as e:
        log.warning("smm %s", e)
        return None


# ───────────────────────── FLASK ─────────────────────────
app = Flask(__name__)
app.json.sort_keys = False


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
        g.uid, g.adm = u["id"], is_admin(u["id"])
        if u["banned"]:
            return jsonify(error="Siz bloklangansiz"), 403
        if sv("maintenance") == "1" and not g.adm:
            return jsonify(error="maint"), 503
        return f(*a, **k)
    return w


def adm(f):
    @auth
    @wraps(f)
    def w(*a, **k):
        if not g.adm:
            return jsonify(error="Ruxsat yo‘q"), 403
        return f(*a, **k)
    return w


@app.get("/")
def index():
    return Response(HTML, mimetype="text/html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return "ok"


IMGC = {}


@app.get("/img/<fid>")
def img(fid):
    if not re.fullmatch(r"[\w-]{10,200}", fid):
        abort(404)
    if fid not in IMGC:
        f = tg("getFile", file_id=fid)
        if not f:
            abort(404)
        r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=30)
        if len(IMGC) < 60:
            IMGC[fid] = (r.content, r.headers.get("Content-Type", "image/jpeg"))
        else:
            return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"))
    d, ct = IMGC[fid]
    return Response(d, mimetype=ct, headers={"Cache-Control": "public,max-age=86400"})


def services():
    out = {}
    for p in q("select * from plats where active=1 order by sort,slug"):
        out[p["slug"]] = dict(t=p["title"], i=p["icon"], s={})
    for s in q("select * from svcs where active=1 order by sort,id"):
        if s["plat"] in out:
            out[s["plat"]]["s"][s["slug"]] = dict(t=s["title"], i=s["icon"], p=s["price"], min=s["minq"], ph=s["ph"])
    return {k: v for k, v in out.items() if v["s"]}


@app.post("/api/me")
@auth
def api_me():
    d = state(get(g.uid))
    d["cfg"] = dict(coin=coin(), ch=ch(), bot=BOT_USER, admin=sv("admin_username").lstrip("@"), ads=sv("adsgram"),
                    ref=si("ref_reward"), refnew=si("ref_new"), announce=sv("announce"), is_admin=g.adm,
                    paid=[[p["icon"], p["title"], p["descr"]] for p in q("select * from paid where active=1 order by sort,id")])
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
        gn = n * p
        x("update users set balance=balance+?,earned=earned+?,energy=?,energy_ts=? where id=?", (gn, gn, e - gn, now, g.uid))
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


@app.post("/api/daily")
@auth
def api_daily():
    with LK:
        u = get(g.uid)
        di = daily_info(u)
        if not di["avail"]:
            raise Err("Bugungi bonus olingan")
        rw = di["rewards"][di["done"]]
        gain(g.uid, rw)
        x("update users set daily_day=?,streak=? where id=?", (today(), di["streak"] + 1, g.uid))
    return jsonify(reward=rw, state=state(get(g.uid)))


# ----- vazifalar -----
TS = {}
def task_wait(kind):
    return max(0, si("wait_" + kind)) if kind in ("link", "youtube", "ad", "channel") else 5


def tdone(uid, t):
    d = today() if t["daily_limit"] > 0 else "once"
    r = q("select cnt from task_done where user_id=? and task_id=? and day=?", (uid, t["id"], d), True)
    return (r["cnt"] if r else 0), d


@app.get("/api/tasks")
@auth
def api_tasks():
    out = []
    for t in q("select * from tasks where active=1 order by sort,id"):
        c, _ = tdone(g.uid, t)
        lim = t["daily_limit"]
        out.append(dict(id=t["id"], title=t["title"], kind=t["kind"], url=t["url"], reward=t["reward"], cnt=c, limit=lim,
                        done=c >= (lim if lim > 0 else 1), wait=task_wait(t["kind"])))
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
    if not st or time.time() - st < task_wait(t["kind"]):
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
        gain(g.uid, t["reward"])
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
    rows = q(sel + "where a.done=0 order by a.ends", (g.uid, g.uid)) + q(sel + "where a.done=1 order by a.ends desc limit 3", (g.uid, g.uid))
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
    by = {"balance": "balance", "refs": "refs", "earned": "earned"}.get(request.args.get("by", "balance"), "balance")
    top = q(f"select id,name,username,balance,refs,earned from users where banned=0 order by {by} desc limit 50")
    me = get(g.uid)
    rank = one(f"select count(*)+1 from users where {by}>? and banned=0", (me[by],))
    return jsonify(top=[dict(r) for r in top], me=rank, by=by)


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
        gain(g.uid, p["reward"])
    return jsonify(reward=p["reward"])


@app.post("/api/send")
@auth
def api_send():
    d = request.json or {}
    to = str(d.get("to", "")).strip().lstrip("@").lower()
    amt = int(d.get("amount", 0))
    if amt < si("min_send"):
        raise Err(f"Minimal miqdor: {si('min_send')}")
    fee = amt * si("send_fee") // 100
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
        x("update users set balance=balance+? where id=?", (amt - fee, r["id"]))
    send(r["id"], f"💸 <b>{_html.escape(u['name'])}</b> sizga {amt - fee} {coin()} yubordi!")
    return jsonify(state(get(g.uid)))


# ----- boost xizmatlar -----
@app.get("/api/services")
@auth
def api_services():
    return jsonify(services())


@app.get("/api/orders")
@auth
def api_orders():
    rows = q("select o.*,(select title from svcs where plat=o.plat and slug=o.svc) title from orders o where user_id=? order by id desc limit 10", (g.uid,))
    return jsonify([dict(id=o["id"], title=o["title"] or o["svc"], qty=o["qty"], cost=o["cost"], status=o["status"]) for o in rows])


@app.post("/api/order")
@auth
def api_order():
    d = request.json or {}
    k, s = d.get("k"), d.get("s")
    link = str(d.get("link", "")).strip()[:300]
    qty = int(d.get("qty", 0))
    it = q("select s.*,p.title ptitle from svcs s join plats p on p.slug=s.plat where s.plat=? and s.slug=? and s.active=1 and p.active=1", (k, s), True)
    if not it:
        raise Err("Xizmat topilmadi")
    if qty < it["minq"] or qty > 1000000:
        raise Err("Noto‘g‘ri miqdor")
    if len(link) < 4:
        raise Err("Havolani kiriting")
    cost = math.ceil(qty * it["price"] / 1000)
    with LK:
        u = get(g.uid)
        if u["balance"] < cost:
            raise Err("Tanga yetarli emas")
        x("update users set balance=balance-? where id=?", (cost, g.uid))
        oid = x("insert into orders(user_id,plat,svc,link,qty,cost,created) values(?,?,?,?,?,?,?)", (g.uid, k, s, link, qty, cost, time.time()))
    auto = ""
    if it["smm_id"] and sv("smm_url") and sv("smm_key"):
        r = smm("add", service=it["smm_id"], link=link, quantity=qty)
        if r and r.get("order"):
            x("update orders set status='processing',ext=? where id=?", (str(r["order"]), oid))
            auto = f"\n🤖 SMM panelga yuborildi (#{r['order']})"
    body = (f"🛒 <b>Yangi buyurtma #{oid}</b>\n👤 {_html.escape(u['name'])} (<code>{u['id']}</code>)\n"
            f"📦 {it['ptitle']} → {it['title']}\n🔗 {_html.escape(link)}\n🔢 {qty} ta · 💰 {cost} {coin()}{auto}")
    notify_admins(body, None if auto else {"inline_keyboard": [[{"text": "✅ Bajarildi", "callback_data": f"ord:done:{oid}"},
                                                                {"text": "❌ Bekor", "callback_data": f"ord:cancel:{oid}"}]]})
    return jsonify(state(get(g.uid)))


# ───────────────────────── ADMIN API ─────────────────────────
def cast(t, v):
    if t == "i":
        return int(float(v or 0))
    if t == "f":
        return float(v or 0)
    if t == "u":
        return str(v or "").strip().upper()
    return str(v if v is not None else "").strip()


KINDS = {
    "tasks": dict(f=dict(title="s", kind="s", url="s", reward="i", chat_id="s", daily_limit="i", sort="i", active="i"), order="sort,id"),
    "auctions": dict(f=dict(title="s", image="s", price="i", ends="f"), order="done,ends",
                     extra=",(select coalesce(sum(cnt),0) from tickets where auction_id=t.id) total,(select count(*) from tickets where auction_id=t.id) players"),
    "promos": dict(pk="code", f=dict(code="u", reward="i", max_uses="i"), order="code"),
    "paid": dict(f=dict(icon="s", title="s", descr="s", sort="i", active="i"), order="sort,id"),
    "plats": dict(pk="slug", f=dict(slug="s", title="s", icon="s", sort="i", active="i"), order="sort,slug"),
    "svcs": dict(f=dict(plat="s", slug="s", title="s", icon="s", price="i", minq="i", ph="s", smm_id="s", sort="i", active="i"), order="plat,sort,id"),
    "admins": dict(pk="id", manual=True, f=dict(id="i", note="s"), order="id"),
}


@app.get("/api/adm/list/<kind>")
@adm
def a_list(kind):
    K = KINDS.get(kind) or abort(404)
    rows = q(f"select t.*{K.get('extra', '')} from {kind} t order by {K['order']}")
    return jsonify([dict(r) for r in rows])


@app.post("/api/adm/save/<kind>")
@adm
def a_save(kind):
    K = KINDS.get(kind) or abort(404)
    d = request.json or {}
    vals = {c: cast(t, d.get(c)) for c, t in K["f"].items()}
    for c in ("title", "code", "slug"):
        if c in vals and not vals[c]:
            raise Err("Nomi/kodi bo‘sh bo‘lmasin")
    if kind == "tasks" and vals["kind"] not in ("link", "channel", "youtube", "ad"):
        raise Err("Vazifa turi noto‘g‘ri")
    pk = K.get("pk", "id")
    cols = list(vals)
    with LK:
        if pk != "id" or K.get("manual"):
            upd = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk)
            x(f"insert into {kind}({','.join(cols)}) values({','.join('?' * len(cols))}) on conflict({pk}) do update set {upd}", tuple(vals.values()))
        elif d.get("id"):
            x(f"update {kind} set {','.join(c + '=?' for c in cols)} where id=?", (*vals.values(), int(d["id"])))
        else:
            x(f"insert into {kind}({','.join(cols)}) values({','.join('?' * len(cols))})", tuple(vals.values()))
    if kind == "admins":
        reload_adm()
    return jsonify(ok=1)


@app.post("/api/adm/del/<kind>/<path:pkv>")
@adm
def a_del(kind, pkv):
    K = KINDS.get(kind) or abort(404)
    pk = K.get("pk", "id")
    with LK:
        if kind == "tasks":
            x("delete from task_done where task_id=?", (int(pkv),))
        if kind == "auctions":
            x("delete from tickets where auction_id=?", (int(pkv),))
            x("delete from likes where auction_id=?", (int(pkv),))
        if kind == "plats":
            x("delete from svcs where plat=?", (pkv,))
        if kind == "promos":
            x("delete from promo_used where code=?", (pkv,))
        if kind == "admins" and int(pkv) in ADMINS:
            raise Err("Asosiy adminni (ENV) o‘chirib bo‘lmaydi")
        x(f"delete from {kind} where {pk}=?", (int(pkv) if pk == "id" else pkv,))
    if kind == "admins":
        reload_adm()
    return jsonify(ok=1)


@app.get("/api/adm/settings")
@adm
def a_settings():
    return jsonify([dict(k=k, l=l, t=t, g=gr, v=sv(k)) for k, l, d, t, gr in SETDEF])


@app.post("/api/adm/settings")
@adm
def a_settings_save():
    d = request.json or {}
    for k, l, df, t, gr in SETDEF:
        if k in d:
            v = str(d[k]).strip()
            try:
                if t == "int":
                    v = str(int(float(v)))
                    if k in ("max_lvl", "base_energy", "energy_step") and int(v) < 1:
                        raise ValueError
                    if k in ("send_fee",) and not 0 <= int(v) <= 100:
                        raise ValueError
                    if k in ("start_bonus", "ref_reward", "ref_new", "daily_base", "daily_step",
                             "up_tap", "up_energy", "up_regen", "min_send", "lvl_bronze", "lvl_silver",
                             "lvl_gold", "lvl_platinum", "lvl_diamond", "lvl_legend",
                             "wait_link", "wait_youtube", "wait_ad", "wait_channel") and int(v) < 0:
                        raise ValueError
                elif t == "float":
                    v = str(float(v))
                    if k == "up_growth" and float(v) < 1:
                        raise ValueError
            except (ValueError, OverflowError):
                raise Err(f"«{l}» qiymatini tekshiring")
            x("insert or replace into settings values(?,?)", (k, v))
    reload_st()
    return jsonify(ok=1)


@app.get("/api/adm/dash")
@adm
def a_dash():
    now = time.time()
    t0 = now - now % 86400
    ser = []
    for i in range(6, -1, -1):
        a = t0 - i * 86400
        ser.append([datetime.fromtimestamp(a, timezone.utc).strftime("%d.%m"), one("select count(*) from users where created>=? and created<?", (a, a + 86400))])
    return jsonify(
        users=one("select count(*) from users"), today=one("select count(*) from users where created>=?", (t0,)),
        active=one("select count(*) from users where last_seen>?", (now - 86400,)), bal=one("select coalesce(sum(balance),0) from users"),
        earned=one("select coalesce(sum(earned),0) from users"), banned=one("select count(*) from users where banned=1"),
        op=one("select count(*) from orders where status in ('pending','processing')"), od=one("select count(*) from orders where status='done'"),
        tasks=one("select count(*) from tasks where active=1"), auctions=one("select count(*) from auctions where done=0"),
        promos=one("select count(*) from promos"), ser=ser,
        top=[dict(r) for r in q("select name,username,refs from users where refs>0 order by refs desc limit 5")])


@app.post("/api/adm/auction/<int:aid>/finish")
@adm
def a_afinish(aid):
    r = finish_auction(aid)
    if r is None:
        raise Err("Allaqachon yakunlangan")
    return jsonify(winner=r)


@app.get("/api/adm/auction/<int:aid>/players")
@adm
def a_aplayers(aid):
    rows = q("select u.id,u.name,u.username,t.cnt from tickets t join users u on u.id=t.user_id where t.auction_id=? order by t.cnt desc limit 100", (aid,))
    return jsonify([dict(r) for r in rows])


@app.get("/api/adm/orders")
@adm
def a_orders():
    st = request.args.get("st", "pending")
    w = {"pending": "where o.status in ('pending','processing')", "done": "where o.status='done'", "cancel": "where o.status='cancel'"}.get(st, "")
    rows = q(f"select o.*,u.name uname,u.username uun,(select title from svcs where plat=o.plat and slug=o.svc) title from orders o left join users u on u.id=o.user_id {w} order by o.id desc limit 40")
    return jsonify([dict(r) for r in rows])


@app.post("/api/adm/order/<int:oid>")
@adm
def a_order(oid):
    act = (request.json or {}).get("act")
    if act not in ("done", "cancel") or not order_act(oid, act):
        raise Err("Buyurtma allaqachon ishlangan")
    return jsonify(ok=1)


@app.get("/api/adm/users")
@adm
def a_users():
    qq = request.args.get("q", "").strip().lstrip("@")
    pg = int(request.args.get("p", 0))
    od = {"new": "created desc", "bal": "balance desc", "refs": "refs desc", "act": "last_seen desc"}.get(request.args.get("s", "new"), "created desc")
    w, a = "", ()
    if qq.isdigit():
        w, a = "where id=?", (int(qq),)
    elif qq:
        w, a = "where lower(username) like ? or lower(name) like ?", (f"%{qq.lower()}%",) * 2
    rows = q(f"select id,name,username,balance,earned,refs,banned,created,last_seen,tap_lvl,energy_lvl,regen_lvl,ref_by from users {w} order by {od} limit 30 offset ?", a + (pg * 30,))
    return jsonify(rows=[dict(r) for r in rows], total=one(f"select count(*) from users {w}", a))


@app.post("/api/adm/user/<int:uid>")
@adm
def a_user(uid):
    d = request.json or {}
    op = d.get("op")
    if not get(uid):
        raise Err("Foydalanuvchi topilmadi")
    amt = int(float(d.get("amount") or 0))
    if op == "add":
        x("update users set balance=max(0,balance+?),earned=earned+? where id=?", (amt, max(amt, 0), uid))
        send(uid, f"🎁 Admin balansingizga <b>{amt:+d}</b> {coin()} {'qo‘shdi' if amt >= 0 else 'ayirdi'}")
    elif op == "set":
        x("update users set balance=? where id=?", (max(0, amt), uid))
    elif op in ("ban", "unban"):
        x("update users set banned=? where id=?", (1 if op == "ban" else 0, uid))
    elif op == "msg":
        if not send(uid, str(d.get("text", ""))):
            raise Err("Yuborib bo‘lmadi (foydalanuvchi botni bloklagan)")
    elif op == "profile":
        name = str(d.get("name", "")).strip()[:60]
        username = str(d.get("username", "")).strip().lstrip("@").lower()[:64]
        if not name:
            raise Err("Ism bo‘sh bo‘lmasin")
        if username and not re.fullmatch(r"[a-z0-9_]{5,64}", username):
            raise Err("Username formati noto‘g‘ri")
        x("update users set name=?,username=? where id=?", (name, username, uid))
    elif op == "lvls":
        mx = si("max_lvl")
        x("update users set tap_lvl=?,energy_lvl=?,regen_lvl=? where id=?",
          tuple(max(0, min(mx, int(float(d.get(k) or 0)))) for k in ("tap", "energy", "regen")) + (uid,))
    else:
        raise Err("Noma’lum amal")
    return jsonify(dict(get(uid)))


BC = dict(running=False, sent=0, fail=0, total=0)


def do_bc(admin, text, btn_t, btn_u, image, target):
    where = " and last_seen>?" if target == "active" else ""
    ids = [r["id"] for r in q("select id from users where banned=0" + where, (time.time() - 7 * 86400,) if where else ())]
    BC.update(running=True, sent=0, fail=0, total=len(ids))
    mk = None
    if btn_t:
        b = {"text": btn_t}
        if btn_u.startswith("http"):
            b["url"] = btn_u
        else:
            b["web_app"] = {"url": BASE_URL}
        mk = {"inline_keyboard": [[b]]}
    for i in ids:
        if image:
            p = dict(chat_id=i, photo=image, caption=text[:1000], parse_mode="HTML")
            if mk:
                p["reply_markup"] = mk
            r = tg("sendPhoto", **p)
        else:
            r = send(i, text, mk)
        BC["sent" if r else "fail"] += 1
        time.sleep(0.05)
    BC["running"] = False
    send(admin, f"📣 Xabar yuborildi: ✅ {BC['sent']} · ❌ {BC['fail']}")


@app.post("/api/adm/bc")
@adm
def a_bc():
    d = request.json or {}
    if BC["running"]:
        raise Err("Oldingi xabar hali yuborilmoqda")
    text = str(d.get("text", "")).strip()
    if not text:
        raise Err("Matn kiriting")
    target = d.get("target", "all")
    if target not in ("all", "active"):
        raise Err("Auditoriya tanlovi noto‘g‘ri")
    threading.Thread(target=do_bc, args=(g.uid, text, str(d.get("btn_t", "")).strip(), str(d.get("btn_u", "")).strip(),
                                         str(d.get("image", "")).strip(), target), daemon=True).start()
    return jsonify(ok=1)


@app.get("/api/adm/bc")
@adm
def a_bc_status():
    return jsonify(BC)


@app.post("/api/adm/backup")
@adm
def a_backup():
    tmp = "/tmp/backup_%d.db" % int(time.time())
    b = sqlite3.connect(tmp)
    with LK:
        DB.backup(b)
    b.close()
    with open(tmp, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", data={"chat_id": g.uid, "caption": "💾 Baza zaxirasi. Tiklash: shu faylni botga /restore izohi bilan yuboring."},
                          files={"document": ("backup.db", f)}, timeout=120).json()
    os.remove(tmp)
    if not r.get("ok"):
        raise Err("Yuborib bo‘lmadi")
    return jsonify(ok=1)


# ───────────────────────── BOT ─────────────────────────
def webapp_kb(text="🚀 O‘yinni ochish", path=""):
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": BASE_URL + path}}]]}


def on_msg(m):
    uid = m["from"]["id"]
    text = (m.get("text") or "").strip()
    name = ((m["from"].get("first_name") or "") + " " + (m["from"].get("last_name") or "")).strip() or "User"
    if text.startswith("/start"):
        parts = text.split()
        ref = int(parts[1][4:]) if len(parts) > 1 and parts[1].startswith("ref_") and parts[1][4:].isdigit() else None
        reg(uid, name[:60], (m["from"].get("username") or "").lower(), ref)
        send(uid, sv("welcome").replace("{name}", _html.escape(name)).replace("{coin}", coin()), webapp_kb())
        return
    if text.startswith("/help"):
        send(uid, "✨ <b>Yordam markazi</b>\n\n🚀 <b>Mini App</b> — o‘yin, vazifalar, boost va auksionlar.\n💰 <b>Balans</b> — /balance orqali tangalaringizni ko‘ring.\n🆔 <b>ID</b> — /id orqali Telegram ID raqamingizni biling.\n🎁 <b>Bonus</b> — ilovadagi kunlik bonus va promokodlardan foydalaning.\n\nSavol yoki muammo bo‘lsa: @" + _html.escape(sv("admin_username").lstrip("@")), webapp_kb())
        return
    if text.startswith("/balance"):
        u = get(uid)
        if not u:
            send(uid, "Avval /start buyrug‘ini yuboring.")
        else:
            send(uid, f"💎 <b>Balansingiz:</b> {int(u['balance']):,} { _html.escape(coin()) }\n🏅 <b>Jami topilgan:</b> {int(u['earned'] or 0):,}", webapp_kb())
        return
    if text.startswith("/id"):
        send(uid, f"🆔 <b>Telegram ID:</b> <code>{uid}</code>")
        return
    if not is_admin(uid):
        return
    if text.startswith("/admin"):
        send(uid, "🛠 <b>Admin panel</b>\nBot to‘liq shu yerdan boshqariladi 👇", webapp_kb("⚙️ Admin panelni ochish", "/?admin=1"))
    elif m.get("photo"):
        fid = m["photo"][-1]["file_id"]
        send(uid, f"🖼 Rasm havolasi (auksion/e’lon uchun):\n<code>{BASE_URL}/img/{fid}</code>")
    elif m.get("document") and (m.get("caption") or "").startswith("/restore"):
        f = tg("getFile", file_id=m["document"]["file_id"])
        if not f:
            return send(uid, "❌ Faylni olib bo‘lmadi")
        try:
            r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=60)
            open("/tmp/restore.db", "wb").write(r.content)
            src = sqlite3.connect("/tmp/restore.db")
            src.execute("select count(*) from users")
            with LK:
                src.backup(DB)
            src.close()
            init_db()
            send(uid, "✅ Baza tiklandi")
        except Exception as e:
            send(uid, f"❌ Tiklab bo‘lmadi: {_html.escape(str(e))}")


def on_cb(c):
    uid, data = c["from"]["id"], c.get("data", "")
    if not is_admin(uid) or not data.startswith("ord:"):
        return tg("answerCallbackQuery", callback_query_id=c["id"])
    _, act, oid = data.split(":")
    done = order_act(int(oid), act)
    tg("answerCallbackQuery", callback_query_id=c["id"], text="Bajarildi" if done else "Allaqachon ishlangan")
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


def bg_loop():
    n = 0
    while True:
        try:
            for a in q("select id from auctions where done=0 and ends<=?", (time.time(),)):
                finish_auction(a["id"])
            if n % 10 == 0 and sv("smm_url") and sv("smm_key"):
                for o in q("select * from orders where status='processing' and ext!=''"):
                    st = str((smm("status", order=o["ext"]) or {}).get("status", "")).lower()
                    if st == "completed":
                        order_act(o["id"], "done")
                    elif st in ("canceled", "cancelled", "refunded"):
                        order_act(o["id"], "cancel")
        except Exception:
            log.exception("bg")
        n += 1
        time.sleep(30)


def keepalive():
    while True:
        time.sleep(600)
        try:
            requests.get(BASE_URL + "/health", timeout=20)
        except Exception:
            pass


# ───────────────────────── MINI APP ─────────────────────────
HTML = r"""<!DOCTYPE html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>AKCOIN · Digital Universe</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Unbounded:wght@500;700;800&display=swap" rel="stylesheet">
<style>
:root{--ink:#06182a;--turq:#22d1c0;--turq2:#0aa49a;--gold:#ffcf4d;--gold2:#f59e0b;--cream:#fff6dc;--coral:#ff6384;--vio:#8f7bff;--blue:#4aa8ff;--tx:#f4f8ff;--mut:rgba(208,226,242,.6);--bd:rgba(255,255,255,.1);--card:linear-gradient(160deg,rgba(255,255,255,.1),rgba(255,255,255,.035))}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none;-webkit-user-select:none}
html,body{margin:0;height:100%;overflow:hidden;background:var(--ink);color:var(--tx);font-family:'Manrope',system-ui,sans-serif;font-weight:600}
.dsp{font-family:'Unbounded','Manrope',sans-serif}
#bg{position:fixed;inset:0;overflow:hidden;background:radial-gradient(120% 55% at 0% 0%,rgba(34,209,192,.3),transparent 62%),radial-gradient(90% 50% at 100% 100%,rgba(255,170,40,.22),transparent 62%),linear-gradient(170deg,#082540,#071a2e 55%,#05111d)}
#bg:before{content:'';position:absolute;inset:0;opacity:.075;background-size:84px;background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='84' height='84'><path d='M42 6l9 22 22-9-9 22 22 9-22 9 9 22-22-9-9 22-9-22-22 9 9-22-22-9 22-9-9-22 22 9z' fill='none' stroke='white' stroke-width='1'/><circle cx='42' cy='42' r='6' fill='none' stroke='white'/></svg>") 0 0/84px}
.orb{position:absolute;border-radius:50%;filter:blur(60px);animation:orb 16s ease-in-out infinite}
.o1{width:280px;height:280px;background:rgba(34,209,192,.25);top:-60px;right:-80px}.o2{width:300px;height:300px;background:rgba(255,190,60,.16);bottom:80px;left:-120px;animation-delay:-8s}
@keyframes orb{50%{transform:translate(30px,40px) scale(1.1)}}
#view{position:fixed;inset:0;overflow-y:auto;padding:calc(env(safe-area-inset-top) + 12px) 14px 118px;-webkit-overflow-scrolling:touch}
#view::-webkit-scrollbar{display:none}.fade{animation:fd .28s ease-out}@keyframes fd{from{opacity:0;transform:translateY(8px)}}
h3{margin:20px 4px 10px;font-size:15px;font-weight:800;display:flex;align-items:center;gap:8px;letter-spacing:.2px}
h2{margin:0}small{font-size:12px;color:var(--mut);font-weight:600}.mut{color:var(--mut)}.c{text-align:center}code{user-select:text;font-size:12px}
.card{background:var(--card);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--bd);border-radius:22px;padding:14px;margin-bottom:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 14px 30px -14px rgba(0,0,0,.6)}
.card.dim{opacity:.5}.row{display:flex;align-items:center;gap:12px}.sb{justify-content:space-between}.f1{flex:1}.gr{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.gr b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.click:active{transform:scale(.975)}.click{transition:transform .12s}
.ic{width:46px;height:46px;border-radius:15px;display:grid;place-items:center;font-size:22px;flex:none;background:rgba(0,0,0,.35);box-shadow:inset 0 1px 0 rgba(255,255,255,.15)}
.ic.g{background:linear-gradient(145deg,#ffd75e,#f08c00)}.ic.t{background:linear-gradient(145deg,#2fe0cf,#0a8f94)}.ic.c{background:linear-gradient(145deg,#ff7d96,#d6366a)}.ic.v{background:linear-gradient(145deg,#a592ff,#5a46d8)}.ic.b{background:linear-gradient(145deg,#6cbcff,#2268d6)}
.btn{border:1px solid var(--bd);border-radius:14px;padding:11px 15px;font:800 13px 'Manrope',sans-serif;color:#fff;background:rgba(255,255,255,.12);cursor:pointer;white-space:nowrap}
.btn:active{transform:scale(.96)}.btn.sm{padding:8px 12px;font-size:12px}.btn.wide{width:100%;padding:16px;font-size:15px;margin-top:8px;display:block}
.btn.gold{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#3a2500;border:0;box-shadow:0 6px 18px rgba(245,158,11,.4)}
.btn.tq{background:linear-gradient(135deg,#34e6d4,var(--turq2));color:#00211f;border:0;box-shadow:0 6px 18px rgba(34,209,192,.3)}
.btn.red{background:rgba(255,99,132,.18);border-color:rgba(255,99,132,.4);color:#ff9db0}.btn:disabled{opacity:.45;box-shadow:none}
.inp{width:100%;padding:14px 15px;border-radius:15px;border:1px solid var(--bd);background:rgba(0,0,0,.32);color:#fff;font:700 15px 'Manrope',sans-serif;outline:0;user-select:text;-webkit-user-select:text}
.inp::placeholder{color:rgba(255,255,255,.35)}.inp:focus{border-color:var(--turq);box-shadow:0 0 0 3px rgba(34,209,192,.15)}select.inp option{background:#0b2a44}textarea.inp{resize:vertical}
.fg{margin-bottom:12px}.fg label{display:block;font-size:12px;color:var(--mut);margin:0 0 6px 4px;font-weight:700}
.mc{display:inline-grid;place-items:center;width:1.2em;height:1.2em;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff4ac,#f5a300);color:#5a3300;font:800 .62em/1 'Unbounded',sans-serif;font-style:normal;vertical-align:-.2em;box-shadow:inset 0 0 0 1.5px #ffd24a}
.chip{display:inline-block;padding:4px 10px;border-radius:20px;background:rgba(255,255,255,.1);font-size:11px;font-weight:800}.chip.done{background:rgba(34,209,192,.2);color:#6ff0e2}.chip.cancel{background:rgba(255,99,132,.2);color:#ff9db0}.chip.pending,.chip.processing{background:rgba(255,207,77,.2);color:var(--gold)}
.lv{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;background:rgba(255,207,77,.15);color:var(--gold);font:800 11px 'Manrope';width:fit-content}
.tb{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}
.pill{display:flex;align-items:center;gap:8px;padding:9px 14px;border-radius:30px;background:var(--card);border:1px solid var(--bd);font-size:14px;font-weight:700}
.av{width:42px;height:42px;border-radius:50%;object-fit:cover;background:#12406b;display:grid;place-items:center;font-weight:800;border:2px solid var(--gold);flex:none}
.ok{color:#6ff0e2;font-weight:800;font-size:13px}.bad{color:#ff9db0}.badge{background:var(--gold);color:#3a2500;border-radius:20px;padding:2px 9px;font-size:12px}
.hd{display:flex;align-items:center;gap:12px;margin-bottom:14px;font-size:18px;font-weight:800}
.bk{width:42px;height:42px;border-radius:50%;border:1px solid var(--bd);background:rgba(255,255,255,.12);color:#fff;font-size:20px}
/* tap */
.tapv{min-height:calc(100vh - 140px);display:flex;flex-direction:column;align-items:center}
.ann{width:100%;margin-bottom:8px;padding:9px 14px;border-radius:16px;background:rgba(255,207,77,.12);border:1px solid rgba(255,207,77,.25);font-size:12.5px;color:var(--cream)}
.gift{position:relative;width:46px;height:46px;border-radius:15px;border:1px solid var(--bd);background:var(--card);font-size:22px}.gift.on{animation:wob 2s infinite;border-color:var(--gold);box-shadow:0 0 18px rgba(255,207,77,.5)}
.gift.on:after{content:'';position:absolute;top:6px;right:6px;width:9px;height:9px;border-radius:50%;background:var(--coral)}@keyframes wob{0%,80%,100%{transform:none}86%{transform:rotate(-10deg)}92%{transform:rotate(10deg)}}
.bal{display:flex;align-items:center;justify-content:center;gap:10px;font-size:40px;font-weight:800;margin-top:2px;text-shadow:0 6px 22px rgba(0,0,0,.45)}.bal .mc{font-size:30px}
.lvl{width:78%;margin:10px auto 0;display:flex;align-items:center;gap:8px;font-size:10.5px;color:var(--mut);font-weight:800}.lb{flex:1;height:6px;border-radius:6px;background:rgba(255,255,255,.12);overflow:hidden}.lb i{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,var(--turq),var(--gold));transition:width .3s}
#tz{position:relative;flex:1;display:grid;place-items:center;width:100%;touch-action:none;perspective:700px;min-height:260px}
.halo{position:absolute;width:min(94vw,390px);aspect-ratio:1;border-radius:50%;background:radial-gradient(circle,rgba(255,200,70,.4),rgba(255,200,70,0) 62%);animation:pulse 3.2s ease-in-out infinite}@keyframes pulse{50%{transform:scale(1.08);opacity:.75}}
.coinw{position:relative;animation:flo 4.5s ease-in-out infinite}@keyframes flo{50%{transform:translateY(-9px)}}
.coin{width:min(64vw,268px);aspect-ratio:1;border-radius:50%;overflow:hidden;position:relative;transition:transform .1s ease-out;filter:drop-shadow(0 24px 26px rgba(0,0,0,.55))}.coin svg{width:100%;height:100%;display:block}
.coin:after{content:'';position:absolute;top:-30%;left:-70%;width:40%;height:160%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.6),transparent);transform:rotate(20deg);animation:sh 5s ease-in-out infinite}@keyframes sh{0%,62%{left:-70%}100%{left:140%}}
.floor{width:46%;height:16px;border-radius:50%;background:radial-gradient(rgba(0,0,0,.5),transparent 70%);margin:8px auto 0}
.en{width:100%}.eh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:13px;font-weight:800}.eh small{font-size:11px}
.bar{height:18px;border-radius:12px;background:rgba(0,0,0,.35);border:1px solid var(--bd);overflow:hidden;padding:2px}.bar i{display:block;height:100%;width:100%;border-radius:10px;background:linear-gradient(90deg,#17c2b3,#7df0c5 55%,var(--gold));transition:width .25s}
.fl{position:fixed;font:800 28px 'Unbounded',sans-serif;color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.6);pointer-events:none;z-index:9;animation:up .85s ease-out forwards}@keyframes up{from{transform:translate(-50%,-50%)}to{transform:translate(-50%,-230%);opacity:0}}
.pt{position:fixed;width:7px;height:7px;margin:-3px;border-radius:50%;background:var(--gold);box-shadow:0 0 8px var(--gold);pointer-events:none;z-index:9;animation:pt .55s ease-out forwards}@keyframes pt{to{transform:translate(var(--dx),var(--dy)) scale(.2);opacity:0}}
/* nav */
#nav{position:fixed;left:14px;right:14px;bottom:calc(env(safe-area-inset-bottom) + 12px);height:64px;border-radius:32px;background:rgba(6,24,42,.85);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid var(--bd);display:flex;align-items:center;z-index:5;box-shadow:0 18px 40px -8px rgba(0,0,0,.75)}
#nav button{flex:1;background:none;border:0;color:var(--mut);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font:700 10px 'Manrope',sans-serif;height:100%;position:relative}
#nav svg{width:23px;height:23px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#nav button.on{color:var(--gold)}#nav button.on:after{content:'';position:absolute;bottom:6px;width:14px;height:3px;border-radius:3px;background:var(--gold)}
#nav .mid{flex:none;width:84px;justify-content:flex-end;padding-bottom:9px}#nav .mid:after{display:none}
#nav .mid i{position:absolute;top:-24px;width:64px;height:64px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 25%,#fff0a0,#f5a300);box-shadow:0 10px 26px rgba(245,163,0,.55),0 0 0 6px rgba(6,24,42,.95);color:#3a2500}
#nav .mid.on i{box-shadow:0 10px 30px rgba(245,163,0,.8),0 0 0 6px rgba(6,24,42,.95)}#nav .mid svg{width:30px;height:30px;stroke-width:2.2}
/* sections */
.hero{display:flex;align-items:center;gap:10px;padding:18px;border-radius:24px;margin-bottom:6px;background:linear-gradient(135deg,rgba(34,209,192,.35),rgba(18,64,107,.5));border:1px solid rgba(34,209,192,.35);position:relative;overflow:hidden}
.hero .he{font-size:60px;filter:drop-shadow(0 8px 14px rgba(0,0,0,.4))}.hero b{font-size:16px;line-height:1.25}.hero .btn{margin-top:10px}
.pips{display:flex;gap:4px;margin-top:12px}.pips i{flex:1;height:5px;border-radius:5px;background:rgba(255,255,255,.12)}.pips i.on{background:linear-gradient(90deg,var(--turq),var(--gold))}
.plat{display:flex;align-items:center;gap:14px}.plat .ic{width:52px;height:52px;font-size:26px}
.au{padding:8px}.img{height:176px;border-radius:17px;position:relative;overflow:hidden;background:linear-gradient(135deg,#12406b,#5a3fd1) center/cover;display:grid;place-items:center;font-size:64px}.img.big{height:200px;margin-bottom:6px}
.img .ov{position:absolute;inset:0;background:linear-gradient(transparent 40%,rgba(0,0,0,.78))}.img .tt{position:absolute;left:12px;right:12px;bottom:10px;font:800 17px 'Unbounded',sans-serif;line-height:1.2;text-align:left;text-shadow:0 2px 8px rgba(0,0,0,.6)}
.hp{position:absolute;top:10px;left:10px;border:0;padding:7px 12px;border-radius:20px;background:rgba(0,0,0,.45);color:#fff;font:800 12px 'Manrope';backdrop-filter:blur(8px)}.hp.on{color:#ff6b8b}
.cdc{position:absolute;top:10px;right:10px;padding:7px 12px;border-radius:20px;background:rgba(0,0,0,.5);backdrop-filter:blur(8px);font:800 11px 'Manrope';color:#8ff5e8}.cdc.end{color:var(--gold)}
.ab{padding:12px 8px 4px}.qrow{display:flex;gap:8px;margin:12px 0 8px}.qi{text-align:center;font-size:20px;padding:11px}.chipsr{display:flex;gap:8px;flex-wrap:wrap}.chipsr .btn{flex:1}
.row2{display:flex;justify-content:space-between;padding:8px 2px;font-weight:700}.row2 span{color:var(--mut)}.row2+.row2{border-top:1px solid var(--bd)}
.stats{display:flex;gap:8px;margin:10px 0}.stats>div{flex:1;background:rgba(0,0,0,.28);border-radius:15px;padding:11px 6px;display:flex;flex-direction:column;gap:4px;text-align:center}.stats b{font:800 15px 'Unbounded'}
.ph{display:flex;flex-direction:column;align-items:center;gap:6px;margin:10px 0 16px}.ph .av{width:104px;height:104px;font-size:42px;border-width:3px;box-shadow:0 0 0 6px rgba(255,207,77,.18),0 14px 34px rgba(0,0,0,.4)}.ph h2{font:800 22px 'Unbounded';margin-top:8px}
.balc{text-align:center;padding:18px}.balc .big{font:800 36px 'Unbounded';display:flex;justify-content:center;align-items:center;gap:10px;margin:4px 0 6px}.balc .big .mc{font-size:28px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.grid .card{margin:0;display:flex;flex-direction:column;gap:14px;padding:16px;font-weight:800;min-height:116px;justify-content:space-between}
.rk{width:32px;text-align:center}.meh{border-color:var(--gold);background:linear-gradient(160deg,rgba(255,207,77,.2),rgba(255,207,77,.05))}
.seg{display:flex;gap:6px;background:rgba(0,0,0,.3);padding:4px;border-radius:16px;margin-bottom:12px}.seg button{flex:1;border:0;background:none;color:var(--mut);font:800 12px 'Manrope';padding:10px;border-radius:12px}.seg button.on{background:rgba(255,255,255,.14);color:#fff}
.dayg{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.day{border-radius:16px;padding:10px 4px;text-align:center;background:rgba(0,0,0,.28);border:1px solid var(--bd);display:flex;flex-direction:column;gap:4px;font-size:11px}.day b{font:800 13px 'Unbounded'}
.day.dn{background:rgba(34,209,192,.2);border-color:rgba(34,209,192,.5)}.day.nx{border-color:var(--gold);background:rgba(255,207,77,.16);box-shadow:0 0 16px rgba(255,207,77,.3)}.day:last-child{grid-column:span 1}
#sheet{position:fixed;inset:0;background:rgba(2,10,20,.65);backdrop-filter:blur(4px);display:none;align-items:flex-end;z-index:20}#sheet.on{display:flex}
.sh{width:100%;max-height:90vh;overflow-y:auto;background:linear-gradient(180deg,#0d2c48,#081c31);border-radius:28px 28px 0 0;padding:12px 16px calc(env(safe-area-inset-bottom) + 20px);border-top:1px solid var(--bd);animation:sl .24s ease-out}.sh:before{content:'';display:block;width:42px;height:4px;border-radius:4px;background:rgba(255,255,255,.2);margin:0 auto 14px}
@keyframes sl{from{transform:translateY(70px);opacity:0}}
#toast{position:fixed;left:50%;top:calc(env(safe-area-inset-top) + 14px);transform:translate(-50%,-100px);background:rgba(8,28,49,.97);border:1px solid var(--bd);padding:12px 18px;border-radius:16px;font-weight:800;font-size:14px;z-index:50;transition:transform .3s;max-width:90vw;text-align:center;box-shadow:0 12px 30px rgba(0,0,0,.5)}#toast.on{transform:translate(-50%,0)}
.spn{width:34px;height:34px;border-radius:50%;border:3px solid rgba(255,255,255,.15);border-top-color:var(--gold);animation:rot .8s linear infinite;margin:90px auto}@keyframes rot{to{transform:rotate(360deg)}}
.mt{text-align:center;margin-top:30vh;font:800 20px 'Unbounded';line-height:1.6}
/* admin */
.atabs{display:flex;gap:8px;overflow-x:auto;margin:0 -14px 14px;padding:2px 14px}.atabs::-webkit-scrollbar{display:none}
.at{flex:none;padding:10px 14px;border-radius:15px;border:1px solid var(--bd);background:var(--card);color:var(--mut);font:800 12px 'Manrope';display:flex;gap:6px;align-items:center}.at.on{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#3a2500;border:0}
.sg{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}.sg .card{margin:0;padding:14px}.sg .n{font:800 22px 'Unbounded';margin-top:6px}
.bars{display:flex;align-items:flex-end;gap:8px;height:110px;margin-top:10px}.bars div{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:5px;height:100%;font-size:10px;color:var(--mut)}.bars i{display:block;width:100%;border-radius:8px 8px 3px 3px;background:linear-gradient(var(--turq),var(--turq2));min-height:4px}
.addb{width:100%;padding:15px;margin-bottom:12px;border:1.5px dashed rgba(255,207,77,.5);background:rgba(255,207,77,.07);color:var(--gold);border-radius:18px;font:800 14px 'Manrope'}
/* premium admin workspace */
.admin-head{padding:18px;border-radius:24px;margin:2px 0 14px;background:radial-gradient(circle at 100% 0,rgba(34,209,192,.2),transparent 45%),linear-gradient(135deg,#123b5b,#0a2239);border:1px solid rgba(91,220,214,.2);box-shadow:0 16px 34px rgba(0,0,0,.22)}
.admin-head .eyebrow{font-size:10px;letter-spacing:1.7px;color:#73e5dc;font-weight:900;text-transform:uppercase}
.admin-head h2{font:800 22px 'Unbounded';margin:7px 0}
.admin-head p{font-size:12px;line-height:1.55;color:#b8cfdf;margin:0}
.admin-head .admin-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.admin-head .admin-actions .btn{flex:1;min-width:120px}
.atabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:0 0 15px;padding:0;overflow:visible}
.at{min-width:0;justify-content:center;padding:11px 5px;border-radius:14px;font-size:11px;white-space:nowrap}
.at.on{box-shadow:0 7px 18px rgba(245,163,0,.2)}
.admin-section-title{display:flex;align-items:center;justify-content:space-between;margin:18px 2px 9px}
.admin-section-title b{font:800 13px 'Unbounded'}
.admin-section-title small{font-size:10px}
.admin-tip{padding:12px 14px;border-radius:15px;background:rgba(34,209,192,.08);border:1px solid rgba(34,209,192,.16);font-size:11px;line-height:1.55;color:#c8e8e9;margin-bottom:12px}
.admin-item{transition:transform .15s,border-color .15s}
.admin-item:active{transform:scale(.985);border-color:rgba(255,207,77,.5)}
.admin-empty{padding:26px 12px;text-align:center;border:1px dashed var(--bd);border-radius:18px;color:var(--mut);font-size:12px}
.fg{margin:12px 0}
.fg label{display:block;margin:0 0 7px;color:#b9d0e0;font-size:11px;line-height:1.4;font-weight:800}
.inp{min-height:46px}
@media(min-width:700px){
 #view{max-width:900px;margin:0 auto;left:0;right:0;padding-left:24px;padding-right:24px}
 .atabs{grid-template-columns:repeat(4,minmax(0,1fr))}
 .sg{grid-template-columns:repeat(4,minmax(0,1fr))}
 .admin-head{padding:24px}
}

/* premium admin workspace */
.admin-head{padding:18px;border-radius:24px;margin:2px 0 14px;background:radial-gradient(circle at 100% 0,rgba(34,209,192,.2),transparent 45%),linear-gradient(135deg,#123b5b,#0a2239);border:1px solid rgba(91,220,214,.2);box-shadow:0 16px 34px rgba(0,0,0,.22)}
.admin-head .eyebrow{font-size:10px;letter-spacing:1.7px;color:#73e5dc;font-weight:900;text-transform:uppercase}
.admin-head h2{font:800 22px 'Unbounded';margin:7px 0}
.admin-head p{font-size:12px;line-height:1.55;color:#b8cfdf;margin:0}
.admin-head .admin-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.admin-head .admin-actions .btn{flex:1;min-width:120px}
.atabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:0 0 15px;padding:0;overflow:visible}
.at{min-width:0;justify-content:center;padding:11px 5px;border-radius:14px;font-size:11px;white-space:nowrap}
.at.on{box-shadow:0 7px 18px rgba(245,163,0,.2)}
.admin-section-title{display:flex;align-items:center;justify-content:space-between;margin:18px 2px 9px}
.admin-section-title b{font:800 13px 'Unbounded'}
.admin-section-title small{font-size:10px}
.admin-tip{padding:12px 14px;border-radius:15px;background:rgba(34,209,192,.08);border:1px solid rgba(34,209,192,.16);font-size:11px;line-height:1.55;color:#c8e8e9;margin-bottom:12px}
.admin-item{transition:transform .15s,border-color .15s}
.admin-item:active{transform:scale(.985);border-color:rgba(255,207,77,.5)}
.admin-empty{padding:26px 12px;text-align:center;border:1px dashed var(--bd);border-radius:18px;color:var(--mut);font-size:12px}
.fg{margin:12px 0}
.fg label{display:block;margin:0 0 7px;color:#b9d0e0;font-size:11px;line-height:1.4;font-weight:800}
.inp{min-height:46px}
.sh .fg:first-of-type{margin-top:8px}
@media(min-width:700px){
 #view{max-width:900px;margin:0 auto;left:0;right:0;padding-left:24px;padding-right:24px}
 .atabs{grid-template-columns:repeat(4,minmax(0,1fr))}
 .sg{grid-template-columns:repeat(4,minmax(0,1fr))}
 .admin-head{padding:24px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}

/* ═════════ NOVA UI REFRESH · 2026 ═════════ */
:root{--ink:#070d19;--turq:#54e4d2;--turq2:#16b8aa;--gold:#c9f36a;--gold2:#9bc83d;--cream:#f2ffd8;--coral:#ff718c;--vio:#a895ff;--blue:#6abaff;--tx:#f4f7fb;--mut:#91a2b8;--bd:rgba(183,205,232,.13);--card:linear-gradient(145deg,rgba(22,36,57,.94),rgba(12,23,40,.94))}
html,body{background:#070d19;color:var(--tx);font-family:'Manrope',sans-serif}
#bg{background:radial-gradient(65% 42% at 4% 0%,rgba(30,181,170,.16),transparent 75%),radial-gradient(60% 42% at 100% 100%,rgba(139,168,67,.11),transparent 70%),linear-gradient(145deg,#0a1423,#070d19 62%,#0b1422)}
#bg:before{opacity:.025}.orb{filter:blur(90px);opacity:.6}
#view{padding-top:calc(env(safe-area-inset-top) + 16px);padding-left:16px;padding-right:16px;scrollbar-width:none}
.card{background:linear-gradient(145deg,rgba(20,35,56,.94),rgba(12,23,39,.96));border:1px solid rgba(167,193,225,.12);border-radius:20px;padding:15px;box-shadow:0 12px 28px rgba(0,0,0,.16),inset 0 1px 0 rgba(255,255,255,.035);backdrop-filter:blur(18px)}
.ic{border-radius:14px;background:linear-gradient(145deg,#1d344c,#13243a);border:1px solid rgba(255,255,255,.07)}
.btn{border-radius:13px;background:#1b2b40;border:1px solid rgba(180,204,232,.15);transition:transform .16s,filter .16s,background .16s}
.btn:hover{filter:brightness(1.12)}.btn.gold{background:linear-gradient(135deg,#d8fa82,#a9d64e);color:#17230a;box-shadow:0 8px 22px rgba(169,214,78,.18)}
.btn.tq{background:linear-gradient(135deg,#6cebd9,#21b7a9);color:#06211f;box-shadow:0 8px 22px rgba(33,183,169,.16)}
.btn.red{background:rgba(255,91,120,.1);border-color:rgba(255,91,120,.24);color:#ff9aaa}
.inp{border-radius:13px;background:#0a1524;border:1px solid rgba(174,199,229,.15);color:#f5f8fc}.inp:focus{border-color:#54e4d2;box-shadow:0 0 0 3px rgba(84,228,210,.1)}
h3{font-size:14px;letter-spacing:.1px}.hd{font-size:17px}
/* Admin header and navigation */
.admin-head{position:relative;overflow:hidden;padding:22px 20px;border-radius:25px;margin:0 0 16px;background:radial-gradient(ellipse at 95% 0%,rgba(84,228,210,.17),transparent 45%),linear-gradient(135deg,#172c42 0%,#101d30 58%,#13251f 100%);border:1px solid rgba(84,228,210,.18);box-shadow:0 18px 42px rgba(0,0,0,.25)}
.admin-head:after{content:'✦';position:absolute;right:18px;top:20px;font-size:68px;line-height:1;color:rgba(201,243,106,.09);pointer-events:none}
.admin-head .eyebrow{display:inline-flex;align-items:center;gap:7px;padding:6px 9px;border-radius:8px;background:rgba(84,228,210,.09);border:1px solid rgba(84,228,210,.16);font-size:9px;letter-spacing:1.4px;color:#7ceadd}
.admin-head .eyebrow:before{content:'';width:6px;height:6px;border-radius:50%;background:#75edb4;box-shadow:0 0 10px #75edb4}
.admin-head h2{font:800 clamp(20px,5vw,25px) 'Unbounded';letter-spacing:-.8px;margin:13px 0 8px;max-width:85%}
.admin-head p{max-width:520px;font-size:12px;line-height:1.7;color:#a9bbcd}
.admin-head .admin-actions{position:relative;z-index:1;margin-top:18px;gap:9px}.admin-head .admin-actions .btn{flex:0 1 auto;min-width:130px;padding:11px 14px}
.atabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 18px;padding:0;overflow:visible}
.at{position:relative;display:flex;flex-direction:column;gap:5px;align-items:flex-start;justify-content:center;min-height:64px;padding:10px 11px;border-radius:15px;border:1px solid rgba(165,190,220,.12);background:linear-gradient(145deg,rgba(22,38,59,.95),rgba(13,25,42,.95));color:#9bacc0;font:800 10px 'Manrope';white-space:normal;text-align:left;line-height:1.2;transition:all .16s}
.at:first-letter{font-size:16px}.at.on{color:#dfff9b;background:linear-gradient(145deg,rgba(89,124,45,.26),rgba(28,54,43,.55));border:1px solid rgba(201,243,106,.43);box-shadow:0 7px 22px rgba(0,0,0,.18),inset 0 0 0 1px rgba(201,243,106,.06)}
.at.on:after{content:'';position:absolute;left:11px;right:11px;bottom:5px;height:2px;border-radius:2px;background:#c9f36a}
.admin-section-title{margin:21px 2px 10px}.admin-section-title b{font:800 12px 'Unbounded';letter-spacing:.1px;color:#e8f1fb}.admin-section-title small{font-size:10px;color:#8295ab}
.admin-tip{padding:13px 14px;border-radius:15px;background:rgba(84,228,210,.065);border:1px solid rgba(84,228,210,.15);color:#b5d9d7;font-size:11px;line-height:1.65}
.admin-item{min-height:70px;margin-bottom:8px;cursor:pointer}.admin-item:hover{border-color:rgba(84,228,210,.3);transform:translateY(-1px)}.admin-item .ic{width:43px;height:43px}.admin-item .gr b{font-size:13px}.admin-item .gr small{font-size:10px;line-height:1.45}.admin-item>span{width:30px;height:30px;display:grid;place-items:center;border-radius:10px;background:rgba(84,228,210,.08);color:#72dfd2}
.admin-empty{padding:30px 16px;background:rgba(255,255,255,.018);border:1px dashed rgba(165,190,220,.2);border-radius:18px;line-height:1.7}
.addb{border:1px dashed rgba(201,243,106,.38);background:rgba(201,243,106,.065);color:#d9f99a;border-radius:15px;padding:14px;font-size:12px;letter-spacing:.1px;transition:.15s}.addb:active{transform:scale(.985)}
.sg{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.sg .card{position:relative;overflow:hidden;min-height:100px;padding:14px;border-radius:17px}.sg .card:after{content:'';position:absolute;width:65px;height:65px;right:-20px;bottom:-28px;border-radius:50%;background:rgba(84,228,210,.06)}.sg .card small{font-size:10px;line-height:1.4}.sg .n{font:800 clamp(17px,4vw,21px) 'Unbounded';margin-top:12px;color:#e8f5fa;overflow-wrap:anywhere}
.bars{height:125px}.bars i{border-radius:7px 7px 2px 2px;background:linear-gradient(180deg,#79ead9,#278f91)}
#ac{min-height:160px}.ac .card{margin-bottom:9px}
#sheet{align-items:flex-end;background:rgba(2,8,16,.76);backdrop-filter:blur(9px)}.sh{max-width:680px;margin:0 auto;max-height:92vh;padding:14px 20px calc(env(safe-area-inset-bottom) + 24px);background:linear-gradient(180deg,#14283e,#0b1728);border:1px solid rgba(166,195,225,.16);border-bottom:0;border-radius:26px 26px 0 0;box-shadow:0 -18px 60px rgba(0,0,0,.32)}
.sh h3{font:800 15px 'Unbounded';margin:5px 0 18px}.fg{margin:14px 0}.fg label{color:#aebfd1;font-size:11px;letter-spacing:.1px}.inp{min-height:48px;font-size:14px}.fg textarea.inp{min-height:110px}
#toast{background:#14283d;border-color:rgba(84,228,210,.25);box-shadow:0 12px 35px rgba(0,0,0,.4)}
@media(min-width:700px){
 #view{max-width:1120px;padding-left:28px;padding-right:28px}
 .admin-head{padding:28px 30px}.admin-head h2{font-size:27px}
 .atabs{grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}
 .at{min-height:72px;padding:12px 13px;font-size:11px}
 .sg{grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
 .admin-item{padding:16px}
}
@media(max-width:380px){.atabs{grid-template-columns:repeat(2,minmax(0,1fr))}.at{min-height:54px;flex-direction:row;align-items:center}.admin-head{padding:18px}.admin-head h2{font-size:19px}}
@media(prefers-reduced-motion:reduce){.admin-item,.btn{transition:none}}

/* ═══════════════════════════════════════════════════════════════
   AKCOIN — COMPLETE EXPERIENCE REDESIGN
   User app · Tap game · Tasks · Boosts · Services · Auctions · Profile · Admin
   ═══════════════════════════════════════════════════════════════ */
:root{
 --ink:#080f1d;--turq:#62e6d4;--turq2:#1bb9a9;--gold:#d7fa83;--gold2:#a7d64d;
 --cream:#f3ffd9;--coral:#ff7892;--vio:#b3a2ff;--blue:#83c7ff;
 --tx:#f5f8ff;--mut:#9baec4;--bd:rgba(177,201,231,.14);
 --card:linear-gradient(145deg,rgba(22,38,61,.97),rgba(11,22,39,.97));
}
html,body{background:#080f1d;color:var(--tx);font-family:'Manrope',sans-serif;letter-spacing:-.12px}
#bg{background:radial-gradient(ellipse at 8% -5%,rgba(51,207,190,.19),transparent 38%),radial-gradient(ellipse at 100% 75%,rgba(145,178,77,.12),transparent 40%),linear-gradient(155deg,#0b192a 0%,#080f1d 54%,#0c1726 100%)}
#bg:before{opacity:.018}.orb{filter:blur(100px);opacity:.55}
#view{padding:calc(env(safe-area-inset-top) + 17px) 16px 120px;scrollbar-width:none}
#view:empty{display:none}
h3{font:800 14px 'Unbounded',sans-serif;letter-spacing:-.3px;margin:22px 2px 12px;color:#edf5ff}
small{color:#9caec2;font-size:11px;line-height:1.55}
.card{position:relative;background:linear-gradient(145deg,rgba(23,40,64,.96),rgba(12,24,42,.98));border:1px solid rgba(172,198,229,.13);border-radius:21px;padding:15px;margin-bottom:10px;box-shadow:0 13px 28px rgba(0,0,0,.17),inset 0 1px 0 rgba(255,255,255,.035);backdrop-filter:blur(18px)}
.card:has(.row){transition:border-color .18s,transform .18s,box-shadow .18s}
.click{cursor:pointer;transition:transform .16s,border-color .16s}.click:active{transform:scale(.982)}
.ic{width:48px;height:48px;border-radius:16px;background:linear-gradient(145deg,#243d59,#15283f);border:1px solid rgba(255,255,255,.07);box-shadow:inset 0 1px rgba(255,255,255,.08);font-size:23px}
.ic.g{background:linear-gradient(145deg,#ffe28a,#d18b25)}.ic.t{background:linear-gradient(145deg,#75efdc,#159d99)}.ic.c{background:linear-gradient(145deg,#ff9aae,#c94e72)}.ic.v{background:linear-gradient(145deg,#c2b5ff,#705bd4)}.ic.b{background:linear-gradient(145deg,#9bd5ff,#397dc5)}
.btn{min-height:42px;border-radius:14px;padding:11px 15px;background:linear-gradient(145deg,#243a55,#192b42);border:1px solid rgba(178,203,232,.17);color:#f5f8ff;font:800 12px 'Manrope',sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.12);transition:transform .15s,filter .15s,box-shadow .15s}
.btn:hover{filter:brightness(1.12)}.btn:active{transform:scale(.97)}
.btn.gold{background:linear-gradient(135deg,#e3ff9b,#a9d84c);border:0;color:#17220a;box-shadow:0 8px 20px rgba(169,216,76,.2)}
.btn.tq{background:linear-gradient(135deg,#7af0df,#22b9a9);border:0;color:#062622;box-shadow:0 8px 20px rgba(34,185,169,.18)}
.btn.red{background:rgba(255,91,122,.12);border:1px solid rgba(255,112,143,.28);color:#ff9bad}
.btn.wide{min-height:49px;border-radius:16px;font-size:13px;letter-spacing:.1px}
.inp{min-height:49px;padding:13px 15px;border-radius:14px;background:#0b1727;border:1px solid rgba(169,196,228,.17);color:#f6f8ff;font:700 14px 'Manrope',sans-serif;box-shadow:inset 0 2px 8px rgba(0,0,0,.12)}
.inp:focus{border-color:rgba(98,230,212,.8);box-shadow:0 0 0 3px rgba(98,230,212,.11)}
.fg label{color:#aebfd1;font-size:11px;letter-spacing:.2px;margin-left:3px}
/* Main tap screen */
.tapv{min-height:calc(100dvh - 145px);justify-content:flex-start;gap:0}
.tapv>.tb{padding:8px 2px 17px;border-bottom:1px solid rgba(180,205,232,.09);margin-bottom:14px!important}
.av{width:44px;height:44px;border:2px solid rgba(215,250,131,.8);box-shadow:0 0 0 4px rgba(215,250,131,.08);background:linear-gradient(145deg,#2a5268,#172c43)}
.lv{padding:5px 10px;border-radius:9px;background:rgba(215,250,131,.11);border:1px solid rgba(215,250,131,.2);color:#dafa9b;font-size:10px;letter-spacing:.3px}
.gift{width:47px;height:47px;border-radius:15px;background:linear-gradient(145deg,#273c55,#17283e);border:1px solid rgba(215,250,131,.24);box-shadow:0 8px 18px rgba(0,0,0,.18)}
.ann{padding:12px 14px;border-radius:15px;background:linear-gradient(100deg,rgba(215,250,131,.12),rgba(215,250,131,.035));border:1px solid rgba(215,250,131,.2);color:#e7f7c8;font-size:12px;line-height:1.55}
.bal{font-size:clamp(36px,10vw,48px);font-weight:800;letter-spacing:-2px;text-shadow:0 8px 28px rgba(0,0,0,.3);margin:12px 0 0}.bal .mc{font-size:.62em}
.lvl{width:84%;margin:12px auto 0;font-size:10px;letter-spacing:.2px}.lb{height:7px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.04)}.lb i{background:linear-gradient(90deg,#4bd8c5,#d7fa83);box-shadow:0 0 12px rgba(98,230,212,.35)}
#tz{min-height:clamp(270px,42vh,390px);margin:4px 0 8px}.halo{width:min(90vw,370px);background:radial-gradient(circle,rgba(215,250,131,.24),rgba(98,230,212,.09) 38%,transparent 68%)}
.coin{width:min(62vw,258px);filter:drop-shadow(0 26px 28px rgba(0,0,0,.52))}.floor{width:43%;height:19px;filter:blur(2px)}
.en{padding:13px 14px 14px;border:1px solid rgba(171,199,230,.12);border-radius:17px;background:linear-gradient(145deg,rgba(24,42,64,.92),rgba(13,26,43,.92))}.eh{font-size:12px}.bar{height:11px;border:0;background:rgba(255,255,255,.09);padding:0}.bar i{background:linear-gradient(90deg,#1bb9a9,#78e7c9,#d7fa83)}
/* Navigation */
#nav{left:12px;right:12px;bottom:calc(env(safe-area-inset-bottom) + 9px);height:68px;border-radius:23px;background:rgba(12,24,40,.94);border:1px solid rgba(170,199,229,.16);box-shadow:0 16px 44px rgba(0,0,0,.46),inset 0 1px rgba(255,255,255,.06);backdrop-filter:blur(28px)}
#nav button{color:#8296ad;font-size:9px;font-weight:800;letter-spacing:.15px;gap:4px}#nav svg{width:21px;height:21px}
#nav button.on{color:#dcff9c}#nav button.on:after{bottom:5px;width:18px;height:3px;background:#c9f36a;box-shadow:0 0 10px rgba(201,243,106,.45)}
#nav .mid{width:76px;padding-bottom:8px}#nav .mid i{top:-20px;width:58px;height:58px;background:linear-gradient(145deg,#edffb5,#a8d94c);box-shadow:0 9px 24px rgba(169,216,76,.27),0 0 0 5px #0c1828;color:#1c2a0e}#nav .mid svg{width:27px;height:27px}#nav .mid.on i{box-shadow:0 9px 28px rgba(169,216,76,.4),0 0 0 5px #0c1828}
/* Task / referral */
.hero{padding:19px;border-radius:23px;background:radial-gradient(circle at 95% 10%,rgba(215,250,131,.18),transparent 36%),linear-gradient(135deg,#183c4a,#172d42 55%,#182a3e);border:1px solid rgba(98,230,212,.22);box-shadow:0 14px 30px rgba(0,0,0,.2)}
.hero b{font:800 15px 'Unbounded';line-height:1.45;max-width:260px}.hero small{color:#c1d7d8}.hero .he{font-size:54px;filter:drop-shadow(0 9px 13px rgba(0,0,0,.28))}.hero .btn{margin-top:13px}
/* boost and service catalog */
.pips{gap:5px;margin-top:13px}.pips i{height:6px;border-radius:9px;background:rgba(255,255,255,.1)}.pips i.on{background:linear-gradient(90deg,#4bd8c5,#d7fa83);box-shadow:0 0 9px rgba(98,230,212,.2)}
.plat{min-height:76px;padding:14px 16px}.plat .ic{width:50px;height:50px}.plat .f1{font-size:13px}.plat>.mut{width:29px;height:29px;display:grid;place-items:center;border-radius:10px;background:rgba(255,255,255,.055);font-size:22px}
.qrow .btn{min-width:47px}.qi{font-size:18px;font-weight:800}.chipsr{gap:7px}.chipsr .btn{min-height:36px}
.row2{padding:10px 2px;font-size:12px}.row2 b{font-size:13px}
/* Auctions */
.au{padding:8px;border-radius:22px;overflow:hidden}.img{height:190px;border-radius:16px;background-color:#203954}.img.big{height:215px}.img .ov{background:linear-gradient(180deg,rgba(5,12,22,.02) 25%,rgba(5,12,22,.82) 100%)}.img .tt{font-size:16px;line-height:1.35;letter-spacing:-.4px}.hp,.cdc{border:1px solid rgba(255,255,255,.13);background:rgba(8,17,29,.68);padding:8px 11px}.ab{padding:13px 9px 6px}.ab .dsp{font-size:17px;color:#e3ff9b}
/* Profile */
.ph{padding:17px 12px 20px;margin:3px 0 12px;border-radius:23px;background:radial-gradient(circle at 50% 0,rgba(98,230,212,.15),transparent 60%),linear-gradient(145deg,rgba(22,40,61,.65),rgba(12,23,39,.2));border:1px solid rgba(173,202,231,.1)}
.ph .av{width:92px;height:92px;border-color:#d7fa83;box-shadow:0 0 0 7px rgba(215,250,131,.08),0 15px 30px rgba(0,0,0,.3)}.ph h2{font-size:20px;letter-spacing:-.6px}.ph .lv{margin-top:3px}
.balc{padding:19px;border-radius:22px;background:radial-gradient(circle at 50% 0,rgba(215,250,131,.1),transparent 60%),linear-gradient(145deg,#1c344b,#101f33)}.balc .big{font-size:clamp(30px,8vw,39px);letter-spacing:-1.4px;color:#e6ffad}.balc>small:first-child{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#a9bdce}
.grid{gap:9px}.grid .card{min-height:112px;border-radius:18px;padding:14px;background:linear-gradient(145deg,#1a3049,#101f34);font-size:12px}.grid .ic{width:42px;height:42px;font-size:20px}
/* Common lists and statuses */
.chip{padding:5px 10px;border:1px solid rgba(255,255,255,.08);font-size:10px;letter-spacing:.1px}.chip.done{color:#80efcf;background:rgba(54,196,155,.12);border-color:rgba(54,196,155,.2)}.chip.pending,.chip.processing{color:#f5d889;background:rgba(226,176,75,.12);border-color:rgba(226,176,75,.2)}.chip.cancel{color:#ff9aaa;background:rgba(255,100,130,.1)}
.stats{gap:8px}.stats>div{background:linear-gradient(145deg,rgba(32,54,79,.9),rgba(16,31,50,.9));border:1px solid rgba(175,200,229,.09);border-radius:14px;padding:12px 5px}.stats b{font-size:13px}.stats small{font-size:9px}
.seg{padding:4px;background:#0b1727;border:1px solid rgba(171,197,225,.1);border-radius:14px}.seg button{font-size:10px;padding:10px 5px;border-radius:10px}.seg button.on{background:linear-gradient(135deg,#2c465d,#1d354b);color:#e0ff9d;box-shadow:inset 0 0 0 1px rgba(215,250,131,.16)}
.dayg{gap:7px}.day{background:linear-gradient(145deg,#1c314a,#112238);border:1px solid rgba(176,201,230,.1);border-radius:14px;padding:11px 3px}.day.dn{background:rgba(45,177,151,.15);border-color:rgba(98,230,212,.3)}.day.nx{background:rgba(215,250,131,.1);border-color:rgba(215,250,131,.45);box-shadow:0 0 18px rgba(215,250,131,.1)}
/* Modal sheets and feedback */
#sheet{background:rgba(3,8,15,.78);backdrop-filter:blur(12px)}.sh{max-width:720px;padding:15px 19px calc(env(safe-area-inset-bottom) + 25px);background:linear-gradient(180deg,#172d45,#0c192b);border:1px solid rgba(178,203,231,.16);border-bottom:0;border-radius:27px 27px 0 0;box-shadow:0 -20px 65px rgba(0,0,0,.45)}.sh:before{width:44px;height:4px;background:rgba(203,222,242,.28)}.sh h3{font-size:15px;margin:4px 0 17px}
#toast{background:rgba(17,37,57,.97);border:1px solid rgba(98,230,212,.25);border-radius:15px;box-shadow:0 16px 40px rgba(0,0,0,.4);font-size:12px}
.spn{border-color:rgba(255,255,255,.12);border-top-color:#d7fa83}.mt{color:#eff8ff}
/* Admin is a complete workspace, not a separate visual theme */
.admin-head{padding:23px;border-radius:23px;background:radial-gradient(ellipse at 100% 0,rgba(215,250,131,.14),transparent 45%),linear-gradient(135deg,#1c3b4d,#13283e 60%,#172b37);border:1px solid rgba(98,230,212,.19);box-shadow:0 18px 42px rgba(0,0,0,.25)}
.admin-head h2{font-size:clamp(20px,5vw,26px);line-height:1.25}.admin-head p{font-size:11px;line-height:1.7}.admin-head .admin-actions .btn{flex:1;min-width:115px}
.atabs{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.at{min-height:65px;border-radius:15px;background:linear-gradient(145deg,#1c314a,#112238);border-color:rgba(175,201,231,.12);font-size:10px}.at.on{background:linear-gradient(145deg,rgba(95,139,54,.28),rgba(30,58,44,.7));border-color:rgba(215,250,131,.42);color:#e1ffad;box-shadow:0 8px 20px rgba(0,0,0,.15)}.at.on:after{background:#d7fa83}
.sg{gap:9px}.sg .card{min-height:105px;border-radius:17px;background:linear-gradient(145deg,#1b3049,#112238);border-color:rgba(175,201,231,.1)}.sg .n{color:#e4ffad;font-size:clamp(17px,4vw,22px)}
.admin-section-title b{font-size:11px}.admin-tip{background:rgba(98,230,212,.07);border-color:rgba(98,230,212,.17);color:#bfe2df}.admin-item{min-height:72px}.admin-item .ic{width:44px;height:44px}.admin-item>span{background:rgba(98,230,212,.08);color:#78e5d8}.admin-empty{background:rgba(255,255,255,.025);border-color:rgba(175,201,231,.18);line-height:1.7}
.addb{border-radius:15px;background:rgba(215,250,131,.07);border-color:rgba(215,250,131,.3);color:#e2ffa5;font-weight:800}
#ac{min-height:150px}.ac .card{border-radius:18px}
@media(min-width:700px){#view{max-width:980px;padding-left:28px;padding-right:28px}.tapv{max-width:680px;margin:0 auto}.atabs{grid-template-columns:repeat(5,minmax(0,1fr))}.sg{grid-template-columns:repeat(4,minmax(0,1fr))}.admin-head{padding:28px 30px}.admin-head h2{font-size:28px}.grid{grid-template-columns:repeat(4,minmax(0,1fr))}.au{max-width:640px}}
@media(max-width:380px){#view{padding-left:12px;padding-right:12px}.card{padding:13px}.atabs{grid-template-columns:repeat(2,minmax(0,1fr))}.at{min-height:54px}.bal{font-size:35px}.hero{padding:15px}.hero .he{font-size:44px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important}}


/* ═════════ AKCOIN / ORBIT DESIGN SYSTEM ═════════ */
:root{--orbit:#9ee86b;--orbit2:#53d7c4;--panel:#111f32;--panel2:#172b42;--line:rgba(177,205,230,.12)}
::selection{background:rgba(158,232,107,.28);color:#fff}
button{font-family:inherit}
#view{max-width:1160px;margin:0 auto;padding-bottom:calc(env(safe-area-inset-bottom) + 112px)}
.brandline{width:100%;display:flex;align-items:center;gap:10px;margin:0 0 13px;padding:0 2px}
.brandmark{width:31px;height:31px;display:grid;place-items:center;border-radius:10px;background:linear-gradient(145deg,#e5ffad,#80c83d);color:#17240c;font:900 18px 'Unbounded';box-shadow:0 5px 17px rgba(158,232,107,.18)}
.brandname{font:900 11px 'Unbounded';letter-spacing:1.1px;color:#eaf4ff}.brandname small{display:block;margin-top:3px;font:800 8px 'Manrope';letter-spacing:2px;color:#8195aa}
.live-dot{margin-left:auto;display:flex;align-items:center;gap:6px;padding:6px 9px;border-radius:30px;border:1px solid rgba(98,230,212,.17);background:rgba(98,230,212,.055);font:800 8px 'Manrope';letter-spacing:1.2px;color:#8ce8d8}
.live-dot:before{content:'';width:6px;height:6px;border-radius:50%;background:#75e9ae;box-shadow:0 0 9px #75e9ae}
.tap-stats,.profile-kpis{width:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:15px 0 0}
.tap-stats>div,.profile-kpis>div{min-width:0;padding:10px 9px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,rgba(29,49,73,.82),rgba(13,25,42,.82));text-align:center}
.tap-stats small,.profile-kpis small{display:block;font-size:8px;letter-spacing:.8px;color:#8298af;font-weight:900;white-space:nowrap}
.tap-stats b,.profile-kpis b{display:block;margin-top:5px;font:800 12px 'Unbounded';color:#e6f7d0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.section-kicker{display:flex;align-items:center;gap:8px;margin:18px 2px 11px;font:900 9px 'Manrope';letter-spacing:1.3px;color:#9eb2c8}
.section-kicker b{margin-left:auto;color:#d9f79a;font-size:9px;letter-spacing:.4px}
.kicker-dot{width:7px;height:7px;border-radius:50%;background:#9ee86b;box-shadow:0 0 11px rgba(158,232,107,.5)}.kicker-line{height:1px;flex:1;background:linear-gradient(90deg,rgba(158,232,107,.28),transparent)}
.hero{position:relative;overflow:hidden;display:flex;align-items:center;min-height:150px;padding:20px 19px;background:radial-gradient(circle at 90% 20%,rgba(158,232,107,.2),transparent 35%),linear-gradient(120deg,#183c4a,#172b42 60%,#15283b);border:1px solid rgba(98,230,212,.2)}
.hero:after{content:'✦';position:absolute;right:17px;bottom:-32px;font:900 116px 'Unbounded';color:rgba(214,255,155,.055);pointer-events:none}
.hero .he{z-index:1}.hero .btn{position:relative;z-index:2}
.feature-banner{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;min-height:155px;margin:8px 0 19px;padding:22px;border:1px solid rgba(98,230,212,.18);border-radius:22px;background:radial-gradient(circle at 85% 30%,rgba(98,230,212,.18),transparent 30%),linear-gradient(120deg,#183b4a,#152a42 58%,#202f3e)}
.feature-banner>div:first-child{display:flex;flex-direction:column;align-items:flex-start;gap:7px;position:relative;z-index:1}
.feature-banner span{font:900 8px 'Manrope';letter-spacing:1.8px;color:#8be6d7}.feature-banner b{font:800 18px 'Unbounded';line-height:1.45;letter-spacing:-.6px;color:#f3f8ff}.feature-banner small{max-width:235px;font-size:10px;color:#a8bdcc}
.feature-orb{width:76px;height:76px;flex:none;display:grid;place-items:center;border-radius:50%;font-size:38px;color:#e8ffad;background:radial-gradient(circle at 35% 28%,#4e8172,#1c4350 65%,#142a3c);border:1px solid rgba(215,250,131,.24);box-shadow:0 0 0 9px rgba(98,230,212,.035),0 0 40px rgba(98,230,212,.13)}
.upgrade-grid{display:grid;grid-template-columns:1fr;gap:0}.upgrade-grid>.card{margin-bottom:9px}
.service-grid{display:grid;grid-template-columns:1fr;gap:0}.service-grid>.card{margin-bottom:9px}
.auction-grid{display:grid;grid-template-columns:1fr;gap:11px}.auction-grid>.au{margin:0;min-width:0}.auction-grid .img{height:clamp(165px,42vw,225px)}
.au{background:linear-gradient(145deg,#1a2d45,#101d30);border:1px solid rgba(180,204,230,.14);transition:transform .18s,border-color .18s}.au:active{transform:scale(.99)}
.profile-label{display:flex;align-items:center;gap:9px;margin:2px 2px 13px;font:900 9px 'Manrope';letter-spacing:1.6px;color:#9eb1c6}.smallmark{width:25px;height:25px;font-size:13px;border-radius:8px}.profile-label i{margin-left:auto;width:6px;height:6px;border-radius:50%;background:#9ee86b;box-shadow:0 0 10px #9ee86b}
.ph{position:relative;overflow:hidden;background:radial-gradient(ellipse at 50% -10%,rgba(98,230,212,.2),transparent 62%),linear-gradient(145deg,#1b334d,#101f34);border:1px solid rgba(174,201,229,.13);box-shadow:0 15px 35px rgba(0,0,0,.18)}
.ph:after{content:'✧';position:absolute;right:18px;top:9px;font-size:62px;color:rgba(215,250,131,.08);pointer-events:none}
.profile-kpis{margin:10px 0 18px}.profile-kpis>div{padding:12px 6px}.profile-kpis b{font-size:10px}
.grid .card{border:1px solid rgba(174,201,229,.12);transition:transform .16s,border-color .16s}.grid .card:active{transform:scale(.98);border-color:rgba(158,232,107,.4)}
#nav{box-shadow:0 18px 55px rgba(0,0,0,.52),inset 0 1px rgba(255,255,255,.07)}
#nav button{transition:color .16s,transform .16s}#nav button:active{transform:scale(.94)}
.card:not(.au):hover{border-color:rgba(98,230,212,.22)}
.admin-head{background:radial-gradient(ellipse at 95% 0,rgba(158,232,107,.16),transparent 40%),radial-gradient(ellipse at 0 100%,rgba(98,230,212,.1),transparent 45%),linear-gradient(135deg,#1b3048,#101d30 70%,#172b31)}
.admin-head .admin-actions .btn{min-height:43px}
.at{box-shadow:inset 0 1px rgba(255,255,255,.035)}
.at.on{border-color:rgba(158,232,107,.48);background:linear-gradient(145deg,rgba(92,131,52,.28),rgba(25,51,43,.7));color:#e3ffad}
.admin-section-title{padding-bottom:8px;border-bottom:1px solid rgba(177,201,231,.09)}
.admin-item{background:linear-gradient(145deg,rgba(24,42,64,.97),rgba(12,24,41,.98))}
.admin-tip{border-radius:13px}
.sh{border-color:rgba(174,201,229,.18);box-shadow:0 -22px 70px rgba(0,0,0,.48)}
.btn:focus-visible,.at:focus-visible,.inp:focus-visible{outline:2px solid #9ee86b;outline-offset:2px}
@media(min-width:620px){
 .tapv{max-width:690px}.upgrade-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.upgrade-grid>.card{margin:0}.service-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.service-grid>.card{margin:0}.auction-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.auction-grid .img{height:205px}
}
@media(min-width:960px){.auction-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.auction-grid .img{height:190px}.upgrade-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.service-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:380px){.tap-stats{gap:5px}.tap-stats>div{padding:9px 4px}.tap-stats small{font-size:7px}.tap-stats b{font-size:10px}.feature-banner{padding:17px}.feature-orb{width:62px;height:62px;font-size:30px}.hero{padding:16px}}
@media(prefers-reduced-motion:reduce){.orb,.halo,.coinw,.coin:after,.gift{animation:none!important}}

</style></head><body>
<div id="bg"><div class="orb o1"></div><div class="orb o2"></div></div>
<div id="view"></div><nav id="nav"></nav><div id="sheet"><div class="sh" id="shc"></div></div><div id="toast"></div>
<script>
const tg=Telegram.WebApp;tg.ready();tg.expand();
try{tg.setHeaderColor('#080f1d');tg.setBackgroundColor('#080f1d');tg.setBottomBarColor&&tg.setBottomBarColor('#080f1d');tg.disableVerticalSwipes&&tg.disableVerticalSwipes()}catch(e){}
const $=s=>document.querySelector(s);
const N=n=>Number(n).toLocaleString('en');
const K=n=>n>=1000000?(n/1e6).toFixed(1)+'M':n>=10000?(n/1000).toFixed(1)+'K':N(n);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let S={},CFG={},tab='tap',pending=0,busy=false,SV={},ORD={},AU=[],AQ={},TK=[],TT={},ADT='dash',ADMC={},AF={},OS='pending',US={q:'',s:'new',p:0},BCT=null;
const USER=(tg.initDataUnsafe&&tg.initDataUnsafe.user)||{};
async function api(p,b){const r=await fetch(p,{method:b===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Init':tg.initData},body:b===undefined?undefined:JSON.stringify(b)});let j={};try{j=await r.json()}catch(e){}if(!r.ok){const er=new Error(j.error||'Xatolik');er.code=r.status;throw er}return j}
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('on'),2400)};
const hap=(t='light')=>{try{tg.HapticFeedback.impactOccurred(t)}catch(e){}};
const good=()=>{try{tg.HapticFeedback.notificationOccurred('success')}catch(e){}};
const ask=(m,cb)=>{try{tg.showConfirm(m,y=>y&&cb())}catch(e){confirm(m)&&cb()}};
const mc=()=>`<i class="mc">${esc(CFG.ch)}</i>`;
const view=(h,keep)=>{const v=$('#view'),s=v.scrollTop;v.innerHTML=h;if(keep){v.scrollTop=s}else{v.scrollTop=0;v.classList.remove('fade');void v.offsetWidth;v.classList.add('fade')}};
const av=cls=>USER.photo_url?`<img class="av ${cls}" src="${esc(USER.photo_url)}">`:`<div class="av ${cls}">${esc((S.name||'?')[0])}</div>`;
const tbar=()=>`<div class="tb"><div class="row">${av('')}<div class="gr"><b>${esc(S.name)}</b><span class="lv">${esc(S.lvl.name)}</span></div></div><div class="pill dsp"><b id="tbal">${K(S.balance)}</b>${mc()}</div></div>`;
const hd=(t,fn)=>`<div class="hd"><button class="bk" onclick="${fn}">←</button><span>${t}</span></div>`;
const sheet=h=>{$('#shc').innerHTML=h;$('#sheet').classList.add('on')};
const closeSheet=()=>$('#sheet').classList.remove('on');
$('#sheet').addEventListener('click',e=>{if(e.target.id==='sheet')closeSheet()});
const refresh=async()=>{const r=await api('/api/me',{});S=r;CFG=r.cfg};
const cd=ts=>{const s=Math.max(0,Math.floor(ts-Date.now()/1000)),d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return s<=0?'Tugadi':d?`${d}k ${h}s ${m}d`:`${h}s ${m}d ${s%60}s`};
const star=(cx,cy,ro,ri,n)=>{let p='';for(let i=0;i<n*2;i++){const r=i%2?ri:ro,a=Math.PI*i/n-Math.PI/2;p+=(i?'L':'M')+(cx+r*Math.cos(a)).toFixed(1)+' '+(cy+r*Math.sin(a)).toFixed(1)}return p+'Z'};
const coinSVG=c=>`<svg viewBox="0 0 200 200"><defs><radialGradient id="cgf" cx="35%" cy="25%" r="85%"><stop offset="0" stop-color="#fff6c0"/><stop offset=".42" stop-color="#ffc83a"/><stop offset="1" stop-color="#d2790a"/></radialGradient><linearGradient id="cgr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff2a8"/><stop offset=".5" stop-color="#d98a0c"/><stop offset="1" stop-color="#ffe680"/></linearGradient></defs><circle cx="100" cy="100" r="99" fill="url(#cgr)"/><circle cx="100" cy="100" r="93.5" fill="none" stroke="#9a5a00" stroke-opacity=".55" stroke-width="5" stroke-dasharray="1.8 3.1"/><circle cx="100" cy="100" r="87" fill="url(#cgf)"/><circle cx="100" cy="100" r="79" fill="none" stroke="#fff4b8" stroke-opacity=".9" stroke-width="1.6"/><path d="${star(100,100,74,50,8)}" fill="#f2a516" fill-opacity=".45" stroke="#fff1a8" stroke-opacity=".7"/><text x="100" y="${c.length>1?121:127}" text-anchor="middle" font-family="Unbounded,Manrope,sans-serif" font-weight="800" font-size="${c.length>1?56:84}" fill="#fff8dc" stroke="#b86a00" stroke-width="3" paint-order="stroke" stroke-linejoin="round">${esc(c)}</text></svg>`;

/* NAV */
const IC={boost:'<path d="M12 2.5c3 2.4 4.6 6 4.1 9.8l-2.5 3.2h-3.2L7.9 12.3C7.4 8.5 9 4.9 12 2.5z"/><circle cx="12" cy="9.5" r="1.7"/><path d="M8 13.5l-3 3 2.2.6M16 13.5l3 3-2.2.6M10.5 19l1.5 3 1.5-3"/>',tasks:'<rect x="5" y="4" width="14" height="17" rx="3"/><path d="M9 4V3h6v1M9 13l2.2 2.2L15.5 11"/>',tap:'<circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="8"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22"/>',auction:'<path d="M8 4h8v5a4 4 0 01-8 0zM8 6H5v1a3 3 0 003 3M16 6h3v1a3 3 0 01-3 3M12 13v4M8.5 21h7M9.5 17h5"/>',profile:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>'};
const TABS=[['boost','Boost'],['tasks','Vazifalar'],['tap','Bosish'],['auction','Auksion'],['profile','Profil']];
const navR=()=>{$('#nav').innerHTML=TABS.map(([k,l])=>k==='tap'?`<button class="mid ${tab===k?'on':''}" onclick="go('${k}')"><i><svg viewBox="0 0 24 24">${IC[k]}</svg></i>${l}</button>`:`<button class="${k===tab?'on':''}" onclick="go('${k}')"><svg viewBox="0 0 24 24">${IC[k]}</svg>${l}</button>`).join('')};
function go(t){flush();clearInterval(BCT);tab=t;navR();closeSheet();if(t!=='tap')view('<div class="spn"></div>');const f={tap:tapV,tasks:taskV,boost:boostV,auction:auV,profile:profV}[t];Promise.resolve().then(f).catch(e=>{if(e.message==='maint')return maintV();toast(e.message)})}
const maintV=()=>view('<div class="mt">🛠<br>Texnik ishlar<br><small>Tez orada qaytamiz</small></div>');

/* BOSISH */
function tapV(){
 const L=S.lvl,pc=L.hi?Math.min(100,(S.earned-L.lo)/(L.hi-L.lo)*100):100,dg=S.daily.avail;
 view(`<div class="tapv"><div class="brandline"><span class="brandmark">A</span><span class="brandname">AKCOIN <small>PLAY · EARN · WIN</small></span><span class="live-dot">LIVE</span></div><div class="tb" style="width:100%"><div class="row">${av('')}<div class="gr"><b>${esc(S.name)}</b><span class="lv">${esc(L.name)}</span></div></div><button class="gift ${dg?'on':''}" onclick="dailyV()">🎁</button></div>
 ${CFG.announce?`<div class="ann">📢 ${esc(CFG.announce)}</div>`:''}
 <div style="text-align:center;width:100%"><div class="bal dsp">${mc()}<b id="bb"></b></div><div class="lvl"><span>${esc(L.name)}</span><div class="lb"><i id="lbar" style="width:${pc}%"></i></div><span>${esc(L.next||'MAX')}</span></div><div class="tap-stats"><div><small>JAMI TOPILGAN</small><b>${K(S.earned)}</b></div><div><small>DO‘STLAR</small><b>${N(S.refs)}</b></div><div><small>HAR BOSISH</small><b>+${N(S.power)}</b></div></div></div>
 <div id="tz"><div class="halo"></div><div class="coinw"><div class="coin" id="coin">${coinSVG(CFG.ch)}</div><div class="floor"></div></div></div>
 <div class="en"><div class="eh"><span id="et"></span><small>👆 +${S.power} · ⚡ +${S.regen}/s</small></div><div class="bar"><i id="eb"></i></div></div></div>`);
 updTap();
 $('#tz').addEventListener('pointerdown',e=>{e.preventDefault();
  if(S.energy<S.power){try{tg.HapticFeedback.notificationOccurred('error')}catch(_){}return}
  const c=$('#coin'),r=c.getBoundingClientRect(),dx=(e.clientX-r.left-r.width/2)/r.width,dy=(e.clientY-r.top-r.height/2)/r.height;
  c.style.transform=`perspective(500px) rotateX(${-dy*30}deg) rotateY(${dx*30}deg) scale(.93)`;setTimeout(()=>c.style.transform='',110);
  S.energy-=S.power;S.balance+=S.power;S.earned+=S.power;pending++;updTap();hap();
  const s=document.createElement('span');s.className='fl';s.textContent='+'+S.power;s.style.left=e.clientX+'px';s.style.top=e.clientY+'px';document.body.appendChild(s);setTimeout(()=>s.remove(),900);
  for(let i=0;i<5;i++){const p=document.createElement('i'),a=Math.random()*6.28,d=36+Math.random()*46;p.className='pt';p.style.cssText=`left:${e.clientX}px;top:${e.clientY}px;--dx:${Math.cos(a)*d}px;--dy:${Math.sin(a)*d-18}px`;document.body.appendChild(p);setTimeout(()=>p.remove(),600)}})
}
function updTap(){const a=$('#bb');if(!a)return;a.textContent=N(S.balance);$('#et').innerHTML=`⚡ ${Math.floor(S.energy)} <small>/ ${S.max}</small>`;$('#eb').style.width=(S.energy/S.max*100)+'%';const L=S.lvl;if(L.hi)$('#lbar').style.width=Math.min(100,(S.earned-L.lo)/(L.hi-L.lo)*100)+'%'}
async function flush(){if(!pending||busy)return;const n=pending;pending=0;busy=true;
 try{const r=await api('/api/tap',{n});const p=pending*S.power;Object.assign(S,r);S.balance+=p;S.earned+=p;S.energy=Math.max(0,S.energy-p);updTap()}catch(e){pending+=n}busy=false}
setInterval(flush,900);
setInterval(()=>{if(S.max){S.energy=Math.min(S.max,S.energy+S.regen/4);if(tab==='tap')updTap()}},250);
document.addEventListener('visibilitychange',()=>{if(document.hidden)flush()});
function dailyV(){const d=S.daily;sheet(`<h3 style="margin-top:0">🎁 Kunlik bonus</h3><small>Har kuni kiring — seriya uzilmasin! Ketma-ket: <b>${d.streak}</b> kun</small><div class="dayg">${d.rewards.map((r,i)=>`<div class="day ${i<d.done?'dn':(d.avail&&i===d.done?'nx':'')}"><span>${i+1}-kun</span><span style="font-size:20px">${i<d.done?'✅':i===6?'💎':'🎁'}</span><b>+${N(r)}</b></div>`).join('')}</div><button class="btn gold wide" ${d.avail?'':'disabled'} onclick="dailyGo()">${d.avail?'Bonusni olish':'Ertaga qaytib keling'}</button>`)}
async function dailyGo(){try{const r=await api('/api/daily',{});Object.assign(S,r.state);good();closeSheet();toast(`+${N(r.reward)} ${CFG.coin} 🎉`);tapV()}catch(e){toast(e.message)}}

/* VAZIFALAR */
const KI={link:['🔗','t'],channel:['✈️','b'],ad:['🎬','g'],youtube:['▶️','c']},KL={ad:'Ko‘rish',channel:'Obuna',link:'Ochish',youtube:'O‘tish'};
const lbl=t=>{const s=TT[t.id];if(!s)return KL[t.kind]||'Bajarish';const r=Math.ceil((s.at-Date.now())/1000);return r>0?r+'s':(t.kind==='channel'?'Tekshirish':'Olish')};
async function taskV(){TK=await api('/api/tasks');trk()}
function trk(keep){const o=TK.filter(t=>!t.done).length,l=TK.slice().sort((a,b)=>a.done-b.done);
 view(tbar()+`<div class="section-kicker"><span class="kicker-dot"></span> MISSIYALAR MARKAZI <span class="kicker-line"></span><b>${o} TA FAOL</b></div><div class="hero"><div class="f1"><b class="dsp">Do‘stlaringizni taklif qiling</b><div style="margin-top:6px"><small style="color:#cfeff0">Siz +${N(CFG.ref)} ${mc()} · do‘stingiz +${N(CFG.refnew)} ${mc()}<br>Taklif qilinganlar: <b>${S.refs}</b></small></div><button class="btn gold" onclick="inv()">Taklif qilish</button></div><div class="he">🎁</div></div>
 <h3>Vazifalar <span class="badge">${o}</span></h3>`+(l.map(t=>{const k=KI[t.kind]||['⭐','v'];return `<div class="card row ${t.done?'dim':''}"><div class="ic ${k[1]}">${k[0]}</div><div class="gr"><b>${esc(t.title)}</b><small>+${N(t.reward)} ${mc()}${t.limit?` · ${t.cnt}/${t.limit} bugun`:''}</small></div>${t.done?'<span class="ok">✓</span>':`<button class="btn" id="tk${t.id}" onclick="tdo(${t.id})">${lbl(t)}</button>`}</div>`}).join('')||'<p class="mut c">Hozircha vazifa yo‘q</p>'),keep)}
function inv(){const l=`https://t.me/${CFG.bot}?start=ref_${S.id}`;tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(l)}&text=${encodeURIComponent('🎁 Tanga yig‘ing, auksionda sovg‘alar yuting! Qo‘shiling:')}`)}
let adsL=null;const loadAds=()=>adsL||(adsL=new Promise((res,rej)=>{const s=document.createElement('script');s.src='https://sad.adsgram.ai/js/sad.min.js';s.onload=res;s.onerror=rej;document.head.appendChild(s)}));
async function tdo(id){const t=TK.find(x=>x.id==id);
 if(TT[id]){if(Date.now()<TT[id].at)return toast('Biroz kuting…');
  try{const r=await api(`/api/task/${id}/claim`,{});delete TT[id];S.balance+=r.reward;S.earned+=r.reward;good();toast(`+${N(r.reward)} ${CFG.coin}`);TK=await api('/api/tasks');trk(1)}catch(e){toast(e.message)}return}
 try{
  if(t.kind==='ad'&&CFG.ads){await loadAds();await api(`/api/task/${id}/start`,{});await window.Adsgram.init({blockId:CFG.ads}).show();TT[id]={at:0};return tdo(id)}
  await api(`/api/task/${id}/start`,{});TT[id]={at:Date.now()+t.wait*1000};
  if(t.url){/^https:\/\/t\.me\//.test(t.url)?tg.openTelegramLink(t.url):tg.openLink(t.url)}
 }catch(e){toast(e.message||'Reklama topilmadi')}}
setInterval(()=>{for(const id in TT){const b=$('#tk'+id),t=TK.find(x=>x.id==id);if(b&&t){b.textContent=lbl(t);b.classList.toggle('gold',Date.now()>=TT[id].at)}}},500);

/* BOOST */
async function boostV(){
 const [sv,od]=await Promise.all([api('/api/services'),api('/api/orders')]);SV=sv;
 const up=[['tap','👆','g','Bosish kuchi',`+${S.power} → +${S.power+1} har bosishda`],['energy','🔋','t','Energiya hajmi',`${S.max} → ${S.max+S.estep}`],['regen','⚡','v','Tiklanish tezligi',`${S.regen}/s → ${S.regen+1}/s`]];
 view(tbar()+`<div class="feature-banner"><div><span>UPGRADE CENTER</span><b>Imkoniyatingizni<br>kuchaytiring.</b><small>Har bir upgrade sizga ko‘proq imkoniyat beradi.</small></div><div class="feature-orb">✦</div></div><h3>Kuchaytirish</h3><div class="upgrade-grid">`+up.map(([k,i,cl,t,d])=>{const c=S.cost[k];return `<div class="card"><div class="row"><div class="ic ${cl}">${i}</div><div class="gr"><b>${t}</b><small>${c===null?'Maksimal daraja 🔥':d}</small></div>${c===null?'':`<button class="btn gold" onclick="upg('${k}')">${N(c)} ${mc()}</button>`}</div><div class="pips">${Array.from({length:S.maxl},(_,j)=>`<i class="${j<S.lv[k]?'on':''}"></i>`).join('')}</div></div>`}).join('')+'</div>'+`<h3>Xizmatlar</h3><div class="service-grid">`+(Object.entries(SV).map(([k,p])=>`<div class="card plat click" onclick="plat('${k}')"><div class="ic b">${esc(p.i)}</div><b class="f1">${esc(p.t)}</b><span class="mut">›</span></div>`).join('')||'<p class="mut c">Xizmatlar yo‘q</p>')+'</div>'
 +(od.length?`<h3>Buyurtmalarim</h3>`+od.map(o=>`<div class="card row sb"><div class="gr"><b>#${o.id} ${esc(o.title)}</b><small>${N(o.qty)} ta · ${N(o.cost)} ${esc(CFG.coin)}</small></div><span class="chip ${o.status}">${{pending:'⏳ Kutilmoqda',processing:'⚙️ Jarayonda',done:'✓ Bajarildi',cancel:'Bekor'}[o.status]}</span></div>`).join(''):''))}
async function upg(k){try{const r=await api('/api/upgrade',{k});Object.assign(S,r);good();toast('Kuchaytirildi! 🔥');boostV()}catch(e){toast(e.message)}}
function plat(k){const p=SV[k];view(hd(esc(p.t),'boostV()')+Object.entries(p.s).map(([s,it])=>`<div class="card row click" onclick="svc('${k}','${s}')"><div class="ic t">${esc(it.i)}</div><div class="gr"><b>${esc(it.t)}</b><small>1000 ta = ${N(it.p)} ${mc()}</small></div><span class="mut">›</span></div>`).join(''))}
function svc(k,s){const it=SV[k].s[s];ORD={k,s,min:it.min,p:it.p,qty:it.min};
 view(hd(esc(it.t),`plat('${k}')`)+`<div class="fg"><label>Havolani kiriting</label><input id="lk" class="inp" placeholder="${esc(it.ph)}"></div>
 <div class="card"><div class="row sb"><b>${esc(it.t)}</b><small>Min: ${it.min}</small></div><small>1000 ta = ${N(it.p)} ${mc()}</small>
 <div class="qrow"><button class="btn" onclick="qd(-1)">−${it.min}</button><input id="qn" class="inp qi" type="number" inputmode="numeric" value="${it.min}" oninput="qs(+this.value,1)"><button class="btn" onclick="qd(1)">+${it.min}</button></div>
 <div class="chipsr">${[1,5,10,50].map(m=>`<button class="btn sm" onclick="qs(${it.min*m})">${N(it.min*m)}</button>`).join('')}</div></div>
 <div class="card" id="sm"></div><button class="btn gold wide" id="ob" onclick="order()"></button>`);qs(it.min)}
function qs(n,inp){ORD.qty=Math.max(0,Math.floor(n)||0);if(!inp)$('#qn').value=ORD.qty;const c=Math.ceil(ORD.qty*ORD.p/1000);
 $('#sm').innerHTML=`<div class="row2"><span>Miqdor</span><b>${N(ORD.qty)} ta</b></div><div class="row2"><span>Jami</span><b>${N(c)} ${mc()}</b></div><div class="row2"><span>Balansingiz</span><b class="${S.balance<c?'bad':''}">${N(S.balance)} ${mc()}</b></div>`;
 const b=$('#ob');b.disabled=ORD.qty<ORD.min||S.balance<c;b.textContent=ORD.qty<ORD.min?`Minimal: ${ORD.min}`:S.balance<c?'Tanga yetarli emas':'Buyurtma berish'}
const qd=d=>qs(Math.max(ORD.min,ORD.qty+d*ORD.min));
async function order(){const link=$('#lk').value.trim();if(link.length<4)return toast('Havolani kiriting');
 try{const r=await api('/api/order',{k:ORD.k,s:ORD.s,link,qty:ORD.qty});Object.assign(S,r);good();toast('Buyurtma qabul qilindi ✅');boostV()}catch(e){toast(e.message)}}

/* AUKSION */
async function auV(){AU=await api('/api/auctions');auR()}
function auR(keep){view(tbar()+`<div class="section-kicker"><span class="kicker-dot"></span> PRIZE ARENA <span class="kicker-line"></span><b>${AU.length} TA LOT</b></div><div class="auction-grid">`+(AU.map(a=>`<div class="card au click" onclick="auO(${a.id})"><div class="img" style="${a.image?`background-image:url('${esc(a.image)}')`:''}">${a.image?'':'🎁'}<div class="ov"></div><button class="hp ${a.liked?'on':''}" onclick="event.stopPropagation();lk(${a.id})">${a.liked?'♥':'♡'} ${a.likes}</button>${a.done?'<span class="cdc end">Yakunlangan</span>':`<span class="cdc cd" data-e="${a.ends}">${cd(a.ends)}</span>`}<div class="tt">${esc(a.title)}</div></div><div class="ab row sb"><span><b class="dsp">${N(a.price)}</b> ${mc()} <small>/ bilet</small></span>${a.done?`<span class="ok">🏆 ${esc(a.winner_name||'—')}</span>`:`<small>Sizda: <b style="color:#fff">${N(a.mine)}</b> bilet</small>`}</div></div>`).join('')||'<p class="mut c" style="margin-top:40px">Hozircha auksion yo‘q</p>')+'</div>',keep)}
setInterval(()=>document.querySelectorAll('.cd').forEach(e=>e.textContent=cd(+e.dataset.e)),1000);
async function lk(id){const a=AU.find(x=>x.id==id);a.liked=a.liked?0:1;a.likes+=a.liked?1:-1;auR(1);hap();try{await api(`/api/auction/${id}/like`,{})}catch(e){}}
function auO(id){const a=AU.find(x=>x.id==id);AQ={id,q:1,price:a.price};
 sheet(`<div class="img big" style="${a.image?`background-image:url('${esc(a.image)}')`:''}">${a.image?'':'🎁'}<div class="ov"></div><div class="tt">${esc(a.title)}</div></div>
 <div class="stats"><div><small>Jami biletlar</small><b>${N(a.total)}</b></div><div><small>Sizning biletlar</small><b>${N(a.mine)}</b></div><div><small>Imkoniyat</small><b>${a.total?(a.mine/a.total*100).toFixed(1):0}%</b></div></div>`+
 (a.done?`<p class="c ok">🏆 G‘olib: ${esc(a.winner_name||'—')}</p>`:`<div class="qrow"><button class="btn" onclick="aq(-1)">−</button><input id="aqn" class="inp qi" type="number" inputmode="numeric" value="1" oninput="aq(0,+this.value)"><button class="btn" onclick="aq(1)">+</button></div>
 <div class="chipsr">${[1,5,10,50].map(m=>`<button class="btn sm" onclick="aq(0,${m})">${m}</button>`).join('')}</div><div class="card" id="asm" style="margin-top:12px"></div><button class="btn gold wide" id="abtn" onclick="abuy()"></button>`));if(!a.done)aq(0,1)}
function aq(d,v){AQ.q=Math.max(1,Math.min(1000,Math.floor(v!==undefined?v:AQ.q+d)||1));if(v===undefined)$('#aqn').value=AQ.q;const c=AQ.q*AQ.price;
 $('#asm').innerHTML=`<div class="row2"><span>Biletlar</span><b>${N(AQ.q)} ta</b></div><div class="row2"><span>Jami</span><b>${N(c)} ${mc()}</b></div><div class="row2"><span>Balansingiz</span><b class="${S.balance<c?'bad':''}">${N(S.balance)} ${mc()}</b></div>`;
 const b=$('#abtn');b.disabled=S.balance<c;b.textContent=S.balance<c?'Tanga yetarli emas':'Bilet olish'}
async function abuy(){try{const r=await api(`/api/auction/${AQ.id}/buy`,{qty:AQ.q});Object.assign(S,r);good();closeSheet();toast('Bilet olindi! Omad 🍀');AU=await api('/api/auctions');auR(1)}catch(e){toast(e.message)}}

/* PROFIL */
function profV(){view(`<div class="profile-label"><span class="brandmark smallmark">A</span><span>PLAYER IDENTITY</span><i></i></div><div class="ph">${av('')}<h2>${esc(S.name)}</h2><small>${S.username?'@'+esc(S.username):'ID '+S.id}</small><span class="lv">${esc(S.lvl.name)}</span></div>
 <div class="card balc"><small>Balans</small><div class="big">${mc()}<b>${N(S.balance)}</b></div><small>Jami topilgan: ${N(S.earned)} · Do‘stlar: ${S.refs}</small></div><div class="profile-kpis"><div><small>TOPILGAN</small><b>${K(S.earned)}</b></div><div><small>TAKLIFLAR</small><b>${N(S.refs)}</b></div><div><small>DARAJA</small><b>${esc(S.lvl.name)}</b></div></div>
 <h3>Tezkor amallar</h3><div class="grid"><div class="card click" onclick="promo()"><div class="ic g">🎟</div>Promokod</div><div class="card click" onclick="sendV()"><div class="ic t">📤</div>Tanga yuborish</div>
 <div class="card click" onclick="rate('balance')"><div class="ic v">📊</div>Reyting</div><div class="card click" onclick="paid()"><div class="ic c">🏅</div>Pullik xizmatlar</div></div>`+(CFG.is_admin?`<button class="btn tq wide" style="margin-top:14px" onclick="admV()">⚙️ Admin panel</button>`:''))}
function promo(){sheet(`<h3 style="margin-top:0">🎟 Promokod</h3><input id="pc" class="inp" placeholder="KODNI KIRITING" style="text-transform:uppercase"><button class="btn gold wide" onclick="dopromo()">Faollashtirish</button>`)}
async function dopromo(){try{const r=await api('/api/promo',{code:$('#pc').value});S.balance+=r.reward;S.earned+=r.reward;good();closeSheet();toast(`+${N(r.reward)} ${CFG.coin} 🎉`);profV()}catch(e){toast(e.message)}}
function sendV(){sheet(`<h3 style="margin-top:0">📤 Tanga yuborish</h3><div class="fg"><input id="st" class="inp" placeholder="@username yoki ID"></div><div class="fg"><input id="sa" class="inp" type="number" inputmode="numeric" placeholder="Miqdor"></div><button class="btn gold wide" onclick="dosend()">Yuborish</button>`)}
async function dosend(){try{const r=await api('/api/send',{to:$('#st').value,amount:+$('#sa').value});Object.assign(S,r);good();closeSheet();toast('Yuborildi ✅');profV()}catch(e){toast(e.message)}}
async function rate(by){const r=await api('/api/rating?by='+by);const fv={balance:u=>u.balance,refs:u=>u.refs,earned:u=>u.earned}[by];
 view(hd('Reyting','profV()')+`<div class="seg">${[['balance','Balans'],['earned','Topilgan'],['refs','Do‘stlar']].map(([k,l])=>`<button class="${k===by?'on':''}" onclick="rate('${k}')">${l}</button>`).join('')}</div><div class="card row sb meh"><b>Sizning o‘rningiz</b><b class="dsp">#${r.me}</b></div>`+r.top.map((u,i)=>`<div class="card row ${u.id==S.id?'meh':''}"><b class="rk">${['🥇','🥈','🥉'][i]||i+1}</b><div class="gr"><b>${esc(u.name)}</b><small>${u.username?'@'+esc(u.username):''}</small></div><b class="dsp" style="font-size:13px">${K(fv(u))}</b></div>`).join(''))}
function paid(){view(hd('Pullik xizmatlar','profV()')+CFG.paid.map(p=>`<div class="card row"><div class="ic c">${esc(p[0])}</div><div class="gr"><b>${esc(p[1])}</b><small>${esc(p[2])}</small></div><button class="btn gold" onclick="tg.openTelegramLink('https://t.me/${esc(CFG.admin)}')">Aloqa</button></div>`).join('')||'<p class="mut c">Yo‘q</p>')}

/* ═════════ ADMIN PANEL ═════════ */
const fld=([k,l,t,o],v)=>`<div class="fg"><label>${l}</label>`+(t==='sel'?`<select class="inp" id="f_${k}">${(typeof o==='function'?o():o).map(([a,b])=>`<option value="${esc(a)}" ${String(a)===String(v)?'selected':''}>${esc(b)}</option>`).join('')}</select>`:t==='area'?`<textarea class="inp" id="f_${k}" rows="5">${esc(v)}</textarea>`:t==='dt'?`<input class="inp" id="f_${k}" type="datetime-local" value="${v}">`:`<input class="inp" id="f_${k}" type="${t==='int'||t==='float'?'number':'text'}" ${t==='float'?'step="any"':''} value="${esc(v)}">`)+`</div>`;
const dtv=ts=>{const d=new Date(ts*1000);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16)};
const ON=[[1,'✅ Faol'],[0,'⏸ O‘chirilgan']];
const ADM={
 tasks:{add:'Vazifa qo‘shish',pk:'id',def:{kind:'link',reward:100,daily_limit:0,sort:0,active:1},f:[['title','Nomi','text'],['kind','Turi','sel',[['link','🔗 Havola'],['channel','✈️ Kanalga obuna'],['youtube','▶️ YouTube'],['ad','🎬 Reklama ko‘rish']]],['reward','Mukofot','int'],['url','Havola (URL)','text'],['chat_id','Kanal (@username) — faqat «obuna» uchun. Bot kanalda admin bo‘lsin','text'],['daily_limit','Kunlik limit (0 = bir marta)','int'],['sort','Tartib raqami','int'],['active','Holati','sel',ON]],row:r=>[(KI[r.kind]||['⭐'])[0],r.title,`+${N(r.reward)} · ${r.kind}${r.daily_limit?' · kunlik '+r.daily_limit:''}`,r.active]},
 auctions:{add:'Auksion qo‘shish',pk:'id',def:{price:100,image:''},f:[['title','Sovg‘a nomi','text'],['image','Rasm havolasi (botga rasm yuborib havola oling)','text'],['price','Bilet narxi','int'],['ends','Tugash vaqti','dt']],row:r=>['🏆',r.title,`${N(r.price)}/bilet · ${N(r.total)} bilet · ${r.players} kishi · ${r.done?'tugagan':cd(r.ends)}`,r.done?0:1],
  extra:r=>`<div class="row" style="margin-top:8px"><button class="btn f1" onclick="aPl(${r.id})">👥 Ishtirokchilar</button>${r.done?'':`<button class="btn tq f1" onclick="aFin(${r.id})">🏁 Hozir yakunlash</button>`}</div>`},
 promos:{add:'Promokod qo‘shish',pk:'code',man:1,def:{reward:500,max_uses:0},f:[['code','Kod','text'],['reward','Mukofot','int'],['max_uses','Limit (0 = cheksiz)','int']],row:r=>['🎟',r.code,`+${N(r.reward)} · ishlatilgan ${r.uses}/${r.max_uses||'∞'}`,1]},
 plats:{add:'Platforma qo‘shish',pk:'slug',man:1,def:{icon:'✨',sort:0,active:1},f:[['slug','Kod (lotin, masalan youtube)','text'],['title','Nomi','text'],['icon','Emoji','text'],['sort','Tartib','int'],['active','Holati','sel',ON]],row:r=>[r.icon,r.title,r.slug,r.active]},
 svcs:{add:'Xizmat qo‘shish',pk:'id',def:{icon:'👥',minq:100,price:50000,sort:0,active:1,plat:''},f:[['plat','Platforma','sel',()=>(ADMC.plats||[]).map(p=>[p.slug,p.icon+' '+p.title])],['slug','Kod (lotin, masalan sub)','text'],['title','Nomi','text'],['icon','Emoji','text'],['price','1000 ta narxi (tanga)','int'],['minq','Minimal miqdor','int'],['ph','Havola namunasi','text'],['smm_id','SMM panel xizmat ID (avtomatik uchun, ixtiyoriy)','text'],['sort','Tartib','int'],['active','Holati','sel',ON]],row:r=>[r.icon,`${r.plat} → ${r.title}`,`1000 ta = ${N(r.price)} · min ${r.minq}${r.smm_id?' · SMM '+r.smm_id:''}`,r.active]},
 paid:{add:'Xizmat qo‘shish',pk:'id',def:{icon:'⭐',sort:0,active:1},f:[['icon','Emoji','text'],['title','Nomi','text'],['descr','Tavsif','text'],['sort','Tartib','int'],['active','Holati','sel',ON]],row:r=>[r.icon,r.title,r.descr,r.active]},
 admins:{add:'Admin qo‘shish',pk:'id',man:1,def:{},f:[['id','Telegram ID','int'],['note','Izoh (ism)','text']],row:r=>['🛡',r.note||('ID '+r.id),String(r.id),1]}
};
const AT=[['dash','📊','Statistika'],['set','⚙️','Sozlamalar'],['tasks','🎯','Vazifalar'],['auctions','🏆','Auksion'],['promos','🎟','Promokod'],['svcs','🚀','Xizmatlar'],['orders','🛒','Buyurtmalar'],['users','👥','Foydalanuvchilar'],['bc','📣','Xabar'],['paid','💎','Pullik'],['admins','🛡','Adminlar'],['bk','💾','Zaxira']];
function admV(t){clearInterval(BCT);if(t)ADT=t;
 view(`<div class="admin-head"><div class="eyebrow">OWNER WORKSPACE · LIVE CONTROL</div><h2>Boshqaruv markazi</h2><p>Botning barcha muhim bo‘limlari shu yerda. Foydalanuvchilar, balanslar, vazifalar, xizmatlar, buyurtmalar va ko‘rinadigan matnlarni boshqaring.</p><div class="admin-actions"><button class="btn tq" onclick="admV('dash')">▦ Umumiy ko‘rsatkichlar</button><button class="btn" onclick="admV('set')">⚙ Barcha sozlamalar</button></div></div><div class="atabs">${AT.map(([k,i,l])=>`<button class="at ${k===ADT?'on':''}" onclick="admV('${k}')">${i} ${l}</button>`).join('')}</div><div id="ac"><div class="spn"></div></div>`);
 admT(ADT).catch(e=>toast(e.message))}
async function admT(t){ADT=t;const c=$('#ac');if(!c)return;
 if(t==='dash'){const d=await api('/api/adm/dash'),mx=Math.max(1,...d.ser.map(s=>s[1]));
  c.innerHTML=`<div class="sg">${[['👥','Foydalanuvchi',N(d.users)],['🆕','Bugun yangi',N(d.today)],['🔥','24 soatda aktiv',N(d.active)],['🛒','Kutilayotgan buyurtma',N(d.op)],['💰','Jami balans',K(d.bal)],['⛏','Jami topilgan',K(d.earned)],['🎯','Faol vazifa',d.tasks],['🏆','Faol auksion',d.auctions]].map(([i,l,v])=>`<div class="card"><small>${i} ${l}</small><div class="n">${v}</div></div>`).join('')}</div>
  <div class="card"><b>So‘nggi 7 kun — yangi foydalanuvchilar</b><div class="bars">${d.ser.map(s=>`<div><span>${s[1]}</span><i style="height:${Math.max(4,s[1]/mx*80)}px"></i><span>${s[0]}</span></div>`).join('')}</div></div>
  <h3>🏅 Eng ko‘p do‘st taklif qilganlar</h3>`+(d.top.map((u,i)=>`<div class="card row sb"><b>${i+1}. ${esc(u.name)}</b><span class="ok">${u.refs} ta</span></div>`).join('')||'<p class="mut c">Hali yo‘q</p>')+`<small>Bloklangan: ${d.banned} · Bajarilgan buyurtma: ${d.od} · Promokod: ${d.promos}</small>`}
 else if(t==='set'){const r=await api('/api/adm/settings');const gs=[...new Set(r.map(s=>s.g))];
  c.innerHTML=`<div class="admin-tip">Bu yerdagi o‘zgarishlar saqlangach bot va Mini App sozlamalariga qo‘llanadi. Matn maydonlariga HTML formatidan foydalanishingiz mumkin.</div>`+gs.map(g=>`<div class="admin-section-title"><b>${esc(g)}</b><small>${r.filter(s=>s.g===g).length} ta sozlama</small></div><div class="card">`+r.filter(s=>s.g===g).map(s=>fld([s.k,s.l,s.t==='sel01'?'sel':s.t,s.t==='sel01'?[[0,'⏸ O‘chiq'],[1,'✅ Yoqilgan']]:undefined],s.v)).join('')+`</div>`).join('')+`<button class="btn gold wide" onclick="setSave()">💾 Barcha sozlamalarni saqlash</button>`;AF.set=r}
 else if(t==='orders')return admOrders();
 else if(t==='users')return admUsers();
 else if(t==='bc'){c.innerHTML=`<div class="card"><div class="fg"><label>Matn (HTML: &lt;b&gt;qalin&lt;/b&gt;)</label><textarea id="b_t" class="inp" rows="5" placeholder="Xabar matni…"></textarea></div><div class="fg"><label>Rasm havolasi (ixtiyoriy)</label><input id="b_i" class="inp"></div><div class="fg"><label>Tugma matni (ixtiyoriy)</label><input id="b_bt" class="inp" placeholder="🚀 Ochish"></div><div class="fg"><label>Tugma havolasi (bo‘sh = ilovani ochadi)</label><input id="b_bu" class="inp"></div><div class="fg"><label>Kimlarga</label><select id="b_g" class="inp"><option value="all">Hammaga</option><option value="active">Oxirgi 7 kunda aktivlarga</option></select></div><button class="btn gold wide" onclick="bcGo()">📣 Yuborish</button><div id="bcs" style="margin-top:12px"></div></div>`;bcPoll()}
 else if(t==='bk'){c.innerHTML=`<div class="card"><b>💾 Baza zaxirasi</b><p><small>Render bepul rejimida disk o‘chib ketishi mumkin. Zaxirani Telegramga yuboring va vaqti-vaqti bilan saqlab turing.</small></p><button class="btn tq wide" onclick="bkGo()">Bazani menga yuborish</button></div><div class="card"><b>♻️ Tiklash</b><p><small>Zaxira faylini (.db) botga <code>/restore</code> izohi bilan yuboring.</small></p></div><div class="card"><b>🖼 Rasm yuklash</b><p><small>Botga oddiy rasm yuboring — u sizga havola beradi. Uni auksion yoki xabarga qo‘ying.</small></p></div><div class="card"><b>🛠 Texnik ishlar</b><p><small>Sozlamalar → «Texnik ishlar rejimi»ni yoqing — foydalanuvchilar uchun ilova vaqtincha yopiladi.</small></p></div>`}
 else if(t==='svcs'){await admLoad('plats');await admLoad('svcs');c.innerHTML=`<h3>Platformalar</h3><button class="addb" onclick="admForm('plats',null)">＋ Platforma qo‘shish</button><div id="l_plats">${admRows('plats')}</div><h3>Xizmatlar</h3><button class="addb" onclick="admForm('svcs',null)">＋ Xizmat qo‘shish</button><div id="l_svcs">${admRows('svcs')}</div>`}
 else{await admLoad(t);c.innerHTML=`<button class="addb" onclick="admForm('${t}',null)">＋ ${ADM[t].add}</button>`+admRows(t)}}
const admLoad=async k=>{ADMC[k]=await api('/api/adm/list/'+k)};
function admRows(k){const C=ADM[k],L=ADMC[k]||[];return L.map((r,i)=>{const [ic,t,s,on]=C.row(r);return `<div class="card row click admin-item ${on===0?'dim':''}" onclick="admForm('${k}',${i})"><div class="ic t">${esc(ic)}</div><div class="gr"><b>${esc(t)}</b><small>${esc(s)}</small></div><span class="mut">✎</span></div>`}).join('')||'<div class="admin-empty">Hozircha ma’lumot yo‘q.<br>Yuqoridagi tugma orqali yangisini qo‘shing.</div>'}
function admForm(kind,i){const C=ADM[kind],r=i===null?Object.assign({},C.def||{}):ADMC[kind][i];if(i===null&&kind==='auctions')r.ends=Date.now()/1000+7*86400;if(i===null&&kind==='svcs'&&ADMC.plats&&ADMC.plats[0])r.plat=ADMC.plats[0].slug;
 AF={kind,i,r};sheet(`<h3 style="margin-top:0">${i===null?'➕ '+C.add:'✏️ Tahrirlash'}</h3>`+C.f.map(f=>fld(f,r[f[0]]===undefined?'':(f[2]==='dt'?dtv(r[f[0]]):r[f[0]]))).join('')+`<button class="btn gold wide" onclick="admSave()">Saqlash</button>`+(i!==null?(C.extra?C.extra(r):'')+`<button class="btn red wide" onclick="admDel()">🗑 O‘chirish</button>`:''))}
async function admSave(){const C=ADM[AF.kind],b={};C.f.forEach(([k,l,t])=>{const e=$('#f_'+k).value;b[k]=t==='dt'?new Date(e).getTime()/1000:e});if(!C.man&&AF.i!==null)b.id=AF.r.id;
 try{await api('/api/adm/save/'+AF.kind,b);closeSheet();good();toast('Saqlandi ✅');admT(ADT)}catch(e){toast(e.message)}}
function admDel(){const C=ADM[AF.kind];ask('Rostdan o‘chirasizmi?',async()=>{try{await api(`/api/adm/del/${AF.kind}/${encodeURIComponent(AF.r[C.pk])}`,{});closeSheet();toast('O‘chirildi');admT(ADT)}catch(e){toast(e.message)}})}
async function setSave(){const b={};AF.set.forEach(s=>b[s.k]=$('#f_'+s.k).value);try{await api('/api/adm/settings',b);await refresh();good();toast('Saqlandi ✅')}catch(e){toast(e.message)}}
async function aPl(id){try{const r=await api(`/api/adm/auction/${id}/players`);sheet(`<h3 style="margin-top:0">👥 Ishtirokchilar</h3>`+(r.map(u=>`<div class="card row sb"><div class="gr"><b>${esc(u.name)}</b><small>${u.username?'@'+esc(u.username)+' · ':''}${u.id}</small></div><b>${N(u.cnt)} 🎫</b></div>`).join('')||'<p class="mut c">Hali yo‘q</p>'))}catch(e){toast(e.message)}}
function aFin(id){ask('Auksionni hozir yakunlab g‘olibni tanlaysizmi?',async()=>{try{const r=await api(`/api/adm/auction/${id}/finish`,{});closeSheet();toast(r.winner&&r.winner.name?'🏆 G‘olib: '+r.winner.name:'Ishtirokchi yo‘q edi');admT(ADT)}catch(e){toast(e.message)}})}
/* buyurtmalar */
const STL={pending:'⏳ Kutilmoqda',processing:'⚙️ Jarayonda',done:'✓ Bajarildi',cancel:'Bekor'};
async function admOrders(st){OS=st||OS;const r=await api('/api/adm/orders?st='+OS);
 $('#ac').innerHTML=`<div class="seg">${[['pending','Kutilmoqda'],['done','Bajarilgan'],['cancel','Bekor'],['all','Hammasi']].map(([k,l])=>`<button class="${k===OS?'on':''}" onclick="admOrders('${k}')">${l}</button>`).join('')}</div>`+(r.map(o=>`<div class="card"><div class="row sb"><b>#${o.id} ${esc(o.title||o.svc)}</b><span class="chip ${o.status}">${STL[o.status]||o.status}</span></div><small>👤 ${esc(o.uname)} ${o.uun?'@'+esc(o.uun):''} · <code>${o.user_id}</code></small><div style="margin:8px 0;word-break:break-all;user-select:text">🔗 ${esc(o.link)}</div><small>${N(o.qty)} ta · ${N(o.cost)} ${esc(CFG.coin)}${o.ext?' · SMM #'+esc(o.ext):''}</small>${o.status==='pending'||o.status==='processing'?`<div class="row" style="margin-top:10px"><button class="btn tq f1" onclick="ordAct(${o.id},'done')">✅ Bajarildi</button><button class="btn red f1" onclick="ordAct(${o.id},'cancel')">↩ Bekor</button></div>`:''}</div>`).join('')||'<p class="mut c">Buyurtma yo‘q</p>')}
async function ordAct(id,a){try{await api('/api/adm/order/'+id,{act:a});good();toast('Bajarildi');admOrders()}catch(e){toast(e.message)}}
/* foydalanuvchilar */
let UL=[];
async function admUsers(){const r=await api(`/api/adm/users?q=${encodeURIComponent(US.q)}&s=${US.s}&p=${US.p}`);UL=r.rows;
 $('#ac').innerHTML=`<div class="row" style="margin-bottom:10px"><input id="uq" class="inp f1" placeholder="ID, @username yoki ism" value="${esc(US.q)}"><button class="btn tq" onclick="US.q=$('#uq').value;US.p=0;admUsers()">🔎</button></div><div class="seg">${[['new','Yangi'],['bal','Boy'],['refs','Do‘stlar'],['act','Aktiv']].map(([k,l])=>`<button class="${k===US.s?'on':''}" onclick="US.s='${k}';US.p=0;admUsers()">${l}</button>`).join('')}</div><small>Jami: ${N(r.total)}</small><div style="height:8px"></div>`+
 UL.map((u,i)=>`<div class="card row click ${u.banned?'dim':''}" onclick="uOpen(${i})"><div class="ic t">${esc((u.name||'?')[0])}</div><div class="gr"><b>${esc(u.name)}${u.banned?' 🚫':''}</b><small>${u.username?'@'+esc(u.username)+' · ':''}${u.id}</small></div><b class="dsp" style="font-size:12px">${K(u.balance)}</b></div>`).join('')+
 `<div class="row" style="margin-top:6px"><button class="btn f1" ${US.p?'':'disabled'} onclick="US.p--;admUsers()">←</button><button class="btn f1" ${(US.p+1)*30<r.total?'':'disabled'} onclick="US.p++;admUsers()">→</button></div>`}
function uOpen(i){const u=UL[i];AF={u:i};sheet(`<h3 style="margin-top:0">${esc(u.name)}</h3><small>${u.username?'@'+esc(u.username)+' · ':''}ID <code>${u.id}</code>${u.ref_by?' · taklif qilgan: <code>'+u.ref_by+'</code>':''}</small>
 <div class="stats"><div><small>Balans</small><b>${K(u.balance)}</b></div><div><small>Topilgan</small><b>${K(u.earned)}</b></div><div><small>Do‘stlar</small><b>${u.refs}</b></div></div>
 <div class="row"><button class="btn tq f1" onclick="uOp(${i},'add')">＋ Qo‘shish</button><button class="btn red f1" onclick="uOp(${i},'sub')">− Ayirish</button><button class="btn f1" onclick="uOp(${i},'set')">= O‘rnatish</button></div>
 <div class="row" style="margin-top:8px"><button class="btn f1" onclick="uProfileEdit(${i})">✏️ Profil</button><button class="btn f1" onclick="uOp(${i},'msg')">✉️ Xabar</button><button class="btn f1" onclick="uOp(${i},'lvls')">⚙️ Darajalar</button></div>
 <button class="btn ${u.banned?'tq':'red'} wide" style="margin-top:8px" onclick="uBan(${i})">${u.banned?'♻️ Blokdan chiqar':'🚫 Bloklash'}</button>`)}
function uProfileEdit(i){const u=UL[i];sheet(`<h3 style="margin-top:0">✏️ Profilni tahrirlash</h3><div class="fg"><label>Ism</label><input id="up_name" class="inp" maxlength="60" value="${esc(u.name)}"></div><div class="fg"><label>Username (@ belgisiz)</label><input id="up_username" class="inp" maxlength="64" value="${esc(u.username||'')}"></div><button class="btn gold wide" onclick="uProfileSave(${i})">Saqlash</button>`)}
async function uProfileSave(i){const u=UL[i];try{await api('/api/adm/user/'+u.id,{op:'profile',name:$('#up_name').value,username:$('#up_username').value});closeSheet();toast('Profil yangilandi ✅');admUsers()}catch(e){toast(e.message)}}
function uOp(i,op){const u=UL[i];const inner=op==='msg'?`<textarea id="uv" class="inp" rows="4" placeholder="Xabar matni"></textarea>`:op==='lvls'?`${[['tap','Bosish kuchi',u.tap_lvl],['energy','Energiya',u.energy_lvl],['regen','Tiklanish',u.regen_lvl]].map(([k,l,v])=>`<div class="fg"><label>${l} (daraja)</label><input id="ul_${k}" class="inp" type="number" value="${v}"></div>`).join('')}`:`<input id="uv" class="inp" type="number" inputmode="numeric" placeholder="Miqdor">`;
 sheet(`<h3 style="margin-top:0">${esc(u.name)}</h3>${inner}<button class="btn gold wide" onclick="uGo(${i},'${op}')">Tasdiqlash</button>`)}
async function uGo(i,op){const u=UL[i];let b={op};if(op==='msg')b.text=$('#uv').value;else if(op==='lvls'){['tap','energy','regen'].forEach(k=>b[k]=$('#ul_'+k).value)}else{let a=+$('#uv').value;if(op==='sub'){b.op='add';a=-a}b.amount=a}
 try{await api('/api/adm/user/'+u.id,b);closeSheet();good();toast('Bajarildi ✅');admUsers()}catch(e){toast(e.message)}}
async function uBan(i){const u=UL[i];try{await api('/api/adm/user/'+u.id,{op:u.banned?'unban':'ban'});closeSheet();toast('Bajarildi');admUsers()}catch(e){toast(e.message)}}
/* xabar */
function bcGo(){const b={text:$('#b_t').value,image:$('#b_i').value,btn_t:$('#b_bt').value,btn_u:$('#b_bu').value,target:$('#b_g').value};ask('Xabar yuborilsinmi?',async()=>{try{await api('/api/adm/bc',b);toast('Yuborish boshlandi 🚀');bcPoll()}catch(e){toast(e.message)}})}
function bcPoll(){clearInterval(BCT);const f=async()=>{const e=$('#bcs');if(!e){clearInterval(BCT);return}try{const r=await api('/api/adm/bc');e.innerHTML=r.total?`<small>${r.running?'⏳ Yuborilmoqda…':'✅ Tugadi'} ${r.sent+r.fail}/${r.total} · ✅ ${r.sent} · ❌ ${r.fail}</small><div class="bar" style="margin-top:6px"><i style="width:${(r.sent+r.fail)/r.total*100}%"></i></div>`:'';if(!r.running)clearInterval(BCT)}catch(x){}};f();BCT=setInterval(f,2000)}
async function bkGo(){try{await api('/api/adm/backup',{});good();toast('Telegramga yuborildi 💾')}catch(e){toast(e.message)}}

(async()=>{try{await refresh()}catch(e){if(e.message==='maint'){navR();return maintV()}document.body.innerHTML='<p style="padding:40px;text-align:center">Ilovani Telegram ichida oching.</p>';return}
 go('tap');if(/[?&]admin=1/.test(location.search)&&CFG.is_admin){tab='profile';navR();admV('dash')}})();
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
    threading.Thread(target=bg_loop, daemon=True).start()
    log.info("Bot @%s ishga tushdi, port %s", BOT_USER, PORT)
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
