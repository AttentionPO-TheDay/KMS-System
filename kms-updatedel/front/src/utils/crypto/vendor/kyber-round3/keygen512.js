/**
 * Minimal KeyGen dependency closure from crystals-kyber@5.1.0 kyber512.js.
 * Copyright (c) 2020 Anton Tutoveanu; MIT license in ./LICENSE.
 * Upstream SHA-256: a3a8a4bcb307d73e9f9ebeeb1c06aa38077ddddb342a8af17d48cbb951ba7312
 * Changes: ESM/local Buffer imports; explicit d32/z32 instead of RNG calls;
 * unused encapsulation/decapsulation/test functions removed. Core math/encoding retained.
 * Input validation and temporary-buffer cleanup belong to ./adapter.js.
 */
import sha3 from 'sha3'
import { Buffer } from 'buffer'
const { SHA3, SHAKE } = sha3

const nttZetas = [
    2285, 2571, 2970, 1812, 1493, 1422, 287, 202, 3158, 622, 1577, 182, 962,
    2127, 1855, 1468, 573, 2004, 264, 383, 2500, 1458, 1727, 3199, 2648, 1017,
    732, 608, 1787, 411, 3124, 1758, 1223, 652, 2777, 1015, 2036, 1491, 3047,
    1785, 516, 3321, 3009, 2663, 1711, 2167, 126, 1469, 2476, 3239, 3058, 830,
    107, 1908, 3082, 2378, 2931, 961, 1821, 2604, 448, 2264, 677, 2054, 2226,
    430, 555, 843, 2078, 871, 1550, 105, 422, 587, 177, 3094, 3038, 2869, 1574,
    1653, 3083, 778, 1159, 3182, 2552, 1483, 2727, 1119, 1739, 644, 2457, 349,
    418, 329, 3173, 3254, 817, 1097, 603, 610, 1322, 2044, 1864, 384, 2114, 3193,
    1218, 1994, 2455, 220, 2142, 1670, 2144, 1799, 2051, 794, 1819, 2475, 2459,
    478, 3221, 3021, 996, 991, 958, 1869, 1522, 1628];

const paramsK = 2;

const paramsN = 256;

const paramsQ = 3329;

const paramsQinv = 62209;

const paramsETA1 = 3;

const paramsETA2 = 2;

export function keygen(d, z) {
    // IND-CPA keypair
    let indcpakeys = indcpaKeyGen(d);

    let pk = indcpakeys[0];
    let sk = indcpakeys[1];

    // FO transform to make IND-CCA2

    // get hash of pk
    const buffer1 = Buffer.from(pk);
    const hash1 = new SHA3(256);
    hash1.update(buffer1);
    let pkh = hash1.digest();

    // read 32 random values (0-255) into a 32 byte array
    let rnd = z; // Explicit 32-byte FO rejection entropy; no RNG hook.

    // concatenate to form IND-CCA2 private key: sk + pk + h(pk) + rnd
    for (let i = 0; i < pk.length; i++) {
        sk.push(pk[i]);
    }
    for (let i = 0; i < pkh.length; i++) {
        sk.push(pkh[i]);
    }
    for (let i = 0; i < rnd.length; i++) {
        sk.push(rnd[i]);
    }

    let keys = new Array(2);
    keys[0] = pk;
    keys[1] = sk;
    return keys;
}

