"""Read-only numerical comparison; run next to reference_math.py and pqkds/."""
import json
import statistics
import time

import reference_math
from pqkds import lattice_preallocation_math as accelerated


def measure(context, messages, workers, old=False):
    metrics = {}
    before = time.perf_counter()
    vectors = (reference_math if old else accelerated).sample_parallel(context, messages, workers, metrics)
    elapsed = (time.perf_counter() - before) * 1000
    valid = all(accelerated.verify(context['public'], accelerated.target_for(message), vector,
        accelerated.norm_bound(context)) for message, vector in zip(messages, vectors))
    return dict(count=len(messages), workers=workers, implementation='thread' if old else 'process',
        elapsedMs=elapsed, valid=valid, **{key: value for key, value in metrics.items() if key != 'spans'})


def main():
    context = accelerated.delegate(accelerated.trapgen(), 'sampling-acceleration-benchmark')
    cold = measure(context, [b'cold-start'], 1)
    rows = []
    for count in (32, 64):
        messages = [f'benchmark-envelope-{i}'.encode() for i in range(count)]
        for order in ((1, 2, 4, 8), (8, 4, 2, 1), (2, 1, 8, 4)):
            for workers in order:
                rows.append(measure(context, messages, workers))
        for workers in (1, 4):
            for _ in range(3):
                rows.append(measure(context, messages, workers, old=True))
    summaries = []
    for count in (32, 64):
        for mode, counts in (('thread', (1, 4)), ('process', (1, 2, 4, 8))):
            for workers in counts:
                selected = [r for r in rows if r['count'] == count and r['implementation'] == mode and r['workers'] == workers]
                summaries.append(dict(count=count, mode=mode, workers=workers,
                    medianMs=statistics.median(r['elapsedMs'] for r in selected), allValid=all(r['valid'] for r in selected)))
    accelerated.shutdown_sampling_pool()
    print(json.dumps(dict(scope='isolated in-memory mathematics; no database changes',
        coldStart=cold, summary=summaries, rows=rows), indent=2), flush=True)


if __name__ == '__main__':
    main()
