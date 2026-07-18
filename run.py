"""一键启动：后台起 FastAPI，前台起 Streamlit"""
import subprocess
import sys
import time
import threading
import webbrowser

import uvicorn


def start_backend():
    """在后台线程启动 FastAPI"""
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, log_level="info")


def main():
    print("=" * 50)
    print("  通用数据分析 Agent — 一键启动")
    print("=" * 50)

    # 后台启动 FastAPI
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # 等后端就绪
    print(" 等待后端启动...", end=" ", flush=True)
    for _ in range(10):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8000/health", timeout=1)
            print("OK")
            break
        except Exception:
            pass
    else:
        print("超时，请检查")

    print(f"  后端: http://localhost:8000")
    print(f"  前端: http://localhost:8501")
    print("=" * 50)

    # 前台启动 Streamlit
    subprocess.run([sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.port", "8501"])


if __name__ == "__main__":
    main()
