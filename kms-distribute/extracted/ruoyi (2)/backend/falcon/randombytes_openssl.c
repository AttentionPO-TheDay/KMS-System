/*
 * randombytes_openssl.c —— 为 Falcon 共享库补齐 randombytes 实现
 * ---------------------------------------------------------------------------
 * 背景：
 *   Falcon 参考实现的 nist.c 只**声明**了 randombytes，未提供定义
 *   （原设计由 NIST KAT 测试框架注入）。直接编译成共享库会得到
 *   `undefined symbol: randombytes`，ctypes.CDLL 加载失败。
 *
 * 实现：
 *   使用 OpenSSL 的 RAND_bytes 作为密码学安全随机源。
 *   Python 镜像里 cryptography/cffi 已依赖 OpenSSL，运行时必然可用。
 *
 * 签名须与 nist.c 中的声明完全一致：
 *   int randombytes(unsigned char *x, unsigned long long xlen);
 */

#include <openssl/rand.h>
#include <stddef.h>

int
randombytes(unsigned char *x, unsigned long long xlen)
{
    /*
     * RAND_bytes 的第二个参数是 int，而 xlen 为 unsigned long long，
     * 需分块调用以免大长度时溢出。
     */
    while (xlen > 0) {
        int chunk = (xlen > 1048576ULL) ? 1048576 : (int)xlen;
        if (RAND_bytes(x, chunk) != 1) {
            return -1;
        }
        x += chunk;
        xlen -= (unsigned long long)chunk;
    }
    return 0;
}

/*
 * falcon_inner_get_seed —— Falcon 私钥生成时的种子来源
 * ---------------------------------------------------------------------------
 * inner.h 中声明为：int Zf(get_seed)(void *seed, size_t seed_len);
 * 参考实现原本也依赖 KAT 框架提供（Makefile 的 katrng.o），源码中无定义，
 * 缺失会导致 `undefined symbol: falcon_inner_get_seed`。
 *
 * 语义即「用密码学安全随机数填满 seed」，因此直接复用 randombytes。
 * 内部符号名由 Falcon 的 Zf 宏拼装：无 FALCON_AVX2 时为
 * falcon_inner_get_seed；用别名同时导出，令两种命名都能解析。
 */
int
falcon_inner_get_seed(void *seed, size_t seed_len)
{
    return randombytes((unsigned char *)seed, (unsigned long long)seed_len);
}

/* 兼容 Zf 宏展开出的符号名 */
int falcon_get_seed(void *seed, size_t seed_len)
    __attribute__((alias("falcon_inner_get_seed")));
