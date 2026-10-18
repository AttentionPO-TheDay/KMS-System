# Django 链写入恢复及单条更新存证补录

修复服务器 FISCO 覆盖配置中 Django 的 KMS_CHAIN_WRITES_ENABLED=false。Java 生成、生命周期服务原已启用；本次只将 Django 改为 true，重建 Django 容器，不替换应用镜像，不更新密钥。

apply.sh 检查发布前配置摘要、镜像、渲染后 Compose 的精确差异，只允许一个开关变化；失败恢复原配置。网关、Java、数据库、Redis 和回收任务不重建。

repair-event.py 默认只读，逐块查真实回执，避免重复存证。显式 --submit 仅补录 A-SSCL-4cfab58e/v2（数据库主键 37，节点 A）的 KEY_UPDATED；写入前后检查两版密钥元数据不变。真实交易必须有成功回执，事件中的类型、主键、版本、节点及公钥摘要都须吻合。它不更新 SQL，不调用密钥轮换接口。

补录是延迟发生的真实链交易，不伪造原更新时刻，也不改变先前浏览器收到的失败回执。

服务器执行：

```bash
bash /home/rbf/kms-sys/releases/django-chain-write-20261015/apply.sh
docker exec -i dvadmin3-django python - --submit < /home/rbf/kms-sys/releases/django-chain-write-20261015/repair-event.py
```

恢复配置时将发布目录的 docker-compose.fisco-enabled.before.yml 复制回 /home/rbf/kms-sys/docker-compose.fisco-enabled.yml，再用原 Compose 命令仅重建 dvadmin3-django。已确认的链交易不能通过配置回滚删除。
