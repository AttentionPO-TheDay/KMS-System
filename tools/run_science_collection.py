#!/usr/bin/env python3
"""Collect real executions, checkpoint each batch, export public CSV and SHA256.

Default is a read-only server inventory. Online generation and update persist
business changes. Other modes execute existing services against temporary tables.
"""
import argparse
import csv
from contextlib import ExitStack, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import uuid

WORKER=Path(__file__).resolve().parent/'science_data'/'worker.py'
BATCHES=dict(generation=128,preallocation=32,agreements=10,update=6000,revoke=6000)
TARGETS=dict(generation=3_000_000,agreements=3_000,members=9_000,preallocation=90_000,operations=540_000)


@contextmanager
def output_lock(path):
    with path.open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('此输出目录已有采集进程运行') from exc
        yield


def database_free_bytes(host,container):
    cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
        'docker exec '+shlex.quote(container)+' df -Pk /var/lib/mysql']
    result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
    return int(result.stdout.splitlines()[-1].split()[3])*1024


def atomic_json(path,data):
    temporary=path.with_suffix('.writing')
    with temporary.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


def remote_copy_command(host, container, path):
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
            'docker exec -i '+shlex.quote(container)+' sh -c '+shlex.quote('umask 077; cat > '+shlex.quote(path))]


def remote_run_command(host, container, path):
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
            'docker exec '+shlex.quote(container)+' python -u '+shlex.quote(path)]


def remote_remove_command(host, container, path):
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
            'docker exec '+shlex.quote(container)+' rm -f '+shlex.quote(path)]


def finalize(output,state):
    directory=output/'datasets';directory.mkdir(exist_ok=True)
    writers={};handles={};counts={};hashes=[]
    try:
        for index in range(state['next_batch']):
            batch=json.loads((output/'batches'/f'{index:06d}.json').read_text(encoding='utf-8'))
            for table,rows in batch['tables'].items():
                if not rows:continue
                if table not in writers:
                    h=(directory/(table+'.csv')).open('w',encoding='utf-8-sig',newline='')
                    handles[table]=h;writers[table]=csv.DictWriter(h,fieldnames=list(rows[0]))
                    writers[table].writeheader();counts[table]=0
                for row in rows:
                    public={k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in row.items()}
                    public={k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for k,v in public.items()}
                    writers[table].writerow(public);counts[table]+=1
    finally:
        for h in handles.values():h.close()
    for table,n in counts.items():
        path=directory/(table+'.csv');digest=hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
        hashes.append(dict(file=path.name,records=n,bytes=path.stat().st_size,sha256=digest.hexdigest()))
    complete=state['next_batch']==state['config']['batch_count'] and not state.get('pending')
    metadata=dict(version=1,kind=state['config']['kind'],run_id=state['config']['run_id'],complete=complete,
        requested=state['config']['count'],completed_batches=state['next_batch'],files=hashes,
        scope='live_execution 为实际接口及落库结果；isolated_real_execution 为构造输入的真实隔离执行，不能计作生产库存。',
        excluded='私钥、陷门、随机贡献、会话密钥、密文载荷及有效凭据不导出。')
    atomic_json(directory/'manifest.json',metadata)
    return metadata


