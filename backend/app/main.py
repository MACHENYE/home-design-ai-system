from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
import hashlib
import hmac
import secrets
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .models import (
    AssetUploadResponse,
    AuthResponse,
    DesignFeedbackRequest,
    DesignRecord,
    FavoriteScheme,
    FavoriteSchemeCreate,
    GenerateMode,
    GenerateRequest,
    GenerateType,
    NanoBananaTaskStatus,
    PromptOptimizeRequest,
    PromptOptimizeResponse,
    StyleTemplate,
    StyleTemplateRequest,
    StyleTemplateResponse,
    SystemLog,
    SubmitResponse,
    TaskRecord,
    UserLoginRequest,
    UserProfile,
    UserRegisterRequest,
)
from .nanobanana_client import NanoBananaClient
from .prompting import build_home_design_prompt
from .settings import settings
from .tasks_store import TasksStore


def _default_callback_url() -> str:  # 根据公网基础地址拼接 NanoBanana 异步回调地址
    return settings.public_base_url.rstrip("/") + "/api/v1/nanobanana/callback"


def _has_nanobanana_key() -> bool:  # 检查 NanoBanana API Key 是否已经配置为可用值
    key = settings.nanobanana_api_key.strip()
    return bool(key and key.lower() not in {"replace_me", "your_api_key", "your_api_key_here"})


def _safe_filename(name: str) -> str:  # 清洗用户上传文件名并追加随机后缀，避免路径注入和重名
    stem = Path(name).stem or "upload"
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")[:40] or "upload"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    return f"{stem}-{uuid.uuid4().hex[:10]}{suffix}"


def _sftp_mkdirs(sftp: object, remote_dir: str) -> None:  # 在远程 SFTP 服务器上递归创建上传目录
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


def _upload_file_to_remote(local_path: Path, filename: str) -> str:  # 通过 SFTP 将本地上传文件同步到公网服务器并返回访问 URL
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

def _extract_task_id(resp: object) -> str | None:  # 兼容不同响应格式，从模型服务返回值中提取远程任务编号
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


def _nanobanana_error_detail(resp: object) -> str:  # 把 NanoBanana 异常响应整理成便于排查的错误描述
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


def _parse_record_info(data: dict[str, object], rec: TaskRecord) -> tuple[NanoBananaTaskStatus, str | None, str | None]:  # 把远程任务详情转换为本地任务状态、结果图和错误信息
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


STYLE_TEMPLATE_BANK = [
    {
        "name": "现代奶油客厅",
        "room": "客厅",
        "style": "奶油风",
        "color": "奶油色+浅咖",
        "material": "布艺",
        "prompt": "保留客厅结构，提升空间通透感，加入柔和奶油色墙面、圆角家具和温暖灯带，整体干净舒适。",
        "desc": "柔和、明亮、适合年轻家庭",
    },
    {
        "name": "新中式会客区",
        "room": "客厅",
        "style": "新中式",
        "color": "米色+胡桃木",
        "material": "原木",
        "prompt": "保留空间边界，生成克制雅致的新中式会客区，强调木质格栅、留白与东方秩序感。",
        "desc": "稳重、雅致、结构清晰",
    },
    {
        "name": "北欧卧室",
        "room": "卧室",
        "style": "北欧",
        "color": "暖白+原木",
        "material": "原木",
        "prompt": "保留卧室结构，呈现自然松弛的北欧卧室，光线柔和，床品简洁，适度加入收纳。",
        "desc": "轻盈、自然、居住感强",
    },
    {
        "name": "侘寂书房",
        "room": "书房",
        "style": "侘寂风",
        "color": "深色沉稳",
        "material": "微水泥",
        "prompt": "保留书房结构，生成克制安静的侘寂空间，突出材质肌理、灰调光影和低干扰工作氛围。",
        "desc": "安静、克制、材质感强",
    },
    {
        "name": "中古风客厅",
        "room": "客厅",
        "style": "中古风",
        "color": "米色+胡桃木",
        "material": "皮革",
        "prompt": "保持原有采光和主要家具尺度，加入胡桃木、皮革单椅和复古灯具，营造温润中古氛围。",
        "desc": "复古、温润、层次丰富",
    },
    {
        "name": "原木餐厨区",
        "room": "餐厅",
        "style": "现代简约",
        "color": "暖白+原木",
        "material": "原木",
        "prompt": "保留餐厨动线，增加原木餐桌、简洁收纳柜和柔和吊灯，让空间更通透自然。",
        "desc": "温暖、实用、餐厨一体",
    },
    {
        "name": "轻奢主卧",
        "room": "卧室",
        "style": "轻奢",
        "color": "黑白灰",
        "material": "金属线条",
        "prompt": "保留门窗位置，使用低饱和灰调、金属细节和简洁床头背景，形成克制高级的主卧氛围。",
        "desc": "精致、克制、质感突出",
    },
    {
        "name": "清爽儿童房",
        "room": "儿童房",
        "style": "现代简约",
        "color": "低饱和莫兰迪",
        "material": "布艺",
        "prompt": "保留房间结构，增加安全圆角家具、低饱和配色和充足收纳，形成明亮柔和的儿童房。",
        "desc": "安全、清爽、收纳友好",
    },
    {
        "name": "工业风书房",
        "room": "书房",
        "style": "工业风",
        "color": "黑白灰",
        "material": "金属线条",
        "prompt": "保留书房结构，使用深灰墙面、金属书架和线性灯光，营造克制高效的工作空间。",
        "desc": "利落、硬朗、适合工作",
    },
    {
        "name": "奶油风卧室",
        "room": "卧室",
        "style": "奶油风",
        "color": "奶油色+浅咖",
        "material": "布艺",
        "prompt": "保留卧室门窗与床位关系，加入奶油色墙面、柔软布艺床品和暖光灯，营造放松睡眠氛围。",
        "desc": "柔软、温暖、睡眠友好",
    },
    {
        "name": "北欧玄关",
        "room": "玄关",
        "style": "北欧",
        "color": "暖白+原木",
        "material": "藤编",
        "prompt": "保留玄关通行动线，加入原木鞋柜、藤编细节和柔和灯光，提升入户收纳与清爽感。",
        "desc": "清爽、自然、收纳明确",
    },
    {
        "name": "微水泥厨房",
        "room": "厨房",
        "style": "现代简约",
        "color": "低饱和莫兰迪",
        "material": "微水泥",
        "prompt": "保留厨房操作动线，使用微水泥质感、无把手柜门和柔和灰调，让厨房整洁高级。",
        "desc": "整洁、耐看、材质统一",
    },
]


