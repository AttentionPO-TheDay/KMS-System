# 量子攻击仿真与参数评估

验收台保留任务书原要求：**系统能够抵御量子攻击种类不少于3种**。

本模块提供三层独立证据：

1. **量子电路仿真**：8量子位、256候选的弱参数二元秘密LWE问题。实际计算H门、对角相位Oracle和扩散算子的状态向量，运行12次Grover迭代并按Born概率抽样256次。公开种子、A、b和噪声界可复算。禁用Oracle的对照须保持均匀分布，结果还须符合解析概率和归一化检验。
2. **实际参数成本评估**：对KYBER round-3的512/768/1024参数，分别调用固定版本lattice-estimator的`primal_usvp`、`primal_bdd`、`dual`，显式传入`ADPS16(mode='quantum')`。秘密/误差分布、n/q/m、BKZ块大小、原始成本、版本及耗时进入结果。
3. **部署业务对照**：评估前后均通过现有网关调用原生KYBER正常封装、互操作和负向验证。不读取业务私钥，不登记、更新、回收业务密钥。

三种评估是三种格攻击成本模型，**不是三份量子电路，也不自动证明抵御三种量子攻击**。共用的Grover电路仅验证弱样本搜索算法；它不是生产参数的uSVP/BDD/dual电路实现。模型成本`rop`不是秒数、量子门数或安全证明，未覆盖完整KEM、压缩、自定义无证书协议或全部攻击。量子筛法使用启发式Core-SVP成本`2^(0.265*β)`，模型与版本变化可能影响数值。没有以任意成本阈值判定任务书通过。

结果契约为`status=completed, verdict=evaluated, passed=false`，嵌套证据`evaluationComplete=true, acceptancePassed=false`。验收台显示“评估完成，指标待核验”；原四项KYBER/FALCON算法与协议测试单列保留。验收口径由第三方依据攻击分类与证据确认。

## 执行与复核

```powershell
python -m unittest discover -s kms-acceptance/quantum -p test_quantum.py -q
docker build -t kms-quantum-evaluator:local -f kms-acceptance/quantum/evaluator.Dockerfile kms-acceptance/quantum
# 单模型可直接运行；结果保存到当前目录指定的挂载位置。
docker run --rm --entrypoint sage -v "${PWD}/output/quantum-attack-research:/evidence" kms-quantum-evaluator:local -python /app/evaluate.py --case-id quantum-lwe-usvp --output /evidence/quantum-lwe-usvp.json
```

其余固定caseId为`quantum-lwe-bdd`和`quantum-lwe-dual`。Docker镜像同时固定SageMath镜像摘要、估算器Git版本和源码归档SHA-256；估算器原许可保留在镜像`/app/LICENSE`。

HTTP服务仅提供内部`POST /evaluate`，请求为`{"caseId":"quantum-lwe-usvp"}`，需`X-Internal-Token`；不接受参数、材料或命令覆盖。只允许一个任务，工作进程100秒超时，失败返回503而非通过结果。调用者取消后，不再采纳结果；服务端工作进程最多继续到100秒硬超时。没有宿主端口、数据库挂载或Docker套接字。

部署时需先重建验收后端和前端，再叠加`kms-ops/docker-compose.quantum.yml`启用独立评估器。要求`INTERNAL_TOKEN`至少16字符；验收后端使用同一内部凭据。仍使用既有管理员权限、任务租约、取消及终态栅栏。`ACCEPTANCE_SECURITY_NODE_ID`必须指向已有可登录节点，不自动创建节点。

2026-10-22已部署至10服务器（10.112.125.22），版本`quantum-evaluation-20261022`；通过远端验收台实际执行三项评估并核验九组参数结果、原生KYBER前后对照和响应式页面。部署证据位于`output/quantum-deployment/`，远端备份位于`/home/rbf/kms-sys/releases/quantum-evaluation-20261022/backup/`。
