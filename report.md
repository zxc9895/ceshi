# 数据源可用性测试报告

- 测试日期：2026-09-30
- 规则：每个源最多试 3 次，间隔 3 秒；日涨跌幅差距 ≤ 0.1 个百分点算一致
- 重跑：`python test_sources.py`（会覆盖本报告和 samples/）

## 结论

- 8 个数据源（第 5 项按 JEPI/QYLD/SPYI 拆成 3 行，共 10 行）：9 行能用，1 行不能用。

## 结果总表

| # | 数据源 | 能不能用 | 拿到什么 | 起止日期 | 行数 | 失败原因 | 一致性结果 |
|---|---|---|---|---|---|---|---|
| 1 | Yahoo Finance | ✅ 能 | SPY 近1年日线（含 Close / Adj Close） | 2025-09-30 ~ 2026-09-29 | 251 | — | 无法比对：Stooq 没拿到数据 |
| 2 | Stooq | ❌ 不能 | 无（目标：SPY 近1年日线） | — | 0 | 返回的不是 CSV：'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"></head><body><noscript>T' | 无法比对：Stooq 没拿到数据 |
| 3 | Ken French | ✅ 能 | Mom 动量因子月度收益（%） | 1927-01-01 ~ 2026-08-01 | 1196 | — | — |
| 4 | Cboe BXM | ✅ 能 | BXM 指数全部历史日线 | 2002-03-22 ~ 2026-09-29 | 6167 | — | — |
| 5a | 发行商分红 JEPI | ✅ 能 | JEPI 近12个月分红（来源：Yahoo，官网失败：No tables found） | 2025-10-01 ~ 2026-09-01 | 12 | — | 19a 返还本金比例：官网未取得 |
| 5b | 发行商分红 QYLD | ✅ 能 | QYLD 近12个月分红（来源：Yahoo，官网失败：页面里没找到分红表（可能靠 JS 动态加载）） | 2025-10-20 ~ 2026-09-21 | 12 | — | 19a 返还本金比例：官网未取得 |
| 5c | 发行商分红 SPYI | ✅ 能 | SPYI 分红表（来源：发行商官网） | — | 12 | — | — |
| 6 | 东方财富 | ✅ 能 | 510300 近1年日线（不复权，akshare） | 2025-09-30 ~ 2026-09-30 | 242 | — | 东方财富 vs 新浪：重叠 240 天，一致 240 天（100.0%），最大差 0.000 个百分点（2025-10-09） |
| 7 | 新浪财经 | ✅ 能 | 510300 近1年日线（不复权，akshare） | 2025-09-30 ~ 2026-09-29 | 241 | — | 东方财富 vs 新浪：重叠 240 天，一致 240 天（100.0%），最大差 0.000 个百分点（2025-10-09） |
| 8 | 中证指数 | ✅ 能 | 沪深300当前成分股 | — | 300 | — | — |

## 对照组（判断是个别网站被挡，还是整体外网不通）

| 网址 | 结果 |
|---|---|
| https://pypi.org/simple/ | 通 |
| https://api.github.com | 通 |
| https://www.google.com | 通 |
| https://example.com | 通 |
| https://www.baidu.com | 通 |

## 每次尝试的记录

- **Yahoo Finance**：第1次：成功
- **Stooq**：第1次：('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))；第2次：('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))；第3次：返回的不是 CSV：'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"></head><body><noscript>T'
- **Ken French**：第1次：成功
- **Cboe BXM**：第1次：成功
- **发行商分红 JEPI**：官网 第1次：No tables found；官网 第2次：No tables found；官网 第3次：No tables found；Yahoo 第1次：成功
- **发行商分红 QYLD**：官网 第1次：页面里没找到分红表（可能靠 JS 动态加载）；官网 第2次：页面里没找到分红表（可能靠 JS 动态加载）；官网 第3次：页面里没找到分红表（可能靠 JS 动态加载）；Yahoo 第1次：成功
- **发行商分红 SPYI**：第1次：成功
- **东方财富**：第1次：HTTPSConnectionPool(host='push2his.eastmoney.com', port=443): Max retries exceeded with url: /api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57；第2次：成功
- **新浪财经**：第1次：成功
- **中证指数**：第1次：成功

## 样本文件

- `samples/yahoo_spy.csv`
- `samples/french_momentum_monthly.csv`
- `samples/cboe_bxm_history.csv`
- `samples/yahoo_jepi_dividends.csv`
- `samples/yahoo_qyld_dividends.csv`
- `samples/issuer_spyi_dist.csv`
- `samples/eastmoney_510300.csv`
- `samples/sina_510300.csv`
- `samples/csindex_hs300_cons.csv`
- `samples/attempt_log.json`：完整尝试日志（含报错堆栈）
