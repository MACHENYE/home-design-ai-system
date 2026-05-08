from __future__ import annotations

import re
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from pathlib import Path, PurePosixPath

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .models import (
    AssetUploadResponse,
    AuthResponse,
    DesignRecord,
    FavoriteScheme,
    FavoriteSchemeCreate,
    GenerateMode,
    GenerateRequest,
    GenerateType,
    NanoBananaTaskStatus,
    SubmitResponse,
    TaskRecord,
    UserLoginRequest,
    UserProfile,
    UserRegisterRequest,
)
from .mock_provider import make_demo_result, make_demo_task_id
from .nanobanana_client import NanoBananaClient
from .prompting import build_home_design_prompt
from .settings import settings
from .tasks_store import TasksStore


def _default_callback_url() -> str:
    return settings.public_base_url.rstrip("/") + "/api/v1/nanobanana/callback"


def _active_provider() -> str:
    provider = settings.ai_provider.lower().strip()
    if provider == "auto":
        return "nanobanana" if _has_nanobanana_key() else "mock"
    if provider not in {"nanobanana", "mock"}:
        raise HTTPException(status_code=500, detail=f"Unsupported AI_PROVIDER: {settings.ai_provider}")
    return provider


def _has_nanobanana_key() -> bool:
    key = settings.nanobanana_api_key.strip()
    return bool(key and key.lower() not in {"replace_me", "your_api_key", "your_api_key_here"})


def _safe_filename(name: str) -> str:
    stem = Path(name).stem or "upload"
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")[:40] or "upload"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    return f"{stem}-{uuid.uuid4().hex[:10]}{suffix}"


def _sftp_mkdirs(sftp: object, remote_dir: str) -> None:
    current = ""
    for part in PurePosixPath(remote_dir).parts:
        if part == "/":
            current = "/"
            continue
        current = str(PurePosixPath(current) / part) if current else part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def _upload_file_to_remote(local_path: Path, filename: str) -> str:
    if not settings.remote_upload_host.strip():
        raise RuntimeError("REMOTE_UPLOAD_HOST is required when REMOTE_UPLOAD_ENABLED=true")
    if not settings.remote_upload_user.strip():
        raise RuntimeError("REMOTE_UPLOAD_USER is required when REMOTE_UPLOAD_ENABLED=true")
    if not settings.remote_upload_dir.strip():
        raise RuntimeError("REMOTE_UPLOAD_DIR is required when REMOTE_UPLOAD_ENABLED=true")
    if not settings.remote_public_base_url.strip().startswith(("http://", "https://")):
        raise RuntimeError("REMOTE_PUBLIC_BASE_URL must be an http(s) URL when REMOTE_UPLOAD_ENABLED=true")

    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("paramiko is required for remote uploads. Run: pip install -r requirements.txt") from exc

    remote_dir = str(PurePosixPath(settings.remote_upload_dir))
    remote_path = str(PurePosixPath(remote_dir) / filename)
    key_path = settings.remote_upload_key_path.strip()
    password = settings.remote_upload_password or None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.remote_upload_host.strip(),
            port=settings.remote_upload_port,
            username=settings.remote_upload_user.strip(),
            password=password,
            key_filename=str(Path(key_path).expanduser()) if key_path else None,
            timeout=settings.remote_upload_timeout_s,
            banner_timeout=settings.remote_upload_timeout_s,
            auth_timeout=settings.remote_upload_timeout_s,
        )
        sftp = client.open_sftp()
        try:
            _sftp_mkdirs(sftp, remote_dir)
            sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()
    finally:
        client.close()

    return f"{settings.remote_public_base_url.rstrip('/')}/{filename}"

def _extract_task_id(resp: object) -> str | None:
    """
    NanoBanana responses seen in the wild vary:
    - {"taskId": "..."}
    - {"code": 200, "data": {"taskId": "..."}, ...}
    """
    if not isinstance(resp, dict):
        return None

    task_id = resp.get("taskId")
    if task_id:
        return str(task_id)

    data = resp.get("data")
    if isinstance(data, dict):
        task_id = data.get("taskId") or data.get("task_id") or data.get("id")
        if task_id:
            return str(task_id)

    return None


def _nanobanana_error_detail(resp: object) -> str:
    if not isinstance(resp, dict):
        return "Unexpected NanoBanana response (not a JSON object)"

    code = resp.get("code")
    message = resp.get("msg") or resp.get("message") or resp.get("error") or resp.get("errorMessage")
    data = resp.get("data")
    if isinstance(data, dict):
        message = message or data.get("msg") or data.get("message") or data.get("error") or data.get("errorMessage")

    parts = ["Unexpected NanoBanana response (missing taskId)"]
    if code is not None:
        parts.append(f"code={code}")
    if message:
        parts.append(f"message={message}")
    return "; ".join(parts)


