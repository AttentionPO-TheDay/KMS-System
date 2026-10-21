# 密钥算法核验过程折叠

- SecurityResult将算法过程改为原生details/summary，默认收起；点击标题展开或收起，支持Enter/Space键盘操作。
- 外部结论、检查汇总和失败提示保持可见；26条算法证据完整保留。
- 已部署kms-gateway-nginx:pq-collapse-20261019，仅重建nginx；其余82容器ID/启动时间不变，挂载/端口/环境保持。
- 前端生产构建通过。原HTTPS地址Chrome：4个算法区默认收起、展开/收起/键盘操作、刷新状态、收起时失败可见、1024无横向溢出均通过，真实26条算法检查通过，无页面错误。
- 证据：deployment-result.json、ui-verification.json、algorithm-collapsed.png、algorithm-expanded.png。失败显示回归仅使用浏览器本地响应拦截，不写入服务器。
- apply.py已用，勿重跑覆盖backup。未提交或推送Git。
