import sqlite3, hashlib, secrets, os, hmac
from datetime import datetime, timedelta, timezone
from database import DB_PATH

SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
PBKDF2_ITERATIONS = 310_000

def _hash(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return "pbkdf2_sha256$" + str(PBKDF2_ITERATIONS) + "$" + digest

def _verify_password(password: str, salt: str, stored: str) -> tuple[bool, str | None]:
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, digest = stored.split("$", 2)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
            return hmac.compare_digest(candidate, digest), None
        except (ValueError, TypeError):
            return False, None
    # Legacy accounts used SHA-256(salt + password); upgrade after successful login.
    legacy = hashlib.sha256((salt + password).encode()).hexdigest()
    ok = hmac.compare_digest(legacy, stored)
    return ok, (_hash(password, salt) if ok else None)

def init_users_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL, salt TEXT NOT NULL, password_h TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')) )""")
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, email TEXT NOT NULL,
        name TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')), expires_at TEXT)""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(sessions)")}
    if "expires_at" not in cols:
        con.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT")
    con.execute("UPDATE sessions SET expires_at=datetime(created_at, '+30 days') WHERE expires_at IS NULL")
    # Attach older email-based saved trips to an account when the email matches.
    try:
        con.execute("UPDATE saved_trips SET user_id=(SELECT users.id FROM users WHERE lower(users.email)=lower(saved_trips.email)) WHERE user_id IS NULL AND EXISTS (SELECT 1 FROM users WHERE lower(users.email)=lower(saved_trips.email))")
    except sqlite3.OperationalError:
        pass
    con.commit(); con.close()

def signup(email: str, name: str, password: str) -> dict:
    email=email.strip().lower(); name=name.strip()
    salt=secrets.token_hex(16); pw_h=_hash(password, salt)
    con=sqlite3.connect(DB_PATH)
    try:
        con.execute("INSERT INTO users (email,name,salt,password_h) VALUES (?,?,?,?)", (email,name,salt,pw_h))
        con.commit()
    except sqlite3.IntegrityError:
        con.close(); return {"error":"Email already registered. Please login instead."}
    con.close()
    return _make_session(email,name)

def login(email: str, password: str) -> dict:
    email=email.strip().lower(); con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row
    row=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not row:
        con.close(); return {"error":"No account found with this email. Please sign up first."}
    ok, upgraded=_verify_password(password,row["salt"],row["password_h"])
    if not ok:
        con.close(); return {"error":"Incorrect password. Please try again."}
    if upgraded:
        con.execute("UPDATE users SET password_h=? WHERE id=?",(upgraded,row["id"]))
        con.commit()
    name=row["name"]; con.close()
    return _make_session(email,name)

def _make_session(email: str, name: str) -> dict:
    token=secrets.token_hex(32); expires=(datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    con=sqlite3.connect(DB_PATH); uid=con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()[0]
    con.execute("INSERT INTO sessions (token,user_id,email,name,expires_at) VALUES (?,?,?,?,?)",(token,uid,email,name,expires))
    con.commit(); con.close()
    return {"token":token,"email":email,"name":name,"user_id":uid}

def verify_token(token: str) -> dict | None:
    if not token: return None
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row
    row=con.execute("SELECT * FROM sessions WHERE token=? AND expires_at > datetime('now')",(token,)).fetchone()
    if not row: con.execute("DELETE FROM sessions WHERE token=?",(token,)); con.commit()
    con.close(); return dict(row) if row else None

def logout(token: str):
    con=sqlite3.connect(DB_PATH); con.execute("DELETE FROM sessions WHERE token=?",(token,)); con.commit(); con.close()
