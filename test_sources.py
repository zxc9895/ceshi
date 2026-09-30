"""测试 8 个数据源能否从当前机器访问，存样本到 samples/，生成 report.md。

用法：python test_sources.py
依赖：pip install yfinance akshare pandas requests lxml xlrd
"""
import io
import json
import re
import time
import traceback
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)

TODAY = date.today()
ONE_YEAR_AGO = TODAY - timedelta(days=365)
MAX_TRIES = 3
WAIT_SECONDS = 3
TOLERANCE_PP = 0.1  # 日涨跌幅差距阈值（百分点）
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

results = {}   # 数据源名 -> 结果字典
frames = {}    # 数据源名 -> DataFrame（用于一致性比对）


def http_get(url, **kw):
    r = requests.get(url, headers=UA, timeout=20, **kw)
    r.raise_for_status()
    return r


def explain(err, host=""):
    """把异常翻成一句人话。host 用于报错里不带域名的库（如 yfinance）。"""
    msg = str(err)
    m = re.search(r"host='([^']+)'", msg)
    host = m.group(1) if m else host
    if "403" in msg and ("Tunnel" in msg or "CONNECT" in msg or "ProxyError" in msg):
        return f"代理拒绝连接（CONNECT 403，网络策略不放行{' ' + host if host else ''}）"
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return f"连接超时 {host}".strip()
    if "certificate" in msg.lower():
        return f"TLS 证书校验失败 {host}".strip()
    return msg.splitlines()[0][:200] if msg else type(err).__name__


def attempt(name, fn, host=""):
    """最多试 MAX_TRIES 次，每次间隔 WAIT_SECONDS 秒；返回 fn 的结果或 None。"""
    log, reasons = [], []
    r = results[name]
    for i in range(1, MAX_TRIES + 1):
        try:
            out = fn()
            log.append(f"第{i}次：成功")
            r["attempts"] = log
            return out
        except Exception as e:  # noqa: BLE001 失败只记录，不中断
            reasons.append(explain(e, host))
            log.append(f"第{i}次：{reasons[-1]}")
            r.setdefault("raw_errors", []).append(traceback.format_exc(limit=3))
            if i < MAX_TRIES:
                time.sleep(WAIT_SECONDS)
    # 首因优先：被代理拒绝后 yfinance 等库会再报"疑似退市"之类的次生错误
    r["reason"] = next((x for x in reasons if "代理拒绝" in x), reasons[-1])
    r["attempts"] = log
    return None


def record(name, df, what, date_col=None, file=None):
    r = results[name]
    r["ok"] = True
    r["reason"] = ""
    r["what"] = what
    r["rows"] = len(df)
    if date_col is not None:
        d = pd.to_datetime(df[date_col])
        r["start"], r["end"] = str(d.min().date()), str(d.max().date())
    if file:
        df.to_csv(SAMPLES / file, index=False)
        r["file"] = f"samples/{file}"


def source(no, name, what):
    results[name] = {"no": no, "ok": False, "what": what, "rows": 0, "start": "", "end": "",
                     "reason": "", "file": "", "consistency": ""}


# ---------- 1. Yahoo Finance ----------
def yahoo_spy():
    import yfinance as yf
    df = yf.Ticker("SPY").history(start=str(ONE_YEAR_AGO), end=str(TODAY + timedelta(days=1)),
                                  auto_adjust=False, raise_errors=True)
    if df.empty:
        raise RuntimeError("yfinance 返回空表")
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date
    return df[["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]]


# ---------- 2. Stooq ----------
def stooq_spy():
    url = (f"https://stooq.com/q/d/l/?s=spy.us&i=d"
           f"&d1={ONE_YEAR_AGO:%Y%m%d}&d2={TODAY:%Y%m%d}")
    text = http_get(url).text
    if not text.startswith("Date"):
        raise RuntimeError(f"返回的不是 CSV：{text[:120]!r}")
    return pd.read_csv(io.StringIO(text))


# ---------- 3. Ken French 动量因子 ----------
def french_mom():
    url = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
           "F-F_Momentum_Factor_CSV.zip")
    z = zipfile.ZipFile(io.BytesIO(http_get(url).content))
    lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    rows = []
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) == 2 and re.fullmatch(r"\d{6}", parts[0]):
            rows.append((parts[0], float(parts[1])))
        elif rows and "Annual" in ln:   # 月度段结束，后面是年度数据
            break
    df = pd.DataFrame(rows, columns=["YYYYMM", "Mom"])
    df["Date"] = pd.to_datetime(df["YYYYMM"], format="%Y%m")
    return df


# ---------- 4. Cboe BXM ----------
def cboe_bxm():
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/BXM_History.csv"
    text = http_get(url).text
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    return df


# ---------- 5. 发行商分红 ----------
ISSUER_PAGES = {
    "JEPI": "https://am.jpmorgan.com/us/en/asset-management/adv/products/"
            "jpmorgan-equity-premium-income-etf-etf-shares-46641q332",
    "QYLD": "https://www.globalxetfs.com/funds/qyld/",
    "SPYI": "https://neosfunds.com/spyi/",
}


