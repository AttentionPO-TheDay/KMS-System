"""Package a verified database export and completed real experiment runs.

Only public datasets and batch summaries are copied. Mapping keys, checkpoints,
private baselines and logs are deliberately kept outside the shared package.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone


NAMES = {'001': '分布式密钥生成与协商数据集', '002': '抗量子密钥预分配与分发数据集',
         '003': '密钥动态更新与回收数据集'}
DATASETS = dict(generation='001', agreements='001', preallocation='002', update='003', revoke='003')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def inside(parent, child):
    parent, child = parent.resolve(), child.resolve()
    if parent != child and parent not in child.parents:
        raise ValueError('文件不在指定输入目录内')
    return child


def build(snapshot, runs, output):
    snapshot = snapshot.resolve()
    if (snapshot / 'EXPORT_INCOMPLETE.txt').exists():
        raise ValueError('数据库导出不完整')
    meta = read_json(snapshot / 'metadata.json')
    if meta['per_table_limit'] != 0:
        raise ValueError('汇交包必须使用完整数据库快照')
    with (snapshot / 'manifest.csv').open(encoding='utf-8-sig', newline='') as stream:
        database_files = list(csv.DictReader(stream))
    checked_runs = []
    for run in runs:
        manifest = read_json(run / 'datasets' / 'manifest.json')
        if not manifest['complete']:
            raise ValueError('采集尚未完成：' + run.name)
        if manifest['kind'] not in DATASETS:
            raise ValueError('未知采集类别')
        checked_runs.append((run, manifest))
    output.mkdir(parents=True, exist_ok=False)
    incomplete = output / 'PACKAGE_INCOMPLETE.txt'
    incomplete.write_text('正在核验与整理，完成前不可作为正式汇交包。', encoding='utf-8')
    files, counts, isolated = [], {}, {}

    def directory(ds):
        p = output / ('2023YFB3105902-' + ds + '-' + NAMES[ds])
        p.mkdir(exist_ok=True)
        return p

    def copy(source, target, expected=None, records=None, origin=None):
        source_hash = digest(source)
        if expected and source_hash != expected:
            raise ValueError('来源文件校验失败：' + source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != source_hash:
            raise ValueError('复制文件校验失败：' + target.name)
        files.append(dict(path=target.relative_to(output).as_posix(), records=records,
                          bytes=target.stat().st_size, sha256=source_hash, origin=origin))

    for row in database_files:
        source = inside(snapshot, snapshot / row['path'])
        if row['format'] != 'csv':
            raise ValueError('请使用 CSV 格式导出数据库，避免重复统计同表不同格式')
        records = int(row['records'])
        copy(source, directory(row['dataset']) / '数据文件' / source.name, row['sha256'],
             records, 'database_snapshot')
        counts[row['dataset'] + ':' + row['table']] = records
    for name in ('metadata.json', 'manifest.csv', 'data_dictionary.csv'):
        copy(snapshot / name, output / ('数据库' + name), origin='database_snapshot_metadata')
    for run, manifest in checked_runs:
        kind = manifest['kind']
        ds = DATASETS[kind]
        target = directory(ds) / '测试与研究附件' / run.name
        scope = 'live_execution' if kind in ('generation', 'update') else 'isolated_real_execution'
        for row in manifest['files']:
            source = inside(run / 'datasets', run / 'datasets' / row['file'])
            copy(source, target / source.name, row['sha256'], row['records'], scope)
            if scope == 'isolated_real_execution':
                key = Path(row['file']).stem
                isolated[key] = isolated.get(key, 0) + row['records']
        copy(run / 'datasets' / 'manifest.json', target / 'manifest.json', origin='execution_metadata')
        summaries = []
        for index in range(manifest['completed_batches']):
            batch = read_json(run / 'batches' / f'{index:06d}.json')
            if not batch['summary']['verified']:
                raise ValueError('存在未通过批次')
            summaries.append(dict(batch_id=batch['batch_id'], index=index, **batch['summary']))
        target.mkdir(parents=True, exist_ok=True)
        summary = target / '批次核验与耗时.json'
        summary.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(dict(path=summary.relative_to(output).as_posix(), records=len(summaries),
                          bytes=summary.stat().st_size, sha256=digest(summary), origin='execution_summary'))
    observed = dict(
        generation=counts.get('001:kms.keymanage', 0),
        agreements=counts.get('001:falcon_kds.dvadmin_pqkds_group_agreements', 0) + isolated.get('agreements', 0),
        members=counts.get('001:falcon_kds.dvadmin_pqkds_group_agreement_members', 0) + isolated.get('members', 0),
        preallocation=counts.get('002:falcon_kds.dvadmin_pqkds_pre_distributed_keys', 0) + isolated.get('preallocation', 0),
        update_revoke=counts.get('003:kms.key_operation_record', 0) + isolated.get('revocations', 0),
        normal_controls=isolated.get('controls', 0))
    targets = dict(generation=3000000, agreements=3000, members=9000, preallocation=90000,
                   update_revoke=540000, normal_controls=240)
    report = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
                  targets=targets, observed=observed,
                  meets_numeric_targets={key: observed[key] >= n for key, n in targets.items()},
                  database_table_rows=counts, isolated_execution_rows=isolated,
                  counting='数据库快照与隔离实验按来源分别计数；线上采集附件仅用于核验，不能与数据库记录重复相加。表行数不等于不同密钥数。',
                  limitations=['隔离预分配不属于生产预分配库存，未覆盖节点本机Falcon上传。',
                               '隔离协商使用构造节点及真实算法执行，不属于现有业务节点协商历史。',
                               '更新以版本、材料变化、历史及审计记录核验；链上状态单独保存。',
                               '数量核验不代替研究论证、第三方检测、论文或抗攻击指标认定。'])
    report_path = output / '目标与来源核验.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    files.append(dict(path=report_path.name, bytes=report_path.stat().st_size, sha256=digest(report_path),
                      records=None, origin='derived_summary'))
    manifest = dict(complete=all(report['meets_numeric_targets'].values()), files=files,
                    bytes=sum(row['bytes'] for row in files),
                    excluded='映射密钥、控制文件、私钥、陷门、秘密贡献、共享秘密、会话密文和有效凭据。')
    (output / '汇交清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if not manifest['complete']:
        raise ValueError('仍有数值目标未满足，详见目标与来源核验.json')
    incomplete.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot, args.run, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
