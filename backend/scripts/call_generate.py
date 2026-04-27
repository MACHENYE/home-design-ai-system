from __future__ import annotations

import argparse
import time

import httpx

DEFAULT_PROMPT = "a modern minimalist living room, warm lighting, photorealistic"

def _client() -> httpx.Client:
    # Avoid system/conda proxy settings interfering with localhost calls.
    return httpx.Client(timeout=60, trust_env=False)


def submit(base_url: str, prompt: str, *, mode: str, gen_type: str, num_images: int) -> str:
    payload = {
        "mode": mode,
        "type": gen_type,
        "prompt": prompt,
        "numImages": num_images,
    }
    with _client() as client:
        r = client.post(f"{base_url}/api/v1/design/submit", json=payload)
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id") or data.get("taskId") or data.get("task_id".upper())
    if not task_id:
        raise RuntimeError(f"Unexpected response (no task_id): {data}")
    return str(task_id)


def refresh(base_url: str, task_id: str) -> dict:
    with _client() as client:
        r = client.post(f"{base_url}/api/v1/tasks/{task_id}/refresh")
    r.raise_for_status()
    return r.json()


def get_task(base_url: str, task_id: str) -> dict:
    with _client() as client:
        r = client.get(f"{base_url}/api/v1/tasks/{task_id}")
    r.raise_for_status()
    return r.json()


def main() -> int:
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

    # Last fetch for debugging
    rec = get_task(args.base_url, task_id)
    raise SystemExit(f"Timed out waiting for result. Last task record: {rec}")


if __name__ == "__main__":
    raise SystemExit(main())