def issuer_page(ticker):
    html = http_get(ISSUER_PAGES[ticker]).text
    tables = pd.read_html(io.StringIO(html))
    dist = [t for t in tables if any("ex" in str(c).lower() for c in t.columns)]
    if not dist:
        raise RuntimeError("页面里没找到分红表（可能靠 JS 动态加载）")
    return dist[0]


def yahoo_divs(ticker):
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="1y", actions=True, raise_errors=True)
    s = h.loc[h["Dividends"] > 0, "Dividends"]
    if s.empty:
        raise RuntimeError("yfinance 分红记录为空")
    df = s.reset_index()
    df.columns = ["ExDate", "Dividend"]
    df["ExDate"] = pd.to_datetime(df["ExDate"]).dt.tz_localize(None).dt.date
    return df


# ---------- 6. 东方财富 510300 ----------
def em_510300():
    import akshare as ak
    df = ak.fund_etf_hist_em(symbol="510300", period="daily",
                             start_date=f"{ONE_YEAR_AGO:%Y%m%d}",
                             end_date=f"{TODAY:%Y%m%d}", adjust="")
    if df.empty:
        raise RuntimeError("akshare 返回空表")
    return df


# ---------- 7. 新浪 510300 ----------
def sina_510300():
    import akshare as ak
    df = ak.fund_etf_hist_sina(symbol="sh510300")
    if df.empty:
        raise RuntimeError("akshare 返回空表")
    df["date"] = pd.to_datetime(df["date"])
    return df[df["date"].dt.date >= ONE_YEAR_AGO]


# ---------- 8. 中证指数 沪深300成分股 ----------
def csindex_hs300():
    import akshare as ak
    df = ak.index_stock_cons_csindex(symbol="000300")
    if df.empty:
        raise RuntimeError("akshare 返回空表")
    return df


def compare(a, b, a_col, b_col, label):
    """两份日线按日期对齐，比较每日涨跌幅差距 ≤ TOLERANCE_PP 的比例。"""
    x = a.set_index("Date")[a_col].pct_change() * 100
    y = b.set_index("Date")[b_col].pct_change() * 100
    both = pd.concat([x, y], axis=1, keys=["a", "b"], join="inner").dropna()
    if both.empty:
        return f"{label}：无重叠日期"
    diff = (both["a"] - both["b"]).abs()
    ok = (diff <= TOLERANCE_PP).sum()
    worst = diff.idxmax()
    return (f"{label}：重叠 {len(both)} 天，一致 {ok} 天（{ok / len(both):.1%}），"
            f"最大差 {diff.max():.3f} 个百分点（{worst}）")


def probe(url):
    try:
        requests.get(url, timeout=10)
        return "通"
    except Exception as e:  # noqa: BLE001
        return "不通：" + explain(e)


