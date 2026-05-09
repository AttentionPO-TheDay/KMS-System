#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ref/api.h"
#include "ref/randombytes.h"

// 辅助函数：打印字节数组为十六进制
void print_hex(const char *prefix, const uint8_t *bytes, size_t len) {
    printf("%s: ", prefix);
    for (size_t i = 0; i < len; i++) {
        printf("%02x", bytes[i]);
    }
    printf("\n");
}

// 使用Kyber-768进行RLWE密钥协商的示例
int main() {
    int ret = 0;
    
    // 定义Kyber-768所需的密钥和密文长度
    #define PUBLIC_KEY_LEN  pqcrystals_kyber768_ref_PUBLICKEYBYTES
    #define SECRET_KEY_LEN  pqcrystals_kyber768_ref_SECRETKEYBYTES
    #define CIPHERTEXT_LEN  pqcrystals_kyber768_ref_CIPHERTEXTBYTES
    #define SHARED_KEY_LEN  pqcrystals_kyber768_ref_BYTES
    
    printf("=== RLWE 密钥协商示例（基于Kyber-768）===\n\n");
    
    // 1. Alice生成密钥对
    printf("1. Alice生成密钥对...\n");
    uint8_t alice_public_key[PUBLIC_KEY_LEN] = {0};
    uint8_t alice_secret_key[SECRET_KEY_LEN] = {0};
    
    ret = pqcrystals_kyber768_ref_keypair(alice_public_key, alice_secret_key);
    if (ret != 0) {
        printf("错误：Alice密钥生成失败！\n");
        return -1;
    }
    
    printf("   Alice生成了公钥（%d字节）和私钥（%d字节）\n", PUBLIC_KEY_LEN, SECRET_KEY_LEN);
    print_hex("   Alice公钥（前32字节）", alice_public_key, 32);
    
    // 2. Alice将公钥发送给Bob
    printf("\n2. Alice将公钥发送给Bob...\n");
    
    // 3. Bob使用Alice的公钥生成共享密钥和密文
    printf("\n3. Bob使用Alice的公钥生成共享密钥和密文...\n");
    uint8_t bob_shared_key[SHARED_KEY_LEN] = {0};
    uint8_t ciphertext[CIPHERTEXT_LEN] = {0};
    
    ret = pqcrystals_kyber768_ref_enc(ciphertext, bob_shared_key, alice_public_key);
    if (ret != 0) {
        printf("错误：Bob的密钥封装失败！\n");
        return -1;
    }
    
    printf("   Bob生成了共享密钥（%d字节）和密文（%d字节）\n", SHARED_KEY_LEN, CIPHERTEXT_LEN);
    print_hex("   Bob的共享密钥", bob_shared_key, SHARED_KEY_LEN);
    print_hex("   发送给Alice的密文（前32字节）", ciphertext, 32);
    
    // 4. Bob将密文发送给Alice
    printf("\n4. Bob将密文发送给Alice...\n");
    
    // 5. Alice使用她的私钥和Bob的密文恢复共享密钥
    printf("\n5. Alice使用她的私钥和Bob的密文恢复共享密钥...\n");
    uint8_t alice_shared_key[SHARED_KEY_LEN] = {0};
    
    ret = pqcrystals_kyber768_ref_dec(alice_shared_key, ciphertext, alice_secret_key);
    if (ret != 0) {
        printf("错误：Alice的密钥解封装失败！\n");
        return -1;
    }
    
    print_hex("   Alice恢复的共享密钥", alice_shared_key, SHARED_KEY_LEN);
    
    // 6. 验证共享密钥是否一致
    printf("\n6. 验证Alice和Bob的共享密钥是否一致...\n");
    if (memcmp(alice_shared_key, bob_shared_key, SHARED_KEY_LEN) == 0) {
        printf("   成功！Alice和Bob已建立相同的共享密钥\n");
    } else {
        printf("   失败！Alice和Bob的共享密钥不同\n");
        return -1;
    }
    
    printf("\n=== RLWE密钥协商协议成功完成 ===\n");
    
    return 0;
} 