def _parse_record_info(data: dict[str, object], rec: TaskRecord) -> tuple[NanoBananaTaskStatus, str | None, str | None]:
    status = rec.status
    success_flag = data.get("successFlag")
    error_code = data.get("errorCode")
    error_msg = data.get("errorMsg") or data.get("errorMessage") or rec.error_message

    if success_flag in {1, "1", True}:
        status = NanoBananaTaskStatus.success
    elif success_flag in {0, "0", False, None} and not error_msg and error_code in {None, 0, "0"}:
        status = NanoBananaTaskStatus.processing
    elif success_flag in {2, "2", 3, "3"} or error_msg or error_code not in {None, 0, "0"}:
        status = NanoBananaTaskStatus.failed
    else:
        status_raw = data.get("status")
        if status_raw is not None:
            try:
                status_int = int(status_raw)
                status = {
                    0: NanoBananaTaskStatus.processing,
                    1: NanoBananaTaskStatus.success,
                    2: NanoBananaTaskStatus.failed,
                    3: NanoBananaTaskStatus.failed,
                }.get(status_int, status)
            except (TypeError, ValueError):
                pass

    response = data.get("response")
    response_data = response if isinstance(response, dict) else {}
    result_url = (
        data.get("resultImageUrl")
        or response_data.get("resultImageUrl")
        or response_data.get("originImageUrl")
        or rec.result_image_url
    )

    return status, str(result_url) if result_url else None, str(error_msg) if error_msg else None


