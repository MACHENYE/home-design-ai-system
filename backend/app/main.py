from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    AssetUploadResponse,
    DesignRecord,
    GenerateMode,
    GenerateRequest,
    NanoBananaCallback,
    NanoBananaTaskStatus,
    SubmitResponse,
    TaskRecord,
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
    if isinstance(data, dict) and data.get("taskId"):
        return str(data["taskId"])

    return None


def _parse_record_info(data: dict[str, object], rec: TaskRecord) -> tuple[NanoBananaTaskStatus, str | None, str | None]:
    status = rec.status
    success_flag = data.get("successFlag")
    if success_flag in {1, "1", True}:
        status = NanoBananaTaskStatus.success
    elif data.get("errorCode") or data.get("errorMsg") or data.get("errorMessage"):
        status = NanoBananaTaskStatus.failed
    else:
        status_raw = data.get("status")
        if status_raw is not None:
            try:
                status_int = int(status_raw)
                if status_int in {1, 2, 3, 4}:
                    status = NanoBananaTaskStatus(status_int)
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
    error_msg = data.get("errorMsg") or data.get("errorMessage") or rec.error_message

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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "provider": _active_provider()}


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
        "culturalElements": ["无", "桃花坞木版年画", "宋式雅韵", "岭南纹样", "青花瓷元素", "敦煌色彩"],
        "budgetLevels": ["经济型", "标准型", "品质型", "高端定制"],
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
    if settings.public_base_url.startswith("http://localhost") or settings.public_base_url.startswith("http://127.0.0.1"):
        warning = "For real NanoBanana calls, set PUBLIC_BASE_URL to a public tunnel URL so the API can fetch uploaded images."

    return AssetUploadResponse(filename=safe_name, url=public_url, local_url=local_url, warning=warning)


@app.post("/api/v1/design/submit", response_model=SubmitResponse)
async def submit(req: GenerateRequest) -> SubmitResponse:
    provider = _active_provider()
    final_prompt = build_home_design_prompt(req)

    if provider == "mock":
        task_id = make_demo_task_id()
        result_image_url = make_demo_result(req)
        store.upsert(
            task_id,
            NanoBananaTaskStatus.processing,
            raw={"provider": "mock", "request": req.model_dump(), "prompt": final_prompt},
        )
        store.save_design_request(
            task_id,
            req,
            status=NanoBananaTaskStatus.processing,
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
        payload: dict[str, object] = {
            "type": req.type.value,
            "prompt": final_prompt,
            "callBackUrl": callback_url,
        }
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
        raise HTTPException(status_code=502, detail="Unexpected NanoBanana response (missing taskId)")

    store.upsert(
        task_id,
        NanoBananaTaskStatus.created,
        raw={"provider": "nanobanana", "submit": resp, "request": req.model_dump(), "prompt": final_prompt},
    )
    store.save_design_request(
        task_id,
        req,
        status=NanoBananaTaskStatus.created,
    )
    return SubmitResponse(task_id=task_id)


@app.get("/api/v1/design/records", response_model=list[DesignRecord])
async def list_design_records(limit: int = 50, design_style: str | None = None) -> list[DesignRecord]:
    return store.list_design_records(limit=limit, design_style=design_style)


@app.get("/api/v1/design/records/{task_id}", response_model=DesignRecord)
async def get_design_record(task_id: str) -> DesignRecord:
    rec = store.get_design_record(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="design record not found")
    return rec


@app.delete("/api/v1/design/records/{task_id}")
async def delete_design_record(task_id: str) -> dict[str, bool]:
    deleted = store.delete_design_record(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="design record not found")
    return {"deleted": True}


@app.get("/api/v1/tasks", response_model=list[TaskRecord])
async def list_tasks(limit: int = 50) -> list[TaskRecord]:
    return store.list_recent(limit)


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
async def nanobanana_callback(cb: NanoBananaCallback) -> dict[str, str]:
    task_id = cb.taskId
    status_raw = int(cb.status)
    status = NanoBananaTaskStatus(status_raw) if status_raw in {1, 2, 3, 4} else NanoBananaTaskStatus.processing

    if not store.get(task_id):
        store.upsert(task_id, NanoBananaTaskStatus.processing, raw={"callback_first": cb.model_dump()})

    store.update_result(
        task_id,
        status=status,
        result_image_url=cb.resultImageUrl,
        error_message=cb.errorMsg,
        raw={"callback": cb.model_dump()},
    )
    store.update_design_result(
        task_id,
        status=status,
        result_image_url=cb.resultImageUrl,
        error_message=cb.errorMsg,
    )
    return {"ok": "true"}


app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")
if frontend_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
