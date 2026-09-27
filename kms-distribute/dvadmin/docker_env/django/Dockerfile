FROM debian:bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

WORKDIR /backend

# build-essential / gcc: 后量子原生库需在构建期编译（见下方编译步骤）
# libssl-dev: 提供 OpenSSL 头文件与 -lcrypto，Falcon 的 randombytes 实现依赖它
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        gfortran \
        libjpeg62-turbo-dev \
        libssl-dev \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# cryptography 必须显式安装：
#   MySQL 8 默认使用 caching_sha2_password 认证，PyMySQL 在处理该认证时
#   需要 cryptography，否则 manage.py migrate 会以
#   "'cryptography' package is required for sha256_password or
#    caching_sha2_password auth methods" 失败——
#   迁移不执行则业务表全部缺失，PQKDS 所有接口都会 500。
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install setuptools wheel \
    && /opt/venv/bin/pip install -r /tmp/requirements.txt \
    && /opt/venv/bin/pip install django-restql gunicorn uvicorn cryptography

ENV PATH="/opt/venv/bin:$PATH"

COPY ./backend/ /backend/

# ---------------------------------------------------------------------------
# 编译后量子原生库
# ---------------------------------------------------------------------------
# 仓库只带 PQClean 的 C 源码，不带任何 .so/.dll，而 PQKDS 是通过 ctypes
# 在运行时加载它们的，因此必须在构建期编译，否则：
#   CL-Kyber  → 「Kyber动态库未找到或不可加载」
#   CL-Falcon → 「找不到可用的 falcon512.dll」
# 两个脚本内的注释记录了各自踩过的坑（randombytes / get_seed 未定义符号）。
RUN bash /backend/kyber/build_shared_libs.sh /backend/kyber/ref \
    && bash /backend/falcon/build_shared_lib.sh /backend

# 启动脚本需可执行（Windows 检出时可能丢失执行位）
RUN chmod +x /backend/start.sh

EXPOSE 8000
# 启动逻辑放在 start.sh：等待数据库 → 迁移 → gunicorn，并带重试，
# 避免数据库未就绪时迁移失败导致容器"运行但无表"（PQKDS 全部 500）。
CMD ["bash", "/backend/start.sh"]
