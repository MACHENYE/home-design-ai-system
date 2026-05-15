from __future__ import annotations

from .models import GenerateRequest


def build_home_design_prompt(req: GenerateRequest) -> str:  # 把表单参数拼接为完整的家装设计提示词
    parts: list[str] = [
        "You are an interior renovation rendering assistant.",
        "Generate a realistic, physically plausible home design rendering.",
    ]

    if req.keep_structure:
        parts.append(
            "Strictly preserve the room layout, wall boundaries, doors, windows, perspective, and main furniture positions from the input design draft."
        )

    field_map = [
        ("Room type", req.room_type),
        ("Design style", req.design_style),
        ("Preferred colors", req.color_preference),
        ("Preferred materials", req.material_preference),
        ("User request", req.prompt),
        ("Additional notes", req.notes),
    ]
    for label, value in field_map:
        if value:
            parts.append(f"{label}: {value}.")

    if req.mask_url:
        parts.append(
            "A mask image is provided. Only modify the masked local area and keep all unmasked regions visually consistent."
        )

    if req.negative_prompt:
        parts.append(f"Avoid: {req.negative_prompt}.")

    parts.append(
        "Output should look like a clean professional interior design visualization with coherent lighting, materials, scale, and usable layout."
    )
    return "\n".join(parts)
