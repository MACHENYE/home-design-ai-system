from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NanoBananaTaskStatus(int, Enum):
    created = 1
    processing = 2
    success = 3
    failed = 4


class GenerateMode(str, Enum):
    basic = "basic"
    pro = "pro"


class GenerateType(str, Enum):
    text_to_image = "TEXTTOIAMGE"
    image_to_image = "IMAGETOIAMGE"


class GenerateRequest(BaseModel):
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

    # Basic endpoint options
    model_name: str | None = None
    safe_word: str | None = None
    enable_translation: bool | None = None
    output_format: str | None = None
    safety_filter_level: str | None = None

    # Pro endpoint options
    resolution: str | None = None
    aspect_ratio: str | None = None

    # Optional override if you host callback separately
    callback_url: str | None = None


class SubmitResponse(BaseModel):
    task_id: str


class TaskRecord(BaseModel):
    task_id: str
    status: NanoBananaTaskStatus
    created_at: int | None = None
    updated_at: int | None = None
    result_image_url: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] | None = None


class DesignRecord(BaseModel):
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
    created_at: int | None = None
    updated_at: int | None = None


class AssetUploadResponse(BaseModel):
    filename: str
    url: str
    local_url: str
    warning: str | None = None


class NanoBananaCallback(BaseModel):
    taskId: str
    status: int
    fileId: str | None = None
    successFlag: bool | None = None
    errorCode: str | None = None
    errorMsg: str | None = None
    resultImageUrl: str | None = None
