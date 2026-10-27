import subprocess
import sys
import time

def main():
    print("🚀 正在准备启动 AI Agent 服务...")
    
    # 检查环境
    python_exe = sys.executable
    
    print("1. 启动后端 FastAPI...")
    # 启动 uvicorn 子进程
    backend = subprocess.Popen([python_exe, "-m", "uvicorn", "main:app", "--reload"])
    
    print("2. 等待后端就绪...")
    time.sleep(2)
    
    print("3. 启动前端 Streamlit...")
    # 启动 streamlit 子进程
    frontend = subprocess.Popen([python_exe, "-m", "streamlit", "run", "app.py"])
    
    try:
        # 保持主进程运行，直到前端退出
        frontend.wait()
    except KeyboardInterrupt:
        print("\n正在关闭所有服务...")
    finally:
        backend.terminate()
        frontend.terminate()
        print("✅ 所有服务已关闭。")

if __name__ == "__main__":
    main()