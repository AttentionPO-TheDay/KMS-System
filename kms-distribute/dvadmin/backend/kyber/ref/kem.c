#include <stddef.h>
#include <stdint.h>
#include "params.h"
#include "kem.h"
#include "indcpa.h"
#include "verify.h"
#include "symmetric.h"
#include "randombytes.h"

/*************************************************
* Name:        crypto_kem_keypair
*
* Description: Generates public and private key
*              for CCA-secure Kyber key encapsulation mechanism
*
* Arguments:   - uint8_t *pk: pointer to output public key
*                (an already allocated array of KYBER_PUBLICKEYBYTES bytes)
*              - uint8_t *sk: pointer to output private key
*                (an already allocated array of KYBER_SECRETKEYBYTES bytes)
*
* Returns 0 (success)
**************************************************/
int crypto_kem_keypair_derand(uint8_t pk[KYBER_PUBLICKEYBYTES],
                              uint8_t sk[KYBER_SECRETKEYBYTES],
                              const uint8_t coins[2*KYBER_SYMBYTES])
{
  size_t i;

  /* coins 布局与后续版本一致：前 32 字节 d 作密钥种子，后 32 字节 z 作拒绝值。
   *
   * ⚠️ z **必须在这里填**，不能留给调用方事后覆写：`crypto_kem_keypair`
   *    的入参里没有 coins。少了它，解封走拒绝分支时会退化成
   *    "返回全零/未初始化内存"，那是个不会报错的错误。
   *
   * ⚠️ 顺序也是刻意的：必须在算完 hash_h 之后再写 z。
   *    先写会被 indcpa_keypair_derand 之后的处理覆盖掉，
   *    而 sk 里位置相邻，混起来不会有任何报错。 */
  indcpa_keypair_derand(pk, sk, coins);
  for(i=0;i<KYBER_INDCPA_PUBLICKEYBYTES;i++)
    sk[i+KYBER_INDCPA_SECRETKEYBYTES] = pk[i];
  hash_h(sk+KYBER_SECRETKEYBYTES-2*KYBER_SYMBYTES, pk, KYBER_PUBLICKEYBYTES);
  /* Value z for pseudo-random output on reject */
  for(i=0;i<KYBER_SYMBYTES;i++)
    sk[KYBER_SECRETKEYBYTES-KYBER_SYMBYTES+i] = coins[KYBER_SYMBYTES+i];
  return 0;
}

int crypto_kem_keypair(uint8_t pk[KYBER_PUBLICKEYBYTES],
                       uint8_t sk[KYBER_SECRETKEYBYTES])
{
  uint8_t coins[2*KYBER_SYMBYTES];
  randombytes(coins, 2*KYBER_SYMBYTES);
  return crypto_kem_keypair_derand(pk, sk, coins);
}

/*************************************************
* Name:        crypto_kem_enc
*
* Description: Generates cipher text and shared
*              secret for given public key
*
* Arguments:   - uint8_t *ct: pointer to output cipher text
*                (an already allocated array of KYBER_CIPHERTEXTBYTES bytes)
*              - uint8_t *ss: pointer to output shared secret
*                (an already allocated array of KYBER_SSBYTES bytes)
*              - const uint8_t *pk: pointer to input public key
*                (an already allocated array of KYBER_PUBLICKEYBYTES bytes)
*
* Returns 0 (success)
**************************************************/
int crypto_kem_enc(uint8_t ct[KYBER_CIPHERTEXTBYTES],
                   uint8_t ss[KYBER_SSBYTES],
                   const uint8_t pk[KYBER_PUBLICKEYBYTES])
{
  uint8_t buf[2*KYBER_SYMBYTES];
  /* Will contain key, coins */
  uint8_t kr[2*KYBER_SYMBYTES];

  randombytes(buf, KYBER_SYMBYTES);
  /* Don't release system RNG output */
  hash_h(buf, buf, KYBER_SYMBYTES);

  /* Multitarget countermeasure for coins + contributory KEM */
  hash_h(buf+KYBER_SYMBYTES, pk, KYBER_PUBLICKEYBYTES);
  hash_g(kr, buf, 2*KYBER_SYMBYTES);

  /* coins are in kr+KYBER_SYMBYTES */
  indcpa_enc(ct, buf, pk, kr+KYBER_SYMBYTES);

  /* overwrite coins in kr with H(c) */
  hash_h(kr+KYBER_SYMBYTES, ct, KYBER_CIPHERTEXTBYTES);
  /* hash concatenation of pre-k and H(c) to k */
  kdf(ss, kr, 2*KYBER_SYMBYTES);
  return 0;
}

/*************************************************
* Name:        crypto_kem_dec
*
* Description: Generates shared secret for given
*              cipher text and private key
*
* Arguments:   - uint8_t *ss: pointer to output shared secret
*                (an already allocated array of KYBER_SSBYTES bytes)
*              - const uint8_t *ct: pointer to input cipher text
*                (an already allocated array of KYBER_CIPHERTEXTBYTES bytes)
*              - const uint8_t *sk: pointer to input private key
*                (an already allocated array of KYBER_SECRETKEYBYTES bytes)
*
* Returns 0.
*
* On failure, ss will contain a pseudo-random value.
**************************************************/
int crypto_kem_dec(uint8_t ss[KYBER_SSBYTES],
                   const uint8_t ct[KYBER_CIPHERTEXTBYTES],
                   const uint8_t sk[KYBER_SECRETKEYBYTES])
{
  size_t i;
  int fail;
  uint8_t buf[2*KYBER_SYMBYTES];
  /* Will contain key, coins */
  uint8_t kr[2*KYBER_SYMBYTES];
  uint8_t cmp[KYBER_CIPHERTEXTBYTES];
  const uint8_t *pk = sk+KYBER_INDCPA_SECRETKEYBYTES;

  indcpa_dec(buf, ct, sk);

  /* Multitarget countermeasure for coins + contributory KEM */
  for(i=0;i<KYBER_SYMBYTES;i++)
    buf[KYBER_SYMBYTES+i] = sk[KYBER_SECRETKEYBYTES-2*KYBER_SYMBYTES+i];
  hash_g(kr, buf, 2*KYBER_SYMBYTES);

  /* coins are in kr+KYBER_SYMBYTES */
  indcpa_enc(cmp, buf, pk, kr+KYBER_SYMBYTES);

  fail = verify(ct, cmp, KYBER_CIPHERTEXTBYTES);

  /* overwrite coins in kr with H(c) */
  hash_h(kr+KYBER_SYMBYTES, ct, KYBER_CIPHERTEXTBYTES);

  /* Overwrite pre-k with z on re-encryption failure */
  cmov(kr, sk+KYBER_SECRETKEYBYTES-KYBER_SYMBYTES, KYBER_SYMBYTES, fail);

  /* hash concatenation of pre-k and H(c) to k */
  kdf(ss, kr, 2*KYBER_SYMBYTES);
  return 0;
}
