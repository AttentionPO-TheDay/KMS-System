# -*- coding: utf-8 -*-
"""
PQKDS - 后量子密钥分发系统  Windows 一键部署脚本
前置条件: Python 3.9+, Node.js 16+, MySQL 8.0+ (已安装并运行)
用法: python deploy.py  或双击 deploy.bat
"""
import subprocess, sys, os, shutil, time, json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(PROJECT_ROOT, "backend")
WEB_DIR      = os.path.join(PROJECT_ROOT, "web")

os.system("")  # enable ANSI on Windows 10+

# ── 日志工具 ──────────────────────────────────────────────
def ok(m):   print(f"  \033[32m[OK]\033[0m {m}")
def info(m): print(f"  \033[36m[..]\033[0m {m}")
def warn(m): print(f"  \033[33m[!!]\033[0m {m}")
def fail(m): print(f"  \033[31m[XX]\033[0m {m}")

def header(step, text):
    print(f"\n{'='*60}\n  Step {step}: {text}\n{'='*60}")

# ── 命令执行 ──────────────────────────────────────────────
def run(cmd, cwd=None, capture=False, timeout=600):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd or PROJECT_ROOT,
                           capture_output=capture, text=True, timeout=timeout,
                           encoding='utf-8', errors='replace')
        return r.returncode, (r.stdout or "") if capture else ""
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"
    except Exception as e:
        return 1, str(e)

def run_ok(cmd):
    c, _ = run(cmd, capture=True)
    return c == 0

def get_out(cmd):
    _, o = run(cmd, capture=True)
    return o.strip()

# ==============================================================
#  Step 0: 环境检查
# ==============================================================
def step0():
    header(0, "Check Environment")
    errs = []
    if run_ok("python --version"):
        ok(f"Python -> {get_out('python --version')}")
    else:
        fail("Python not found"); errs.append("python")
    if run_ok("python -m pip --version"):
        ok("pip ready")
    else:
        fail("pip not available"); errs.append("pip")
    if run_ok("node --version"):
        ok(f"Node.js -> {get_out('node --version')}")
    else:
        fail("Node.js not found"); errs.append("node")
    if run_ok("npm --version"):
        ok("npm ready")
    else:
        fail("npm not available"); errs.append("npm")
    if run_ok("mysql --version"):
        ok("MySQL client ready")
    else:
        warn("mysql CLI not in PATH, make sure MySQL service is running")
    if errs:
        fail(f"Missing: {', '.join(errs)}"); sys.exit(1)
    ok("Environment check passed")

# ==============================================================
#  Step 1: 配置 MySQL 数据库
# ==============================================================
def step1():
    header(1, "Configure MySQL Database")
    D = {"DB_NAME":"falcon_kds","DB_USER":"root","DB_PASS":"password","DB_HOST":"127.0.0.1","DB_PORT":"3306"}
    labels = [("DB_NAME","DB Name"),("DB_USER","Username"),("DB_PASS","Password"),("DB_HOST","Host"),("DB_PORT","Port")]
    print(f"\n  Current defaults:")
    for k,l in labels:
        print(f"    {l}: {D[k]}")
    print()
    cfg = {}
    for k,l in labels:
        v = input(f"  {l} [{D[k]}]: ").strip()
        cfg[k] = v if v else D[k]
    info(f"Using: {cfg['DB_USER']}@{cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}")

    # 生成 backend/conf/env.py
    info("Generating backend/conf/env.py ...")
    env_path = os.path.join(BACKEND_DIR, "conf", "env.py")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"""import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_ENGINE = "django.db.backends.mysql"
DATABASE_NAME = '{cfg["DB_NAME"]}'
DATABASE_HOST = "{cfg["DB_HOST"]}"
DATABASE_PORT = {cfg["DB_PORT"]}
DATABASE_USER = "{cfg["DB_USER"]}"
DATABASE_PASSWORD = "{cfg["DB_PASS"]}"
TABLE_PREFIX = "dvadmin_"
DEBUG = True
ENABLE_LOGIN_ANALYSIS_LOG = True
LOGIN_NO_CAPTCHA_AUTH = True
ALLOWED_HOSTS = ["*"]
COLUMN_EXCLUDE_APPS = []
""")
    ok("env.py generated")

    # 创建数据库
    info(f"Creating database {cfg['DB_NAME']} ...")
    sql = f"CREATE DATABASE IF NOT EXISTS `{cfg['DB_NAME']}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
    c, _ = run(
        f'mysql -h {cfg["DB_HOST"]} -P {cfg["DB_PORT"]} -u {cfg["DB_USER"]} -p{cfg["DB_PASS"]} -e "{sql}"',
        capture=True
    )
    if c != 0:
        warn("Auto-create failed. Please create the database manually:")
        warn(f"  {sql}")
        input("  Press Enter after database is ready...")
    else:
        ok(f"Database {cfg['DB_NAME']} ready")
    return cfg

