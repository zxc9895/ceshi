"""下载美国市值前 500 公司（用标普500成分股近似）的全部历史日线。

用法：python download_sp500.py
依赖：pip install yfinance pandas requests lxml pyarrow
输出：
  data/sp500_constituents.csv   成分股名单 + 当前市值 + 市值排名
  data/prices/<TICKER>.parquet  每只股票全部历史日线（不复权 OHLC + Adj Close + 成交量 + 分红 + 拆股）
  data/download_log.csv         每只股票的行数、起止日期、失败原因
"""
import io
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PRICES = DATA / "prices"
PRICES.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
BATCH = 50
MAX_TRIES = 3


def constituents():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    t = pd.read_html(io.StringIO(requests.get(url, headers=UA, timeout=20).text))[0]
    t = t.rename(columns={"Symbol": "Ticker", "Security": "Name"})
    t["YahooTicker"] = t["Ticker"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    return t[["Ticker", "YahooTicker", "Name", "GICS Sector", "Date added"]]


def market_caps(tickers):
    caps = {}
    for t in tickers:
        try:
            caps[t] = yf.Ticker(t).fast_info["marketCap"]
        except Exception:  # noqa: BLE001
            caps[t] = None
    return caps


def download_batch(tickers):
    for i in range(1, MAX_TRIES + 1):
        try:
            return yf.download(tickers, period="max", interval="1d", auto_adjust=False,
                               actions=True, group_by="ticker", threads=True, progress=False)
        except Exception:  # noqa: BLE001
            if i == MAX_TRIES:
                raise
            time.sleep(5 * i)


def save(ticker, df):
    df = df.dropna(how="all")
    if df.empty or df["Close"].dropna().empty:
        return None
    df = df.dropna(subset=["Close"]).reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df.columns.name = None
    df.to_parquet(PRICES / f"{ticker}.parquet", index=False)
    return df


def main():
    cons = constituents()
    tickers = cons["YahooTicker"].tolist()
    print(f"成分股 {len(tickers)} 只，开始下载…")

    log = {}
    for s in range(0, len(tickers), BATCH):
        chunk = tickers[s:s + BATCH]
        try:
            raw = download_batch(chunk)
        except Exception as e:  # noqa: BLE001
            for t in chunk:
                log[t] = {"rows": 0, "start": "", "end": "", "error": str(e)[:200]}
            continue
        for t in chunk:
            try:
                df = save(t, raw[t]) if t in raw.columns.get_level_values(0) else None
            except Exception as e:  # noqa: BLE001
                log[t] = {"rows": 0, "start": "", "end": "", "error": str(e)[:200]}
                continue
            log[t] = ({"rows": len(df), "start": df["Date"].min().date(), "end": df["Date"].max().date(),
                       "error": ""} if df is not None else
                      {"rows": 0, "start": "", "end": "", "error": "无数据"})
        print(f"  {min(s + BATCH, len(tickers))}/{len(tickers)}")

    # 批量失败的逐只重试一次
    for t in [t for t, r in log.items() if r["rows"] == 0]:
        try:
            df = save(t, yf.Ticker(t).history(period="max", auto_adjust=False, actions=True))
            if df is not None:
                log[t] = {"rows": len(df), "start": df["Date"].min().date(),
                          "end": df["Date"].max().date(), "error": ""}
        except Exception as e:  # noqa: BLE001
            log[t]["error"] = str(e)[:200]

    print("拉取当前市值…")
    cons["MarketCap"] = cons["YahooTicker"].map(market_caps(tickers))
    cons["CapRank"] = cons["MarketCap"].rank(ascending=False, method="first").astype("Int64")
    cons = cons.sort_values("CapRank")
    cons.to_csv(DATA / "sp500_constituents.csv", index=False)

    lg = pd.DataFrame.from_dict(log, orient="index").rename_axis("YahooTicker").reset_index()
    lg.to_csv(DATA / "download_log.csv", index=False)
    ok = (lg["rows"] > 0).sum()
    print(f"完成：{ok}/{len(lg)} 只成功，共 {lg['rows'].sum():,} 行")


if __name__ == "__main__":
    main()
