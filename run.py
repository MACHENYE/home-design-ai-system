from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    backend_dir = project_dir / "backend"
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    os.environ["PYTHONPATH"] = (
        str(backend_dir)
        if not os.environ.get("PYTHONPATH")
        else str(backend_dir) + os.pathsep + os.environ["PYTHONPATH"]
    )

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        reload_dirs=[str(backend_dir)],
    )


if __name__ == "__main__":
    main()