# ==============================================================
#  Step 2: 安装 Python 依赖
# ==============================================================
def step2():
    header(2, "Install Python Dependencies")
    info("Upgrading pip ...")
    run("python -m pip install --upgrade pip -q", capture=True)

    # 先安装核心依赖，避免 requirements.txt 中某些包拖后腿
    info("Installing core packages first ...")
    core_pkgs = [
        "django==4.2.30", "djangorestframework==3.14.0",
        "mysqlclient==2.2.4", "PyMySQL==1.1.0",
        "django-cors-headers==4.3.1", "django-comment-migrate==0.1.7",
        "django-redis==4.12.1", "whitenoise==6.6.0", "Pillow==10.1.0",
        "pycryptodome==3.20.0", "numpy==1.26.4",
    ]
    for pkg in core_pkgs:
        run(f"python -m pip install {pkg} -q", capture=True)

    info("Installing requirements.txt ...")
    req = os.path.join(PROJECT_ROOT, "requirements.txt")
    c, _ = run(f'python -m pip install -r "{req}"')
    if c != 0:
        warn("Batch install had errors, trying one by one ...")
        with open(req, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    run(f"python -m pip install {line} -q", capture=True)

    # 确保关键包都在
    info("Verifying extra required packages ...")
    extras = [
        "djangorestframework-simplejwt==5.3.1", "django-filter==23.5",
        "django-simple-captcha==0.6.0", "drf-yasg==1.21.7",
        "channels==4.0.0", "celery==5.3.6",
        "django-celery-beat==2.5.0", "django-celery-results==2.5.1",
        "web3==6.15.1", "py-solc-x==1.1.1",
        "scipy==1.12.0", "openpyxl==3.1.2", "pypinyin==0.49.0",
        "user-agents==2.2.0", "PyJWT==2.8.0", "requests==2.31.0",
    ]
    for pkg in extras:
        run(f"python -m pip install {pkg} -q", capture=True)
    ok("Python dependencies installed")

# ==============================================================
#  Step 3: 安装 Solidity 编译器
# ==============================================================
def step3():
    header(3, "Install Solidity Compiler")
    info("Installing solc 0.8.20 ...")
    c, _ = run("python -c \"import solcx; solcx.install_solc('0.8.20')\"", capture=True)
    if c != 0:
        warn("solc install failed, blockchain features may not work")
    else:
        ok("solc 0.8.20 installed")


# ==============================================================
#  Step 4: Django 数据库迁移
# ==============================================================
def step4():
    header(4, "Django Database Migration")
    info("Running makemigrations ...")
    c, o = run("python manage.py makemigrations", cwd=BACKEND_DIR, capture=True)
    if c != 0:
        # 如果 makemigrations 失败，尝试单独对 pqkds 做
        warn("makemigrations failed, trying app by app ...")
        run("python manage.py makemigrations system", cwd=BACKEND_DIR, capture=True)
        run("python manage.py makemigrations pqkds", cwd=BACKEND_DIR, capture=True)
    info("Running migrate ...")
    c, _ = run("python manage.py migrate", cwd=BACKEND_DIR)
    if c != 0:
        fail("migrate failed, check DB connection"); sys.exit(1)
    ok("Database migration complete")

# ==============================================================
#  Step 5: 初始化系统数据 (菜单/角色/权限/管理员)
# ==============================================================
def step5():
    header(5, "Initialize System Data")

    # 5a: 运行 DVAdmin 基础初始化 (部门/角色/用户/菜单/权限等)
    info("Initializing base data (menus/roles/permissions) ...")
    init_py = os.path.join(BACKEND_DIR, "dvadmin", "system", "fixtures", "initialize.py")
    c, _ = run(f'python "{init_py}"', cwd=BACKEND_DIR)
    if c != 0:
        warn("Base init returned non-zero, continuing ...")

    # 5b: 初始化 PQKDS 菜单 + 强制更新菜单排序/可见性 + 创建管理员
    info("Initializing PQKDS menus + admin account ...")
    helper = os.path.join(BACKEND_DIR, "_init_helper.py")
    # 写入一个完整的初始化脚本
    _write_init_helper(helper)
    c, o = run(f'python "{helper}"', cwd=BACKEND_DIR, capture=True)
    if c != 0:
        warn(f"Init helper output: {o[:500]}")
    else:
        for line in o.strip().splitlines():
            if line.strip():
                ok(line.strip())
    # 清理临时文件
    try: os.remove(helper)
    except: pass

    ok("System data initialized")
    print("\n    >>> Admin account: superadmin")
    print("    >>> Admin password: admin123456")


def _write_init_helper(path):
    """生成初始化辅助脚本，确保菜单顺序和可见性正确"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(r'''# -*- coding: utf-8 -*-
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

# ── 1. 初始化 PQKDS 菜单(含区块链管理 + 日志管理) ──
from pqkds.fixtures.initialize import Initialize
Initialize(app='pqkds').run()
print('PQKDS menus initialized')

# ── 2. 强制更新菜单排序和可见性 ──
from dvadmin.system.models import Menu

# 删除数据库中的"首页"菜单(前端 handleMenu 已硬编码添加，数据库中的会导致重复)
dup_home = Menu.objects.filter(component_name='home', web_path='/')
if dup_home.exists():
    dup_home.delete()
    print('Removed duplicate home menu from DB (frontend adds it automatically)')

# 按 web_path 更新顶级目录排序
CATALOG_ORDER = {
    '/system':  {'sort': 2, 'visible': True, 'name': '系统管理'},
    '/pqkds':   {'sort': 3, 'visible': True, 'name': '区块链管理'},
    '/log':     {'sort': 4, 'visible': True, 'name': '日志管理'},
}
# 区块链管理子菜单
PQKDS_CHILDREN = {
    'pqkdsDashboard':   {'sort': 1, 'visible': True, 'name': '系统概览'},
    'pqkdsBlockchain':  {'sort': 2, 'visible': True, 'name': '区块链配置'},
    'pqkdsNodes':       {'sort': 3, 'visible': True, 'name': '节点管理'},
    'pqkdsKeyPool':     {'sort': 4, 'visible': True, 'name': '密钥预分配'},
    'pqkdsSessions':    {'sort': 5, 'visible': True, 'name': '会话管理'},
}
# 日志管理子菜单
LOG_CHILDREN = {
    'operationLog': {'sort': 1, 'visible': True, 'name': '操作日志'},
}
# 系统管理子菜单
SYS_CHILDREN = {
    'menu':          {'sort': 1, 'visible': True, 'name': '菜单管理'},
    'dept':          {'sort': 2, 'visible': True, 'name': '部门管理'},
    'role':          {'sort': 3, 'visible': True, 'name': '角色管理'},
    'user':          {'sort': 4, 'visible': True, 'name': '用户管理'},
    'messageCenter': {'sort': 5, 'visible': True, 'name': '消息中心'},
    'apiWhiteList':  {'sort': 6, 'visible': True, 'name': '接口白名单'},
}

updated = 0
for comp_name, props in {**PQKDS_CHILDREN, **LOG_CHILDREN, **SYS_CHILDREN}.items():
    qs = Menu.objects.filter(component_name=comp_name)
    if qs.exists():
        qs.update(sort=props['sort'], visible=props['visible'], name=props['name'])
        updated += 1
for web_path, props in CATALOG_ORDER.items():
    qs = Menu.objects.filter(web_path=web_path, parent__isnull=True)
    if qs.exists():
        qs.update(sort=props['sort'], visible=props['visible'], name=props['name'])
        updated += 1

# 删除旧的 pqkdsLogs 菜单(已移到顶级日志管理下)
old_pqkds_logs = Menu.objects.filter(component_name='pqkdsLogs')
if old_pqkds_logs.exists():
    old_pqkds_logs.delete()
    print('Removed old pqkdsLogs menu entry')

# 删除登录日志菜单(已移除该模块)
old_login_log = Menu.objects.filter(component_name='loginLog')
if old_login_log.exists():
    old_login_log.delete()
    print('Removed loginLog menu entry')

print(f'Menu order updated: {updated} items')

# ── 3. 收集静态文件 ──
from django.core.management import call_command
call_command('collectstatic', '--noinput', verbosity=0)
print('Static files collected')

# ── 4. 创建/重置管理员账号 superadmin ──
from dvadmin.system.models import Users
u, created = Users.objects.get_or_create(
    username='superadmin',
    defaults={
        'is_superuser': True, 'is_staff': True, 'is_active': True,
        'name': '超级管理员', 'user_type': 0
    }
)
u.set_password('admin123456')
u.is_superuser = True
u.is_staff = True
u.save()
print('superadmin account: ' + ('created' if created else 'exists, password reset'))

# ── 5. 给 admin 角色分配所有菜单权限 ──
from dvadmin.system.models import Role, RoleMenuPermission, RoleMenuButtonPermission, MenuButton
try:
    admin_role = Role.objects.filter(key='admin').first()
    if admin_role:
        all_menus = Menu.objects.all()
        for menu in all_menus:
            RoleMenuPermission.objects.get_or_create(role=admin_role, menu=menu)
            for btn in MenuButton.objects.filter(menu=menu):
                RoleMenuButtonPermission.objects.get_or_create(role=admin_role, menu_button=btn)
        # 确保 superadmin 拥有 admin 角色
        u.role.add(admin_role)
        print(f'Admin role permissions synced ({all_menus.count()} menus)')
    else:
        print('No admin role found, skipping permission sync')
except Exception as e:
    print(f'Permission sync warning: {e}')
''')

# ==============================================================
#  Step 6: 安装前端依赖
# ==============================================================
def step6():
    header(6, "Install Frontend Dependencies")
    node_check = os.path.join(WEB_DIR, "node_modules", "vue", "package.json")
    if os.path.exists(node_check):
        ok("node_modules already exists, skipping")
        return
    info("Running npm install (may take 2~5 min) ...")
    c, _ = run("npm install", cwd=WEB_DIR, timeout=600)
    if c != 0:
        warn("npm install failed, retrying with China mirror ...")
        c, _ = run("npm install --registry=https://registry.npmmirror.com", cwd=WEB_DIR, timeout=600)
        if c != 0:
            fail("Frontend dependency install failed"); sys.exit(1)
    ok("Frontend dependencies installed")


# ==============================================================
#  Step 7: 部署验证
# ==============================================================
def step7():
    header(7, "Verify Deployment")

    # 7a: Django check
    info("Checking Django config ...")
    c, o = run("python manage.py check", cwd=BACKEND_DIR, capture=True)
    if c == 0:
        ok("Django check passed")
    else:
        warn(f"Django check warnings: {o[:200]}")

    # 7b: 数据库连接
    info("Checking database connection ...")
    helper = os.path.join(BACKEND_DIR, "_check_db.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write(
            "import os,django\n"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','application.settings')\n"
            "django.setup()\n"
            "from django.db import connection\n"
            "connection.cursor().execute('SELECT 1')\n"
            "print('DB OK')\n"
        )
    c, o = run(f'python "{helper}"', cwd=BACKEND_DIR, capture=True)
    try: os.remove(helper)
    except: pass
    if c == 0:
        ok("Database connection OK")
    else:
        fail("Database connection failed!")

    # 7c: DLL 文件检查
    info("Checking DLL files ...")
    dll_ok = True
    for p in ["falcon/falcon512.dll", "kyber/libpqcrystals_kyber512_ref.dll"]:
        full = os.path.join(BACKEND_DIR, p)
        if not os.path.exists(full):
            warn(f"Missing: {p}"); dll_ok = False
    if dll_ok:
        ok("Falcon/Kyber DLL files ready")

    # 7d: 前端检查
    info("Checking frontend ...")
    if os.path.exists(os.path.join(WEB_DIR, "node_modules", "vue", "package.json")):
        ok("Frontend dependencies ready")
    else:
        warn("Frontend node_modules incomplete")

    # 7e: 菜单数据验证
    info("Verifying menu data ...")
    helper = os.path.join(BACKEND_DIR, "_check_menu.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write(
            "import os,django\n"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','application.settings')\n"
            "django.setup()\n"
            "from dvadmin.system.models import Menu\n"
            "tops = Menu.objects.filter(parent__isnull=True).order_by('sort')\n"
            "for t in tops:\n"
            "    print(f'{t.sort}. {t.name}')\n"
            "    children = Menu.objects.filter(parent_id=t.id).order_by('sort')\n"
            "    for c in children:\n"
            "        print(f'   {c.sort}. {c.name}')\n"
        )
    c, o = run(f'python "{helper}"', cwd=BACKEND_DIR, capture=True)
    try: os.remove(helper)
    except: pass
    if c == 0 and o.strip():
        ok("Menu structure:")
        for line in o.strip().splitlines():
            print(f"    {line}")
    else:
        warn("Could not verify menu structure")


# ==============================================================
#  主流程
# ==============================================================
def main():
    print("\n" + "="*60)
    print("  PQKDS - 后量子密钥分发系统")
    print("  一键部署脚本")
    print("="*60)

    step0()       # 环境检查
    cfg = step1() # MySQL 配置
    step2()       # Python 依赖
    step3()       # Solidity 编译器
    step4()       # 数据库迁移
    step5()       # 初始化数据 (菜单/权限/管理员)
    step6()       # 前端依赖
    step7()       # 部署验证

    print(f"""
{'='*60}
  部署完成!
{'='*60}

  启动后端:
    cd backend
    python manage.py runserver 0.0.0.0:8000

  启动前端:
    cd web
    npm run dev

  或者双击: start.bat (同时启动前后端)

  访问地址:
    前端: http://localhost:8081
    后端: http://localhost:8000
    账号: superadmin / admin123456

  侧边栏菜单:
    首页
    系统管理
      ├─ 菜单管理
      ├─ 部门管理
      ├─ 角色管理
      ├─ 用户管理
      ├─ 消息中心
      └─ 接口白名单
    区块链管理
      ├─ 系统概览
      ├─ 区块链配置
      ├─ 节点管理
      ├─ 密钥预分配
      └─ 会话管理
    日志管理
      └─ 操作日志
{'='*60}
""")

if __name__ == "__main__":
    main()