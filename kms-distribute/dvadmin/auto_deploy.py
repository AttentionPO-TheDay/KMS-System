# -*- coding: utf-8 -*-
"""
PQKDS 一键自动化部署脚本 (Windows)
前提: Python 3.9+, Node.js 16+, MySQL 8.0+ 已安装并可用
用法: python auto_deploy.py
      python auto_deploy.py --db-name falcon_kds --db-user root --db-pass password
      python auto_deploy.py --db-pass 123456   (只改密码，其余用默认值)
"""
import subprocess, sys, os, shutil, time, argparse, traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(PROJECT_ROOT, "backend")
WEB_DIR      = os.path.join(PROJECT_ROOT, "web")

os.system("")  # enable ANSI escape on Windows 10+

# ── 日志工具 ──────────────────────────────────────────────
def ok(m):   print(f"  \033[32m[✓]\033[0m {m}")
def info(m): print(f"  \033[36m[·]\033[0m {m}")
def warn(m): print(f"  \033[33m[!]\033[0m {m}")
def fail(m): print(f"  \033[31m[✗]\033[0m {m}")
def header(step, text):
    print(f"\n{'='*60}\n  Step {step}: {text}\n{'='*60}")

def run(cmd, cwd=None, timeout=600):
    """执行命令，返回 (returncode, stdout)"""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd or PROJECT_ROOT,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        return r.returncode, (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"
    except Exception as e:
        return 1, str(e)

def run_or_die(cmd, cwd=None, msg="命令执行失败", timeout=600):
    """执行命令，失败则终止脚本"""
    code, out = run(cmd, cwd=cwd, timeout=timeout)
    if code != 0:
        fail(f"{msg}\n    命令: {cmd}\n    输出: {out[:500]}")
        sys.exit(1)
    return out

def pip_install(pkg, quiet=True):
    q = "-q" if quiet else ""
    code, _ = run(f'python -m pip install {pkg} {q}')
    return code == 0

# ── 参数解析 ──────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="PQKDS 一键部署")
    p.add_argument("--db-name", default="falcon_kds",   help="MySQL 数据库名 (默认 falcon_kds)")
    p.add_argument("--db-user", default="root",         help="MySQL 用户名 (默认 root)")
    p.add_argument("--db-pass", default="password",     help="MySQL 密码 (默认 password)")
    p.add_argument("--db-host", default="127.0.0.1",    help="MySQL 地址 (默认 127.0.0.1)")
    p.add_argument("--db-port", default="3306",         help="MySQL 端口 (默认 3306)")
    p.add_argument("--skip-npm", action="store_true",   help="跳过前端 npm install")
    return p.parse_args()

# ══════════════════════════════════════════════════════════
#  Step 0: 环境检查
# ══════════════════════════════════════════════════════════
def step0_check_env():
    header(0, "环境检查")
    errors = []

    code, out = run("python --version")
    if code == 0:
        ok(f"Python: {out}")
    else:
        fail("未找到 Python"); errors.append("python")

    code, _ = run("python -m pip --version")
    if code == 0:
        ok("pip 可用")
    else:
        fail("pip 不可用"); errors.append("pip")

    code, out = run("node --version")
    if code == 0:
        ok(f"Node.js: {out}")
    else:
        fail("未找到 Node.js"); errors.append("node")

    code, _ = run("npm --version")
    if code == 0:
        ok("npm 可用")
    else:
        fail("npm 不可用"); errors.append("npm")

    # MySQL 客户端不是必须的，只要服务在跑就行
    code, _ = run("mysql --version")
    if code == 0:
        ok("MySQL 客户端可用")
    else:
        warn("mysql CLI 不在 PATH 中（不影响部署，只要 MySQL 服务在运行）")

    if errors:
        fail(f"缺少必要工具: {', '.join(errors)}")
        sys.exit(1)
    ok("环境检查通过")

# ══════════════════════════════════════════════════════════
#  Step 1: 生成数据库配置 + 建库
# ══════════════════════════════════════════════════════════
def step1_configure_db(cfg):
    header(1, "配置 MySQL 数据库")
    info(f"数据库: {cfg.db_user}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}")

    # 写 env.py
    env_path = os.path.join(BACKEND_DIR, "conf", "env.py")
    env_content = f"""import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_ENGINE = "django.db.backends.mysql"
DATABASE_NAME = '{cfg.db_name}'
DATABASE_HOST = "{cfg.db_host}"
DATABASE_PORT = {cfg.db_port}
DATABASE_USER = "{cfg.db_user}"
DATABASE_PASSWORD = "{cfg.db_pass}"
TABLE_PREFIX = "dvadmin_"
DEBUG = True
ENABLE_LOGIN_ANALYSIS_LOG = True
LOGIN_NO_CAPTCHA_AUTH = True
ALLOWED_HOSTS = ["*"]
COLUMN_EXCLUDE_APPS = []
"""
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)
    ok("backend/conf/env.py 已生成")

    # 尝试自动建库
    sql = f"CREATE DATABASE IF NOT EXISTS `{cfg.db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
    code, _ = run(
        f'mysql -h {cfg.db_host} -P {cfg.db_port} -u {cfg.db_user} -p{cfg.db_pass} -e "{sql}"'
    )
    if code == 0:
        ok(f"数据库 {cfg.db_name} 已就绪")
    else:
        # mysql CLI 不在 PATH 也没关系，用 Python 建库
        info("mysql CLI 建库失败，尝试用 Python 连接建库...")
        try:
            _create_db_via_python(cfg)
            ok(f"数据库 {cfg.db_name} 已就绪 (Python 方式)")
        except Exception as e:
            warn(f"自动建库失败: {e}")
            warn(f"请手动创建数据库: {sql}")
            warn("确保 MySQL 服务正在运行且账号密码正确")
            fail("无法继续，请先解决数据库问题后重新运行脚本")
            sys.exit(1)

