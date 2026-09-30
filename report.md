# 数据源可用性测试报告

- 测试日期：2026-09-30
- 规则：每个源最多试 3 次，间隔 3 秒；日涨跌幅差距 ≤ 0.1 个百分点算一致
- 重跑：`python test_sources.py`（会覆盖本报告和 samples/）

## 结论

- 8 个数据源（第 5 项按 JEPI/QYLD/SPYI 拆成 3 行，共 10 行）：0 行能用，10 行不能用。
- 连 google.com / baidu.com 这种普通网站也被代理 403 拒绝，只有 pypi、GitHub 能通：说明这台云电脑实际生效的是「只放行包仓库和 GitHub」的受限网络，而不是 Full。问题不在这些数据源本身，要先改环境的网络设置（改完新开会话），再重跑本脚本。

## 结果总表

| # | 数据源 | 能不能用 | 拿到什么 | 起止日期 | 行数 | 失败原因 | 一致性结果 |
|---|---|---|---|---|---|---|---|
| 1 | Yahoo Finance | ❌ 不能 | 无（目标：SPY 近1年日线） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com） | 无法比对：Yahoo Finance、Stooq 没拿到数据 |
| 2 | Stooq | ❌ 不能 | 无（目标：SPY 近1年日线） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 stooq.com） | 无法比对：Yahoo Finance、Stooq 没拿到数据 |
| 3 | Ken French | ❌ 不能 | 无（目标：动量因子月度数据） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 mba.tuck.dartmouth.edu） | — |
| 4 | Cboe BXM | ❌ 不能 | 无（目标：BXM 全部历史日线） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 cdn.cboe.com） | — |
| 5a | 发行商分红 JEPI | ❌ 不能 | 无（目标：JEPI 近12个月每月分红） | — | 0 | 官网：代理拒绝连接（CONNECT 403，网络策略不放行 am.jpmorgan.com）；Yahoo 兜底：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com） | 19a 返还本金比例：官网不可达，未取得 |
| 5b | 发行商分红 QYLD | ❌ 不能 | 无（目标：QYLD 近12个月每月分红） | — | 0 | 官网：代理拒绝连接（CONNECT 403，网络策略不放行 www.globalxetfs.com）；Yahoo 兜底：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com） | 19a 返还本金比例：官网不可达，未取得 |
| 5c | 发行商分红 SPYI | ❌ 不能 | 无（目标：SPYI 近12个月每月分红） | — | 0 | 官网：代理拒绝连接（CONNECT 403，网络策略不放行 neosfunds.com）；Yahoo 兜底：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com） | 19a 返还本金比例：官网不可达，未取得 |
| 6 | 东方财富 | ❌ 不能 | 无（目标：510300 近1年日线） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 push2his.eastmoney.com） | 无法比对：东方财富、新浪财经 没拿到数据 |
| 7 | 新浪财经 | ❌ 不能 | 无（目标：510300 近1年日线） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 finance.sina.com.cn） | 无法比对：东方财富、新浪财经 没拿到数据 |
| 8 | 中证指数 | ❌ 不能 | 无（目标：沪深300成分股名单） | — | 0 | 代理拒绝连接（CONNECT 403，网络策略不放行 oss-ch.csindex.com.cn） | — |

## 对照组（判断是个别网站被挡，还是整体外网不通）

| 网址 | 结果 |
|---|---|
| https://pypi.org/simple/ | 通 |
| https://api.github.com | 通 |
| https://www.google.com | 不通：代理拒绝连接（CONNECT 403，网络策略不放行 www.google.com） |
| https://example.com | 不通：代理拒绝连接（CONNECT 403，网络策略不放行 example.com） |
| https://www.baidu.com | 不通：代理拒绝连接（CONNECT 403，网络策略不放行 www.baidu.com） |

## 每次尝试的记录

- **Yahoo Finance**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；第3次：$SPY: possibly delisted; no timezone found
- **Stooq**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 stooq.com）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 stooq.com）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 stooq.com）
- **Ken French**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 mba.tuck.dartmouth.edu）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 mba.tuck.dartmouth.edu）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 mba.tuck.dartmouth.edu）
- **Cboe BXM**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 cdn.cboe.com）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 cdn.cboe.com）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 cdn.cboe.com）
- **发行商分红 JEPI**：官网 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 am.jpmorgan.com）；官网 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 am.jpmorgan.com）；官网 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 am.jpmorgan.com）；Yahoo 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）
- **发行商分红 QYLD**：官网 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 www.globalxetfs.com）；官网 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 www.globalxetfs.com）；官网 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 www.globalxetfs.com）；Yahoo 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）
- **发行商分红 SPYI**：官网 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 neosfunds.com）；官网 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 neosfunds.com）；官网 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 neosfunds.com）；Yahoo 第1次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第2次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）；Yahoo 第3次：代理拒绝连接（CONNECT 403，网络策略不放行 query*.finance.yahoo.com）
- **东方财富**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 push2his.eastmoney.com）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 push2his.eastmoney.com）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 push2his.eastmoney.com）
- **新浪财经**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 finance.sina.com.cn）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 finance.sina.com.cn）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 finance.sina.com.cn）
- **中证指数**：第1次：代理拒绝连接（CONNECT 403，网络策略不放行 oss-ch.csindex.com.cn）；第2次：代理拒绝连接（CONNECT 403，网络策略不放行 oss-ch.csindex.com.cn）；第3次：代理拒绝连接（CONNECT 403，网络策略不放行 oss-ch.csindex.com.cn）

## 样本文件

- 无（所有源都没拿到数据）
- `samples/attempt_log.json`：完整尝试日志（含报错堆栈）