def _default_style_templates_response(summary: str | None = None) -> StyleTemplateResponse:  # 在大模型不可用时返回一组默认风格推荐模板
    return StyleTemplateResponse(
        templates=[
            StyleTemplate(
                **item,
                reason=f"该模板适合作为「{item['style']}」方向的初始参考。",
            )
            for item in STYLE_TEMPLATE_BANK[:4]
        ],
        summary=summary or "请上传底稿后点击智能推荐，由多模态大模型生成图片相关模板。",
        source="default",
    )


def _bailian_api_key() -> str:  # 读取百炼或 DashScope 大模型接口密钥
    return settings.bailian_api_key.strip() or settings.dashscope_api_key.strip()


def _bailian_error_summary(status_code: int | None = None, body: str | None = None) -> str:  # 解析百炼接口错误响应并生成简洁失败原因
    message = ""
    if body:
        try:
            data = json.loads(body)
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                message = str(error.get("message") or error.get("code") or "")
        except json.JSONDecodeError:
            message = body[:160]

    if status_code == 401:
        return "百炼 API Key 无效或未生效，请检查 backend/.env 后重启后端。"
    if status_code == 403:
        return "当前百炼 API Key 没有访问该模型的权限，请检查账号权限或模型配置。"
    if status_code == 429:
        return "百炼额度不足或请求过于频繁，智能推荐暂不可用。"
    if status_code:
        return f"百炼接口返回 {status_code}，智能推荐暂不可用。{message}".strip()
    return f"百炼请求失败，智能推荐暂不可用。{message}".strip()


def _extract_response_text(payload: dict[str, object]) -> str:  # 从百炼普通响应结构中提取模型生成文本
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
    return "\n".join(texts).strip()


def _extract_chat_completion_text(payload: dict[str, object]) -> str:  # 从兼容 Chat Completions 的响应结构中提取文本
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


async def _bailian_text_completion(
    system_text: str,
    user_text: str,
    *,
    model: str | None = None,
    temperature: float = 0.45,
    max_tokens: int = 900,
) -> str:  # 调用百炼文本模型完成提示词优化或视觉推荐文本生成
    api_key = _bailian_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="请在 backend/.env 中配置 BAILIAN_API_KEY 或 DASHSCOPE_API_KEY")
    payload = {
        "model": model or settings.bailian_text_model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    endpoint = settings.bailian_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.bailian_timeout_s) as bailian_client:
            response = await bailian_client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=_bailian_error_summary(exc.response.status_code, exc.response.text)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=_bailian_error_summary(body=str(exc))) from exc

    text = _extract_chat_completion_text(data)
    if not text:
        raise HTTPException(status_code=502, detail="百炼未返回可用内容")
    return text


def _json_object_from_text(text: str) -> dict[str, object] | None:  # 从模型输出文本中截取并解析 JSON 对象
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    candidates = [cleaned]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL))
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(cleaned[first_brace : last_brace + 1])

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                start = candidate.find("{")
                if start < 0:
                    continue
                data, _ = decoder.raw_decode(candidate[start:])
            except json.JSONDecodeError:
                continue
        if isinstance(data, str):
            nested = _json_object_from_text(data)
            if nested:
                return nested
        if isinstance(data, dict):
            return data
    return None


