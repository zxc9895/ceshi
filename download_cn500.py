"""下载 A 股市值前 500 公司的全部历史日线（数据来自 Yahoo）。

候选池 = 沪深300 + 中证500 成分股（中证指数官网），按 Yahoo 当前总市值排序取前 500。
东方财富 / 新浪的历史接口在本环境会被对方断开，所以历史数据走 Yahoo（.SS 上交所 / .SZ 深交所）。

用法：python download_cn500.py
依赖：pip install yfinance akshare pandas pyarrow
输出：
  data_cn/cn500_constituents.csv   前 500 名单 + 当前市值（人民币）+ 市值排名 + 来源指数
  data_cn/prices/<代码>.parquet    每只股票全部历史日线（不复权 OHLC + Adj Close + 成交量 + 分红 + 拆股）
  data_cn/download_log.csv         每只股票的行数、起止日期、失败原因
"""
import time
from pathlib import Path

import akshare as ak
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent
DATA = ROOT / "data_cn"
PRICES = DATA / "prices"
PRICES.mkdir(parents=True, exist_ok=True)
TOP_N = 500
BATCH = 50
MAX_TRIES = 3


def universe():
    frames = []
    for code, name in [("000300", "沪深300"), ("000905", "中证500")]:
        c = ak.index_stock_cons_csindex(symbol=code)
        frames.append(pd.DataFrame({"Code": c["成分券代码"].astype(str).str.zfill(6),
                                    "Name": c["成分券名称"], "Exchange": c["交易所"],
                                    "Index": name}))
    u = pd.concat(frames, ignore_index=True).drop_duplicates("Code")
    u["YahooTicker"] = u["Code"] + u["Exchange"].map(lambda x: ".SS" if "上海" in x else ".SZ")
    return u


def market_cap(t):
    for i in range(MAX_TRIES):
        try:
            return yf.Ticker(t).fast_info["marketCap"]
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


def save(ticker, df):
    df = df.dropna(how="all")
    if df.empty or df["Close"].dropna().empty:
        return None
    df = df.dropna(subset=["Close"]).reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df.columns.name = None
    df.to_parquet(PRICES / f"{ticker.split('.')[0]}.parquet", index=False)
    return df


def entry(df, err=""):
    if df is None:
        return {"rows": 0, "start": "", "end": "", "error": err or "无数据"}
    return {"rows": len(df), "start": df["Date"].min().date(), "end": df["Date"].max().date(), "error": ""}


def main():
    u = universe()
    print(f"候选池 {len(u)} 只，查询当前市值…")
    u["MarketCapCNY"] = u["YahooTicker"].map(market_cap)
    u = u.sort_values("MarketCapCNY", ascending=False).head(TOP_N).reset_index(drop=True)
    u["CapRank"] = range(1, len(u) + 1)
    u.to_csv(DATA / "cn500_constituents.csv", index=False)

    tickers = u["YahooTicker"].tolist()
    log = {}
    for s in range(0, len(tickers), BATCH):
        chunk = tickers[s:s + BATCH]
        raw = None
        for i in range(1, MAX_TRIES + 1):
            try:
                raw = yf.download(chunk, period="max", interval="1d", auto_adjust=False, actions=True,
                                  group_by="ticker", threads=True, progress=False)
                break
            except Exception:  # noqa: BLE001
                time.sleep(5 * i)
        for t in chunk:
            try:
                has = raw is not None and t in raw.columns.get_level_values(0)
                log[t] = entry(save(t, raw[t]) if has else None)
            except Exception as e:  # noqa: BLE001
                log[t] = entry(None, str(e)[:200])
        print(f"  {min(s + BATCH, len(tickers))}/{len(tickers)}")

    for t in [t for t, r in log.items() if r["rows"] == 0]:  # 批量失败的逐只重试
        try:
            log[t] = entry(save(t, yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)))
        except Exception as e:  # noqa: BLE001
            log[t] = entry(None, str(e)[:200])

    lg = pd.DataFrame.from_dict(log, orient="index").rename_axis("YahooTicker").reset_index()
    lg.to_csv(DATA / "download_log.csv", index=False)
    print(f"完成：{(lg['rows'] > 0).sum()}/{len(lg)} 只成功，共 {lg['rows'].sum():,} 行")


if __name__ == "__main__":
    main()
