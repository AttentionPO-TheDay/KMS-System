"""Run inside Django container. Real execution results only, no canned outcomes."""
import base64
import hashlib
import hmac
import itertools
import json
import os
import secrets
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def encoded(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':')).encode()


def hkdf(secret, salt, info, length):
    prk = hmac.new(salt, secret, hashlib.sha256).digest()
    result, block = b'', b''
    for i in range(1, (length + 31) // 32 + 1):
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        result += block
    return result[:length]


def changed(a, b):
    return bool(b and b['status'] == '0' and int(b['version']) == int(a['version']) + 1
        and a['digest'] and b['digest'] and a['digest'] != b['digest'])


def emit(event, **data):
    print(json.dumps(dict(event=event, **data), ensure_ascii=False, default=str), flush=True)


def sql(query, args=()):
    from django.db import connection
    with connection.cursor() as c:
        c.execute(query, args)
        return [dict(zip([x[0] for x in c.description], row)) for row in c.fetchall()]


def public_id(cfg, value):
    return hmac.new(bytes.fromhex(cfg['mapping_key']), str(value).encode(), hashlib.sha256).hexdigest()


def inventory():
    tables = dict(generation='kms.keymanage', agreements='falcon_kds.dvadmin_pqkds_group_agreements',
        members='falcon_kds.dvadmin_pqkds_group_agreement_members',
        preallocation='falcon_kds.dvadmin_pqkds_pre_distributed_keys',
        operations='kms.key_operation_record', history='kms.keymanage_version_history')
    result = {k: sql('SELECT COUNT(*) AS n FROM ' + t)[0]['n'] for k,t in tables.items()}
    result.update(free_disk_bytes_container=shutil.disk_usage('/').free, raw_counts_only=True)
    return result


def post(cfg, url, data, idem=None):
    token = os.environ.get('INTERNAL_TOKEN')
    if not token:
        raise RuntimeError('INTERNAL_TOKEN missing in container')
    headers = {'Content-Type':'application/json', 'X-Internal-Token':token, 'X-Kms-User':cfg['user']}
    if idem:
        headers['Idempotency-Key'] = idem
    try:
        with urlopen(Request(url, data=encoded(data), headers=headers), timeout=30) as r:
            obj = json.loads(r.read(65536))
            return r.status == 200 and obj.get('code') == 200
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False


def generation(cfg, bid, n, prior):
    baseline = prior.get('baseline') if prior else None
    accepted = None
    if baseline is None:
        baseline = {'max_id': sql('SELECT COALESCE(MAX(key_id),0) AS n FROM kms.keymanage')[0]['n']}
        emit('prepared', baseline=baseline, batch_id=bid)
        url = os.environ.get('GENERATE_BACKEND_BASE','http://generate-go:8081').rstrip('/') + '/generate/request/ENROLL_KEY'
        def request(i):
            from pqkds.sm2_crypto import SM2Crypto, SM2_N
            ua = SM2Crypto.public_key_of(format(secrets.randbelow(SM2_N-1)+1,'064x'))
            return post(cfg, url, dict(encryt_type='无证书非对称加密', encryt_name='SSCL', ua=ua,
                key_domain='science-collection', key_name=bid, key_use='科学数据采集', auto_update='false'))
        with ThreadPoolExecutor(max_workers=cfg['workers']) as ex:
            accepted = sum(ex.map(request, range(n)))
    # Reconcile uncertain submissions, never repeat a non-idempotent generation.
    deadline = time.monotonic() + cfg['wait_seconds']
    while True:
        rows = sql('SELECT key_id,version,status,encryt_name,cre_time,algorithm_version,key_material_state,'
            'SHA2(ua,256) AS ua_digest,SHA2(key_value,256) AS digest FROM kms.keymanage '
            'WHERE key_id > %s AND key_name = %s ORDER BY key_id', [baseline['max_id'],bid])
        if len(rows) >= n or time.monotonic() >= deadline:
            break
        time.sleep(1)
    valid = (len(rows) == n and len({r['ua_digest'] for r in rows}) == n
        and len({r['digest'] for r in rows}) == n
        and all(r['status']=='0' and r['encryt_name']=='SSCL' for r in rows))
    out = [dict(key_id=public_id(cfg,r['key_id']), version=r['version'], status=r['status'],
        algorithm=r['encryt_name'], created_at=r['cre_time'], algorithm_version=r['algorithm_version'],
        key_material_state=r['key_material_state'], public_input_digest=r['ua_digest'],
        batch_id=bid, origin='live_execution') for r in rows]
    return {'generation':out}, dict(requested=n, http_accepted=accepted, completed=len(rows),
        verified=valid, unique_inputs=len({r['ua_digest'] for r in rows}), recovery=bool(prior))


def update(cfg, bid, n, prior):
    baseline = prior.get('baseline') if prior else None
    if baseline is None:
        rows = sql('SELECT key_id,version,status,SHA2(key_value,256) AS digest FROM kms.keymanage '
            'WHERE user_name=%s AND key_domain=%s AND encryt_name=%s AND status=%s '
            'ORDER BY key_id DESC LIMIT %s',[cfg['user'],'acceptance','SM2','0',n])
        if len(rows)!=n:
            raise RuntimeError('Not enough active SM2 acceptance keys')
        baseline = {'rows':rows}
        emit('prepared', baseline=baseline, batch_id=bid)
    rows = baseline['rows']
    url = os.environ.get('LIFECYCLE_BACKEND_BASE','http://updatedel-go:8082').rstrip('/') + '/lifecycle/request/UPDATE_KEY'
    def request(row):
        return post(cfg,url,dict(keyId=row['key_id'],user=cfg['user'],keyName='science-update',
            keyUse='科学数据采集',keyDomain='acceptance',autoUpdate='false'),
            f'science:{bid}:{row["key_id"]}')
    # Redis idempotency expires. Recovery only reconciles the saved versions;
    # it must never rotate a key again just because the old token has expired.
    accepted = None
    if not prior or prior.get('baseline') is None:
        with ThreadPoolExecutor(max_workers=cfg['workers']) as ex:
            accepted = sum(ex.map(request,rows))
    marks = ','.join(['%s']*len(rows)); ids=[r['key_id'] for r in rows]
    deadline=time.monotonic()+cfg['wait_seconds']
    while True:
        after={r['key_id']:r for r in sql('SELECT key_id,version,status,SHA2(key_value,256) AS digest '
            'FROM kms.keymanage WHERE key_id IN ('+marks+')',ids)}
        if all(changed(r,after.get(r['key_id'])) for r in rows) or time.monotonic()>=deadline:
            break
        time.sleep(1)
    history={(r['key_id'],int(r['version'])) for r in sql('SELECT key_id,version FROM '
        'kms.keymanage_version_history WHERE key_id IN ('+marks+')',ids)}
    audits={(r['key_id'],int(r['key_version'])):r for r in sql('SELECT key_id,key_version,result_status,'
        'chain_status FROM kms.key_operation_record WHERE action_type=%s AND key_id IN ('+marks+')',['UPDATE',*ids])}
    out=[]
    for old in rows:
        new=after.get(old['key_id']); hist=(old['key_id'],int(old['version'])) in history
        audit=audits.get((old['key_id'],int(old['version'])+1),{})
        out.append(dict(batch_id=bid,key_id=public_id(cfg,old['key_id']),action='UPDATE',
            before_version=old['version'],after_version=new['version'] if new else None,
            material_changed=changed(old,new),history_present=hist,
            audit_result_status=audit.get('result_status'),chain_status=audit.get('chain_status'),
            # Audit result_status includes asynchronous chain work. Keep its
            # actual value separate from the verified database rotation.
            completed=bool(changed(old,new) and hist and audit),origin='live_execution'))
    return {'updates':out},dict(requested=n,http_accepted=accepted,
        completed=sum(r['completed'] for r in out),verified=all(r['completed'] for r in out))


def preallocation(cfg,bid,n,prior):
    from django.utils import timezone
    from pqkds.acceptance_revoke import isolated_tables
    from pqkds.crypto_utils import KyberCrypto
    from pqkds.models import Node,NodeLongTermKey,PreDistributedKey,LatticePreparation
    from pqkds import lattice_preallocation as service
    from pqkds.lattice_test_views import run_sampling
    from pqkds.sm4_crypto import SM4Crypto,PayloadCipher
    with isolated_tables((Node,NodeLongTermKey,PreDistributedKey,LatticePreparation)):
        kem=KyberCrypto(768);pk,sk=kem.generate_keypair()
        node=Node.objects.create(node_id='science-lattice',name='科学数据隔离节点',status='active',
            ip_address='127.0.0.1',port=0,kyber_public_key=base64.b64encode(pk).decode())
        NodeLongTermKey.objects.create(node=node,algorithm='KYBER',key_id='science-kyber',key_version=1,
            status='ACTIVE',public_key=pk.hex(),public_key_hash=hashlib.sha256(pk.hex().encode()).hexdigest())
        root,root_checks=service.create_root();child,child_checks=service.create_delegation(root,node)
        result=run_sampling(child,n,cfg['sampling_workers']);out=[]
        for sample in result['samples']:
            p=json.loads(sample['message']);shared=kem.decrypt(base64.b64decode(p['kem_ciphertext']),sk)
            key=SM4Crypto.decrypt(base64.b64decode(p['encrypted_aes_key']),
                PayloadCipher.kek_from_shared_secret('sm4',shared),
                base64.b64decode(p['nonce'])+base64.b64decode(p['tag']))
            out.append(dict(batch_id=bid,pool_id=result['poolId'],key_index=sample['index'],
                algorithm='kyber_kem',payload_algorithm='sm4',key_hash=sample['keyHash'],
                lattice_public_digest=sample['publicDigest'],package_digest=sample['packageDigest'],
                vector=sample['vector'],target=sample['target'],norm=sample['norm'],bound=sample['bound'],
                proof_verified=sample['verified'],recovered=hashlib.sha256(key).hexdigest()==sample['keyHash'],
                origin='isolated_real_execution',observed_at=timezone.now().isoformat()))
        params=dict(batch_id=bid,profile=result['preparation']['profile'],n=result['preparation']['n'],
            q=result['preparation']['q'],public_matrix=result['publicMatrix'],public_digest=child.public_digest,
            scope='隔离功能验证池项，不是生产库存，未覆盖跨域业务和节点Falcon上传')
        good=(len(out)==n and all(r['proof_verified'] and r['recovered'] for r in out)
            and all(c['passed'] for c in result['checks']) and root_checks['kernelRelation']
            and child_checks['preimageVerified'])
        service.load_context.cache_clear()
    return {'preallocation':out,'lattice_parameters':[params]},dict(requested=n,completed=len(out),
        verified=bool(good),sampling_ms=result['samplingMs'],checks=result['checks'],
        origin='isolated_real_execution',persistent_database_untouched=True)


def revoke(cfg,bid,n,prior):
    from pqkds.acceptance_revoke import run_abnormal_revocation
    r=run_abnormal_revocation(n);rows=[]
    for row in r['rows']:
        rows.append(dict(batch_id=bid,key_id=public_id(cfg,bid+':'+str(row['keyId'])),
            algorithm=row['algorithm'],input_rule=row['rule'],abnormal=row['abnormal'],
            attempted=row['attempted'],before_status=row['beforeStatus'],after_status=row['afterStatus'],
            detected_rule=row['detectedRule'],action=row['action'],passed=row['passed'],
            observed_at=r['observedAt'],origin='isolated_real_execution'))
    return {'revocations':[x for x in rows if x['abnormal']], 'controls':[x for x in rows if not x['abnormal']]},dict(
        requested=n,completed=r['revoked'],controls=r['controls'],controls_passed=r['controlsPassed'],
        verified=r['passed'] and r['cleanupComplete'],elapsed_ms=r['elapsedMs'],
        detection_elapsed_ms=r['detectionElapsedMs'],pool_revoked=r['poolRevoked'],sessions_revoked=r['sessionsRevoked'],
        invalidations=r['invalidations'],origin='isolated_real_execution',persistent_database_untouched=True)


def seed_channels():
    from django.utils import timezone
    from pqkds.crypto_utils import KyberCrypto,FalconCrypto
    from pqkds.sm4_crypto import PayloadCipher,SM4Crypto
    from pqkds.models import Node,NodeLongTermKey,SessionKey,SessionKeyConfirmation,UserNodeAuthorization
    nodes=[];materials={};channels={};kem=KyberCrypto(768);signer=FalconCrypto(512)
    for code in ('science-A','science-B','science-C'):
        pk,sk=kem.generate_keypair();spk,ssk=signer.generate_keypair()
        node=Node.objects.create(node_id=code,name=code,sys_user_id=990000+len(nodes),status='active',
            ip_address='127.0.0.1',port=0,kyber_public_key=base64.b64encode(pk).decode(),falcon_sign_public_key=spk.hex())
        for alg,pub in (('KYBER',pk),('FALCON',spk)):
            NodeLongTermKey.objects.create(node=node,key_id=code+'-'+alg,key_version=1,algorithm=alg,
                status='ACTIVE',public_key=pub.hex(),public_key_hash=hashlib.sha256(pub.hex().encode()).hexdigest())
        nodes.append(node);materials[code]=pk,sk,spk,ssk
    for a,b in itertools.permutations(nodes,2):
        UserNodeAuthorization.objects.create(user_id=a.sys_user_id,node=b,status='active')
    for a,b in itertools.combinations(nodes,2):
        ct,shared=kem.encrypt(materials[b.node_id][0]);shared2=kem.decrypt(ct,materials[b.node_id][1])
        key=PayloadCipher.generate_key();wrapped,tag=SM4Crypto.encrypt(key,PayloadCipher.kek_from_shared_secret('sm4',shared))
        recovered=SM4Crypto.decrypt(wrapped,PayloadCipher.kek_from_shared_secret('sm4',shared2),tag)
        packet=encoded([a.node_id,b.node_id,ct.hex(),wrapped.hex()]);sig=signer.sign(packet,materials[a.node_id][3])
        if key!=recovered or signer.verify(sig,materials[a.node_id][2])!=packet:
            raise RuntimeError('Pairwise fixture channel cryptographic verification failed')
        session=SessionKey.objects.create(session_id='science-channel-'+secrets.token_hex(16),node1=a,node2=b,
            session_type='kyber_kem',status='established',expires_at=timezone.now()+timedelta(hours=1),
            recipient_key_id=b.node_id+'-KYBER',recipient_key_version=1,
            falcon_key_id=a.node_id+'-FALCON',falcon_key_version=1)
        proof=hmac.new(key,session.session_id.encode(),hashlib.sha256).hexdigest()
        for node in (a,b):
            SessionKeyConfirmation.objects.create(session=session,node=node,proof=proof,key_recovered=True,confirmed_at=timezone.now())
        channels[session.session_id]=key
    return nodes,channels


def agreements(cfg,bid,n,prior):
    from Crypto.Cipher import AES
    from pqkds import group_agreement_service as svc
    from pqkds.acceptance_revoke import isolated_tables
    from pqkds.models import (Node,NodeLongTermKey,SessionKey,SessionKeyConfirmation,
        UserNodeAuthorization,GroupKeyAgreement,GroupAgreementMember)
    models=(Node,NodeLongTermKey,SessionKey,SessionKeyConfirmation,UserNodeAuthorization,GroupKeyAgreement,GroupAgreementMember)
    groups=[];members=[]
    from contextlib import nullcontext
    for model in reversed(models):
        model.objects.all().delete()
    with nullcontext():
        nodes,channels=seed_channels()
        for _ in range(n):
            g=svc.create(nodes[0],{'participantNodeIds':[x.node_id for x in nodes[1:]]});gid=g['agreementId']
            contributions={x.node_id:secrets.token_bytes(32) for x in nodes}
            for node in nodes:
                commitment=svc.digest([g['scopeHash'],node.node_id,contributions[node.node_id].hex()])
                g=svc.operate(gid,node,'commit',{'commitment':commitment})
            for node in nodes:
                packets=[]
                for peer in nodes:
                    if peer==node:continue
                    sid=next(s for a,b,s in g['channels'] if {a,b}=={node.node_id,peer.node_id})
                    ctx=[svc.PROTOCOL,'contribution',g['scopeHash'],g['transcriptHash'],node.node_id,peer.node_id,sid]
                    key=hkdf(channels[sid],bytes.fromhex(g['transcriptHash']),encoded(ctx),32);iv=secrets.token_bytes(12)
                    cipher=AES.new(key,AES.MODE_GCM,nonce=iv);cipher.update(encoded(ctx))
                    ct,tag=cipher.encrypt_and_digest(contributions[node.node_id])
                    packets.append(dict(toNodeId=peer.node_id,channelSessionId=sid,
                        iv=base64.b64encode(iv).decode(),ciphertext=base64.b64encode(ct+tag).decode()))
                g=svc.operate(gid,node,'exchange',{'packets':packets})
            keys=[]
            for node in nodes:
                snapshot=svc.detail(gid,node);recovered={node.node_id:contributions[node.node_id]}
                for packet in snapshot['inbox']:
                    sender=packet['fromNodeId'];sid=packet['channelSessionId']
                    ctx=[svc.PROTOCOL,'contribution',g['scopeHash'],g['transcriptHash'],sender,node.node_id,sid]
                    key=hkdf(channels[sid],bytes.fromhex(g['transcriptHash']),encoded(ctx),32)
                    cipher=AES.new(key,AES.MODE_GCM,nonce=base64.b64decode(packet['iv']));cipher.update(encoded(ctx))
                    raw=base64.b64decode(packet['ciphertext']);value=cipher.decrypt_and_verify(raw[:-16],raw[-16:])
                    commitment=next(x['commitment'] for x in snapshot['members'] if x['nodeId']==sender)
                    if svc.digest([g['scopeHash'],sender,value.hex()])!=commitment:
                        raise RuntimeError('Contribution commitment mismatch')
                    recovered[sender]=value
                material=b''.join(recovered[x['nodeId']] for x in snapshot['members']);salt=bytes.fromhex(g['transcriptHash'])
                keys.append(hkdf(material,salt,encoded([svc.PROTOCOL,'group-sm4-key',g['scopeHash']]),16))
                ck=hkdf(material,salt,encoded([svc.PROTOCOL,'group-confirmation-key',g['scopeHash']]),32)
                proof=hmac.new(ck,encoded([svc.PROTOCOL,'confirm',g['scopeHash'],g['transcriptHash']]),hashlib.sha256).hexdigest()
                g=svc.operate(gid,node,'confirm',{'proof':proof,'transcriptHash':g['transcriptHash']})
            good=g['status']=='established' and len(set(keys))==1
            groups.append(dict(batch_id=bid,agreement_id=gid,status=g['status'],created_at=g['createdAt'],
                expires_at=g['expiresAt'],protocol=svc.PROTOCOL,scope_hash=g['scopeHash'],
                transcript_hash=g['transcriptHash'],all_keys_equal=good,origin='isolated_real_execution'))
            for row in g['members']:
                members.append(dict(batch_id=bid,agreement_id=gid,node_id=row['nodeId'],
                    committed_at=row['committedAt'],exchanged_at=row['exchangedAt'],confirmed_at=row['confirmedAt'],
                    origin='isolated_real_execution'))
    return {'agreements':groups,'members':members},dict(requested=n,completed=sum(x['all_keys_equal'] for x in groups),
        verified=all(x['all_keys_equal'] for x in groups),pairwise_cryptography_verified=True,
        origin='isolated_real_execution',persistent_database_untouched=True)


def run(cfg):
    import fcntl
    # SSH termination may leave its container process alive. Prevent overlapping
    # recovery of the same run, even when the client output lock is released.
    run_lock=open('/tmp/kms-science-lock-'+cfg['run_id'],'a')
    fcntl.flock(run_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','application.settings')
    sys.path.insert(0,os.getcwd())
    import django
    if cfg['kind']=='agreements':
        from django.conf import settings
        settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
        settings.CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}
    django.setup()
    if cfg['kind']=='agreements':
        from django.apps import apps
        from django.db import connection
        if connection.vendor!='sqlite':raise RuntimeError('Agreement fixture must use fresh SQLite')
        with connection.schema_editor() as editor:
            for model in apps.get_models():
                editor.create_model(model)
    if cfg['kind']=='plan':
        emit('inventory',data=inventory());return
    if cfg['kind'] in ('generation','update') and shutil.disk_usage('/').free < cfg['min_free_gib']*1024**3:
        raise RuntimeError('Free disk below configured reserve, no online requests submitted')
    kind=cfg['kind'];fn=globals()[kind]
    for index in range(cfg['first_batch'],cfg['batch_count']):
        n=min(cfg['batch_size'],cfg['count']-index*cfg['batch_size'])
        bid='science-'+cfg['run_id']+'-'+str(index)
        prior=cfg.get('pending') if index==cfg['first_batch'] else None
        started=time.monotonic()
        tables,summary=fn(cfg,bid,n,prior)
        summary['total_ms']=(time.monotonic()-started)*1000
        emit('batch',index=index,batch_id=bid,tables=tables,summary=summary)
        if not summary['verified']:
            raise RuntimeError('Batch did not meet verification conditions, stopped without fabricating results')
    emit('finished')


if __name__=='__main__':
    try:
        run(config)
    except Exception as exc:
        emit('error',error_type=type(exc).__name__,message=str(exc)[:400])
        raise SystemExit(1)
