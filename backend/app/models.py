from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserRegisterRequest(BaseModel):  # 用户注册接口的请求数据模型，限制用户名和密码字段格式
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-\u4e00-\u9fff]+$")
    password: str = Field(min_length=6, max_length=128)


class UserLoginRequest(BaseModel):  # 用户登录接口的请求数据模型，接收账号和密码
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserProfile(BaseModel):  # 前端展示和鉴权使用的用户资料模型
    id: int
    username: str
    role: str = "user"
    created_at: int | None = None


class AuthResponse(BaseModel):  # 登录或注册成功后返回的令牌和用户信息模型
    token: str
    user: UserProfile


class NanoBananaTaskStatus(int, Enum):  # 统一定义本地任务状态码，便于前后端识别任务进度
    created = 1
    processing = 2
    success = 3
    failed = 4


class GenerateMode(str, Enum):  # 定义图像生成模式，区分基础生成和专业生成
    basic = "basic"
    pro = "pro"


class GenerateType(str, Enum):  # 定义生成任务类型，兼容文生图和图生图调用参数
    text_to_image = "TEXTTOIAMGE"
    image_to_image = "IMAGETOIAMGE"


class GenerateRequest(BaseModel):  # 提交设计生成任务时使用的请求体模型
    model_config = ConfigDict(protected_namespaces=())

    mode: GenerateMode = GenerateMode.basic
    type: GenerateType = GenerateType.image_to_image

    prompt: str = Field(min_length=1)
    image_urls: list[str] = Field(default_factory=list, description="Reference/input images (URLs).")

    room_type: str | None = None
    design_style: str | None = None
    color_preference: str | None = None
    material_preference: str | None = None
    budget_level: str | None = None
    cultural_element: str | None = None
    keep_structure: bool = True
    mask_url: str | None = None
    negative_prompt: str | None = None
    notes: str | None = None

    # 基础生成接口的可选参数
    model_name: str | None = None
    safe_word: str | None = None
    enable_translation: bool | None = None
    output_format: str | None = None
    safety_filter_level: str | None = None

    # 专业生成接口的可选参数
    resolution: str | None = None
    aspect_ratio: str | None = None

    # 独立部署回调地址时可覆盖默认配置
    callback_url: str | None = None


class SubmitResponse(BaseModel):  # 提交生成任务后返回给前端的任务编号模型
    task_id: str


class TaskRecord(BaseModel):  # 保存任务状态、结果图和错误信息的响应模型
    task_id: str
    status: NanoBananaTaskStatus
    created_at: int | None = None
    updated_at: int | None = None
    result_image_url: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] | None = None


class DesignRecord(BaseModel):  # 保存一次家装设计生成完整业务信息的模型
    task_id: str
    status: NanoBananaTaskStatus
    prompt: str
    negative_prompt: str | None = None
    room_type: str | None = None
    design_style: str | None = None
    color_preference: str | None = None
    material_preference: str | None = None
    budget_level: str | None = None
    cultural_element: str | None = None
    keep_structure: bool = True
    draft_image_url: str | None = None
    reference_image_url: str | None = None
    mask_url: str | None = None
    result_image_url: str | None = None
    error_message: str | None = None
    lighting_score: int | None = None
    style_match_score: int | None = None
    space_utilization_score: int | None = None
    satisfaction_score: int | None = None
    feedback_text: str | None = None
    feedback_updated_at: int | None = None
    created_at: int | None = None
    updated_at: int | None = None


class DesignFeedbackRequest(BaseModel):  # 用户提交方案评分和文字反馈时使用的请求模型
    lighting_score: int | None = Field(default=None, ge=1, le=5)
    style_match_score: int | None = Field(default=None, ge=1, le=5)
    space_utilization_score: int | None = Field(default=None, ge=1, le=5)
    satisfaction_score: int | None = Field(default=None, ge=1, le=5)
    feedback_text: str | None = Field(default=None, max_length=500)


class FavoriteSchemeCreate(BaseModel):  # 用户新增收藏方案时使用的请求模型
    task_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    style: str | None = Field(default=None, max_length=160)
    image: str = Field(min_length=1)


class FavoriteScheme(BaseModel):  # 前端展示收藏方案时使用的数据模型
    id: int
    user_id: int
    task_id: str | None = None
    title: str
    style: str | None = None
    image: str
    created_at: int | None = None


class SystemLog(BaseModel):  # 系统操作日志和异常日志的数据模型
    id: int
    user_id: int | None = None
    username: str | None = None
    level: str = "info"
    action: str
    target_type: str | None = None
    target_id: str | None = None
    message: str | None = None
    duration_ms: int | None = None
    request_path: str | None = None
    ip_address: str | None = None
    created_at: int | None = None


class AssetUploadResponse(BaseModel):  # 素材上传成功后返回图片地址和提示信息的模型
    filename: str
    url: str
    local_url: str
    warning: str | None = None


class StyleTemplate(BaseModel):  # 智能推荐生成的单个风格模板模型
    name: str
    room: str
    style: str
    color: str
    material: str
    prompt: str
    desc: str
    reason: str | None = None


class StyleTemplateRequest(BaseModel):  # 请求智能推荐风格模板时使用的输入模型
    room_type: str | None = None
    design_style: str | None = None
    color_preference: str | None = None
    material_preference: str | None = None
    prompt: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    refresh_seed: int = 0


class StyleTemplateResponse(BaseModel):  # 智能推荐接口返回模板列表和说明信息的模型
    templates: list[StyleTemplate] = Field(default_factory=list)
    summary: str | None = None
    source: str = "history"


class PromptOptimizeRequest(BaseModel):  # 请求优化提示词时使用的输入模型
    prompt: str = Field(min_length=1, max_length=1200)
    room_type: str | None = None
    design_style: str | None = None
    color_preference: str | None = None
    material_preference: str | None = None
    aspect_ratio: str | None = None


class PromptOptimizeResponse(BaseModel):  # 提示词优化接口返回优化文本和摘要的模型
    prompt: str
    summary: str | None = None


class NanoBananaCallback(BaseModel):  # NanoBanana 异步回调通知的数据模型
    taskId: str
    status: int
    fileId: str | None = None
    successFlag: bool | None = None
    errorCode: str | None = None
    errorMsg: str | None = None
    resultImageUrl: str | None = None
