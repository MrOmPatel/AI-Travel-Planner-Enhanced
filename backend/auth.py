import sqlite3, hashlib, secrets, os
from database import DB_PATH

def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()

def init_users_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT    NOT NULL UNIQUE,
            name       TEXT    NOT NULL,
            salt       TEXT    NOT NULL,
            password_h TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT    PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            email      TEXT    NOT NULL,
            name       TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)
    con.commit()
    con.close()

def signup(email: str, name: str, password: str) -> dict:
    email = email.strip().lower()
    con   = sqlite3.connect(DB_PATH)
    if con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        con.close()
        return {"error": "Email already registered. Please login instead."}
    salt = secrets.token_hex(16)
    pw_h = _hash(password, salt)
    con.execute("INSERT INTO users (email, name, salt, password_h) VALUES (?,?,?,?)",
                (email, name.strip(), salt, pw_h))
    con.commit()
    con.close()
    return _make_session(email, name.strip())

def login(email: str, password: str) -> dict:
    email = email.strip().lower()
    con   = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    con.close()
    if not row:
        return {"error": "No account found with this email. Please sign up first."}
    if _hash(password, row["salt"]) != row["password_h"]:
        return {"error": "Incorrect password. Please try again."}
    return _make_session(email, row["name"])

def _make_session(email: str, name: str) -> dict:
    token = secrets.token_hex(32)
    con   = sqlite3.connect(DB_PATH)
    uid   = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    con.execute("INSERT INTO sessions (token, user_id, email, name) VALUES (?,?,?,?)",
                (token, uid, email, name))
    con.commit()
    con.close()
    return {"token": token, "email": email, "name": name}

def verify_token(token: str) -> dict | None:
    if not token:
        return None
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    con.close()
    return dict(row) if row else None

def logout(token: str):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM sessions WHERE token=?", (token,))
    con.commit()
    con.close()