def main():
    # 1
    source("1", "Yahoo Finance", "SPY 近1年日线")
    df = attempt("Yahoo Finance", yahoo_spy, "query*.finance.yahoo.com")
    if df is not None:
        record("Yahoo Finance", df, "SPY 近1年日线（含 Close / Adj Close）", "Date", "yahoo_spy.csv")
        frames["yahoo"] = df

    # 2
    source("2", "Stooq", "SPY 近1年日线")
    df = attempt("Stooq", stooq_spy)
    if df is not None:
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        record("Stooq", df, "SPY 近1年日线（CSV）", "Date", "stooq_spy.csv")
        frames["stooq"] = df

    # 3
    source("3", "Ken French", "动量因子月度数据")
    df = attempt("Ken French", french_mom)
    if df is not None:
        record("Ken French", df, "Mom 动量因子月度收益（%）", "Date", "french_momentum_monthly.csv")

    # 4
    source("4", "Cboe BXM", "BXM 全部历史日线")
    df = attempt("Cboe BXM", cboe_bxm)
    if df is not None:
        record("Cboe BXM", df, "BXM 指数全部历史日线", df.columns[0], "cboe_bxm_history.csv")

    # 5：官网优先，拿不到用 Yahoo
    for sub, t in zip("abc", ["JEPI", "QYLD", "SPYI"]):
        name = f"发行商分红 {t}"
        source(f"5{sub}", name, f"{t} 近12个月每月分红")
        df = attempt(name, lambda t=t: issuer_page(t))
        if df is not None:
            record(name, df, f"{t} 分红表（来源：发行商官网）", file=f"issuer_{t.lower()}_dist.csv")
            continue
        official_reason = results[name]["reason"]
        official_attempts = results[name]["attempts"]
        df = attempt(name, lambda t=t: yahoo_divs(t), "query*.finance.yahoo.com")
        results[name]["attempts"] = ([f"官网 {a}" for a in official_attempts]
                                     + [f"Yahoo {a}" for a in results[name]["attempts"]])
        if df is not None:
            record(name, df, f"{t} 近12个月分红（来源：Yahoo，官网失败：{official_reason}）",
                   "ExDate", f"yahoo_{t.lower()}_dividends.csv")
        else:
            results[name]["reason"] = f"官网：{official_reason}；Yahoo 兜底：{results[name]['reason']}"
        results[name]["consistency"] = "19a 返还本金比例：官网不可达，未取得"

    # 6
    source("6", "东方财富", "510300 近1年日线")
    df = attempt("东方财富", em_510300)
    if df is not None:
        df = df.rename(columns={"日期": "Date"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        record("东方财富", df, "510300 近1年日线（不复权，akshare）", "Date", "eastmoney_510300.csv")
        frames["em"] = df

    # 7
    source("7", "新浪财经", "510300 近1年日线")
    df = attempt("新浪财经", sina_510300)
    if df is not None:
        df = df.rename(columns={"date": "Date"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        record("新浪财经", df, "510300 近1年日线（不复权，akshare）", "Date", "sina_510300.csv")
        frames["sina"] = df

    # 8
    source("8", "中证指数", "沪深300成分股名单")
    df = attempt("中证指数", csindex_hs300)
    if df is not None:
        record("中证指数", df, "沪深300当前成分股", file="csindex_hs300_cons.csv")

    # 一致性
    if "yahoo" in frames and "stooq" in frames:
        c1 = compare(frames["yahoo"], frames["stooq"], "Close", "Close", "Yahoo Close vs Stooq")
        c2 = compare(frames["yahoo"], frames["stooq"], "Adj Close", "Close", "Yahoo Adj Close vs Stooq")
        spy = f"{c1}<br>{c2}"
    else:
        spy = "无法比对：" + "、".join(k for k in ["Yahoo Finance", "Stooq"] if not results[k]["ok"]) + " 没拿到数据"
    results["Yahoo Finance"]["consistency"] = results["Stooq"]["consistency"] = spy

    if "em" in frames and "sina" in frames:
        cn = compare(frames["em"], frames["sina"], "收盘", "close", "东方财富 vs 新浪")
    else:
        cn = "无法比对：" + "、".join(k for k in ["东方财富", "新浪财经"] if not results[k]["ok"]) + " 没拿到数据"
    results["东方财富"]["consistency"] = results["新浪财经"]["consistency"] = cn

    # 对照组：判断是个别网站挡了，还是整个外网都不通
    control = {u: probe(u) for u in ["https://pypi.org/simple/", "https://api.github.com",
                                     "https://www.google.com", "https://example.com",
                                     "https://www.baidu.com"]}

    (SAMPLES / "attempt_log.json").write_text(
        json.dumps({"run_date": str(TODAY), "results": results, "control": control},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(control)


def write_report(control):
    L = [f"# 数据源可用性测试报告",
         "",
         f"- 测试日期：{TODAY}",
         f"- 规则：每个源最多试 {MAX_TRIES} 次，间隔 {WAIT_SECONDS} 秒；日涨跌幅差距 ≤ {TOLERANCE_PP} 个百分点算一致",
         f"- 重跑：`python test_sources.py`（会覆盖本报告和 samples/）",
         "",
         "## 结论",
         ""]
    n_ok = sum(r["ok"] for r in results.values())
    L.append(f"- 8 个数据源（第 5 项按 JEPI/QYLD/SPYI 拆成 3 行，共 {len(results)} 行）："
             f"{n_ok} 行能用，{len(results) - n_ok} 行不能用。")
    if n_ok == 0 and control.get("https://www.google.com", "").startswith("不通"):
        L.append("- 连 google.com / baidu.com 这种普通网站也被代理 403 拒绝，只有 pypi、GitHub 能通："
                 "说明这台云电脑实际生效的是「只放行包仓库和 GitHub」的受限网络，而不是 Full。"
                 "问题不在这些数据源本身，要先改环境的网络设置（改完新开会话），再重跑本脚本。")
    L += ["",
         "## 结果总表",
         "",
         "| # | 数据源 | 能不能用 | 拿到什么 | 起止日期 | 行数 | 失败原因 | 一致性结果 |",
         "|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        span = f"{r['start']} ~ {r['end']}" if r["start"] else "—"
        L.append(f"| {r['no']} | {name} | {'✅ 能' if r['ok'] else '❌ 不能'} | "
                 f"{r['what'] if r['ok'] else '无（目标：' + r['what'] + '）'} | {span} | "
                 f"{r['rows'] if r['ok'] else 0} | {r['reason'] or '—'} | {r['consistency'] or '—'} |")

    L += ["", "## 对照组（判断是个别网站被挡，还是整体外网不通）", "",
          "| 网址 | 结果 |", "|---|---|"]
    L += [f"| {u} | {s} |" for u, s in control.items()]

    L += ["", "## 每次尝试的记录", ""]
    for name, r in results.items():
        L.append(f"- **{name}**：" + "；".join(r.get("attempts", [])))

    L += ["", "## 样本文件", ""]
    files = [r["file"] for r in results.values() if r["file"]]
    L += [f"- `{f}`" for f in files] or ["- 无（所有源都没拿到数据）"]
    L.append("- `samples/attempt_log.json`：完整尝试日志（含报错堆栈）")
    (ROOT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
