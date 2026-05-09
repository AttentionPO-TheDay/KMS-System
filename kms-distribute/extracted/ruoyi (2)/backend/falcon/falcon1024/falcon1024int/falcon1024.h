#ifndef FALCON1024_H
#define FALCON1024_H

#ifdef __cplusplus
extern "C" {
#endif

#define FALCON_EXPORT __declspec(dllexport)

FALCON_EXPORT int crypto_sign_keypair(unsigned char *pk, unsigned char *sk);
FALCON_EXPORT int crypto_sign(unsigned char *sm, unsigned long long *smlen,
    const unsigned char *m, unsigned long long mlen,
    const unsigned char *sk);
FALCON_EXPORT int crypto_sign_open(unsigned char *m, unsigned long long *mlen,
    const unsigned char *sm, unsigned long long smlen,
    const unsigned char *pk);

#ifdef __cplusplus
}
#endif

#endif 