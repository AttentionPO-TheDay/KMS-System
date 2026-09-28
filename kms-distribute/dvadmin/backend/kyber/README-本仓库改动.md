# Kyber 源码（本仓库有改动，勿直接覆盖）

本目录是 **pq-crystals/kyber `v3.0` 标签**的源码，即 NIST **round-3** 版本。
**不是** ML-KEM（FIPS 203）。

> ⚠️ 这一点必须写死在这里，因为它踩过一次：
> 本目录此前是一份 **ML-KEM** 源码，但目录名、`.so` 文件名
> （`libpqcrystals_kyber768_ref.so`）、以及 `Kyber768_META.yml` 里的
> `name: Kyber768` **全是 round-3 的** —— 只凭名字判断必然误判。
> 而两者解错了**不报错**（KEM 无发送方认证，只会返回另一个共享密钥），
> 所以"跑通了"证明不了任何事。

## 与上游的差异（仅一处）

`ref/` 下**移植了后续版本才有的 derand API**：

| 文件 | 新增 |
|---|---|
| `ref/kem.c` / `ref/kem.h` | `crypto_kem_keypair_derand` |
| `ref/indcpa.c` / `ref/indcpa.h` | `indcpa_keypair_derand` |

原因：本项目的**无证书 Kyber** 链路
（`pqkds/certificateless_kyber_dll_fusion.py`）从 CL 私钥经 SHAKE-256 派生
64 字节 coins，再用 `keypair_derand` 生成密钥对，以保证
「同一 CL 私钥 + 同一身份 → 同一 Kyber 密钥对」。
v3.0 原版只有随机版 `crypto_kem_keypair`，没有它。

**移植的边界：只改变随机数从哪里来。** KEM 数学、格运算、编解码、
共享密钥派生方式**一律未动** —— 所以线上格式与 v3.0 完全一致，
浏览器端的 round-3 实现仍与之互通（有逐字节的共享密钥比对用例守着：
`共享密钥相同` 是唯一有意义的判据）。

coins 布局与后续版本一致：前 32 字节 `d` 作密钥种子，后 32 字节 `z` 作拒绝值。
`z` **必须由 `crypto_kem_keypair_derand` 自己填** —— 包装函数拿不到 coins，
少了它解封走拒绝分支会返回未初始化内存，且不报错。

## `avx2/` 未同步移植

`avx2/` 是 round-3 原版，**没有** derand。这不影响运行：
`docker_env/django/Dockerfile` 只用 `ref/`（`build_shared_libs.sh` 的入参）。

但若日后要改用 avx2，**必须先补上同样的 derand 移植**，
否则无证书 Kyber 会以 `undefined symbol: ..._keypair_derand` 失败 ——
而我们**没有**在这里盲改它：avx2 需要 AVX2 CPU 才能编译与验证，
改一份无法验证的密码学代码，比留一个写明的缺口更糟。

## 构建

`build_shared_libs.sh` 由 Dockerfile 在镜像构建期调用，产物是 `.so`（不入库）。
`ref/` 下**不应**出现 `.a` 静态库 —— 那会把"变体/版本搞错"掩盖成
"看着像已经构建过了"。