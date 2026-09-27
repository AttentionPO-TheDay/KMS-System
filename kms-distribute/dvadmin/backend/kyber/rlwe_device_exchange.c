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

// 辅助函数：保存数据到文件
int save_to_file(const char *filename, const uint8_t *data, size_t len) {
    FILE *f = fopen(filename, "wb");
    if (!f) {
        printf("无法打开文件 %s 进行写入\n", filename);
        return -1;
    }
    
    size_t written = fwrite(data, 1, len, f);
    fclose(f);
    
    if (written != len) {
        printf("写入文件 %s 失败\n", filename);
        return -1;
    }
    
    return 0;
}

// 辅助函数：从文件读取数据
int load_from_file(const char *filename, uint8_t *data, size_t len) {
    FILE *f = fopen(filename, "rb");
    if (!f) {
        printf("无法打开文件 %s 进行读取\n", filename);
        return -1;
    }
    
    size_t read_bytes = fread(data, 1, len, f);
    fclose(f);
    
    if (read_bytes != len) {
        printf("从文件 %s 读取失败\n", filename);
        return -1;
    }
    
    return 0;
}

void alice_generate_keys() {
    // 定义Kyber-768所需的密钥长度
    #define PUBLIC_KEY_LEN  pqcrystals_kyber768_ref_PUBLICKEYBYTES
    #define SECRET_KEY_LEN  pqcrystals_kyber768_ref_SECRETKEYBYTES
    
    printf("=== Alice设备：生成密钥对 ===\n");
    
    uint8_t public_key[PUBLIC_KEY_LEN] = {0};
    uint8_t secret_key[SECRET_KEY_LEN] = {0};
    
    int ret = pqcrystals_kyber768_ref_keypair(public_key, secret_key);
    if (ret != 0) {
        printf("错误：密钥生成失败！\n");
        return;
    }
    
    printf("成功生成密钥对\n");
    print_hex("公钥（前32字节）", public_key, 32);
    
    // 保存密钥到文件
    save_to_file("alice_public.key", public_key, PUBLIC_KEY_LEN);
    save_to_file("alice_secret.key", secret_key, SECRET_KEY_LEN);
    
    printf("密钥对已保存到文件：alice_public.key 和 alice_secret.key\n");
}

void bob_generate_shared_key() {
    // 定义Kyber-768所需的密钥和密文长度
    #define PUBLIC_KEY_LEN  pqcrystals_kyber768_ref_PUBLICKEYBYTES
    #define CIPHERTEXT_LEN  pqcrystals_kyber768_ref_CIPHERTEXTBYTES
    #define SHARED_KEY_LEN  pqcrystals_kyber768_ref_BYTES
    
    printf("\n=== Bob设备：生成共享密钥 ===\n");
    
    // 读取Alice的公钥
    uint8_t alice_public_key[PUBLIC_KEY_LEN] = {0};
    if (load_from_file("alice_public.key", alice_public_key, PUBLIC_KEY_LEN) != 0) {
        return;
    }
    
    printf("已读取Alice的公钥\n");
    print_hex("Alice公钥（前32字节）", alice_public_key, 32);
    
    // 生成共享密钥和密文
    uint8_t shared_key[SHARED_KEY_LEN] = {0};
    uint8_t ciphertext[CIPHERTEXT_LEN] = {0};
    
    int ret = pqcrystals_kyber768_ref_enc(ciphertext, shared_key, alice_public_key);
    if (ret != 0) {
        printf("错误：密钥封装失败！\n");
        return;
    }
    
    printf("成功生成共享密钥和密文\n");
    print_hex("共享密钥", shared_key, SHARED_KEY_LEN);
    
    // 保存密文和共享密钥到文件
    save_to_file("bob_ciphertext.bin", ciphertext, CIPHERTEXT_LEN);
    save_to_file("bob_shared.key", shared_key, SHARED_KEY_LEN);
    
    printf("密文已保存到文件：bob_ciphertext.bin\n");
    printf("共享密钥已保存到文件：bob_shared.key\n");
}

void alice_recover_shared_key() {
    // 定义Kyber-768所需的密钥和密文长度
    #define SECRET_KEY_LEN  pqcrystals_kyber768_ref_SECRETKEYBYTES
    #define CIPHERTEXT_LEN  pqcrystals_kyber768_ref_CIPHERTEXTBYTES
    #define SHARED_KEY_LEN  pqcrystals_kyber768_ref_BYTES
    
    printf("\n=== Alice设备：恢复共享密钥 ===\n");
    
    // 读取Alice的私钥
    uint8_t secret_key[SECRET_KEY_LEN] = {0};
    if (load_from_file("alice_secret.key", secret_key, SECRET_KEY_LEN) != 0) {
        return;
    }
    
    // 读取Bob的密文
    uint8_t ciphertext[CIPHERTEXT_LEN] = {0};
    if (load_from_file("bob_ciphertext.bin", ciphertext, CIPHERTEXT_LEN) != 0) {
        return;
    }
    
    printf("已读取密文和私钥\n");
    
    // 恢复共享密钥
    uint8_t shared_key[SHARED_KEY_LEN] = {0};
    
    int ret = pqcrystals_kyber768_ref_dec(shared_key, ciphertext, secret_key);
    if (ret != 0) {
        printf("错误：密钥解封装失败！\n");
        return;
    }
    
    printf("成功恢复共享密钥\n");
    print_hex("共享密钥", shared_key, SHARED_KEY_LEN);
    
    // 保存共享密钥到文件
    save_to_file("alice_shared.key", shared_key, SHARED_KEY_LEN);
    printf("共享密钥已保存到文件：alice_shared.key\n");
    
    // 验证密钥是否匹配（在真实场景中，两个设备不会直接比较，这里只是演示）
    uint8_t bob_key[SHARED_KEY_LEN] = {0};
    if (load_from_file("bob_shared.key", bob_key, SHARED_KEY_LEN) == 0) {
        if (memcmp(shared_key, bob_key, SHARED_KEY_LEN) == 0) {
            printf("\n验证成功：Alice和Bob生成了相同的共享密钥！\n");
        } else {
            printf("\n验证失败：密钥不匹配！\n");
        }
    }
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("用法: %s [alice|bob|verify]\n", argv[0]);
        printf("  alice  - 生成Alice的密钥对\n");
        printf("  bob    - 使用Alice的公钥生成共享密钥和密文\n");
        printf("  verify - Alice使用密文恢复共享密钥并验证\n");
        return 1;
    }
    
    if (strcmp(argv[1], "alice") == 0) {
        alice_generate_keys();
    } else if (strcmp(argv[1], "bob") == 0) {
        bob_generate_shared_key();
    } else if (strcmp(argv[1], "verify") == 0) {
        alice_recover_shared_key();
    } else {
        printf("未知命令: %s\n", argv[1]);
        return 1;
    }
    
    return 0;
} 