function indcpaKeyGen(d) {

    // random bytes for seed
    let rnd = d; // Explicit 32-byte CPA entropy, hashed exactly as round-3.

    // hash rnd with SHA3-512
    const buffer1 = Buffer.from(rnd);
    const hash1 = new SHA3(512);
    hash1.update(buffer1);
    let seed = new Uint8Array(hash1.digest());
    let publicSeed = seed.slice(0, 32);
    let noiseSeed = seed.slice(32, 64);

    // generate public matrix A (already in NTT form)
    let a = generateMatrixA(publicSeed, false, paramsK);

    // sample secret s
    let s = new Array(paramsK);
    let nonce = 0;
    for (let i = 0; i < paramsK; i++) {
        s[i] = sample1(noiseSeed, nonce);
        nonce = nonce + 1;
    }

    // sample noise e
    let e = new Array(paramsK);
    for (let i = 0; i < paramsK; i++) {
        e[i] = sample1(noiseSeed, nonce);
        nonce = nonce + 1;
    }

    // perform number theoretic transform on secret s
    for (let i = 0; i < paramsK; i++) {
        s[i] = ntt(s[i]);
    }

    // perform number theoretic transform on error/noise e
    for (let i = 0; i < paramsK; i++) {
        e[i] = ntt(e[i]);
    }

    // barrett reduction
    for (let i = 0; i < paramsK; i++) {
        s[i] = reduce(s[i]);
    }

    // KEY COMPUTATION
    // A.s + e = pk

    // calculate A.s
    let pk = new Array(paramsK);
    for (let i = 0; i < paramsK; i++) {
        // montgomery reduction
        pk[i] = polyToMont(multiply(a[i], s));
    }

    // calculate addition of e
    for (let i = 0; i < paramsK; i++) {
        pk[i] = add(pk[i], e[i]);
    }

    // barrett reduction
    for (let i = 0; i < paramsK; i++) {
        pk[i] = reduce(pk[i]);
    }

    // ENCODE KEYS
    let keys = new Array(2);

    // PUBLIC KEY
    // turn polynomials into byte arrays
    keys[0] = [];
    let bytes = [];
    for (let i = 0; i < paramsK; i++) {
        bytes = polyToBytes(pk[i]);
        for (let j = 0; j < bytes.length; j++) {
            keys[0].push(bytes[j]);
        }
    }
    // append public seed
    for (let i = 0; i < publicSeed.length; i++) {
        keys[0].push(publicSeed[i]);
    }

    // PRIVATE KEY
    // turn polynomials into byte arrays
    keys[1] = [];
    bytes = [];
    for (let i = 0; i < paramsK; i++) {
        bytes = polyToBytes(s[i]);
        for (let j = 0; j < bytes.length; j++) {
            keys[1].push(bytes[j]);
        }
    }
    return keys;
}

function polyToBytes(a) {
    let t0, t1;
    let r = new Array(384);
    let a2 = subtract_q(a); // Returns: a - q if a >= q, else a (each coefficient of the polynomial)
    // for 0-127
    for (let i = 0; i < paramsN / 2; i++) {
        // get two coefficient entries in the polynomial
        t0 = uint16(a2[2 * i]);
        t1 = uint16(a2[2 * i + 1]);

        // convert the 2 coefficient into 3 bytes
        r[3 * i + 0] = byte(t0 >> 0); // byte() does mod 256 of the input (output value 0-255)
        r[3 * i + 1] = byte(t0 >> 8) | byte(t1 << 4);
        r[3 * i + 2] = byte(t1 >> 4);
    }
    return r;
}

function generateMatrixA(seed, transposed) {
    let a = new Array(paramsK);
    let output = new Array(3 * 168);
    const xof = new SHAKE(128);
    let ctr = 0;
    for (let i = 0; i < paramsK; i++) {

        a[i] = new Array(paramsK);
        let transpose = new Array(2);

        for (let j = 0; j < paramsK; j++) {

            // set if transposed matrix or not
            transpose[0] = j;
            transpose[1] = i;
            if (transposed) {
                transpose[0] = i;
                transpose[1] = j;
            }

            // obtain xof of (seed+i+j) or (seed+j+i) depending on above code
            // output is 672 bytes in length
            xof.reset();
            const buffer1 = Buffer.from(seed);
            const buffer2 = Buffer.from(transpose);
            xof.update(buffer1).update(buffer2);
            let output = new Uint8Array(xof.digest({ buffer: Buffer.alloc(672)}));

            // run rejection sampling on the output from above
            let outputlen = 3 * 168;
            let result = new Array(2);
            result = indcpaRejUniform(output.slice(0,504), outputlen, paramsN);
            a[i][j] = result[0]; // the result here is an NTT-representation
            ctr = result[1]; // keeps track of index of output array from sampling function

            while (ctr < paramsN) { // if the polynomial hasnt been filled yet with mod q entries

                let outputn = output.slice(504, 672); // take last 168 bytes of byte array from xof

                let result1 = new Array(2);
                result1 = indcpaRejUniform(outputn, 168, paramsN-ctr); // run sampling function again
                let missing = result1[0]; // here is additional mod q polynomial coefficients
                let ctrn = result1[1]; // how many coefficients were accepted and are in the output
                // starting at last position of output array from first sampling function until 256 is reached
                for (let k = ctr; k < paramsN; k++) {
                    a[i][j][k] = missing[k-ctr]; // fill rest of array with the additional coefficients until full
                }
                ctr = ctr + ctrn; // update index
            }

        }
    }
    return a;
}