app = FastAPI(title="Home Design AI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = TasksStore(settings.tasks_db_path)
client = NanoBananaClient(base_url=settings.nanobanana_base_url, api_key=settings.nanobanana_api_key)
uploads_path = Path(settings.uploads_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
frontend_path = Path(settings.frontend_dir)
frontend_static_path = frontend_path / "dist" if (frontend_path / "dist").exists() else frontend_path


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, expected = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    actual = _hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def current_user(authorization: str | None = Header(default=None)) -> UserProfile:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    return user


async def optional_user(authorization: str | None = Header(default=None)) -> UserProfile | None:
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    return store.get_user_by_token(token)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "provider": _active_provider()}


@app.post("/api/v1/auth/register", response_model=AuthResponse)
async def register(req: UserRegisterRequest) -> AuthResponse:
    username = req.username.strip()
    try:
        user = store.create_user(username, _hash_password(req.password))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    token = secrets.token_urlsafe(32)
    store.create_session(token, user.id)
    return AuthResponse(token=token, user=user)


@app.post("/api/v1/auth/login", response_model=AuthResponse)
async def login(req: UserLoginRequest) -> AuthResponse:
    found = store.get_user_by_username(req.username.strip())
    if not found:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user, password_hash = found
    if not _verify_password(req.password, password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_urlsafe(32)
    store.create_session(token, user.id)
    return AuthResponse(token=token, user=user)


@app.get("/api/v1/auth/me", response_model=UserProfile)
async def me(user: UserProfile = Depends(current_user)) -> UserProfile:
    return user


@app.post("/api/v1/auth/logout")
async def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    token = _extract_bearer_token(authorization)
    if token:
        store.delete_session(token)
    return {"ok": True}


@app.get("/", response_model=None)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/api/v1/design/presets")
async def design_presets() -> dict[str, list[str]]:
    return {
        "roomTypes": ["客厅", "卧室", "厨房", "餐厅", "书房", "儿童房", "玄关", "卫生间"],
        "styles": ["现代简约", "新中式", "北欧", "中古风", "奶油风", "侘寂风", "工业风", "轻奢"],
        "colors": ["暖白+原木", "黑白灰", "米色+胡桃木", "低饱和莫兰迪", "奶油色+浅咖", "深色沉稳"],
        "materials": ["原木", "微水泥", "大理石", "藤编", "金属线条", "布艺", "皮革", "玻璃"],
    }


@app.post("/api/v1/assets/upload", response_model=AssetUploadResponse)
async def upload_asset(
    request: Request,
    filename: str = Query(default="upload.png", min_length=1, max_length=160),
) -> AssetUploadResponse:
    content_type = request.headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    body = await request.body()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_upload_mb}MB")

    safe_name = _safe_filename(filename)
    target = uploads_path / safe_name
    target.write_bytes(body)

    local_url = f"/uploads/{safe_name}"
    public_url = settings.public_base_url.rstrip("/") + local_url
    warning = None

    if settings.remote_upload_enabled:
        try:
            public_url = await run_in_threadpool(_upload_file_to_remote, target, safe_name)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Remote upload failed: {exc}") from exc
    elif settings.public_base_url.startswith("http://localhost") or settings.public_base_url.startswith("http://127.0.0.1"):
        warning = "For real NanoBanana calls, set PUBLIC_BASE_URL to a public tunnel URL so the API can fetch uploaded images."

    return AssetUploadResponse(filename=safe_name, url=public_url, local_url=local_url, warning=warning)


@app.post("/api/v1/design/submit", response_model=SubmitResponse)
async def submit(req: GenerateRequest, user: UserProfile | None = Depends(optional_user)) -> SubmitResponse:
    provider = _active_provider()
    final_prompt = build_home_design_prompt(req)

    if provider == "mock":
        task_id = make_demo_task_id()
        result_image_url = make_demo_result(req)
        store.upsert(
            task_id,
            NanoBananaTaskStatus.processing,
            raw={"provider": "mock", "request": req.model_dump(), "prompt": final_prompt},
            user_id=user.id if user else None,
        )
        store.save_design_request(
            task_id,
            req,
            status=NanoBananaTaskStatus.processing,
            user_id=user.id if user else None,
        )
        store.update_result(
            task_id,
            status=NanoBananaTaskStatus.success,
            result_image_url=result_image_url,
            error_message=None,
            raw={"provider": "mock", "request": req.model_dump(), "prompt": final_prompt},
        )
        store.update_design_result(
            task_id,
            status=NanoBananaTaskStatus.success,
            result_image_url=result_image_url,
            error_message=None,
        )
        return SubmitResponse(task_id=task_id)

    if not _has_nanobanana_key():
        raise HTTPException(status_code=400, detail="NANOBANANA_API_KEY is required when AI_PROVIDER=nanobanana")

    callback_url = req.callback_url or _default_callback_url()
    if not callback_url.startswith("http"):
        raise HTTPException(status_code=400, detail="callback_url must be an http(s) URL")

    image_urls = list(req.image_urls)
    if req.mask_url:
        image_urls.append(req.mask_url)

    if req.mode == GenerateMode.basic:
        generate_type = req.type
        if generate_type == GenerateType.image_to_image and not image_urls:
            generate_type = GenerateType.text_to_image

        payload: dict[str, object] = {
            "type": generate_type.value,
            "prompt": final_prompt,
            "callBackUrl": callback_url,
            "numImages": 1,
        }
        if req.aspect_ratio:
            payload["image_size"] = req.aspect_ratio
        if req.model_name:
            payload["modelName"] = req.model_name
        if req.safe_word:
            payload["safeWord"] = req.safe_word
        if req.enable_translation is not None:
            payload["enableTranslation"] = req.enable_translation
        if req.output_format:
            payload["outputFormat"] = req.output_format
        if req.safety_filter_level:
            payload["safetyFilterLevel"] = req.safety_filter_level
        if image_urls:
            payload["imageUrls"] = image_urls

        try:
            resp = await client.generate_or_edit(payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"NanoBanana request failed: {exc}") from exc
    else:
        payload = {
            "prompt": final_prompt,
            "callBackUrl": callback_url,
        }
        if req.resolution:
            payload["resolution"] = req.resolution
        if req.aspect_ratio:
            payload["aspectRatio"] = req.aspect_ratio
        if req.enable_translation is not None:
            payload["enableTranslation"] = req.enable_translation
        if req.output_format:
            payload["outputFormat"] = req.output_format
        if image_urls:
            payload["imageUrls"] = image_urls

        try:
            resp = await client.generate_pro(payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"NanoBanana request failed: {exc}") from exc

    task_id = _extract_task_id(resp)
    if not task_id:
        raise HTTPException(status_code=502, detail=_nanobanana_error_detail(resp))

    store.upsert(
        task_id,
        NanoBananaTaskStatus.created,
        raw={"provider": "nanobanana", "submit": resp, "request": req.model_dump(), "prompt": final_prompt},
        user_id=user.id if user else None,
    )
    store.save_design_request(
        task_id,
        req,
        status=NanoBananaTaskStatus.created,
        user_id=user.id if user else None,
    )
    return SubmitResponse(task_id=task_id)


@app.get("/api/v1/design/records", response_model=list[DesignRecord])
async def list_design_records(
    limit: int = 50,
    design_style: str | None = None,
    user: UserProfile = Depends(current_user),
) -> list[DesignRecord]:
    return store.list_design_records(limit=limit, design_style=design_style, user_id=user.id)


@app.get("/api/v1/design/records/{task_id}", response_model=DesignRecord)
async def get_design_record(task_id: str, user: UserProfile = Depends(current_user)) -> DesignRecord:
    rec = store.get_design_record(task_id, user_id=user.id)
    if not rec:
        raise HTTPException(status_code=404, detail="design record not found")
    return rec


@app.delete("/api/v1/design/records/{task_id}")
async def delete_design_record(task_id: str, user: UserProfile = Depends(current_user)) -> dict[str, bool]:
    deleted = store.delete_design_record(task_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="design record not found")
    return {"deleted": True}


@app.get("/api/v1/favorites", response_model=list[FavoriteScheme])
async def list_favorites(limit: int = 50, user: UserProfile = Depends(current_user)) -> list[FavoriteScheme]:
    return store.list_favorite_schemes(user.id, limit=limit)


@app.post("/api/v1/favorites", response_model=FavoriteScheme)
async def save_favorite(scheme: FavoriteSchemeCreate, user: UserProfile = Depends(current_user)) -> FavoriteScheme:
    return store.save_favorite_scheme(user.id, scheme)


@app.delete("/api/v1/favorites/{favorite_id}")
async def delete_favorite(favorite_id: int, user: UserProfile = Depends(current_user)) -> dict[str, bool]:
    deleted = store.delete_favorite_scheme(user.id, favorite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"deleted": True}


@app.get("/api/v1/tasks", response_model=list[TaskRecord])
async def list_tasks(limit: int = 50, user: UserProfile = Depends(current_user)) -> list[TaskRecord]:
    return store.list_recent(limit, user_id=user.id)


@app.get("/api/v1/tasks/{task_id}", response_model=TaskRecord)
async def get_task(task_id: str) -> TaskRecord:
    rec = store.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="task not found")
    return rec


