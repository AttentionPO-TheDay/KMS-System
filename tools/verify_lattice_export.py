"""Independent public-evidence verification; no trapdoor or app imports."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


def target(message, count, q):
    values, counter = [], 0
    cutoff = (1 << 32) - (1 << 32) % q
    while len(values) < count:
        raw = hashlib.shake_256(b'KMS-LATTICE-ENVELOPE-V1\0' + message + counter.to_bytes(4, 'big')).digest(64)
        values.extend(word % q for (word,) in struct.iter_unpack('<I', raw) if word < cutoff)
        counter += 1
    return values[:count]


def main(path):
    result = json.loads(Path(path).read_text(encoding='utf-8'))
    matrix = result['publicMatrix']
    n, q = result['preparation']['n'], result['preparation']['q']
    packed = b''.join(struct.pack('<q', value) for row in matrix for value in row)
    assert hashlib.sha256(packed).hexdigest() == result['preparation']['publicDigest']
    for sample in result['samples']:
        message = sample['message'].encode('utf-8')
        assert hashlib.sha256(message).hexdigest() == sample['packageDigest']
        expected = target(message, n, q)
        assert expected == sample['target']
        vector = sample['vector']
        assert len(vector) == len(matrix[0])
        assert [sum(a * x for a, x in zip(row, vector)) % q for row in matrix] == expected
        assert math.hypot(*vector) <= sample['bound'] == result['preparation']['normBound']
    events = sorted([(span['startMs'], 1) for span in result['workerSpans']] +
                    [(span['endMs'], -1) for span in result['workerSpans']])
    active, peak = 0, 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert active == 0 and peak == result['peakInFlight']
    assert len({span['worker'] for span in result['workerSpans']}) == result['usedWorkers']
    assert len(result['samples']) == result['valid'] == result['count']
    print(json.dumps(dict(verified=True, samples=result['valid'], usedWorkers=result['usedWorkers'], peakInFlight=peak)))


if __name__ == '__main__': main(sys.argv[1])