def collect(argv, locks):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind',choices=('plan',*BATCHES),default='plan')
    p.add_argument('--count',type=int)
    p.add_argument('--batch-size',type=int)
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--sampling-workers',type=int,choices=(1,2,4,8),default=1)
    p.add_argument('--wait-seconds',type=int,default=120)
    p.add_argument('--min-free-gib',type=int,default=10)
    p.add_argument('--host',default='expert-machine')
    p.add_argument('--container',default='dvadmin3-django')
    p.add_argument('--mysql-container',default='kms_mysql')
    p.add_argument('--user',default='acceptance_user')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--status',action='store_true',help='只读查看输出目录中的已核验进度')
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    if args.status:
        if not args.output:p.error('查看进度需要 --output')
        state=json.loads((args.output/'control.json').read_text(encoding='utf-8'))
        cfg=state['config']
        completed=min(cfg['count'],state['next_batch']*cfg['batch_size'])
        print(json.dumps(dict(kind=cfg['kind'],requested=cfg['count'],verified_records=completed,
            verified_batches=state['next_batch'],batches=cfg['batch_count'],
            complete=state['next_batch']==cfg['batch_count'] and not state.get('pending')),
            ensure_ascii=False,indent=2))
        return 0
    if args.kind!='plan' and not args.resume and (not args.count or args.count<1 or not args.output):
        p.error('采集需要正数 --count 及 --output')
    if not 1<=args.workers<=32 or args.wait_seconds<1 or args.min_free_gib<1:
        p.error('并发数需要1到32，等待时间及磁盘保留量需要正数')
    if args.output and (args.execute or args.resume):
        args.output.parent.mkdir(parents=True,exist_ok=True)
        locks.enter_context(output_lock(args.output.parent/('.'+args.output.name+'.collector.lock')))
    if args.resume:
        if not args.output:p.error('续跑需要 --output')
        state=json.loads((args.output/'control.json').read_text(encoding='utf-8'))
        cfg=state['config']
        if state.get('pending') and cfg['kind'] in ('generation','update') and not state['pending'].get('baseline'):
            p.error('上次中断没有保存提交前状态，不能安全自动重发，请先核对该批次')
    else:
        batch=args.batch_size or BATCHES.get(args.kind,1)
        if batch<1 or batch>dict(generation=1000,preallocation=64,agreements=100,update=6000,revoke=6000).get(args.kind,1):
            p.error('批大小超过模式允许范围')
        if args.kind=='revoke' and (args.count<3 or batch<3 or args.count%batch in (1,2)):
            p.error('每批回收需要3到6000条，请调整批大小避免末批只有1或2条')
        if args.kind=='preallocation' and args.sampling_workers>1 and args.count%batch==1:
            p.error('末批只有1条时请使用 --sampling-workers 1')
        cfg=dict(kind=args.kind,count=args.count or 0,batch_size=batch,
            batch_count=math.ceil((args.count or 0)/batch),first_batch=0,workers=args.workers,
            sampling_workers=args.sampling_workers,wait_seconds=args.wait_seconds,min_free_gib=args.min_free_gib,
            user=args.user,run_id=uuid.uuid4().hex,host=args.host,container=args.container,mysql_container=args.mysql_container)
        state=dict(config=cfg,next_batch=0,pending=None)
    if cfg['kind']!='plan' and not args.execute:
        print(json.dumps(dict(kind=cfg['kind'],requested=cfg['count'],batch_size=cfg['batch_size'],
            batches=cfg['batch_count'],execute=False),ensure_ascii=False));return 0
    if cfg['kind']!='plan':
        if not args.resume:
            args.output.mkdir(parents=True,exist_ok=False);(args.output/'batches').mkdir()
            keypath=args.output.parent/'.science-collection.mapping.key'
            if not keypath.exists():
                with keypath.open('xb') as f:f.write(os.urandom(32))
            if len(keypath.read_bytes())!=32:raise RuntimeError('映射密钥长度错误')
            os.chmod(keypath,0o600);state['key_file']=str(keypath.resolve())
        cfg=dict(cfg,first_batch=state['next_batch'],pending=state.get('pending'),
            mapping_key=Path(state['key_file']).read_bytes().hex())
        if cfg['first_batch']==cfg['batch_count']:
            print(json.dumps(finalize(args.output,state),ensure_ascii=False));return 0
        state['pending']=state.get('pending') or dict(batch_id='science-'+cfg['run_id']+'-'+str(cfg['first_batch']))
        atomic_json(args.output/'control.json',state)
    if cfg['kind'] in ('generation','update'):
        free=database_free_bytes(cfg['host'],cfg.get('mysql_container','kms_mysql'))
        if free<cfg['min_free_gib']*1024**3:raise RuntimeError('数据库磁盘低于保留空间，未提交请求')
    source='config = '+repr(cfg)+'\n'+WORKER.read_text(encoding='utf-8')+'\n'
    result_code=0
    with tempfile.TemporaryFile() as stdin,tempfile.TemporaryFile() as errors:
        stdin.write(source.encode());stdin.seek(0)
        remote_path='/tmp/kms-science-'+cfg['run_id']+'-'+uuid.uuid4().hex+'.py'
        copied=subprocess.run(remote_copy_command(cfg['host'],cfg['container'],remote_path),stdin=stdin,
            stdout=subprocess.PIPE,stderr=errors,timeout=30)
        if copied.returncode:
            raise RuntimeError('无法将采集脚本写入容器临时文件')
        proc=subprocess.Popen(remote_run_command(cfg['host'],cfg['container'],remote_path),
            stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8')
        try:
            for line in proc.stdout:
                event=json.loads(line)
                if event['event']=='inventory':
                    current=event['data']
                    current['targets']=TARGETS
                    current['gaps']={key:max(0,target-current[key]) for key,target in TARGETS.items()}
                    print(json.dumps(current,ensure_ascii=False,indent=2))
                elif event['event']=='prepared':
                    state['pending']=dict(batch_id=event['batch_id'],baseline=event['baseline'])
                    atomic_json(args.output/'control.json',state)
                elif event['event']=='batch':
                    if event['index']!=state['next_batch']:raise RuntimeError('Unexpected batch sequence')
                    atomic_json(args.output/'batches'/f"{event['index']:06d}.json",event)
                    print(json.dumps(dict(batch=event['index'],**event['summary']),ensure_ascii=False),flush=True)
                    if event['summary']['verified']:
                        state['next_batch']+=1;state['pending']=None
                        if state['next_batch']<cfg['batch_count']:
                            state['pending']=dict(batch_id='science-'+cfg['run_id']+'-'+str(state['next_batch']))
                    atomic_json(args.output/'control.json',state)
                elif event['event']=='error':
                    print(json.dumps(event,ensure_ascii=False),flush=True);result_code=1
            result_code=max(result_code,proc.wait())
        except BaseException:
            proc.kill();proc.wait();raise
        finally:
            subprocess.run(remote_remove_command(cfg['host'],cfg['container'],remote_path),
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            if cfg['kind']!='plan':
                finalize(args.output,state)
        if result_code:
            errors.seek(0)
            message=errors.read().decode('utf-8',errors='replace')
            if message: print(message[-1500:])
    return result_code


def main(argv=None):
    with ExitStack() as locks:
        return collect(argv,locks)


if __name__=='__main__':
    raise SystemExit(main())
