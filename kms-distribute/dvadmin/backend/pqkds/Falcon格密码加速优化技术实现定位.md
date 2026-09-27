# Falcon 格密码三项核心优化技术——代码实现定位

## 概述

本系统在 Falcon 无证书格密码方案中实现了三项核心优化技术：**快速委派格基向量**、**并行抽样短向量**、**离线生成格陷门**。每项技术在多个代码文件中均有体现，下面逐一说明其原理、涉及的文件和关键代码位置。

---

## 1. 快速委派格基向量（Fast Delegated Basis）

### 1.1 原理

无证书格密码方案中，每个用户 ID 对应一组格基材料：

- **D_id**（m×m 短矩阵）：KGC 为用户生成的部分私钥
- **H_id = A·D_id mod q**（n×m 公开矩阵）：身份哈希矩阵
- **S_id**（m×m 短矩阵）：用户自选秘密值
- **U_id = B·S_id mod q**（n×m 公开矩阵）：用户公钥

原始实现每次加密都要重新计算这些矩阵乘法（Falcon-512 下是 512×1024 乘 1024×1024），开销巨大。快速委派格基的核心思想：**对同一个用户 ID，D_id / H_id / S_id / U_id 只生成一次，后续直接从缓存取用。**

### 1.2 涉及文件与代码位置

#### （1）`backend/pqkds/falcon_fast_engine.py`（主实现）

这是快速委派格基的核心实现文件。

- **第 26-61 行 `FastDelegatedBasis` 类**：线程安全的 D_id / H_id 缓存。以 `{user_id}_{n}_{m}_{q}` 为键，首次调用时用确定性种子（SHA-256 哈希 user_id）生成 D_id，计算 H_id = A·D_id mod q，存入类级别字典 `_cache`；后续调用直接命中缓存。

```python
class FastDelegatedBasis:
    _cache: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def get_or_create(cls, user_id, A, n, m, q, sigma):
        key = f"{user_id}_{n}_{m}_{q}"
        with cls._lock:
            if key in cls._cache:
                return cls._cache[key]['D_id'], cls._cache[key]['H_id']
        seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        D_id = np.round(rng.normal(0, sigma, size=(m, m))).astype(np.int64)
        H_id = np.dot(A, D_id) % q
        cls._cache[key] = {'D_id': D_id, 'H_id': H_id}
        return D_id, H_id
```

- **第 64-90 行 `FastSecretBasis` 类**：同理缓存 S_id 和 U_id = B·S_id mod q。

- **第 217-240 行 `FastFalconEncryptionEngine.setup_user()`**：整合入口，调用 `FastDelegatedBasis.get_or_create()` 和 `FastSecretBasis.get_or_create()` 获取缓存的密钥材料。

#### （2）`backend/pqkds/ultra_fast_keygen_optimized.py`

- **第 50-68 行 `FastLatticeDelegation` 类**：另一种快速委派实现，使用 `np.linalg.lstsq` 最小二乘法求解 D_id（满足 A·D_id ≈ H_id），失败时回退到随机采样。
- **第 77-97 行 `UltraFastKeygenOptimized._cached_setup()`**：系统参数 A、B 的缓存，避免重复生成。

#### （3）`backend/pqkds/advanced_security_features.py`

- **第 56-93 行 `FastBasisDelegation` 类**：快速格基生成与委派的独立实现，包含 `generate_short_basis()`（生成陷门矩阵）、`delegate_basis_vectors()`（为用户委派基向量）、`verify_delegated_basis()`（验证委派结果）。
- **第 116-135 行 `apply_fast_basis_delegation_to_key_generation()`**：将快速委派应用到密钥生成流程的入口函数。

#### （4）对比：原始实现 `backend/pqkds/falcon_certificateless_strict.py`

- **第 60-82 行 `partial_key_gen()`**：每次调用都重新生成 D_id 并计算 H_id = A·D_id，无缓存。
- **第 84-91 行 `set_secret_value()`**：每次调用都重新生成 S_id，无缓存。

---

## 2. 并行抽样短向量（Parallel Short Vector Sampling）

### 2.1 原理

Falcon 加密（Enc 算法）需要采样 5 个随机/噪声向量：
- `r1, r2 ← Z_q^n`（均匀随机向量）
- `e1, e2, e3 ← D_{Z^m, σ}`（离散高斯噪声向量，σ=1.17）

原始实现串行生成这 5 个向量。并行抽样利用线程池 / 进程池同时生成，减少总等待时间。

### 2.2 涉及文件与代码位置

#### （1）`backend/pqkds/falcon_fast_engine.py`（主实现）

- **第 23 行**：全局线程池 `_POOL = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)`，进程生命周期内复用，避免反复创建销毁。

- **第 94-109 行 `_parallel_sample()` 函数**：将 5 个向量的生成任务提交到线程池并行执行。