def _create_db_via_python(cfg):
    """用 PyMySQL 建库（不依赖 mysql CLI）"""
    import importlib
    pymysql = importlib.import_module("pymysql")
    conn = pymysql.connect(
        host=cfg.db_host, port=int(cfg.db_port),
        user=cfg.db_user, password=cfg.db_pass,
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg.db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
        conn.commit()
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════
#  Step 2: 安装 Python 依赖
# ══════════════════════════════════════════════════════════
def step2_install_python_deps():
    header(2, "安装 Python 依赖")

    info("升级 pip ...")
    run("python -m pip install --upgrade pip -q")

    # 先装 PyMySQL（纯 Python，不需要编译），确保后续建库可用
    info("安装 PyMySQL (纯 Python MySQL 驱动) ...")
    pip_install("PyMySQL")

    # 读 requirements.txt，过滤掉有问题的包
    req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    skip_packages = {"logging", "futures", "crypto"}  # Python 3 内置或冲突包
    problematic = {"mysqlclient"}  # Windows 上经常编译失败

    info("安装 requirements.txt 中的依赖 ...")
    packages = []
    with open(req_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].strip().lower()
            if pkg_name in skip_packages:
                warn(f"跳过 {line} (Python 3 不需要)")
                continue
            if pkg_name in problematic:
                warn(f"跳过 {line} (Windows 编译问题，用 PyMySQL 替代)")
                continue
            packages.append(line)

    # 批量安装
    tmp_req = os.path.join(PROJECT_ROOT, "_requirements_filtered.txt")
    with open(tmp_req, "w", encoding="utf-8") as f:
        f.write("\n".join(packages))

    code, out = run(f'python -m pip install -r "{tmp_req}" -q', timeout=900)
    if code != 0:
        warn("批量安装部分失败，逐个安装 ...")
        for pkg in packages:
            if not pip_install(pkg):
                warn(f"  安装失败: {pkg}")

    # 清理临时文件
    try: os.remove(tmp_req)
    except: pass

    # 确保 PyMySQL 作为 MySQLdb 的替代
    init_file = os.path.join(BACKEND_DIR, "application", "__init__.py")
    init_content = ""
    if os.path.exists(init_file):
        with open(init_file, "r", encoding="utf-8") as f:
            init_content = f.read()
    if "pymysql" not in init_content.lower():
        with open(init_file, "w", encoding="utf-8") as f:
            f.write("import pymysql\npymysql.install_as_MySQLdb()\n")
        ok("已配置 PyMySQL 作为 MySQLdb 替代")

    ok("Python 依赖安装完成")

# ══════════════════════════════════════════════════════════
#  Step 3: 安装 Solidity 编译器
# ══════════════════════════════════════════════════════════
def step3_install_solc():
    header(3, "安装 Solidity 编译器")
    code, _ = run("python -c \"import solcx; solcx.install_solc('0.8.20')\"", timeout=120)
    if code == 0:
        ok("solc 0.8.20 已安装")
    else:
        warn("solc 安装失败，区块链功能可能不可用（不影响核心密钥分发功能）")

# ══════════════════════════════════════════════════════════
#  Step 4: 数据库迁移
# ══════════════════════════════════════════════════════════
def step4_migrate():
    header(4, "数据库迁移")

    # 清理旧的 __pycache__，避免迁移冲突
    info("清理 __pycache__ ...")
    for root, dirs, files in os.walk(BACKEND_DIR):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)

    info("执行 makemigrations ...")
    run_or_die("python manage.py makemigrations", cwd=BACKEND_DIR, msg="makemigrations 失败")
    ok("makemigrations 完成")

    info("执行 migrate ...")
    run_or_die("python manage.py migrate", cwd=BACKEND_DIR, msg="migrate 失败，请检查数据库连接")
    ok("数据库迁移完成")

