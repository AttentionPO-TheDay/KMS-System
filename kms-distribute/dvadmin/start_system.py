import os
import sys
import subprocess
import time
import requests
import webbrowser
from pathlib import Path
def print_banner():
    print("=" * 80)
    print("🔐 Falcon无证书密钥分发系统 (Falcon Certificate-less KDS)")
    print("=" * 80)
    print("基于区块链的后量子密码学密钥分发系统")
    print("支持 Falcon签名 + Kyber加密 + 区块链存储")
    print("=" * 80)
def check_dependencies():
    print("\n📋 检查系统依赖...")
    python_version = sys.version_info
    if python_version.major < 3 or python_version.minor < 8:
        print("❌ Python版本过低，需要Python 3.8+")
        return False
    print(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    required_packages = [
        'django', 'djangorestframework', 'numpy', 
        'cryptography', 'web3', 'requests'
    ]
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}: 已安装")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package}: 未安装")
    if missing_packages:
        print(f"\n⚠️  缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    return True
def start_backend():
    print("\n🚀 启动Django后端服务...")
    backend_dir = Path(__file__).parent / "backend"
    if not backend_dir.exists():
        print("❌ 后端目录不存在")
        return None
    db_file = backend_dir / "db.sqlite3"
    if not db_file.exists():
        print("📊 初始化数据库...")
        subprocess.run([sys.executable, "manage.py", "migrate"], 
                      cwd=backend_dir, check=True)
    print("🌐 启动Django开发服务器...")
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8000"],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print("⏳ 等待服务器启动...")
    for i in range(10):
        try:
            response = requests.get("http://127.0.0.1:8000", timeout=2)
            print("✅ Django后端服务启动成功!")
            print("📍 后端地址: http://127.0.0.1:8000")
            return process
        except requests.exceptions.RequestException:
            time.sleep(1)
            print(f"   等待中... ({i+1}/10)")
    print("❌ Django后端服务启动失败")
    return None
def start_frontend():
    print("\n🎨 启动Vue.js前端服务...")
    frontend_dir = Path(__file__).parent / "web"
    if not frontend_dir.exists():
        print("❌ 前端目录不存在")
        return None
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        print("📦 安装前端依赖...")
        try:
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        except subprocess.CalledProcessError:
            print("❌ npm install 失败，请手动运行: cd web && npm install")
            return None
    print("🌐 启动Vue.js开发服务器...")
    try:
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("⏳ 等待前端服务器启动...")
        time.sleep(5)
        print("✅ Vue.js前端服务启动成功!")
        print("📍 前端地址: http://localhost:3000")
        return process
    except FileNotFoundError:
        print("❌ npm 未找到，请安装Node.js")
        return None
def test_api():
    print("\n🧪 测试系统API接口...")
    test_endpoints = [
        ("系统状态", "http://127.0.0.1:8000/api/pqkds/system/status/"),
        ("区块链状态", "http://127.0.0.1:8000/api/pqkds/blockchain/status/"),
    ]
    for name, url in test_endpoints:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ {name}: 正常")
            else:
                print(f"⚠️  {name}: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ {name}: 连接失败")
def show_usage_guide():
    print("\n📖 系统使用指南:")
    print("-" * 50)
    print("1. 🌐 Web界面访问:")
    print("   - 前端界面: http://localhost:3000")
    print("   - 后端API: http://127.0.0.1:8000")
    print("   - API文档: http://127.0.0.1:8000/swagger/")
    print("\n2. 🔧 API接口测试:")
    print("   - 系统状态: GET /api/pqkds/system/status/")
    print("   - 节点注册: POST /api/pqkds/blockchain/register-node/")
    print("   - 密钥生成: GET /api/pqkds/blockchain/nodes/{node_id}/keys/")
    print("\n3. 🧪 命令行测试:")
    print("   cd backend")
    print("   python test_ideal_flow.py      # 测试完整流程")
    print("   python test_api.py             # 测试API接口")
    print("   python check_db_state.py       # 检查数据库状态")
    print("\n4. 📊 系统监控:")
    print("   - 查看节点状态")
    print("   - 监控密钥分发")
    print("   - 检查区块链交易")
def main():
    print_banner()
    if not check_dependencies():
        print("\n❌ 依赖检查失败，请先安装必要的依赖包")
        return
    backend_process = start_backend()
    if not backend_process:
        print("\n❌ 后端启动失败")
        return
    test_api()
    print("\n❓ 是否启动前端界面? (y/n): ", end="")
    try:
        choice = input().lower().strip()
        if choice in ['y', 'yes', '是']:
            frontend_process = start_frontend()
        else:
            frontend_process = None
    except KeyboardInterrupt:
        frontend_process = None
    show_usage_guide()
    print("\n🌐 打开系统界面...")
    try:
        webbrowser.open("http://127.0.0.1:8000")
        if frontend_process:
            time.sleep(2)
            webbrowser.open("http://localhost:3000")
    except:
        pass
    print("\n✅ 系统启动完成!")
    print("按 Ctrl+C 停止系统")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 正在停止系统...")
        if backend_process:
            backend_process.terminate()
        if 'frontend_process' in locals() and frontend_process:
            frontend_process.terminate()
        print("✅ 系统已停止")
if __name__ == "__main__":
    main()