def _image_url_to_local_path(image_url: str) -> Path | None:  # 将本系统上传图片 URL 反解为服务器本地文件路径
    parsed = urlparse(image_url)
    path = parsed.path or image_url
    if "/uploads/" not in path:
        return None
    filename = PurePosixPath(path).name
    if not filename:
        return None
    candidate = uploads_path / filename
    try:
        candidate.resolve().relative_to(uploads_path.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


async def _image_url_as_model_input(image_url: str) -> str:  # 把图片 URL 转换为大模型可访问的公网地址或 base64 数据
    image_url = image_url.strip()
    if not image_url:
        raise ValueError("empty image url")
    if image_url.startswith("data:image/"):
        return image_url

    local_path = _image_url_to_local_path(image_url)
    if local_path:
        data = await run_in_threadpool(local_path.read_bytes)
        mime_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    if image_url.startswith(("http://", "https://")):
        return image_url
    if image_url.startswith("/uploads/"):
        raise ValueError("local upload is not publicly reachable")
    raise ValueError("unsupported image url")


def _coerce_vision_templates(data: dict[str, object], seed: int) -> list[StyleTemplate]:  # 校验并清洗视觉模型返回的推荐模板列表
    raw_templates = data.get("templates")
    if not isinstance(raw_templates, list):
        return []

    templates: list[StyleTemplate] = []
    for index, item in enumerate(raw_templates):
        if not isinstance(item, dict):
            continue
        fallback = STYLE_TEMPLATE_BANK[(seed + index) % len(STYLE_TEMPLATE_BANK)]
        payload = {
            "name": str(item.get("name") or fallback["name"])[:40],
            "room": str(item.get("room") or fallback["room"])[:20],
            "style": str(item.get("style") or fallback["style"])[:30],
            "color": str(item.get("color") or fallback["color"])[:40],
            "material": str(item.get("material") or fallback["material"])[:30],
            "prompt": str(item.get("prompt") or fallback["prompt"])[:140],
            "desc": str(item.get("desc") or fallback["desc"])[:24],
            "reason": str(item.get("reason") or fallback.get("reason") or "")[:80],
        }
        if not payload["reason"]:
            payload["reason"] = f"识别到图片中的空间与材质特征，因此推荐「{payload['style']}」方向。"
        try:
            templates.append(StyleTemplate(**payload))
        except ValueError:
            continue
        if len(templates) == 4:
            break
    return templates


async def _vision_style_templates(req: StyleTemplateRequest) -> StyleTemplateResponse | None:  # 调用视觉大模型识别图片并生成家装风格推荐模板
    if not settings.vision_recommendation_enabled:
        return None
    api_key = _bailian_api_key()
    if not api_key:
        return _default_style_templates_response("请在 backend/.env 中配置 BAILIAN_API_KEY 或 DASHSCOPE_API_KEY。")

    image_urls = [url for url in req.image_urls if isinstance(url, str) and url.strip()]
    if not image_urls:
        return None

    content_parts: list[dict[str, object]] = []
    for index, image_url in enumerate(image_urls[:2]):
        try:
            model_image_url = await _image_url_as_model_input(image_url)
        except (OSError, ValueError):
            continue
        label = "设计底稿" if index == 0 else "补充图片"
        content_parts.append({"type": "text", "text": f"{label}：请重点识别这张图的空间类型、家具、材质、采光和可保留结构。"})
        content_parts.append({"type": "image_url", "image_url": {"url": model_image_url}})
    if not content_parts:
        return None

    system_text = (
        "你是家装智能设计系统中的风格推荐算法模块。"
        "你必须以上传图片的真实内容为第一依据生成4个中文提示词模板。"
        "如果图片内容和用户下拉选项冲突，以图片内容为准；用户选项只作为轻量参考。"
        "4个模板必须是互相不同的备选方向，不能只围绕同一种材质或同一种风格变化措辞。"
        "输出必须是严格JSON对象，不能包含Markdown、解释、前言、后记。"
    )
    template_style = (
        "既有模板风格示例："
        "name=现代奶油客厅，room=客厅，style=奶油风，color=奶油色+浅咖，material=布艺，"
        "prompt=保留客厅结构，提升空间通透感，加入柔和奶油色墙面、圆角家具和温暖灯带，整体干净舒适。"
        "desc=柔和、明亮、适合年轻家庭。"
        "请模仿这种短句风格：名称简短，描述克制，prompt控制在45到90个中文字符。"
    )
    user_text = (
        "只返回JSON对象，第一字符必须是{，最后一个字符必须是}。格式为："
        '{"templates":[{"name":"","room":"","style":"","color":"","material":"","prompt":"","desc":"","reason":""}],'
        '"summary":""}。templates必须正好4个。'
        "字段要求：name为6到10个汉字；room必须是客厅、卧室、厨房、餐厅、书房、儿童房、玄关、卫生间之一；"
        "style必须是现代简约、新中式、北欧、中古风、奶油风、侘寂风、工业风、轻奢之一；"
        "color必须是暖白+原木、黑白灰、米色+胡桃木、低饱和莫兰迪、奶油色+浅咖、深色沉稳之一；"
        "material必须是原木、微水泥、大理石、藤编、金属线条、布艺、皮革、玻璃之一；"
        "多样性要求：4个templates中至少包含3种不同style、3种不同color、3种不同material；"
        "用户当前选择的材质最多只能出现在1个template里，不能四个都使用同一材质；"
        "每个template都应该从图片中提取不同的可改造重点，例如采光、背景墙、沙发、收纳、灯光、餐厨或软装；"
        "desc为3个短标签，用顿号分隔，总长度不超过16个汉字，例如：柔和、明亮、适合年轻家庭；"
        "reason为推荐解释，必须说明从图片中识别到的1到2个依据以及为什么推荐该风格，控制在28到50个中文字符；"
        "reason示例：识别到大面积落地窗和浅色地面，因此推荐现代简约和北欧方向；"
        "prompt必须符合既有模板语气，并且每个prompt都要包含至少1个从图片中识别到的具体元素；"
        "prompt必须强调保留门窗位置、主要空间边界和合理家具比例。"
        f"{template_style}"
        f"当前用户已选条件仅供参考，不是硬性限制：空间={req.room_type or '未指定'}，风格={req.design_style or '未指定'}，"
        f"配色={req.color_preference or '未指定'}，材质={req.material_preference or '未指定'}，"
        f"需求={req.prompt or '未填写'}。"
    )
    payload = {
        "model": settings.bailian_vision_model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": [{"type": "text", "text": user_text}, *content_parts]},
        ],
        "temperature": 0.75,
        "max_tokens": 1600,
        "response_format": {"type": "json_object"},
    }

    endpoint = settings.bailian_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.bailian_timeout_s) as bailian_client:
            response = await bailian_client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return _default_style_templates_response(
            _bailian_error_summary(exc.response.status_code, exc.response.text)
        )
    except httpx.HTTPError as exc:
        return _default_style_templates_response(_bailian_error_summary(body=str(exc)))
    except ValueError:
        return _default_style_templates_response("百炼返回内容不是有效 JSON，智能推荐暂不可用。")

    parsed = _json_object_from_text(_extract_chat_completion_text(data))
    if not parsed:
        return _default_style_templates_response("百炼返回格式无法解析，智能推荐暂不可用。")

    templates = _coerce_vision_templates(parsed, abs(int(req.refresh_seed or 0)))
    if len(templates) < 4:
        return _default_style_templates_response("百炼未返回完整4个模板，智能推荐暂不可用。")

    summary = parsed.get("summary")
    return StyleTemplateResponse(
        templates=templates,
        summary=str(summary)[:160] if summary else "已根据上传图片生成4个千问视觉推荐模板。",
        source="vision",
    )


