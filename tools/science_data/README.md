# 科学数据采集工具

按课题二汇交计划执行真实业务请求及隔离实验，保留批次证据、实际数量、耗时、来源和文件校验值。默认模式只读，不运行压测，也不根据 HTTP 成功数推算数据记录数。

## 运行条件

本机 Python 3.10 及以上版本、SSH。默认服务器别名为 expert-machine，Django 容器为 dvadmin3-django，MySQL 容器为 kms_mysql。算法、Django 和数据库依赖使用服务器现有运行环境。本机无需安装密码算法包。

生产生成和更新会修改验收用户的业务记录。更新只选择 acceptance 域中已有的有效 SM2 验收密钥，允许同一密钥不同版本形成不同操作样本。预分配、协商和回收使用隔离环境执行真实算法，不增加生产业务库存，不代表浏览器节点本机性能或生产持久化性能。

## 查询库存与缺口

```bash
python tools/run_science_collection.py --kind plan
```

目标为 3000000 条生成登记、3000 条协商主记录、9000 条协商成员、90000 条预分配记录、540000 条更新回收样本。库存查询给出原始表行数，是否有效还需结合字段及采集证据核验。隔离实验按来源单独计数，不能将其填报为生产表行数。计划容量是预估值，最终以实际文件字节数为准，禁止复制文件或填充无意义内容凑容量。

## 采集示例

先执行少量样本确认服务环境，再依据当时的库存缺口设置 count。下列数字仅为示例，每个新任务使用新的输出目录。

```bash
python tools/run_science_collection.py --kind generation --count 1000 --batch-size 1000 --output output/science/generation --execute
python tools/run_science_collection.py --kind update --count 6000 --batch-size 1000 --output output/science/update --execute
python tools/run_science_collection.py --kind preallocation --count 640 --batch-size 64 --sampling-workers 4 --output output/science/preallocation --execute
python tools/run_science_collection.py --kind agreements --count 100 --batch-size 100 --output output/science/agreements --execute
python tools/run_science_collection.py --kind revoke --count 6000 --batch-size 100 --output output/science/revoke --execute
```

回收每批附带 4 条正常对照。按 100 条一批完成 6000 条异常样本，即得到 240 条正常对照。预分配保存公开格参数、短向量、证明及解封核验结果。协商执行三节点承诺、加密贡献交换、承诺核验、密钥派生和确认，每次产生一条主记录及三条成员记录。

不加 execute 时只显示执行配置。采集失败即停止，失败结果保留，不强行标记通过。生成与更新先检查 MySQL 数据卷剩余空间，默认保留 10 GiB。

## 恢复与核验

```bash
python tools/run_science_collection.py --output output/science/generation --resume --execute
python -m unittest tools/science_data/test_collection.py
```

每批保存 control.json 及 batches 目录，只有核验通过才推进批次。生成接口没有持久幂等契约，更新接口的 Redis 幂等记录有有效期，因此中断批次恢复时仅查询保存的基线，不重新发送请求。若中断批次未全部完成，保留实际结果，核对服务器后另建任务补充缺口，不能删除检查点后盲目重发。同一运行编号在服务器也有进程锁，SSH 断连后旧进程尚在运行时会拒绝重叠恢复。

datasets 中的 CSV 和 manifest.json 是公开候选材料。complete 为 false 的运行不能按请求总数填报；本地 control.json、输出根目录中的映射密钥及临时控制文件不得放入汇交包。私钥、陷门、随机贡献、共享秘密、会话密钥及密文载荷不导出。

## 导出数据库

先使用 `output/汇交计划/导出工具/export_kms.py` 检查小样，再进行全量导出。导出器用同一只读事务读取公开字段，并保存表行数、文件字节数、SHA256 和字段字典。数据库快照与隔离实验分别归档，批次结果不能与对应数据库行重复计数。

完成全量导出和所有采集后，可用打包器生成汇交候选目录。它只接收完整数据库快照和 complete 为 true 的运行目录，生成来源核验报告和最终校验清单。

```bash
python tools/science_data/package_collection.py \
  --snapshot output/science-export \
  --run output/science-collection-20261024/generation-target \
  --run output/science-collection-20261024/update-target \
  --run output/science-collection-20261024/agreements \
  --run output/science-collection-20261024/preallocation-target \
  --run output/science-collection-20261024/preallocation \
  --run output/science-collection-20261024/revoke \
  --output output/汇交候选包
```