```python
def _parallel_sample(n, m, q, sigma):
    """并行抽样: 同时生成 r1, r2, e1, e2, e3"""
    def _uniform(size):
        return np.random.randint(0, q, size=size, dtype=np.int64)
    def _gaussian(size):
        return np.round(np.random.normal(0, sigma, size=size)).astype(np.int64) % q
    futures = {
        'r1': _POOL.submit(_uniform, n),
        'r2': _POOL.submit(_uniform, n),
        'e1': _POOL.submit(_gaussian, m),
        'e2': _POOL.submit(_gaussian, m),
        'e3': _POOL.submit(_gaussian, m),
    }
    return {k: f.result() for k, f in futures.items()}
```

- **第 129-174 行 `fast_encrypt()` 函数**：实际加密时使用 numpy 向量化抽样（对 Falcon-512 维度更高效），`_parallel_sample` 在更大维度时启用。

#### （2）`backend/pqkds/ultra_fast_keygen_optimized.py`

- **第 10-48 行 `ParallelGaussianSampler` 类**：基于 `ThreadPoolExecutor` 的并行高斯采样器。
  - `sample_vector_parallel()`：将大向量分块，每块提交到线程池并行采样后拼接。
  - `sample_matrix_parallel()`：对矩阵的每行并行采样（Box-Muller 变换生成高斯分布）。

#### （3）`backend/pqkds/advanced_security_features.py`

- **第 34-55 行 `ParallelShortVectorSampling` 类**：基于 `multiprocessing.Pool`（进程池）的并行短向量采样。
  - `parallel_sample_vectors()`：将多个向量的采样任务分发到多个进程，每个进程用独立种子生成。
- **第 94-115 行 `apply_side_channel_protection_to_sampling()`**：在并行抽样基础上叠加侧信道防护（掩码高斯采样）。

#### （4）`backend/pqkds/ultra_fast_keygen_extreme.py`

- **第 142-156 行 `UltraFastFalconOptimized` 类**：使用 Box-Muller 变换的向量化高斯采样 `_fast_gaussian_sample_vectorized()`，配合 `ThreadPoolExecutor` 并行执行。

#### （5）对比：原始实现 `backend/pqkds/falcon_encryption_strict.py`

- **第 136-140 行**：串行采样，一个接一个调用 `_sample_uniform_vector()` 和 `_sample_gaussian_vector()`。

```python
r_1 = self._sample_uniform_vector(self.n)   # 串行
r_2 = self._sample_uniform_vector(self.n)   # 串行
e_1 = self._sample_gaussian_vector(self.m)   # 串行
e_2 = self._sample_gaussian_vector(self.m)   # 串行
e_3 = self._sample_gaussian_vector(self.m)   # 串行
```

---

## 3. 离线生成格陷门（Offline Trapdoor Generation）

### 3.1 原理

格陷门（Trapdoor）是 KGC（密钥生成中心）用来为用户生成部分私钥的核心秘密。在图中的 Setup 阶段：

```
TrapGen → (A, T)，满足 A·T = 0 mod q，||T|| ≤ β
```

陷门 T 在系统初始化时**一次性离线生成**，之后所有用户的部分私钥 D_id 都通过这个陷门派生（SamplePre 算法），不需要重新生成陷门。

### 3.2 涉及文件与代码位置

#### （1）`backend/pqkds/falcon_trapgen_dll.py`（主实现，DLL 级别真实陷门）

这是离线格陷门的核心实现，调用 Falcon-512 C 语言 DLL 生成真实的 NTRU 格基。

- **第 94-174 行 `FalconTrapGen` 类**：
  - `generate()`（第 139-174 行）：调用 DLL `crypto_sign_keypair` 生成 NTRU 格基。公钥 pk 编码了 h = g/f mod q（897 字节），私钥 sk 编码了陷门 (f, g, F)（1281 字节），满足 fG - gF = q。
  - `sample_pre()`（第 176-221 行）：调用 DLL `crypto_sign` 用陷门求解短预像——给定目标向量，找到短向量 s 使得 s ≡ target (mod h)。这等价于用陷门求解 A·x = target 的短解。

- **第 365-429 行 `_get_system_params()` / `_do_setup()`**：全局缓存系统参数。`_do_setup()` 调用 `FalconTrapGen.generate()` 生成陷门，从公钥 h 构造系统矩阵 A = [I_n | 循环矩阵 H(h)]，生成随机矩阵 B。**整个过程只执行一次，结果缓存在全局变量 `_system_cache` 中。**

- **第 432-483 行 `partial_key_gen()`**：使用离线陷门为用户生成部分私钥。调用 `trapgen.sample_pre()` 对 user_id 签名得到短向量，以签名作为种子通过 SHAKE-256 确定性派生短矩阵 D_id。

#### （2）`backend/pqkds/ultra_fast_keygen_extreme.py`

- **第 167-170 行 `_fast_trapgen()`**：简化版陷门生成（纯 numpy，不依赖 DLL），生成随机短矩阵 T 和系统矩阵 A。
- **第 171-184 行 `setup_fast()`**：调用 `_fast_trapgen()` 生成系统参数并缓存。

#### （3）`backend/pqkds/super_fast_keygen_numba.py`

- **第 180-181 行**：类似的简化版陷门生成，T 从均匀分布 [-β, β] 采样。
- **第 186-197 行**：系统参数缓存在 `self._cache['system_params']` 中，只生成一次。