function indcpaRejUniform(buf, bufl, len) {
    let r = new Array(384).fill(0);
    let val0, val1; // d1, d2 in kyber documentation
    let pos = 0; // i
    let ctr = 0; // j

    while (ctr < len && pos + 3 <= bufl) {

        // compute d1 and d2
        val0 = (uint16((buf[pos]) >> 0) | (uint16(buf[pos + 1]) << 8)) & 0xFFF;
        val1 = (uint16((buf[pos + 1]) >> 4) | (uint16(buf[pos + 2]) << 4)) & 0xFFF;

        // increment input buffer index by 3
        pos = pos + 3;

        // if d1 is less than 3329
        if (val0 < paramsQ) {
            // assign to d1
            r[ctr] = val0;
            // increment position of output array
            ctr = ctr + 1;
        }
        if (ctr < len && val1 < paramsQ) {
            r[ctr] = val1;
            ctr = ctr + 1;
        }


    }

    let result = new Array(2);
    result[0] = r; // returns polynomial NTT representation
    result[1] = ctr; // ideally should return 256
    return result;
}

function sample1(seed, nonce) {
    let l = paramsETA1 * paramsN / 4;
    let p = prf(l, seed, nonce);
    return byteopsCbd(p);
}

function prf(l, key, nonce) {
    let nonce_arr = new Array(1);
    nonce_arr[0] = nonce;
    const hash = new SHAKE(256);
    hash.reset();
    const buffer1 = Buffer.from(key);
    const buffer2 = Buffer.from(nonce_arr);
    hash.update(buffer1).update(buffer2);
    let buf = hash.digest({ buffer: Buffer.alloc(l)}); // 128 long byte array
    return buf;
}

function byteopsCbd(buf) {
    let t, d;
    let a, b;
    let r = new Array(384).fill(0);
    for (let i = 0; i < paramsN/4; i++) {
        t = byteopsLoad24(buf.slice(3*i, buf.length));
        d = t & 0x00249249;
        d = d + ((t >> 1) & 0x00249249);
        d = d + ((t >> 2) & 0x00249249);
        for (let j = 0; j < 4; j++) {
            a = int16((d >> (6*j + 0)) & 0x7);
            b = int16((d >> (6*j + paramsETA1)) & 0x7);
            r[4*i+j] = a - b;
        }
    }
    return r;
}

function byteopsLoad24(x) {
	let r;
	r = uint32(x[0]);
	r = r | (uint32(x[1]) << 8);
	r = r | (uint32(x[2]) << 16);
	return r;
}

function ntt(r) {
    let j = 0;
    let k = 1;
    let zeta;
    let t;
    // 128, 64, 32, 16, 8, 4, 2
    for (let l = 128; l >= 2; l >>= 1) {
        // 0,
        for (let start = 0; start < 256; start = j + l) {
            zeta = nttZetas[k];
            k = k + 1;
            // for each element in the subsections (128, 64, 32, 16, 8, 4, 2) starting at an offset
            for (j = start; j < start + l; j++) {
                // compute the modular multiplication of the zeta and each element in the subsection
                t = nttFqMul(zeta, r[j + l]); // t is mod q
                // overwrite each element in the subsection as the opposite subsection element minus t
                r[j + l] = r[j] - t;
                // add t back again to the opposite subsection
                r[j] = r[j] + t;

            }
        }
    }
    return r;
}

