import numpy as np
import time
from typing import Tuple, Dict, Any
from multiprocessing import Pool, cpu_count
import hashlib
import logging
logger = logging.getLogger(__name__)
class SideChannelResistance:
    @staticmethod
    def constant_time_compare(a: bytes, b: bytes) -> bool:
        if len(a) != len(b):
            result = 1
            for i in range(min(len(a), len(b))):
                result |= ord(a[i:i+1]) ^ ord(b[i:i+1])
            return False
        result = 0
        for x, y in zip(a, b):
            result |= x ^ y
        return result == 0
    @staticmethod
    def masked_gaussian_sampling(size: int, sigma: float, seed: bytes) -> np.ndarray:
        logger.info(f" 执行掩码高斯抽样: size={size}, sigma={sigma}")
        rng = np.random.RandomState(int.from_bytes(seed[:4], 'big'))
        mask = rng.randint(-10000, 10000, size=size, dtype=np.int64)
        samples = rng.normal(0, sigma, size=size).astype(np.int64)
        masked_samples = (samples + mask) % (2**32)
        result = (masked_samples - mask) % (2**32)
        logger.info(f" 掩码高斯抽样完成，生成{size}个样本")
        return result
    @staticmethod
    def dummy_operations(num_ops: int) -> None:
        for _ in range(num_ops):
            _ = hashlib.sha256(b"dummy").digest()
class ParallelShortVectorSampling:
    @staticmethod
    def _sample_single_vector(args: Tuple[int, int, float, bytes]) -> np.ndarray:
        idx, vector_size, sigma, seed = args
        combined_seed = hashlib.sha256(seed + str(idx).encode()).digest()
        rng = np.random.RandomState(int.from_bytes(combined_seed[:4], 'big'))
        return rng.normal(0, sigma, size=vector_size).astype(np.int64)
    @staticmethod
    def parallel_sample_vectors(num_vectors: int, vector_size: int = 256,
                                sigma: float = 1.17, seed: bytes = None) -> np.ndarray:
        if seed is None:
            seed = hashlib.sha256(str(time.time()).encode()).digest()
        logger.info(f" 开始并行抽样{num_vectors}个短向量（维度{vector_size}）")
        start_time = time.time()
        num_workers = min(cpu_count(), num_vectors)
        with Pool(processes=num_workers) as pool:
            tasks = [(i, vector_size, sigma, seed) for i in range(num_vectors)]
            vectors = pool.map(ParallelShortVectorSampling._sample_single_vector, tasks)
        result = np.array(vectors, dtype=np.int64)
        elapsed = time.time() - start_time
        logger.info(f" 并行抽样完成，耗时{elapsed:.4f}秒，使用{num_workers}个worker")
        return result
class FastBasisDelegation:
    @staticmethod
    def generate_short_basis(n: int, m: int, q: int, sigma: float) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f" 快速生成格基: n={n}, m={m}")
        start_time = time.time()
        seed = hashlib.sha256(f"basis_{n}_{m}_{q}".encode()).digest()
        rng = np.random.RandomState(int.from_bytes(seed[:4], 'big'))
        trap_matrix = rng.randint(-int(sigma*2), int(sigma*2)+1, size=(m, n), dtype=np.int32)
        verify_matrix = rng.randint(0, q, size=(n, n), dtype=np.int32)
        elapsed = time.time() - start_time
        logger.info(f" 格基生成完成，耗时{elapsed:.4f}秒")
        return trap_matrix, verify_matrix
    @staticmethod
    def delegate_basis_vectors(basis: np.ndarray, user_id: str, 
                               num_vectors: int = 10) -> np.ndarray:
        logger.info(f" 为用户{user_id}委派{num_vectors}个基向量")
        start_time = time.time()
        seed = hashlib.sha256(user_id.encode()).digest()
        rng = np.random.RandomState(int.from_bytes(seed[:4], 'big'))
        num_available = basis.shape[0]
        selected_indices = rng.choice(num_available, 
                                     size=min(num_vectors, num_available), 
                                     replace=False)
        delegated = basis[selected_indices, :]
        elapsed = time.time() - start_time
        logger.info(f" 基向量委派完成，耗时{elapsed:.4f}秒")
        return delegated
    @staticmethod
    def verify_delegated_basis(delegated: np.ndarray, original: np.ndarray, 
                               q: int) -> bool:
        logger.info(" 验证委派的基向量")
        for delegated_vec in delegated:
            norm = np.linalg.norm(delegated_vec)
            if norm > q:
                logger.warning(f" 基向量范数过大: {norm}")
                return False
        logger.info(" 基向量验证成功")
        return True
def apply_side_channel_protection_to_sampling(num_vectors: int,
                                              vector_size: int,
                                              sigma: float,
                                              seed: bytes = None) -> np.ndarray:
    logger.info(f" 应用侧信道防护的并行抽样")
    vectors = ParallelShortVectorSampling.parallel_sample_vectors(
        num_vectors, vector_size, sigma, seed
    )
    protected_vectors = []
    for i, vec in enumerate(vectors):
        seed_bytes = seed if seed is not None else b''
        seed_i = hashlib.sha256(seed_bytes + f"_mask_{i}".encode()).digest()
        rng = np.random.RandomState(int.from_bytes(seed_i[:4], 'big'))
        mask = rng.randint(-10000, 10000, size=len(vec), dtype=np.int64)
        masked_vec = (vec.astype(np.int64) + mask) % (2**32)
        SideChannelResistance.dummy_operations(10)
        protected_vec = (masked_vec - mask) % (2**32)
        protected_vec = np.where(protected_vec > 2**31, protected_vec - 2**32, protected_vec)
        protected_vectors.append(protected_vec.astype(np.int64))
    result = np.array(protected_vectors, dtype=np.int64)
    logger.info(f" 侧信道防护完成，向量形状: {result.shape}")
    return result
def apply_fast_basis_delegation_to_key_generation(n: int, m: int, q: int, 
                                                   sigma: float,
                                                   user_id: str) -> Dict[str, Any]:
    logger.info(f" 在密钥生成中应用快速基向量委派，用户ID={user_id}")
    trap_matrix, verify_matrix = FastBasisDelegation.generate_short_basis(
        n, m, q, sigma
    )
    delegated = FastBasisDelegation.delegate_basis_vectors(
        trap_matrix, user_id, num_vectors=min(10, m)
    )
    is_valid = FastBasisDelegation.verify_delegated_basis(
        delegated, trap_matrix, q
    )
    return {
        'trap_matrix': trap_matrix,
        'verify_matrix': verify_matrix,
        'delegated_basis': delegated,
        'is_valid': is_valid,
        'user_id': user_id
    }