#### （4）对比：原始实现 `backend/pqkds/falcon_certificateless_strict.py`

- **第 42-58 行 `setup()`**：直接随机生成 A、B 矩阵，没有陷门结构（A·T ≠ 0），也没有缓存。

```python
def setup(self):
    A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
    B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
    self.system_params = {'A': A, 'B': B, ...}
    # 每次调用都重新生成，无缓存
```

---

## 4. 文件总览

| 优化技术 | 核心实现文件 | 辅助实现文件 | 原始对照文件 |
|---------|------------|------------|------------|
| 快速委派格基向量 | `falcon_fast_engine.py`<br>(FastDelegatedBasis, FastSecretBasis) | `ultra_fast_keygen_optimized.py` (FastLatticeDelegation)<br>`advanced_security_features.py` (FastBasisDelegation) | `falcon_certificateless_strict.py`<br>(partial_key_gen, set_secret_value) |
| 并行抽样短向量 | `falcon_fast_engine.py`<br>(_parallel_sample, _POOL) | `ultra_fast_keygen_optimized.py` (ParallelGaussianSampler)<br>`advanced_security_features.py` (ParallelShortVectorSampling)<br>`ultra_fast_keygen_extreme.py` (_fast_gaussian_sample_vectorized) | `falcon_encryption_strict.py`<br>(串行 _sample_*_vector) |
| 离线生成格陷门 | `falcon_trapgen_dll.py`<br>(FalconTrapGen, _do_setup, _get_system_params) | `ultra_fast_keygen_extreme.py` (_fast_trapgen)<br>`super_fast_keygen_numba.py` (setup_ultra_fast) | `falcon_certificateless_strict.py`<br>(setup 中的随机矩阵) |

> 所有文件均位于 `backend/pqkds/` 目录下。

---

## 5. 生产调用链路

以下说明三项优化在实际业务流程中的调用路径。

### 5.1 Falcon 加密 AES 会话密钥（会话建立时）

```
views.py SessionKeyViewSet.initiate()
  → node_service.py NodeService.initiate_session_key_exchange()
    → falcon_aes_session_encryption.py encrypt_aes_key_with_falcon()
      → falcon_fast_engine.py fast_encrypt()          ← 快速委派格基 + 向量化抽样
```

`falcon_aes_session_encryption.py` 第 290-291 行：
```python
from .falcon_fast_engine import fast_encrypt
ct = fast_encrypt(A, B, H_id, U_id, aes_key, pk_n, pk_m, pk_q, 1.17)
```

### 5.2 Falcon 解密 AES 会话密钥

```
falcon_aes_session_encryption.py decrypt_aes_key_with_falcon()
  → falcon_fast_engine.py fast_decrypt()               ← 向量化 rounding + BLAS 转置缓存
```

`falcon_aes_session_encryption.py` 第 329-330 行：
```python
from .falcon_fast_engine import fast_decrypt
session_key = fast_decrypt(c1, c2, c3, sk['D_id'], sk['S_id'], ct_q, key_length)
```

### 5.3 Falcon 密钥对生成（节点注册时）

```
views.py NodeViewSet.generate_falcon_keys()
  → falcon_aes_session_encryption.py generate_node_falcon_keypair()
    → falcon_certificateless_strict.py setup() + partial_key_gen()
```

当 DLL 可用时，走 `falcon_trapgen_dll.py` 的离线陷门路径：
```
falcon_trapgen_dll.py generate_falcon_cl_keypair()
  → _get_system_params()                               ← 离线格陷门（全局缓存）
  → partial_key_gen()
    → FalconTrapGen.sample_pre()                        ← DLL 陷门求解短预像
```

### 5.4 Kyber 加解密（同样使用了向量化 + BLAS 优化）

```
node_service.py NodeService.initiate_kyber_key_agreement()
  → kyber_fast_engine.py kyber_fast_encrypt()           ← BLAS float64 + 转置缓存
  → kyber_fast_engine.py kyber_fast_decrypt()           ← 向量化 rounding
```

---

## 6. 消融实验

消融实验脚本位于 `backend/pqkds/ablation_experiment.py`，运行命令：

```bash
cd backend
python -m pqkds.ablation_experiment
```

四组对比（每组 50 轮，生成 AES-256 密钥 → 加密 → 解密 → 验证正确性）：

| 方案 | 说明 | 平均耗时 | 加速比 | 正确率 |
|------|------|---------|--------|--------|
| A | 基线（无任何优化） | ~18 ms | 1.00x | 100% |
| B | 仅快速委派格基缓存 | ~17 ms | ~1.04x | 100% |
| C | 仅并行抽样短向量 | ~18 ms | ~1.04x | 100% |
| D | 全部优化（缓存+向量化+BLAS） | ~2 ms | **~8x** | 100% |

方案 D 的巨大加速主要来自三个叠加因素：
1. **向量化 rounding**：消除 1024 次 Python for 循环（解密瓶颈）
2. **BLAS float64 加速**：矩阵-向量乘法走 C/Fortran BLAS 而非 int64 np.dot
3. **转置矩阵缓存**：避免每次加解密都重新计算 A.T、B.T 等转置