# ══════════════════════════════════════════════════════════
#  Step 5: 初始化系统数据 (菜单/角色/权限/管理员)
# ══════════════════════════════════════════════════════════
def step5_init_data():
    header(5, "初始化系统数据")

    # 初始化基础数据
    info("初始化基础数据 (菜单/角色/权限) ...")
    init_py = os.path.join(BACKEND_DIR, "dvadmin", "system", "fixtures", "initialize.py")
    code, out = run(f'python "{init_py}"', cwd=BACKEND_DIR)
    if code != 0:
        warn(f"基础数据初始化可能有警告: {out[:200]}")
    else:
        ok("基础数据初始化完成")

    # 初始化 PQKDS 菜单 + 创建管理员 + collectstatic
    info("初始化 PQKDS 菜单 + 创建管理员账号 ...")
    helper = os.path.join(BACKEND_DIR, "_init_helper.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write("""# -*- coding: utf-8 -*-
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

# 初始化 PQKDS 菜单
try:
    from pqkds.fixtures.initialize import Initialize
    Initialize(app='pqkds').run()
    print('[OK] PQKDS menus initialized')
except Exception as e:
    print(f'[WARN] PQKDS menu init: {e}')

# collectstatic
try:
    from django.core.management import call_command
    call_command('collectstatic', '--noinput', verbosity=0)
    print('[OK] Static files collected')
except Exception as e:
    print(f'[WARN] collectstatic: {e}')

# 创建管理员
from dvadmin.system.models import Users
u, created = Users.objects.get_or_create(
    username='admin',
    defaults={
        'is_superuser': True, 'is_staff': True,
        'is_active': True, 'name': 'admin', 'user_type': 0
    }
)
u.set_password('admin123456')
u.is_superuser = True
u.is_staff = True
u.save()
print(f'[OK] admin account: {"created" if created else "exists, password reset"}')
""")
    code, out = run(f'python "{helper}"', cwd=BACKEND_DIR)
    try: os.remove(helper)
    except: pass

    if code == 0:
        ok("系统数据初始化完成")
    else:
        warn(f"初始化可能有警告: {out[:300]}")

    print("\n    ┌─────────────────────────────┐")
    print("    │  管理员账号: admin           │")
    print("    │  管理员密码: admin123456     │")
    print("    └─────────────────────────────┘")


# ══════════════════════════════════════════════════════════
#  Step 6: 安装前端依赖
# ══════════════════════════════════════════════════════════
def step6_install_frontend(skip=False):
    header(6, "安装前端依赖")
    if skip:
        warn("已跳过 (--skip-npm)")
        return

    # 检查 node_modules 是否已存在
    marker = os.path.join(WEB_DIR, "node_modules", "vue", "package.json")
    if os.path.exists(marker):
        ok("node_modules 已存在，跳过安装")
        return

    info("执行 npm install (可能需要 2~5 分钟) ...")
    code, out = run("npm install", cwd=WEB_DIR, timeout=600)
    if code != 0:
        info("npm install 失败，尝试使用国内镜像 ...")
        code, out = run(
            "npm install --registry=https://registry.npmmirror.com",
            cwd=WEB_DIR, timeout=600
        )
        if code != 0:
            fail(f"前端依赖安装失败: {out[:300]}")
            sys.exit(1)
    ok("前端依赖安装完成")

# ══════════════════════════════════════════════════════════
#  Step 7: 部署验证
# ══════════════════════════════════════════════════════════
def step7_verify():
    header(7, "部署验证")

    # Django check
    info("检查 Django 配置 ...")
    code, out = run("python manage.py check", cwd=BACKEND_DIR)
    if code == 0:
        ok("Django 配置正常")
    else:
        warn(f"Django check 有警告: {out[:200]}")

    # 数据库连接
    info("检查数据库连接 ...")
    helper = os.path.join(BACKEND_DIR, "_check_db.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write(
            "import os, django\n"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','application.settings')\n"
            "django.setup()\n"
            "from django.db import connection\n"
            "connection.cursor().execute('SELECT 1')\n"
            "print('OK')\n"
        )
    code, _ = run(f'python "{helper}"', cwd=BACKEND_DIR)
    try: os.remove(helper)
    except: pass
    if code == 0:
        ok("数据库连接正常")
    else:
        fail("数据库连接失败!")

    # DLL 文件
    info("检查 Falcon/Kyber DLL 文件 ...")
    dll_files = [
        "falcon/falcon512.dll",
        "kyber/libpqcrystals_kyber512_ref.dll",
    ]
    all_ok = True
    for p in dll_files:
        full = os.path.join(BACKEND_DIR, p)
        if os.path.exists(full):
            ok(f"  {p}")
        else:
            warn(f"  缺少: {p}")
            all_ok = False
    if all_ok:
        ok("DLL 文件完整")

    # 前端
    info("检查前端 ...")
    if os.path.exists(os.path.join(WEB_DIR, "node_modules", "vue", "package.json")):
        ok("前端依赖完整")
    else:
        warn("前端 node_modules 不完整")

# ══════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════
def main():
    print(r"""
============================================================
  ____   ___  _  ______  ____
 |  _ \ / _ \| |/ /  _ \/ ___|
 | |_) | | | | ' /| | | \___ \
 |  __/| |_| | . \| |_| |___) |
 |_|    \__\_\_|\_\____/|____/

  后量子密钥分发系统 - 一键自动化部署
============================================================""")

    cfg = parse_args()

    try:
        step0_check_env()
        step2_install_python_deps()   # 先装依赖，确保 PyMySQL 可用
        step1_configure_db(cfg)       # 再配置数据库
        step3_install_solc()
        step4_migrate()
        step5_init_data()
        step6_install_frontend(skip=cfg.skip_npm)
        step7_verify()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"部署过程出错: {e}")
        traceback.print_exc()
        sys.exit(1)

    print(f"""
{'='*60}
  ✅ 部署完成!
{'='*60}

  启动后端:
    cd backend
    python manage.py runserver 0.0.0.0:8000

  启动前端:
    cd web
    npm run dev

  或者直接双击: start.bat

  访问地址:
    前端: http://localhost:8081
    后端: http://localhost:8000
    登录: admin / admin123456
{'='*60}
""")

if __name__ == "__main__":
    main()