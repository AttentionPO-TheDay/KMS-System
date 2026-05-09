import numpy as np
import hashlib
import logging
from typing import Tuple
logger = logging.getLogger(__name__)
class TrapGen:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, beta: int = 3072):
        self.n = n
        self.m = m
        self.q = q
        self.beta = beta
        logger.info(f"初始化TrapGen: n={n}, m={m}, q={q}, beta={beta}")
    def generate(self) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"TrapGen: 生成陷门矩阵")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        logger.info(f"生成A矩阵: 形状={A.shape}")
        T = np.random.randint(0, self.q, size=(self.m, self.m), dtype=np.int64)
        logger.info(f"生成T矩阵: 形状={T.shape}")
        return A, T
class LatticeSampler:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        logger.info(f"初始化LatticeSampler: n={n}, m={m}, q={q}, sigma={self.sigma}")
    def sample_chi_n(self) -> np.ndarray:
        samples = np.round(np.random.normal(0, self.sigma, size=self.n)).astype(np.int64)
        return samples % self.q
    def sample_chi_m(self) -> np.ndarray:
        samples = np.round(np.random.normal(0, self.sigma, size=self.m)).astype(np.int64)
        return samples % self.q
class MatrixHash:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        logger.info(f"初始化MatrixHash: n={n}, m={m}, q={q}")
    def hash_to_matrix(self, data: bytes, rows: int, cols: int) -> np.ndarray:
        matrix = np.zeros((rows, cols), dtype=np.int64)
        for i in range(rows):
            for j in range(cols):
                h = hashlib.sha256(data + bytes([i % 256, j % 256])).digest()
                matrix[i, j] = int.from_bytes(h[:8], 'big') % self.q
        return matrix