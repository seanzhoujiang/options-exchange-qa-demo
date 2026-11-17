# JMeter 订单流程

更新时间：2026-11-17 17:42:23 JST。

启动服务：

```sh
env ENABLE_TEST_API=1 ./.venv/bin/uvicorn app.main:app --port 8000
```

运行计划：

```sh
jmeter -n -t perf/order_flow.jmx -l results.jtl -e -o report/
```

setup 线程获取验证码并登录；负载线程创建挂单后撤单。默认目标 `127.0.0.1:8000`，线程数 `10`、ramp-up `10` 秒、时长 `60` 秒。可用 `-Jhost`、`-Jport`、`-Jthreads`、`-Jramp`、`-Jduration` 修改；`-Jsummary_file` 设置计划内汇总文件。HTML 报告包含吞吐量、平均响应时间、p95、p99 和错误率。

所有线程共用演示账户令牌。全局状态锁会限制吞吐；订单留在内存且不会清理，长时间运行会增加内存占用。若下单成功但撤单失败，挂单和冻结金额会保留。计划尚未运行，没有性能基准。
