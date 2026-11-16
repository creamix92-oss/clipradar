"""API web de ClipRadar (FastAPI) con autenticación, prueba gratuita y sistema de cobro."""
from __future__ import annotations

import io
import json
import re
import shutil
import uuid
import zipfile
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import ff
from .audio_events import HYPE, SOUND_GROUPS, yamnet_status
from .auth_billing import (
    activate_license,
    authenticate_user,
    can_user_clip,
    create_session,
    delete_session,
    generate_license_key,
    get_active_sessions,
    get_or_create_default_admin,
    get_user_by_id,
    get_user_from_token,
    get_user_max_screens,
    register_user,
)
from .config import JOBS_DIR, WEB_DIR
from .jobs import DEFAULTS, Job, Manager, clean_settings
from .speech import whisper_status

app = FastAPI(title="ClipRadar", docs_url=None, redoc_url=None)

# True solo si la petición llega directo desde esta PC o la red local (no por un túnel/proxy público).
# Solo esas peticiones pueden entrar como dueño sin iniciar sesión.
_REQ_LOCAL: ContextVar[bool] = ContextVar("clipradar_req_local", default=False)
_PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-real-ip", "forwarded")


def _is_local_client(host: Optional[str]) -> bool:
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    return host.startswith(("192.168.", "10.")) or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host) is not None


@app.middleware("http")
async def _mark_local_requests(request: Request, call_next):
    via_proxy = any(h in request.headers for h in _PROXY_HEADERS)
    local = _is_local_client(request.client.host if request.client else None) and not via_proxy
    token = _REQ_LOCAL.set(local)
    try:
        return await call_next(request)
    finally:
        _REQ_LOCAL.reset(token)
manager = Manager()


# ------------------------------------------------------------- esquemas
class NewJob(BaseModel):
    url: str
    mode: str = "auto"
    settings: dict = {}


class TitleEdit(BaseModel):
    title: str = ""
    emoji: str = ""


class ManualClip(BaseModel):
    start: float
    end: float
    title: str = ""
    emoji: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LicenseRequest(BaseModel):
    key: str


class GenerateLicenseRequest(BaseModel):
    plan: str = "pro_lifetime"
    clips: int = 999999
    minutes: float = 999999.0


