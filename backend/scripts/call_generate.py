# 命令行调试脚本
from __future__ import annotations

import argparse # 解析命令行参数
import time # 用于实现等待和超时功能

import httpx # 用于发送HTTP请求的库

DEFAULT_PROMPT = "a modern minimalist living room, warm lighting, photorealistic"

def _client() -> httpx.Client:  # 创建一个 HTTP 客户端，每个请求最多等待60秒，不读取系统代理、conda 代理等环境变量
    # 避免系统或 conda 代理影响本地接口调试
    return httpx.Client(timeout=60, trust_env=False)


def submit(base_url: str, prompt: str, *, mode: str, gen_type: str, num_images: int) -> str:  # 创建设计生成任务，保存请求参数并进入异步生成流程
    payload = {
        "mode": mode,
        "type": gen_type,
        "prompt": prompt,
        "numImages": num_images, # 生成图片数量
    }
    with _client() as client:
        r = client.post(f"{base_url}/api/v1/design/submit", json=payload) # 向后端提交 POST 请求
    r.raise_for_status() #  如果HTTP 状态码是 4xx 或 5xx，比如接口报错、服务没启动、权限失败，就直接抛出异常
    data = r.json() # 把后端返回的 JSON 转成 Python 字典
    task_id = data.get("task_id") or data.get("taskId") or data.get("task_id".upper())
    if not task_id:
        raise RuntimeError(f"Unexpected response (no task_id): {data}")
    return str(task_id)


def refresh(base_url: str, task_id: str) -> dict:  # 在命令行中主动刷新指定任务状态
    with _client() as client:
        r = client.post(f"{base_url}/api/v1/tasks/{task_id}/refresh") # 让后端去查询或更新这个任务的最新状态
    r.raise_for_status()
    return r.json()


def get_task(base_url: str, task_id: str) -> dict:  # 根据任务编号返回任务当前状态和结果
    with _client() as client:
        r = client.get(f"{base_url}/api/v1/tasks/{task_id}") # 查询当前后端数据库或任务存储里的记录
    r.raise_for_status()
    return r.json()


def main() -> int:  # 解析命令行参数并执行提交、轮询和超时处理流程
    parser = argparse.ArgumentParser(description="Call local backend to submit a NanoBanana generation task.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--prompt", default=None, help="Prompt text. If omitted, uses DEFAULT_PROMPT in the file.")
    parser.add_argument("--mode", default="basic", choices=["basic", "pro"], help="Backend mode.")
    parser.add_argument("--type", default="TEXTTOIAMGE", help="TEXTTOIAMGE or IMAGETOIAMGE.")
    parser.add_argument("--num-images", type=int, default=1)
    parser.add_argument("--wait", action="store_true", help="Poll until result_image_url is available.")
    parser.add_argument("--interval", type=float, default=3.0, help="Polling interval seconds.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Polling timeout seconds.")
    args = parser.parse_args()

    prompt = (args.prompt or DEFAULT_PROMPT).strip()
    if not prompt:
        raise SystemExit("Prompt is empty. Set DEFAULT_PROMPT in the file or pass --prompt.")

    print(f"prompt={prompt}")
    task_id = submit(args.base_url, prompt, mode=args.mode, gen_type=args.type, num_images=args.num_images)
    print(f"task_id={task_id}")

    if not args.wait:
        return 0

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        rec = refresh(args.base_url, task_id)
        result_url = rec.get("result_image_url") or rec.get("resultImageUrl")
        status = rec.get("status")
        print(f"status={status} result_image_url={result_url}")
        if result_url:
            return 0
        time.sleep(args.interval)

    # 超时后再查询一次任务详情，便于定位失败原因
    rec = get_task(args.base_url, task_id)
    raise SystemExit(f"Timed out waiting for result. Last task record: {rec}")


if __name__ == "__main__":
    raise SystemExit(main())
