"""Sistema de autenticación, control de cuotas, licencias y cobro para ClipRadar.
Soporta límites de pantallas concurrentes (4 pantallas para Pro, 6 pantallas para Administrador)."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from typing import Optional

from .config import DATA_DIR

DB_PATH = DATA_DIR / "clipradar.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{k.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, h = stored_hash.split(":", 1)
        k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(k.hex(), h)
    except Exception:
        return False


def get_user_max_screens(user: dict) -> int:
    """Retorna el número máximo de pantallas/dispositivos permitidos."""
    if user.get("role") == "admin":
        return 6  # Tu cuenta de Administrador: 6 pantallas
    if user.get("plan") in ("pro_monthly", "pro_lifetime", "lifetime_vip"):
        return 4  # Cuentas de Pago: 4 pantallas
    return 1     # Prueba gratuita: 1 pantalla


def _random_admin_password() -> str:
    """Genera una contraseña de administrador aleatoria y la guarda en data/ADMIN_PASSWORD.txt (solo la ve el dueño)."""
    pw = secrets.token_urlsafe(9)
    try:
        (DATA_DIR / "ADMIN_PASSWORD.txt").write_text(
            f"Correo: {os.environ.get('CLIPRADAR_ADMIN_EMAIL', 'admin@clipradar.com')}\nContraseña: {pw}\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    print(f"[ClipRadar] Contraseña de administrador nueva guardada en {DATA_DIR / 'ADMIN_PASSWORD.txt'}")
    return pw


def init_db():
    """Inicializa las tablas y el usuario Administrador Maestro (sin cobro / VIP de por vida)."""
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                plan TEXT NOT NULL DEFAULT 'free_trial',
                trial_clips_left INTEGER NOT NULL DEFAULT 3,
                trial_minutes_left REAL NOT NULL DEFAULT 60.0,
                max_screens INTEGER NOT NULL DEFAULT 4,
                created_at REAL NOT NULL,
                license_key TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                key TEXT PRIMARY KEY,
                plan TEXT NOT NULL,
                clips_granted INTEGER NOT NULL,
                minutes_granted REAL NOT NULL,
                max_screens INTEGER NOT NULL DEFAULT 4,
                used_by TEXT,
                used_at REAL,
                created_at REAL NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_name TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                last_active REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        db.commit()

        # Migraciones automáticas seguras si la tabla ya existía
        for col_sql in [
            "ALTER TABLE users ADD COLUMN max_screens INTEGER NOT NULL DEFAULT 4",
            "ALTER TABLE licenses ADD COLUMN max_screens INTEGER NOT NULL DEFAULT 4",
            "ALTER TABLE sessions ADD COLUMN device_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN ip TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN last_active REAL NOT NULL DEFAULT 0.0",
        ]:
            try:
                db.execute(col_sql)
                db.commit()
            except sqlite3.OperationalError:
                pass

        # Crear o verificar cuenta Master Admin (6 pantallas, VIP Sin Cobro)
        admin = db.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if not admin:
            admin_id = "admin_master"
            admin_email = os.environ.get("CLIPRADAR_ADMIN_EMAIL", "admin@clipradar.com")
            admin_pass = os.environ.get("CLIPRADAR_ADMIN_PASS", "admin123")
            pw_hash = _hash_password(admin_pass)
            db.execute("""
                INSERT INTO users (id, email, password_hash, name, role, plan, trial_clips_left, trial_minutes_left, max_screens, created_at, status)
                VALUES (?, ?, ?, 'Dueño / Admin Maestro', 'admin', 'lifetime_vip', 999999, 999999.0, 6, ?, 'active')
            """, (admin_id, admin_email, pw_hash, time.time()))
            db.commit()
            try:
                (DATA_DIR / "ADMIN_PASSWORD.txt").write_text(
                    f"Correo: {admin_email}\nContraseña: {admin_pass}\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        else:
            # Asegurar que el admin tenga 6 pantallas configuradas
            db.execute("UPDATE users SET max_screens = 6 WHERE role = 'admin'")
            db.commit()


# Inicializar al cargar módulo
init_db()


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[dict]:
    with _get_db() as db:
        row = db.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)).fetchone()
        return dict(row) if row else None


def register_user(email: str, password: str, name: str = "") -> dict:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Correo electrónico inválido")
    if len(password) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres")
    if get_user_by_email(email):
        raise ValueError("Este correo ya está registrado")

    user_id = secrets.token_hex(8)
    pw_hash = _hash_password(password)
    now = time.time()
    name = name.strip() or email.split("@")[0]

    with _get_db() as db:
        db.execute("""
            INSERT INTO users (id, email, password_hash, name, role, plan, trial_clips_left, trial_minutes_left, max_screens, created_at, status)
            VALUES (?, ?, ?, ?, 'user', 'free_trial', 3, 60.0, 1, ?, 'active')
        """, (user_id, email, pw_hash, name, now))
        db.commit()

    return get_user_by_id(user_id)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = get_user_by_email(email)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    if user["status"] != "active":
        return None
    return user


def get_active_sessions(user_id: str) -> list[dict]:
    """Retorna las sesiones activas en los últimos 7 días."""
    cutoff = time.time() - (86400 * 7)
    with _get_db() as db:
        rows = db.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND last_active > ?
            ORDER BY last_active DESC
        """, (user_id, cutoff)).fetchall()
        return [dict(r) for r in rows]