# ------------------------------------------------------------- helpers de auth
def _get_current_user(
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    """Obtiene el usuario actual desde el header o cookie. Si no hay sesión, usa el admin por defecto."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif clipradar_session:
        token = clipradar_session

    if token:
        user = get_user_from_token(token)
        if user:
            return user

    # Sin sesión: solo el dueño (esta PC o su red local) entra como Admin Maestro. Desde internet hay que iniciar sesión.
    if _REQ_LOCAL.get():
        return get_or_create_default_admin()
    raise HTTPException(401, "Inicia sesión para continuar")


def _sanitize_user(user: dict) -> dict:
    u = dict(user)
    u.pop("password_hash", None)
    can_clip, reason = can_user_clip(u)
    u["can_clip"] = can_clip
    u["quota_message"] = reason
    u["max_screens"] = get_user_max_screens(u)
    try:
        active = get_active_sessions(u["id"])
        u["active_screens"] = max(1, len(active))
    except Exception:
        u["active_screens"] = 1
    return u


def _job(job_id: str, user: dict | None = None) -> Job:
    try:
        j = manager.get(job_id)
        # Si no es admin y el job pertenece a otro usuario, no permitir acceso
        if user and user.get("role") != "admin" and j.user_id and j.user_id != user.get("id"):
            raise HTTPException(403, "No tienes permiso para ver este trabajo")
        return j
    except KeyError:
        raise HTTPException(404, "Trabajo no encontrado")


# ------------------------------------------------------------- rutas de auth y cobro
@app.post("/api/auth/register")
def api_register(body: RegisterRequest, response: Response):
    try:
        user = register_user(body.email, body.password, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    token = create_session(user["id"])
    response.set_cookie("clipradar_session", token, max_age=86400 * 30, httponly=False)
    return {"ok": True, "token": token, "user": _sanitize_user(user)}


@app.post("/api/auth/login")
def api_login(body: LoginRequest, response: Response):
    user = authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(401, "Correo o contraseña incorrectos")
    token = create_session(user["id"])
    response.set_cookie("clipradar_session", token, max_age=86400 * 30, httponly=False)
    return {"ok": True, "token": token, "user": _sanitize_user(user)}


@app.post("/api/auth/logout")
def api_logout(response: Response, clipradar_session: Optional[str] = Cookie(None)):
    if clipradar_session:
        delete_session(clipradar_session)
    response.delete_cookie("clipradar_session")
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
):
    try:
        user = _get_current_user(authorization, clipradar_session)
    except HTTPException:
        return {"user": None}
    return {"user": _sanitize_user(user)}


@app.get("/api/billing/plans")
def api_billing_plans():
    return {
        "plans": [
            {
                "id": "free_trial",
                "name": "Prueba Gratuita",
                "price": "Gratis",
                "features": [
                    "3 clips completos de prueba",
                    "1 pantalla / dispositivo",
                    "Detección de risas, aplausos y picos",
                    "Subtítulos automáticos en 9:16",
                ],
            },
            {
                "id": "pro_monthly",
                "name": "Pro Mensual",
                "price_dop": "RD$ 990 / mes",
                "price_usd": "$17 USD / mes",
                "badge": "Popular",
                "features": [
                    "Clips ILIMITADOS",
                    "📺 Hasta 4 PANTALLAS simultáneas",
                    "Sin marca de agua · Full HD 1080p",
                    "Directos en vivo sin límites",
                    "Soporte prioritario",
                ],
            },
            {
                "id": "pro_lifetime",
                "name": "VIP Vitalicio (De por vida)",
                "price_dop": "RD$ 2,490 (Pago único)",
                "price_usd": "$39 USD (Pago único)",
                "badge": "Mejor Oferta",
                "features": [
                    "Acceso de por vida sin cuotas mensuales",
                    "📺 Hasta 4 PANTALLAS simultáneas",
                    "Clips ilimitados para siempre",
                    "Actualizaciones futuras incluidas",
                    "Prioridad máxima en cola",
                ],
            },
        ],
        "rd_payment_info": {
            "bancos": [
                {"banco": "Banco Popular Dominicano", "cuenta": "812-XXXXXX-X", "tipo": "Corriente / Ahorros", "titular": "ClipRadar RD"},
                {"banco": "Banreservas", "cuenta": "960-XXXXXX-X", "tipo": "Ahorros", "titular": "ClipRadar RD"},
                {"banco": "Banco BHD", "cuenta": "045-XXXXXX-X", "tipo": "Ahorros", "titular": "ClipRadar RD"},
            ],
            "whatsapp": "https://wa.me/18290000000?text=Hola,%20quiero%20activar%20mi%20licencia%20Pro%20de%20ClipRadar",
            "instrucciones": "Realiza la transferencia bancaria y envía el comprobante a nuestro WhatsApp para enviarte tu clave de activación inmediata.",
        },
    }


@app.post("/api/billing/activate")
def api_activate_license(
    body: LicenseRequest,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
):
    user = _get_current_user(authorization, clipradar_session)
    ok, msg = activate_license(user["id"], body.key)
    if not ok:
        raise HTTPException(400, msg)
    updated = get_user_by_id(user["id"])
    return {"ok": True, "message": msg, "user": _sanitize_user(updated or user)}


@app.post("/api/admin/generate-license")
def api_admin_generate_license(
    body: GenerateLicenseRequest,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
):
    user = _get_current_user(authorization, clipradar_session)
    if user.get("role") != "admin":
        raise HTTPException(403, "Solo el Administrador Maestro puede generar licencias")
    key = generate_license_key(body.plan, body.clips, body.minutes)
    return {"ok": True, "key": key, "plan": body.plan}


# ------------------------------------------------------------- rutas de estado y trabajos
@app.get("/api/status")
def status(
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    try:
        ffmpeg = ff.ffmpeg_bin()
    except RuntimeError as exc:
        ffmpeg = None
        err = str(exc)
    try:
        user = _get_current_user(authorization, clipradar_session)
    except HTTPException:
        user = None  # visitante sin sesión: la web mostrará el inicio de sesión
    return {
        "ffmpeg": bool(ffmpeg),
        "ffmpeg_error": None if ffmpeg else err,
        "yamnet": yamnet_status(),
        "whisper": whisper_status(),
        "sounds": [{"id": k, "emoji": v["emoji"], "label": v["label"]} for k, v in SOUND_GROUPS.items()],
        "hype": HYPE,
        "defaults": DEFAULTS,
        "user": _sanitize_user(user) if user else None,
    }


@app.get("/api/jobs")
def list_jobs(
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> list[dict]:
    user = _get_current_user(authorization, clipradar_session)
    jobs = sorted(manager.jobs.values(), key=lambda j: -j.created)
    if user.get("role") != "admin":
        jobs = [j for j in jobs if not j.user_id or j.user_id == user.get("id")]
    return [j.public(full=False) for j in jobs]


@app.post("/api/jobs")
def create_job(
    body: NewJob,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    can_clip, reason = can_user_clip(user)
    if not can_clip:
        raise HTTPException(402, detail=f"Prueba agotada: {reason}")

    # Límite de pantallas / procesos simultáneos (4 para Pro, 6 para Admin)
    active_jobs = [j for j in manager.jobs.values() if j.user_id == user["id"] and j.status in ("queued", "downloading", "analyzing", "rendering", "live")]
    max_screens = get_user_max_screens(user)
    if len(active_jobs) >= max_screens:
        raise HTTPException(429, detail=f"Límite de {max_screens} pantallas simultáneas alcanzado. Tienes {len(active_jobs)} clips procesándose al mismo tiempo.")

    url = body.url.strip()
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "Pega un enlace válido (https://…)")
    mode = body.mode if body.mode in ("auto", "vod", "live") else "auto"
    return manager.create(url, mode, body.settings, user_id=user["id"]).public()


@app.post("/api/upload")
def upload(
    file: UploadFile = File(...),
    settings: str = Form("{}"),
    mode: str = Form("vod"),
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    can_clip, reason = can_user_clip(user)
    if not can_clip:
        raise HTTPException(402, detail=f"Prueba agotada: {reason}")

    # Límite de pantallas / procesos simultáneos (4 para Pro, 6 para Admin)
    active_jobs = [j for j in manager.jobs.values() if j.user_id == user["id"] and j.status in ("queued", "downloading", "analyzing", "rendering", "live")]
    max_screens = get_user_max_screens(user)
    if len(active_jobs) >= max_screens:
        raise HTTPException(429, detail=f"Límite de {max_screens} pantallas simultáneas alcanzado. Tienes {len(active_jobs)} clips procesándose al mismo tiempo.")

    try:
        cfg = json.loads(settings)
    except json.JSONDecodeError:
        cfg = {}
    name = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "video.mp4").name)[-80:] or "video.mp4"
    mode = "live" if mode == "live" else "vod"
    job = Job(name, mode, clean_settings(cfg), user_id=user["id"])
    dest = job.dir / ("source" + (Path(name).suffix or ".mp4"))
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out, 1024 * 1024)
    job.local_file = str(dest)
    job.title = name
    return manager.create(name, mode, cfg, job=job, user_id=user["id"]).public()


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    return _job(job_id, user).public()


@app.post("/api/jobs/{job_id}/stop")
def stop_job(
    job_id: str,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    job = _job(job_id, user)
    job.stop()
    if job.status == "queued":
        job.say("Cancelado", "stopped")
    return job.public()


@app.delete("/api/jobs/{job_id}")
def delete_job(
    job_id: str,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    _job(job_id, user)
    manager.delete(job_id)
    return {"ok": True}


@app.patch("/api/jobs/{job_id}/clips/{clip_id}")
def edit_clip(
    job_id: str,
    clip_id: str,
    body: TitleEdit,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    try:
        return _job(job_id, user).retitle(clip_id, body.title, body.emoji)
    except KeyError:
        raise HTTPException(404, "Clip no encontrado")
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@app.delete("/api/jobs/{job_id}/clips/{clip_id}")
def delete_clip(
    job_id: str,
    clip_id: str,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    _job(job_id, user).delete_clip(clip_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/clips")
def manual_clip(
    job_id: str,
    body: ManualClip,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
) -> dict:
    user = _get_current_user(authorization, clipradar_session)
    can_clip, reason = can_user_clip(user)
    if not can_clip:
        raise HTTPException(402, detail=f"Prueba agotada: {reason}")
    try:
        return _job(job_id, user).manual_clip(body.start, body.end, body.title, body.emoji)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


def _safe_name(clip: dict) -> str:
    base = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", f"{clip.get('emoji', '')} {clip.get('title', '')}").strip()
    return (base[:80] or clip["id"]) + ".mp4"


@app.get("/api/jobs/{job_id}/zip")
def download_zip(
    job_id: str,
    authorization: Optional[str] = Header(None),
    clipradar_session: Optional[str] = Cookie(None),
):
    user = _get_current_user(authorization, clipradar_session)
    job = _job(job_id, user)
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, c in enumerate(job.clips, 1):
            path = job.dir / c["file"]
            if path.exists():
                name = f"{i:02d} {_safe_name(c)}"
                while name in used:
                    name = f"{uuid.uuid4().hex[:4]} {name}"
                used.add(name)
                z.write(path, name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="clips_{job_id}.zip"'},
    )


@app.get("/media/{job_id}/{name}")
def media(job_id: str, name: str, download: int = 0):
    job = _job(job_id)
    if not re.fullmatch(r"clip_[0-9a-f]{8}\.(mp4|jpg)", name):
        raise HTTPException(404)
    path = (JOBS_DIR / job.id / name).resolve()
    if not path.is_file() or JOBS_DIR.resolve() not in path.parents:
        raise HTTPException(404)
    if download:
        clip = next((c for c in job.clips if c["file"] == name), {"id": name, "title": name})
        return FileResponse(path, media_type="video/mp4", filename=_safe_name(clip))
    return FileResponse(path)


@app.get("/multi")
def multi():
    return FileResponse(WEB_DIR / "multi.html", headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    from .config import HOST, PORT

    uvicorn.run("app.server:app", host=HOST, port=PORT, reload=False)