@app.post("/api/v1/tasks/{task_id}/refresh", response_model=TaskRecord)
async def refresh_task(task_id: str) -> TaskRecord:
    rec = store.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="task not found")

    if task_id.startswith("demo-"):
        return rec

    try:
        details = await client.get_task_details(task_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"NanoBanana refresh failed: {exc}") from exc
    data = details.get("data") if isinstance(details, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected NanoBanana record-info response")

    status, result_url, error_msg = _parse_record_info(data, rec)

    store.update_result(task_id, status=status, result_image_url=result_url, error_message=error_msg, raw={"record": details})
    store.update_design_result(task_id, status=status, result_image_url=result_url, error_message=error_msg)
    return store.get(task_id)  # type: ignore[return-value]


@app.post("/api/v1/nanobanana/callback")
async def nanobanana_callback(cb: dict[str, object]) -> dict[str, str]:
    data = cb.get("data") if isinstance(cb.get("data"), dict) else {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    task_id = cb.get("taskId") or data.get("taskId")
    if not task_id:
        raise HTTPException(status_code=400, detail="callback missing taskId")

    code = cb.get("code")
    status_raw = cb.get("status")
    if code in {200, "200"}:
        status = NanoBananaTaskStatus.success
    elif code in {400, "400", 500, "500", 501, "501"}:
        status = NanoBananaTaskStatus.failed
    else:
        try:
            status_int = int(status_raw) if status_raw is not None else 2
            status = NanoBananaTaskStatus(status_int) if status_int in {1, 2, 3, 4} else NanoBananaTaskStatus.processing
        except (TypeError, ValueError):
            status = NanoBananaTaskStatus.processing

    result_image_url = cb.get("resultImageUrl") or info.get("resultImageUrl")
    error_message = cb.get("errorMsg") or cb.get("msg")

    if not store.get(str(task_id)):
        store.upsert(str(task_id), NanoBananaTaskStatus.processing, raw={"callback_first": cb})

    store.update_result(
        str(task_id),
        status=status,
        result_image_url=str(result_image_url) if result_image_url else None,
        error_message=str(error_message) if error_message and status == NanoBananaTaskStatus.failed else None,
        raw={"callback": cb},
    )
    store.update_design_result(
        str(task_id),
        status=status,
        result_image_url=str(result_image_url) if result_image_url else None,
        error_message=str(error_message) if error_message and status == NanoBananaTaskStatus.failed else None,
    )
    return {"ok": "true"}


app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")
if frontend_static_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_static_path), html=True), name="frontend")