def create_session(user_id: str, device_name: str = "Dispositivo", ip: str = "127.0.0.1") -> str:
    """
    Crea una nueva sesión respetando el límite de pantallas:
    - Admin: 6 pantallas
    - Pago (Pro): 4 pantallas
    - Free: 1 pantalla
    Si se supera el límite, se cierra la sesión más antigua.
    """
    user = get_user_by_id(user_id)
    max_screens = get_user_max_screens(user or {})
    active_sessions = get_active_sessions(user_id)

    with _get_db() as db:
        # Si ya alcanzó el límite de pantallas, eliminar la sesión más antigua
        if len(active_sessions) >= max_screens:
            to_remove = len(active_sessions) - max_screens + 1
            oldest = sorted(active_sessions, key=lambda s: s["last_active"])[:to_remove]
            for s in oldest:
                db.execute("DELETE FROM sessions WHERE token = ?", (s["token"],))

        token = secrets.token_urlsafe(32)
        now = time.time()
        db.execute("""
            INSERT INTO sessions (token, user_id, device_name, ip, last_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token, user_id, device_name[:50], ip[:45], now, now))
        db.commit()

    return token


def get_user_from_token(token: str) -> Optional[dict]:
    if not token:
        return None
    now = time.time()
    with _get_db() as db:
        row = db.execute("""
            SELECT u.* FROM users u
            JOIN sessions s ON u.id = s.user_id
            WHERE s.token = ? AND u.status = 'active'
        """, (token,)).fetchone()
        if row:
            db.execute("UPDATE sessions SET last_active = ? WHERE token = ?", (now, token))
            db.commit()
            return dict(row)
        return None


def delete_session(token: str):
    with _get_db() as db:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()


def get_or_create_default_admin() -> dict:
    """Retorna el usuario admin sin cobro con 6 pantallas."""
    with _get_db() as db:
        row = db.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if row:
            return dict(row)
    init_db()
    with _get_db() as db:
        row = db.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        return dict(row)


def can_user_clip(user: dict) -> tuple[bool, str]:
    """Verifica si el usuario tiene cuota para crear o procesar clips."""
    # 1. Admin y usuarios Pro: Ilimitado
    if user.get("role") == "admin":
        return True, "Acceso VIP Maestro Ilimitado (6 pantallas)"
    if user.get("plan") in ("lifetime_vip", "pro_lifetime", "pro_monthly"):
        return True, "Acceso Pro Ilimitado (4 pantallas)"

    # 2. Plan de prueba gratuita
    if user.get("plan") == "free_trial":
        clips_left = user.get("trial_clips_left", 0)
        minutes_left = user.get("trial_minutes_left", 0.0)
        if clips_left > 0 and minutes_left > 0:
            return True, f"Prueba activa ({clips_left} clips restantes · 1 pantalla)"
        return False, "Tu periodo de prueba ha finalizado. Actualiza a Pro para continuar creando clips."

    return False, "Plan no válido o expirado."


def consume_user_clip(user_id: str, minutes_spent: float = 1.0):
    """Descuenta del balance si el usuario está en prueba gratuita."""
    user = get_user_by_id(user_id)
    if not user:
        return
    if user["role"] == "admin" or user["plan"] in ("lifetime_vip", "pro_lifetime", "pro_monthly"):
        return

    with _get_db() as db:
        db.execute("""
            UPDATE users 
            SET trial_clips_left = MAX(0, trial_clips_left - 1),
                trial_minutes_left = MAX(0.0, trial_minutes_left - ?)
            WHERE id = ?
        """, (minutes_spent, user_id))
        db.commit()


def generate_license_key(plan: str = "pro_lifetime", clips: int = 999999, minutes: float = 999999.0, max_screens: int = 4) -> str:
    """Genera una clave de licencia (4 pantallas para planes de pago)."""
    suffix = secrets.token_hex(4).upper()
    mid = secrets.token_hex(4).upper()
    key = f"CLIP-{plan[:3].upper()}-{mid}-{suffix}"
    now = time.time()
    with _get_db() as db:
        db.execute("""
            INSERT INTO licenses (key, plan, clips_granted, minutes_granted, max_screens, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, plan, clips, minutes, max_screens, now))
        db.commit()
    return key


def activate_license(user_id: str, key: str) -> tuple[bool, str]:
    """Aplica una clave de licencia a un usuario desbloqueando 4 pantallas."""
    key = key.strip().upper()
    with _get_db() as db:
        row = db.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
        if not row:
            return False, "Clave de licencia no válida o inexistente"
        lic = dict(row)
        if lic["used_by"]:
            return False, "Esta clave de licencia ya fue utilizada"

        now = time.time()
        screens = lic.get("max_screens", 4)
        db.execute("UPDATE licenses SET used_by = ?, used_at = ? WHERE key = ?", (user_id, now, key))
        db.execute("""
            UPDATE users 
            SET plan = ?, 
                trial_clips_left = trial_clips_left + ?, 
                trial_minutes_left = trial_minutes_left + ?, 
                max_screens = ?,
                license_key = ? 
            WHERE id = ?
        """, (lic["plan"], lic["clips_granted"], lic["minutes_granted"], screens, key, user_id))
        db.commit()

    return True, f"¡Licencia activada con éxito! Ahora tienes plan {lic['plan']} con hasta {screens} pantallas simultáneas."
