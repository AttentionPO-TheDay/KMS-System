"""Ideal state-vector simulation of Grover search on a deliberately tiny LWE instance.

H gates and the phase oracle act on amplitudes. The predicate truth table is
compiled classically; its compilation cost is reported, not counted as a quantum
speedup. No production key, quantum device, or noisy hardware is involved.
"""
import hashlib
import json
import math
import random
import time


def hadamard(state, bit):
    stride = 1 << bit
    for start in range(0, len(state), stride * 2):
        for j in range(start, start + stride):
            a, b = state[j], state[j + stride]
            state[j], state[j + stride] = (a + b) / math.sqrt(2), (a - b) / math.sqrt(2)


def probabilities(marked, qubits, iterations, enabled=True):
    state = [0.0] * (1 << qubits)
    state[0] = 1.0
    for bit in range(qubits):
        hadamard(state, bit)
    trace = [sum(state[i] ** 2 for i in marked)]
    for _ in range(iterations):
        if enabled:
            for i in marked:
                state[i] *= -1
        for bit in range(qubits):
            hadamard(state, bit)
        # 2|0><0|-I; together with H implements Grover diffusion.
        for i in range(1, len(state)):
            state[i] *= -1
        for bit in range(qubits):
            hadamard(state, bit)
        trace.append(sum(state[i] ** 2 for i in marked))
    return [v * v for v in state], trace


def simulate(seed=20261022):
    started = time.perf_counter()
    rng = random.Random(seed)
    qubits, q, samples = 8, 17, 12
    size = 1 << qubits
    secret = rng.randrange(size)
    matrix = [[rng.randrange(q) for _ in range(qubits)] for _ in range(samples)]
    b = [(sum(a * ((secret >> j) & 1) for j, a in enumerate(row)) + rng.choice([-1, 0, 1])) % q for row in matrix]
    compile_start = time.perf_counter()
    marked = []
    for candidate in range(size):
        residuals = [(sum(a * ((candidate >> j) & 1) for j, a in enumerate(row)) - value) % q for row, value in zip(matrix, b)]
        if all(min(r, q - r) <= 1 for r in residuals):
            marked.append(candidate)
    compile_ms = (time.perf_counter() - compile_start) * 1000
    if marked != [secret]:
        raise ValueError('Toy instance must have one verified solution')
    iterations = math.floor(math.pi * math.sqrt(size) / 4)
    probs, trace = probabilities(marked, qubits, iterations)
    baseline, _ = probabilities(marked, qubits, iterations, enabled=False)
    shots = 256
    counts = {}
    for value in rng.choices(range(size), weights=probs, k=shots):
        label = format(value, f'0{qubits}b')
        counts[label] = counts.get(label, 0) + 1
    target = format(secret, f'0{qubits}b')
    recovered = max(counts, key=counts.get)
    norm = sum(probs)
    theoretical = math.sin((2 * iterations + 1) * math.asin(1 / math.sqrt(size))) ** 2
    verified = (recovered == target and abs(norm - 1) < 1e-10 and
                abs(probs[secret] - theoretical) < 1e-10 and
                abs(baseline[secret] - 1 / size) < 1e-10)
    return {
        'algorithm': 'Grover search / tiny binary-secret LWE',
        'simulator': 'ideal real-amplitude state vector; H + compiled diagonal phase oracle + H/Z0/H',
        'seed': seed, 'qubits': qubits, 'searchSpace': size, 'q': q, 'samples': samples,
        'publicInstance': {'A': matrix, 'b': b, 'noiseBound': 1},
        'instanceSha256': hashlib.sha256(json.dumps([matrix, b], separators=(',', ':')).encode()).hexdigest(),
        'iterations': iterations, 'oracleQueries': iterations, 'classicalPredicateEvaluations': size,
        'oracleCompilationMs': round(compile_ms, 3), 'shots': shots,
        'measurementMode': 'seeded sampling from calculated Born probabilities',
        'counts': counts, 'target': target, 'recovered': recovered,
        'successProbability': probs[secret], 'theoreticalProbability': theoretical,
        'baselineProbability': baseline[secret], 'probabilityTrace': trace, 'norm': norm,
        'verified': verified, 'durationMs': round((time.perf_counter() - started) * 1000, 3),
        'scope': '8-qubit weak-instance positive control only; the same circuit is shared by all cost models. Not a Kyber break or a production-resistance verdict. Oracle ancillas, gate decomposition, noise and fault-tolerance costs are not modeled.',
    }