app = FastAPI(title="Home Design AI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = TasksStore(settings.database_url)
client = NanoBananaClient(base_url=settings.nanobanana_base_url, api_key=settings.nanobanana_api_key)
uploads_path = Path(settings.uploads_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
frontend_path = Path(settings.frontend_dir)
frontend_static_path = frontend_path / "dist" if (frontend_path / "dist").exists() else frontend_path


def _redis_client():  # 按配置创建 Redis 客户端，失败时返回空以便降级运行
    if not settings.redis_url.strip():
        return None
    try:
        import redis
    except ImportError:
        return None
    try:
        return redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1.0)
    except Exception:
        return None


redis_client = _redis_client()
GENERATION_QUEUE_KEY = "home_design:generation_queue"


def _cache_get_json(key: str) -> object | None:  # 从 Redis 读取 JSON 缓存并反序列化为 Python 对象
    if not redis_client:
        return None
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _cache_set_json(key: str, value: object, ttl: int) -> None:  # 将可序列化对象写入 Redis 缓存并设置过期时间
    if not redis_client:
        return
    try:
        redis_client.setex(key, max(1, ttl), json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        pass


def _cache_delete_prefix(prefix: str) -> None:  # 删除指定前缀的 Redis 缓存键，用于数据变更后失效缓存
    if not redis_client:
        return
    try:
        for key in redis_client.scan_iter(f"{prefix}*"):
            redis_client.delete(key)
    except Exception:
        pass


def _cache_key(prefix: str, payload: object) -> str:  # 根据业务前缀和请求参数生成稳定的 Redis 缓存键
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _invalidate_data_cache() -> None:  # 清理管理员统计和列表查询相关缓存
    _cache_delete_prefix("admin_dashboard:")
    _cache_delete_prefix("recommendations:")


def _client_ip(request: Request | None) -> str | None:  # 从请求头或连接信息中提取客户端 IP 地址
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _log_event(
    action: str,
    *,
    level: str = "info",
    user: UserProfile | None = None,
    username: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    message: str | None = None,
    duration_ms: int | None = None,
    request: Request | None = None,
) -> None:  # 写入接口操作、异常和耗时等系统日志
    try:
        store.add_system_log(
            action=action,
            level=level,
            user_id=user.id if user else None,
            username=user.username if user else username,
            target_type=target_type,
            target_id=target_id,
            message=message,
            duration_ms=duration_ms,
            request_path=str(request.url.path) if request else None,
            ip_address=_client_ip(request),
        )
    except Exception:
        pass


def _queue_generation_task(task_id: str) -> bool:  # 把待生成任务写入 Redis 队列或内存队列
    if not redis_client or not settings.generation_queue_enabled:
        return False
    try:
        redis_client.rpush(GENERATION_QUEUE_KEY, task_id)
        return True
    except Exception:
        return False


def _pop_generation_task() -> str | None:  # 从 Redis 队列或内存队列取出一个待处理任务
    if not redis_client:
        return None
    try:
        item = redis_client.blpop(GENERATION_QUEUE_KEY, timeout=max(1, settings.generation_queue_poll_timeout_s))
    except Exception:
        return None
    if not item:
        return None
    _, task_id = item
    return str(task_id)


def _hash_password(password: str, salt: str | None = None) -> str:  # 对用户密码加盐后进行 SHA256 哈希保存
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:  # 校验用户输入密码与数据库中的哈希值是否一致
    try:
        algorithm, salt, expected = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    actual = _hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


@app.middleware("http")
async def system_log_middleware(request: Request, call_next):  # 在每个请求前后记录耗时，并在异常时写入错误日志
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _log_event(
            "api_exception",
            level="error",
            message=f"{exc.__class__.__name__}: {exc}",
            duration_ms=duration_ms,
            request=request,
        )
        raise
    if response.status_code >= 500:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _log_event(
            "api_error_response",
            level="error",
            message=f"HTTP {response.status_code}",
            duration_ms=duration_ms,
            request=request,
        )
    return response


def _extract_bearer_token(authorization: str | None) -> str | None:  # 从 Authorization 请求头中提取 Bearer Token
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def current_user(authorization: str | None = Header(default=None)) -> UserProfile:  # 根据请求令牌查询当前登录用户，未登录则返回 401
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    return user


async def require_admin(user: UserProfile = Depends(current_user)) -> UserProfile:  # 校验当前用户是否为管理员，不是管理员则拒绝访问
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="只有 admin 用户可以访问管理后台")
    return user


async def optional_user(authorization: str | None = Header(default=None)) -> UserProfile | None:  # 尝试解析当前用户，允许未登录用户继续访问部分接口
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    return store.get_user_by_token(token)


@app.get("/healthz")
async def healthz() -> dict[str, str]:  # 返回后端健康状态和当前模型服务商信息
    return {"status": "ok", "provider": "nanobanana"}


@app.post("/api/v1/auth/register", response_model=AuthResponse)
async def register(req: UserRegisterRequest, request: Request) -> AuthResponse:  # 创建新用户账号并返回登录令牌
    username = req.username.strip()
    if store.username_exists(username):
        _log_event("auth_register_failed", level="warning", username=username, message="duplicate username", request=request)
        raise HTTPException(status_code=409, detail="用户名已存在")
    try:
        user = store.create_user(username, _hash_password(req.password))
    except ValueError as exc:
        _log_event("auth_register_failed", level="warning", username=username, message="duplicate username", request=request)
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    _invalidate_data_cache()
    token = secrets.token_urlsafe(32)
    store.create_session(token, user.id)
    _log_event("auth_register", user=user, message="user registered", request=request)
    return AuthResponse(token=token, user=user)


@app.post("/api/v1/auth/login", response_model=AuthResponse)
async def login(req: UserLoginRequest, request: Request) -> AuthResponse:  # 校验用户账号密码并创建登录会话
    found = store.get_user_by_username(req.username.strip())
    if not found:
        _log_event("auth_login_failed", level="warning", username=req.username.strip(), message="username not found", request=request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user, password_hash = found
    if not _verify_password(req.password, password_hash):
        _log_event("auth_login_failed", level="warning", user=user, message="invalid password", request=request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_urlsafe(32)
    store.create_session(token, user.id)
    _log_event("auth_login", user=user, message="user logged in", request=request)
    return AuthResponse(token=token, user=user)


@app.get("/api/v1/auth/me", response_model=UserProfile)
async def me(user: UserProfile = Depends(current_user)) -> UserProfile:  # 返回当前登录用户的资料信息
    return user


@app.post("/api/v1/auth/logout")
async def logout(request: Request, authorization: str | None = Header(default=None)) -> dict[str, bool]:  # 删除当前登录令牌对应的会话记录
    token = _extract_bearer_token(authorization)
    user = store.get_user_by_token(token) if token else None
    if token:
        store.delete_session(token)
    _log_event("auth_logout", user=user, message="user logged out", request=request)
    return {"ok": True}


@app.get("/", response_model=None)
async def index() -> RedirectResponse:  # 访问根路径时跳转到前端应用页面
    return RedirectResponse(url="/app/")


@app.get("/api/v1/design/presets")
async def design_presets() -> dict[str, list[str]]:  # 返回空间、风格、色彩和材质等前端下拉预设
    return {
        "roomTypes": ["客厅", "卧室", "厨房", "餐厅", "书房", "儿童房", "玄关", "卫生间"],
        "styles": ["现代简约", "新中式", "北欧", "中古风", "奶油风", "侘寂风", "工业风", "轻奢"],
        "colors": ["暖白+原木", "黑白灰", "米色+胡桃木", "低饱和莫兰迪", "奶油色+浅咖", "深色沉稳"],
        "materials": ["原木", "微水泥", "大理石", "藤编", "金属线条", "布艺", "皮革", "玻璃"],
    }


@app.get("/api/v1/admin/dashboard")
async def admin_dashboard(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    start_at: int | None = Query(default=None),
    end_at: int | None = Query(default=None),
    username: str | None = Query(default=None),
    room_type: str | None = Query(default=None),
    design_style: str | None = Query(default=None),
    color_preference: str | None = Query(default=None),
    status: int | None = Query(default=None),
    _user: UserProfile = Depends(require_admin),
) -> dict[str, object]:  # 查询管理员后台所需的统计概览、用户列表和生成记录
    key = _cache_key(
        "admin_dashboard",
        {
            "limit": limit,
            "offset": offset,
            "start_at": start_at,
            "end_at": end_at,
            "username": username,
            "room_type": room_type,
            "design_style": design_style,
            "color_preference": color_preference,
            "status": status,
        },
    )
    cached = _cache_get_json(key)
    if isinstance(cached, dict):
        return cached
    data = store.admin_dashboard(
        limit=limit,
        offset=offset,
        start_at=start_at,
        end_at=end_at,
        username=username,
        room_type=room_type,
        design_style=design_style,
        color_preference=color_preference,
        status=status,
    )
    _cache_set_json(key, data, settings.cache_ttl_s)
    return data


@app.get("/api/v1/admin/logs", response_model=list[SystemLog])
async def admin_system_logs(
    limit: int = Query(default=100, ge=1, le=300),
    level: str | None = Query(default=None),
    action: str | None = Query(default=None),
    username: str | None = Query(default=None),
    start_at: int | None = Query(default=None),
    end_at: int | None = Query(default=None),
    _user: UserProfile = Depends(require_admin),
) -> list[SystemLog]:  # 分页返回管理员可查看的系统日志列表
    return store.list_system_logs(
        limit=limit,
        level=level,
        action=action,
        username=username,
        start_at=start_at,
        end_at=end_at,
    )


@app.post("/api/v1/prompts/optimize", response_model=PromptOptimizeResponse)
async def optimize_prompt(req: PromptOptimizeRequest, request: Request, user: UserProfile = Depends(current_user)) -> PromptOptimizeResponse:  # 调用文本模型把用户需求优化成更适合图像生成的提示词
    started = time.perf_counter()
    system_text = (
        "你是家装设计图生成系统的提示词优化助手。"
        "请将用户的原始需求改写为适合图生图家装渲染模型使用的中文提示词，输出必须稳定、具体、可执行。"
        "只返回优化后的提示词，不要返回标题、解释、Markdown。"
    )
    user_text = (
        f"原始提示词：{req.prompt}\n"
        f"空间：{req.room_type or '未指定'}\n"
        f"风格：{req.design_style or '未指定'}\n"
        f"配色：{req.color_preference or '未指定'}\n"
        f"材质：{req.material_preference or '未指定'}\n"
        f"比例：{req.aspect_ratio or '未指定'}\n"
        "优化要求：\n"
        "1. 保留用户原意，不改变指定空间、风格、配色和材质。\n"
        "2. 补充空间结构、光线氛围、家具比例、收纳设计、材质肌理和真实渲染质感。\n"
        "3. 强调保留门窗位置、主要空间边界、承重结构和合理家具比例。\n"
        "4. 避免生成不合理家具、夸张装饰、杂乱布局、低清晰度画面。\n"
        "5. 控制在120到220个中文字符，使用一段完整中文描述。"
    )
    optimized = await _bailian_text_completion(
        system_text,
        user_text,
        model=settings.bailian_text_model,
        temperature=0.35,
        max_tokens=500,
    )
    optimized = optimized.strip().strip("`").strip()
    _log_event("prompt_optimize", user=user, message="prompt optimized", duration_ms=int((time.perf_counter() - started) * 1000), request=request)
    return PromptOptimizeResponse(prompt=optimized[:500], summary="已根据当前空间、风格和比例优化提示词。")


@app.post("/api/v1/assets/upload", response_model=AssetUploadResponse)
async def upload_asset(
    request: Request,
    filename: str = Query(default="upload.png", min_length=1, max_length=160),
) -> AssetUploadResponse:  # 接收前端上传图片，保存本地或远程后返回访问地址
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

    _log_event("asset_upload", target_type="asset", target_id=safe_name, message=f"{len(body)} bytes", request=request)
    return AssetUploadResponse(filename=safe_name, url=public_url, local_url=local_url, warning=warning)


@app.post("/api/v1/design/submit", response_model=SubmitResponse)
async def submit(req: GenerateRequest, request: Request, user: UserProfile | None = Depends(optional_user)) -> SubmitResponse:  # 创建设计生成任务，保存请求参数并进入异步生成流程
    started = time.perf_counter()
    final_prompt = build_home_design_prompt(req)

    if not _has_nanobanana_key():
        raise HTTPException(status_code=400, detail="NANOBANANA_API_KEY is required")

    callback_url = req.callback_url or _default_callback_url()
    if not callback_url.startswith("http"):
        raise HTTPException(status_code=400, detail="callback_url must be an http(s) URL")

    task_id = f"local-{uuid.uuid4().hex}"
    raw = {
        "provider": "nanobanana",
        "queue": {"status": "queued"},
        "request": req.model_dump(),
        "prompt": final_prompt,
        "callback_url": callback_url,
    }
    store.upsert(
        task_id,
        NanoBananaTaskStatus.created,
        raw=raw,
        user_id=user.id if user else None,
    )
    store.save_design_request(
        task_id,
        req,
        status=NanoBananaTaskStatus.created,
        user_id=user.id if user else None,
    )
    queued = _queue_generation_task(task_id)
    if not queued:
        asyncio.create_task(_process_queued_generation(task_id))
    _invalidate_data_cache()
    _log_event(
        "design_submit_queued",
        user=user,
        target_type="task",
        target_id=task_id,
        message=f"provider=nanobanana, queued={queued}",
        duration_ms=int((time.perf_counter() - started) * 1000),
        request=request,
    )
    return SubmitResponse(task_id=task_id)


async def _process_queued_generation(task_id: str) -> None:  # 从数据库读取任务参数并执行一次实际图像生成
    started = time.perf_counter()
    rec = store.get(task_id)
    if not rec or rec.status in {NanoBananaTaskStatus.success, NanoBananaTaskStatus.failed}:
        return
    raw = rec.raw or {}
    if raw.get("remote_task_id"):
        return
    request_data = raw.get("request") if isinstance(raw.get("request"), dict) else {}
    try:
        req = GenerateRequest(**request_data)
    except Exception as exc:
        _mark_queued_generation_failed(task_id, f"Queued request is invalid: {exc}", raw)
        return
    final_prompt = str(raw.get("prompt") or build_home_design_prompt(req))

    store.update_result(
        task_id,
        status=NanoBananaTaskStatus.processing,
        result_image_url=None,
        error_message=None,
        raw={**raw, "queue": {"status": "processing"}},
    )
    store.update_design_result(
        task_id,
        status=NanoBananaTaskStatus.processing,
        result_image_url=None,
        error_message=None,
    )
    _invalidate_data_cache()

    try:
        remote_task_id, submit_resp = await _submit_nanobanana_generation(
            req,
            final_prompt,
            str(raw.get("callback_url") or _default_callback_url()),
        )
    except Exception as exc:
        _mark_queued_generation_failed(task_id, f"NanoBanana request failed: {exc}", raw)
        return

    store.attach_remote_task(
        task_id,
        remote_task_id,
        raw={
            **raw,
            "queue": {"status": "submitted"},
            "remote_task_id": remote_task_id,
            "submit": submit_resp,
        },
    )
    _invalidate_data_cache()
    _log_event(
        "design_remote_submitted",
        target_type="task",
        target_id=task_id,
        message=f"remote_task_id={remote_task_id}",
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _mark_queued_generation_failed(task_id: str, message: str, raw: dict[str, object]) -> None:  # 在队列任务失败时统一更新任务和设计记录状态
    store.update_result(
        task_id,
        status=NanoBananaTaskStatus.failed,
        result_image_url=None,
        error_message=message,
        raw={**raw, "queue": {"status": "failed", "error": message}},
    )
    store.update_design_result(
        task_id,
        status=NanoBananaTaskStatus.failed,
        result_image_url=None,
        error_message=message,
    )
    _invalidate_data_cache()
    _log_event("design_generate_failed", level="error", target_type="task", target_id=task_id, message=message)


async def _submit_nanobanana_generation(
    req: GenerateRequest,
    final_prompt: str,
    callback_url: str,
) -> tuple[str, dict[str, object]]:  # 按任务模式组装参数并提交给 NanoBanana 生成接口
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

        resp = await client.generate_or_edit(payload)
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

        resp = await client.generate_pro(payload)

    task_id = _extract_task_id(resp)
    if not task_id:
        raise RuntimeError(_nanobanana_error_detail(resp))
    return task_id, resp


async def _generation_queue_worker() -> None:  # 后台循环消费生成任务队列，保证任务异步处理
    while True:
        task_id = await run_in_threadpool(_pop_generation_task)
        if not task_id:
            continue
        try:
            await _process_queued_generation(task_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


@app.on_event("startup")
async def start_generation_queue_worker() -> None:  # 应用启动时创建后台任务队列 worker
    if redis_client and settings.generation_queue_enabled:
        app.state.generation_queue_worker = asyncio.create_task(_generation_queue_worker())


@app.on_event("shutdown")
async def stop_generation_queue_worker() -> None:  # 应用关闭时停止后台任务队列 worker
    worker = getattr(app.state, "generation_queue_worker", None)
    if worker:
        worker.cancel()


@app.get("/api/v1/design/records", response_model=list[DesignRecord])
async def list_design_records(
    response: Response,
    limit: int = 50,
    offset: int = 0,
    design_style: str | None = None,
    user: UserProfile = Depends(current_user),
) -> list[DesignRecord]:  # 按当前用户和筛选条件返回设计记录列表
    response.headers["X-Total-Count"] = str(store.count_design_records(design_style=design_style, user_id=user.id))
    return store.list_design_records(limit=limit, offset=offset, design_style=design_style, user_id=user.id)


@app.get("/api/v1/design/records/{task_id}", response_model=DesignRecord)
async def get_design_record(task_id: str, user: UserProfile = Depends(current_user)) -> DesignRecord:  # 查询当前用户可访问的单条设计记录详情
    rec = store.get_design_record(task_id, user_id=user.id)
    if not rec:
        raise HTTPException(status_code=404, detail="design record not found")
    return rec


@app.post("/api/v1/design/records/{task_id}/feedback", response_model=DesignRecord)
async def save_design_feedback(
    task_id: str,
    feedback: DesignFeedbackRequest,
    user: UserProfile = Depends(current_user),
) -> DesignRecord:  # 保存用户对生成方案的多维评分和文字反馈
    rec = store.update_design_feedback(task_id, feedback, user_id=user.id)
    if not rec:
        raise HTTPException(status_code=404, detail="design record not found")
    _invalidate_data_cache()
    _log_event("design_feedback_saved", user=user, target_type="task", target_id=task_id, message="feedback saved")
    return rec


@app.delete("/api/v1/design/records/{task_id}")
async def delete_design_record(task_id: str, user: UserProfile = Depends(current_user)) -> dict[str, bool]:  # 删除当前用户自己的设计记录并清理缓存
    deleted = store.delete_design_record(task_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="design record not found")
    _invalidate_data_cache()
    _log_event("design_record_deleted", user=user, target_type="task", target_id=task_id, message="user deleted design record")
    return {"deleted": True}


@app.delete("/api/v1/tasks/{task_id}")
async def delete_task(task_id: str, user: UserProfile = Depends(current_user)) -> dict[str, bool]:  # 删除当前用户自己的任务记录，兼容没有设计详情的孤儿任务
    deleted = store.delete_task(task_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="task not found")
    _invalidate_data_cache()
    _log_event("task_deleted", user=user, target_type="task", target_id=task_id, message="user deleted task")
    return {"deleted": True}


@app.delete("/api/v1/admin/design/records/{task_id}")
async def admin_delete_design_record(task_id: str, user: UserProfile = Depends(require_admin)) -> dict[str, bool]:  # 管理员删除任意用户的设计记录并写入日志
    deleted = store.admin_delete_design_record(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="design record not found")
    _invalidate_data_cache()
    _log_event("admin_design_record_deleted", user=user, target_type="task", target_id=task_id, message="admin deleted design record")
    return {"deleted": True}


@app.get("/api/v1/favorites", response_model=list[FavoriteScheme])
async def list_favorites(limit: int = 50, user: UserProfile = Depends(current_user)) -> list[FavoriteScheme]:  # 返回当前用户收藏的设计方案列表
    return store.list_favorite_schemes(user.id, limit=limit)


@app.post("/api/v1/favorites", response_model=FavoriteScheme)
async def save_favorite(scheme: FavoriteSchemeCreate, user: UserProfile = Depends(current_user)) -> FavoriteScheme:  # 保存当前用户提交的收藏方案
    saved = store.save_favorite_scheme(user.id, scheme)
    _invalidate_data_cache()
    _log_event("favorite_saved", user=user, target_type="favorite", target_id=str(saved.id), message=saved.task_id or saved.title)
    return saved


@app.delete("/api/v1/favorites/{favorite_id}")
async def delete_favorite(favorite_id: int, user: UserProfile = Depends(current_user)) -> dict[str, bool]:  # 删除当前用户指定的收藏方案
    deleted = store.delete_favorite_scheme(user.id, favorite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="favorite not found")
    _invalidate_data_cache()
    _log_event("favorite_deleted", user=user, target_type="favorite", target_id=str(favorite_id), message="favorite deleted")
    return {"deleted": True}


@app.post("/api/v1/recommendations/style-templates", response_model=StyleTemplateResponse)
async def recommend_style_templates(
    req: StyleTemplateRequest,
    _user: UserProfile = Depends(current_user),
) -> StyleTemplateResponse:  # 结合图片理解和默认模板生成风格推荐
    key = _cache_key("recommendations", req.model_dump())
    cached = _cache_get_json(key)
    if isinstance(cached, dict):
        return StyleTemplateResponse(**cached)
    vision_result = await _vision_style_templates(req)
    if vision_result:
        _cache_set_json(key, vision_result.model_dump(), settings.recommendation_cache_ttl_s)
        return vision_result
    fallback = _default_style_templates_response("智能推荐暂不可用，已保留初始4个模板。")
    _cache_set_json(key, fallback.model_dump(), settings.cache_ttl_s)
    return fallback


@app.get("/api/v1/tasks", response_model=list[TaskRecord])
async def list_tasks(limit: int = 50, user: UserProfile = Depends(current_user)) -> list[TaskRecord]:  # 返回当前用户最近提交的生成任务列表
    return store.list_recent(limit, user_id=user.id)


@app.get("/api/v1/tasks/{task_id}", response_model=TaskRecord)
async def get_task(task_id: str) -> TaskRecord:  # 根据任务编号返回任务当前状态和结果
    rec = store.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="task not found")
    return rec


@app.post("/api/v1/tasks/{task_id}/refresh", response_model=TaskRecord)
async def refresh_task(task_id: str) -> TaskRecord:  # 主动查询远程任务状态并同步更新本地记录
    rec = store.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="task not found")

    if task_id.startswith("demo-"):
        return rec

    remote_task_id = str((rec.raw or {}).get("remote_task_id") or "")
    if task_id.startswith("local-") and not remote_task_id:
        return rec

    try:
        details = await client.get_task_details(remote_task_id or task_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"NanoBanana refresh failed: {exc}") from exc
    data = details.get("data") if isinstance(details, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected NanoBanana record-info response")

    status, result_url, error_msg = _parse_record_info(data, rec)

    store.update_result(task_id, status=status, result_image_url=result_url, error_message=error_msg, raw={**(rec.raw or {}), "record": details})
    store.update_design_result(task_id, status=status, result_image_url=result_url, error_message=error_msg)
    _invalidate_data_cache()
    return store.get(task_id)  # type: ignore[return-value]


@app.post("/api/v1/nanobanana/callback")
async def nanobanana_callback(cb: dict[str, object]) -> dict[str, str]:  # 接收 NanoBanana 异步回调并更新任务结果
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

    remote_task_id = str(task_id)
    local_rec = store.get_by_remote_task_id(remote_task_id)
    target_task_id = local_rec.task_id if local_rec else remote_task_id

    if not store.get(target_task_id):
        store.upsert(target_task_id, NanoBananaTaskStatus.processing, raw={"callback_first": cb})

    store.update_result(
        target_task_id,
        status=status,
        result_image_url=str(result_image_url) if result_image_url else None,
        error_message=str(error_message) if error_message and status == NanoBananaTaskStatus.failed else None,
        raw={**((local_rec.raw if local_rec else {}) or {}), "remote_task_id": remote_task_id, "callback": cb},
    )
    store.update_design_result(
        target_task_id,
        status=status,
        result_image_url=str(result_image_url) if result_image_url else None,
        error_message=str(error_message) if error_message and status == NanoBananaTaskStatus.failed else None,
    )
    _invalidate_data_cache()
    _log_event(
        "nanobanana_callback",
        level="error" if status == NanoBananaTaskStatus.failed else "info",
        target_type="task",
        target_id=target_task_id,
        message=f"remote_task_id={remote_task_id}, status={int(status)}",
    )
    return {"ok": "true"}


app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")
if frontend_static_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_static_path), html=True), name="frontend")