function nttFqMul(a, b) {
    return byteopsMontgomeryReduce(a * b);
}

function reduce(r) {
    for (let i = 0; i < paramsN; i++) {
        r[i] = barrett(r[i]);
    }
    return r;
}

function barrett(a) {
    let v = ( (1<<24) + paramsQ / 2) / paramsQ;
    let t = v * a >> 24;
    t = t * paramsQ;
    return a - t;
}

function byteopsMontgomeryReduce(a) {
    let u = int16(int32(a) * paramsQinv);
    let t = u * paramsQ;
    t = a - t;
    t >>= 16;
    return int16(t);
}

function polyToMont(r) {
    // let f = int16(((uint64(1) << 32) >>> 0) % uint64(paramsQ));
    let f = 1353; // if paramsQ changes then this needs to be updated
    for (let i = 0; i < paramsN; i++) {
        r[i] = byteopsMontgomeryReduce(int32(r[i]) * int32(f));
    }
    return r;
}

function multiply(a, b) {
    let r = polyBaseMulMontgomery(a[0], b[0]);
    let t;
    for (let i = 1; i < paramsK; i++) {
        t = polyBaseMulMontgomery(a[i], b[i]);
        r = add(r, t);
    }
    return reduce(r);
}

function polyBaseMulMontgomery(a, b) {
    let rx, ry;
    for (let i = 0; i < paramsN / 4; i++) {
        rx = nttBaseMul(
            a[4 * i + 0], a[4 * i + 1],
            b[4 * i + 0], b[4 * i + 1],
            nttZetas[64 + i]
        );
        ry = nttBaseMul(
            a[4 * i + 2], a[4 * i + 3],
            b[4 * i + 2], b[4 * i + 3],
            -nttZetas[64 + i]
        );
        a[4 * i + 0] = rx[0];
        a[4 * i + 1] = rx[1];
        a[4 * i + 2] = ry[0];
        a[4 * i + 3] = ry[1];
    }
    return a;
}

function nttBaseMul(a0, a1, b0, b1, zeta) {
    let r = new Array(2);
    r[0] = nttFqMul(a1, b1);
    r[0] = nttFqMul(r[0], zeta);
    r[0] = r[0] + nttFqMul(a0, b0);
    r[1] = nttFqMul(a0, b1);
    r[1] = r[1] + nttFqMul(a1, b0);
    return r;
}

function add(a, b) {
    let c = new Array(384);
    for (let i = 0; i < paramsN; i++) {
        c[i] = a[i] + b[i];
    }
    return c;
}

function subtract_q(r) {
    for (let i = 0; i < paramsN; i++) {
        r[i] = r[i] - paramsQ; // should result in a negative integer
        // push left most signed bit to right most position
        // javascript does bitwise operations in signed 32 bit
        // add q back again if left most bit was 0 (positive number)
        r[i] = r[i] + ((r[i] >> 31) & paramsQ);
    }
    return r;
}

function byte(n) {
    n = n % 256;
    return n;
}

function int16(n) {
    let end = -32768;
    let start = 32767;

    if (n >= end && n <= start) {
        return n;
    }
    if (n < end) {
        n = n + 32769;
        n = n % 65536;
        n = start + n;
        return n;
    }
    if (n > start) {
        n = n - 32768;
        n = n % 65536;
        n = end + n;
        return n;
    }
}

function uint16(n) {
    n = n % 65536;
    return n;
}

function int32(n) {
    let end = -2147483648;
    let start = 2147483647;

    if (n >= end && n <= start) {
        return n;
    }
    if (n < end) {
        n = n + 2147483649;
        n = n % 4294967296;
        n = start + n;
        return n;
    }
    if (n > start) {
        n = n - 2147483648;
        n = n % 4294967296;
        n = end + n;
        return n;
    }
}

function uint32(n) {
    n = n % 4294967296;
    return n;
}
