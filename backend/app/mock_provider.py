from __future__ import annotations

import base64
import html
import textwrap
import time
import uuid

from .models import GenerateRequest


def make_demo_task_id() -> str:
    return "demo-" + uuid.uuid4().hex[:12]


def make_demo_result(req: GenerateRequest) -> str:
    title = req.design_style or "AI Home Design"
    room = req.room_type or "Interior Space"
    colors = req.color_preference or "balanced natural palette"
    materials = req.material_preference or "wood, fabric, stone"
    culture = req.cultural_element or "modern living details"

    body = [
        f"Room: {room}",
        f"Style: {title}",
        f"Colors: {colors}",
        f"Materials: {materials}",
        f"Element: {culture}",
    ]
    if req.keep_structure:
        body.append("Constraint: structure preserved")
    if req.mask_url:
        body.append("Edit: masked local repaint")

    escaped_title = html.escape(title)
    escaped_prompt = html.escape(req.prompt[:160])
    rows = "\n".join(
        f'<text x="76" y="{250 + i * 34}" class="body">{html.escape(line)}</text>'
        for i, line in enumerate(body)
    )
    prompt_lines = textwrap.wrap(req.prompt, width=46)[:3]
    prompt_svg = "\n".join(
        f'<text x="76" y="{500 + i * 28}" class="small">{html.escape(line)}</text>'
        for i, line in enumerate(prompt_lines)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="832" viewBox="0 0 1280 832">
  <defs>
    <linearGradient id="wall" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#f6f2eb"/>
      <stop offset="58%" stop-color="#dfe8e4"/>
      <stop offset="100%" stop-color="#c9d7e7"/>
    </linearGradient>
    <linearGradient id="floor" x1="0" x2="1">
      <stop offset="0%" stop-color="#b8895e"/>
      <stop offset="100%" stop-color="#6f5945"/>
    </linearGradient>
    <style>
      .title {{ font: 700 46px Arial, sans-serif; fill: #18332f; }}
      .body {{ font: 500 24px Arial, sans-serif; fill: #203533; }}
      .small {{ font: 400 21px Arial, sans-serif; fill: #40504d; }}
      .line {{ stroke: #31423f; stroke-width: 5; fill: none; opacity: .65; }}
    </style>
  </defs>
  <rect width="1280" height="832" fill="#eef1ef"/>
  <polygon points="70,70 1210,70 1082,514 198,514" fill="url(#wall)"/>
  <polygon points="198,514 1082,514 1220,790 48,790" fill="url(#floor)"/>
  <polyline points="70,70 198,514 48,790" class="line"/>
  <polyline points="1210,70 1082,514 1220,790" class="line"/>
  <line x1="198" y1="514" x2="1082" y2="514" class="line"/>
  <rect x="810" y="136" width="230" height="210" rx="4" fill="#d9eef3" stroke="#415752" stroke-width="5"/>
  <line x1="925" y1="136" x2="925" y2="346" stroke="#415752" stroke-width="4"/>
  <rect x="312" y="384" width="324" height="108" rx="8" fill="#6a7f76"/>
  <rect x="270" y="444" width="410" height="100" rx="8" fill="#405b56"/>
  <rect x="742" y="444" width="228" height="126" rx="8" fill="#f0ddbd"/>
  <rect x="778" y="338" width="154" height="104" rx="8" fill="#315b63"/>
  <circle cx="410" cy="338" r="58" fill="#d7a75f"/>
  <rect x="60" y="52" width="520" height="590" rx="8" fill="#ffffff" opacity=".86"/>
  <text x="76" y="128" class="title">{escaped_title}</text>
  <text x="76" y="176" class="small">Demo rendering generated at {time.strftime('%Y-%m-%d %H:%M:%S')}</text>
  {rows}
  <text x="76" y="464" class="body">Prompt</text>
  {prompt_svg or f'<text x="76" y="500" class="small">{escaped_prompt}</text>'}
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
