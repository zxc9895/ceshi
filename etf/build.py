"""收息 ETF 体检：JEPI、JEPQ、QYLD、SPYI、QQQI（JEPI/SPYI 对比 SPY，JEPQ/QYLD/QQQI 对比 QQQ）。

用法：先跑 python etf/fetch_roc.py（发行商 ROC 数据），再跑 python etf/build.py
依赖：yfinance pandas requests matplotlib openpyxl；中文字体 fonts-noto-cjk
输出：etf/etf_checkup.xlsx、etf/charts/*.png、etf/results.json（report.md 引用的数字）
"""
import io
import json
from datetime import date
from pathlib import Path

import matplotlib
import matplotlib.dates
import pandas as pd
import requests
import yfinance as yf

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
CHARTS = ROOT / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)
RAW.mkdir(exist_ok=True)

ETFS = {"JEPI": "SPY", "JEPQ": "QQQ", "QYLD": "QQQ", "SPYI": "SPY", "QQQI": "QQQ"}
START_CASH = 100_000
UA = {"User-Agent": "Mozilla/5.0"}
CRASHES = {  # 标普500全收益指数的高点 -> 低点
    "2008 金融危机": ("2007-10-09", "2009-03-09"),
    "2020 新冠暴跌": ("2020-02-19", "2020-03-23"),
    "2022 加息熊市": ("2022-01-03", "2022-10-12"),
}
BIG_UP = 0.20  # 标普500全收益 ≥ 20% 的年份算"大涨"

# ---------- 图表样式（参考调色板：蓝=本 ETF，橙=对照，青=第三系列） ----------
for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f or "NotoSerifCJK" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": ["Noto Sans CJK SC", "Noto Sans CJK JP", "sans-serif"],
    "axes.unicode_minus": False, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": "#c9c8c2", "axes.labelcolor": "#52514e", "xtick.color": "#52514e",
    "ytick.color": "#52514e", "axes.grid": True, "grid.color": "#e7e6e1", "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2,
    "axes.titlesize": 12, "axes.axisbelow": True, "axes.titleweight": "bold", "legend.frameon": False, "font.size": 10,
})
BLUE, ORANGE, AQUA, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e"


# ---------- 数据 ----------
def yahoo(t):
    h = yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)
    if h.empty:
        raise RuntimeError(f"Yahoo 无数据：{t}")
    h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    h.to_csv(RAW / f"yahoo_{t.replace('^', '')}.csv")
    return h


def tbill():
    """先试 FRED DGS3MO，失败用 Yahoo ^IRX。返回 (最新值%, 日期, 来源说明)。"""
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO", headers=UA, timeout=30)
        r.raise_for_status()
        s = pd.read_csv(io.StringIO(r.text), na_values=".").dropna()
        s.to_csv(RAW / "fred_DGS3MO.csv", index=False)
        return float(s.iloc[-1, 1]), str(s.iloc[-1, 0]), "FRED DGS3MO"
    except Exception as e:  # noqa: BLE001
        h = yahoo("^IRX")
        return (float(h["Close"].iloc[-1]), str(h.index[-1].date()),
                f"Yahoo ^IRX（13 周国库券收益率）；FRED 失败：{type(e).__name__}")


def bxm():
    p = RAW / "BXM_History.csv"
    r = requests.get("https://cdn.cboe.com/api/global/us_indices/daily_prices/BXM_History.csv",
                     headers=UA, timeout=60)
    r.raise_for_status()
    p.write_text(r.text)
    d = pd.read_csv(p)
    d.columns = [c.strip() for c in d.columns]
    d["DATE"] = pd.to_datetime(d["DATE"])
    return d.set_index("DATE")["BXM"].astype(float)


# ---------- 计算 ----------
def tr_index(h):
    """分红再投资的总回报指数：每天 (收盘 + 当天除息分红) / 前一天收盘。"""
    c = h["Close"]
    r = (c + h["Dividends"]) / c.shift(1) - 1
    return (1 + r.fillna(0)).cumprod()


def ann(first, last, d0, d1):
    yrs = (d1 - d0).days / 365.25
    return (last / first) ** (1 / yrs) - 1


def mdd(s):
    dd = s / s.cummax() - 1
    return dd.min(), dd.idxmin()


def metrics(h, start):
    h = h[h.index >= start]
    tr, px = tr_index(h), h["Close"]
    d0, d1 = h.index[0], h.index[-1]
    m, when = mdd(tr)
    divs = h.loc[h["Dividends"] > 0, "Dividends"]
    ttm = divs[divs.index > d1 - pd.Timedelta(days=365)]
    return {
        "起始日": d0.date(), "截止日": d1.date(), "年数": round((d1 - d0).days / 365.25, 2),
        "年化总回报(分红再投资)": ann(tr.iloc[0], tr.iloc[-1], d0, d1),
        "年化价格回报": ann(px.iloc[0], px.iloc[-1], d0, d1),
        "最大回撤(总回报)": m, "最大回撤谷底日": when.date(),
        "近12个月分红合计($/股)": ttm.sum(), "最新收盘价": px.iloc[-1],
        "近12个月分红率": ttm.sum() / px.iloc[-1], "近12个月分红次数": len(ttm),
    }


def div_stats(h, since=None):
    d = h.loc[h["Dividends"] > 0, "Dividends"]
    if since is not None:
        d = d[d.index > since]
    return {"次数": len(d), "最高($)": d.max(), "最高日期": d.idxmax().date(), "最低($)": d.min(),
            "最低日期": d.idxmin().date(), "平均($)": d.mean(), "标准差($)": d.std(),
            "变异系数(标准差/平均)": d.std() / d.mean()}


def simulate(etf, bench):
    """上市首日各投 10 万：ETF 分红全部取出；基准每次在 ETF 除息日卖出同样金额（基准自己的分红再投资）。"""
    etf = etf[etf.index >= etf.index[0]]
    b = bench.reindex(etf.index.union(bench.index)).ffill().loc[etf.index[0]:]
    shares = START_CASH / etf["Close"].iloc[0]
    units = START_CASH / b["Close"].iloc[0]
    paid, rows = 0.0, []
    for d in b.index:
        bd = b.at[d, "Dividends"] if d in bench.index else 0.0
        if bd > 0:
            units *= 1 + bd / b.at[d, "Close"]
        if d in etf.index and etf.at[d, "Dividends"] > 0:
            cash = shares * etf.at[d, "Dividends"]
            paid += cash
            units -= cash / b.at[d, "Close"]
            rows.append({"日期": d.date(), "本次领取($)": cash, "累计领取($)": paid,
                         "ETF剩余本金($)": shares * etf.at[d, "Close"],
                         "基准剩余本金($)": units * b.at[d, "Close"]})
    last = etf.index[-1]
    return {"累计领取分红($)": paid, "ETF剩余本金($)": shares * etf.at[last, "Close"],
            "ETF本金变化": shares * etf.at[last, "Close"] / START_CASH - 1,
            "基准同样取钱后剩余本金($)": units * b.at[last, "Close"],
            "基准本金变化": units * b.at[last, "Close"] / START_CASH - 1}, pd.DataFrame(rows)


def main():
    px = {t: yahoo(t) for t in list(ETFS) + ["SPY", "QQQ", "^SP500TR"]}
    tb_val, tb_date, tb_src = tbill()
    bx = bxm()
    res = {"run_date": str(date.today()), "tbill": [tb_val, tb_date, tb_src]}

    # 1. 核心指标
    core, dstat, principal, sims, sim_paths = [], [], [], [], {}
    for t, b in ETFS.items():
        h = px[t]
        start = h.index[0]
        me, mb = metrics(h, start), metrics(px[b], start)
        core.append({"代码": t, "对照": b, **me,
                     "对照年化总回报": mb["年化总回报(分红再投资)"], "对照年化价格回报": mb["年化价格回报"],
                     "对照最大回撤": mb["最大回撤(总回报)"]})
        last = h.index[-1]
        dstat.append({"代码": t, "区间": "上市至今", **div_stats(h)})
        dstat.append({"代码": t, "区间": "近12个月", **div_stats(h, last - pd.Timedelta(days=365))})
        bp = px[b][px[b].index >= start]["Close"]
        principal.append({"代码": t, "上市日": start.date(), "上市首日收盘": h["Close"].iloc[0],
                          "最新收盘": h["Close"].iloc[-1], "价格涨跌": h["Close"].iloc[-1] / h["Close"].iloc[0] - 1,
                          "对照": b, "对照价格涨跌(同期)": bp.iloc[-1] / bp.iloc[0] - 1,
                          "上市以来累计分红($/股)": h["Dividends"].sum(),
                          "累计分红/首日价格": h["Dividends"].sum() / h["Close"].iloc[0]})
        s, path = simulate(h, px[b])
        sims.append({"代码": t, "对照": b, "投入日": start.date(), "投入($)": START_CASH, **s})
        sim_paths[t] = path
    core, dstat, principal, sims = map(pd.DataFrame, (core, dstat, principal, sims))

    # 5. 分红率 vs 3 个月国债
    spread = core[["代码", "近12个月分红率"]].copy()
    spread["3个月国债收益率"] = tb_val / 100
    spread["高出(百分点)"] = (spread["近12个月分红率"] - spread["3个月国债收益率"]) * 100
    spread["国债数据"] = f"{tb_src}，{tb_date}"

    # 4. BXM vs 标普500全收益
    sp = px["^SP500TR"]["Close"]
    both = pd.concat([bx, sp], axis=1, keys=["BXM", "SP500TR"]).dropna()
    yearly = both.groupby(both.index.year).last()
    first = both.iloc[0]
    prev = yearly.shift(1)
    prev.iloc[0] = first
    yr = (yearly / prev - 1).rename_axis("年份").reset_index()
    yr["说明"] = ""
    yr.loc[0, "说明"] = f"{both.index[0].date()} 起（Cboe 文件最早日期），不满一年"
    yr.loc[yr.index[-1], "说明"] = f"截至 {both.index[-1].date()}，年初至今"
    yr["BXM-标普(百分点)"] = (yr["BXM"] - yr["SP500TR"]) * 100
    yr["类型"] = ""
    yr.loc[yr["年份"].isin([2008, 2020, 2022]), "类型"] = "指定大跌年"
    yr.loc[(yr["SP500TR"] >= BIG_UP) & (yr["说明"] == ""), "类型"] = "大涨年(标普≥20%)"
    crash = []
    for k, (a, z) in CRASHES.items():
        seg = both.loc[a:z]
        rb, rs = seg["BXM"].iloc[-1] / seg["BXM"].iloc[0] - 1, seg["SP500TR"].iloc[-1] / seg["SP500TR"].iloc[0] - 1
        crash.append({"事件": k, "起(标普高点)": a, "止(标普低点)": z, "BXM": rb, "标普500全收益": rs,
                      "BXM少亏(百分点)": (rb - rs) * 100})
    crash = pd.DataFrame(crash)
    full = {"区间": f"{both.index[0].date()} ~ {both.index[-1].date()}",
            "BXM年化": ann(both["BXM"].iloc[0], both["BXM"].iloc[-1], both.index[0], both.index[-1]),
            "标普500全收益年化": ann(both["SP500TR"].iloc[0], both["SP500TR"].iloc[-1], both.index[0], both.index[-1]),
            "BXM最大回撤": mdd(both["BXM"])[0], "标普500全收益最大回撤": mdd(both["SP500TR"])[0]}

    # 2. ROC（发行商数据，来自 fetch_roc.py）
    roc = pd.read_csv(RAW / "roc_per_distribution.csv")
    roc_year = (roc.groupby(["Fund", "Source", "Period"])
                .agg(分红次数=("Amount", "size"), 分红合计=("Amount", "sum"), 返还本金合计=("ROC_Amount", "sum"),
                     首次除息=("ExDate", "min"), 末次除息=("ExDate", "max")).reset_index())
    roc_year["返还本金占比"] = roc_year["返还本金合计"] / roc_year["分红合计"]
    latest = pd.read_csv(RAW / "roc_19a_latest.csv").rename(columns={
        "Amount_YTD": "分红合计", "ROC_Amount_YTD": "返还本金合计", "ROC_Pct_YTD": "返还本金占比"})
    latest["返还本金占比"] = latest["返还本金占比"] / 100
    missing = pd.DataFrame([
        {"Fund": f, "Source": "未取得", "Period": "全部年份",
         "Note": "J.P. Morgan 官网：产品页分红表（Playwright 打开后读取）只有除息日/金额，没有 ROC 列；"
                 "年度 ETF Distribution Notice 只给合格股息、股息扣除比例，没有 ROC；"
                 "税务中心列出的 Form 8937 里没有这只基金。未做估计。"} for f in ("JEPI", "JEPQ")] + [
        {"Fund": "QYLD", "Source": "未取得", "Period": "FYE 2014–2018、2021、2024",
         "Note": "Global X 官网文件列表里没有这几个财年的 QYLD Form 8937；日历年 1099 补充表只找到 2023–2025。未做估计。"}])
    roc_summary = pd.concat([roc_year, latest, missing], ignore_index=True)

    # 6. UCITS（爱尔兰注册）同类
    ucits = pd.DataFrame([
        {"对应美国ETF": "JEPI", "UCITS 名称": "JPMorgan US Equity Premium Income Active UCITS ETF USD (dist)",
         "ISIN": "IE000U5MJOZ6", "注册地": "爱尔兰", "代码 / 交易所": "JEPI 伦敦(USD)、JEIP 伦敦(GBX)、JEIP XETRA(EUR)、JEPI 米兰(EUR)、JEPI 瑞士(USD)",
         "费率(TER)": "0.35%", "分红频率": "每月", "成立日": "2024-10-29",
         "来源": "https://www.justetf.com/en/etf-profile.html?isin=IE000U5MJOZ6"},
        {"对应美国ETF": "JEPQ", "UCITS 名称": "JPMorgan Nasdaq Equity Premium Income Active UCITS ETF USD (dist)",
         "ISIN": "IE000U9J8HX9", "注册地": "爱尔兰", "代码 / 交易所": "JEPQ 伦敦(USD)、JEQP 伦敦(GBX)、JEQP XETRA(EUR)、JEPQ 米兰(EUR)、JEPQ 瑞士(USD)",
         "费率(TER)": "0.35%", "分红频率": "每月", "成立日": "2024-10-29",
         "来源": "https://www.justetf.com/en/etf-profile.html?isin=IE000U9J8HX9"},
        {"对应美国ETF": "QYLD", "UCITS 名称": "Global X Nasdaq 100 Covered Call UCITS ETF D",
         "ISIN": "IE00BM8R0J59", "注册地": "爱尔兰", "代码 / 交易所": "QYLD 伦敦(USD)、QYLP 伦敦(GBP)、QYLE XETRA(EUR)、QYLD 米兰(EUR)、QYLD 瑞士(CHF)",
         "费率(TER)": "0.45%", "分红频率": "每月", "成立日": "2022-11-22",
         "来源": "https://www.justetf.com/en/etf-profile.html?isin=IE00BM8R0J59"},
        {"对应美国ETF": "SPYI", "UCITS 名称": "未找到", "ISIN": "", "注册地": "", "代码 / 交易所": "",
         "费率(TER)": "", "分红频率": "", "成立日": "",
         "来源": "网页搜索未找到 NEOS 发行的 UCITS 版本（2026-09-30）"},
        {"对应美国ETF": "QQQI", "UCITS 名称": "未找到", "ISIN": "", "注册地": "", "代码 / 交易所": "",
         "费率(TER)": "", "分红频率": "", "成立日": "",
         "来源": "网页搜索未找到 NEOS 发行的 UCITS 版本（2026-09-30）"},
    ])

    # ---------- Excel ----------
    divs = pd.concat([px[t].loc[px[t]["Dividends"] > 0, ["Dividends", "Close"]].assign(代码=t)
                      for t in list(ETFS) + ["SPY", "QQQ"]]).rename_axis("除息日").reset_index()
    daily = pd.concat([px[t][["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends"]].assign(代码=t)
                       for t in list(ETFS) + ["SPY", "QQQ"]]).rename_axis("日期").reset_index()
    readme = pd.DataFrame({"项目": [
        "数据日期", "价格与分红", "返还本金", "BXM", "国债", "年化总回报", "最大回撤", "近12个月分红率",
        "模拟", "说明"], "内容": [
        res["run_date"], "Yahoo Finance（yfinance，不复权收盘价 + 每次分红）",
        "发行商官网：NEOS / Global X 的 Form 8937、年度 1099 补充表、19a 通知；JEPI/JEPQ 未取得",
        "Cboe 官网 BXM_History.csv（最早 2002-03-22）；对比 Yahoo ^SP500TR", tb_src,
        "每天 (收盘+当天分红)/前一天收盘 连乘，再按年数开方", "按总回报指数，从历史最高点到之后最低点的跌幅",
        "近 365 天分红合计 ÷ 最新收盘价", "上市首日收盘买入 10 万美元；不计税费和交易成本",
        "只列数据事实，不构成买卖建议"]})
    sheets = {"说明": readme, "1_核心指标": core, "1_每次分红统计": dstat, "2_本金变化": principal,
              "2_返还本金_汇总": roc_summary, "2_返还本金_逐次": roc, "3_模拟取息": sims,
              "4_BXM_年度": yr, "4_BXM_大跌区间": crash, "4_BXM_全区间": pd.DataFrame([full]),
              "5_分红率vs国债": spread, "6_UCITS": ucits, "分红明细": divs}
    for t, p in sim_paths.items():
        sheets[f"3_模拟过程_{t}"] = p
    with pd.ExcelWriter(ROOT / "etf_checkup.xlsx", engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w * 1.2), 60)
        daily.to_excel(xw, sheet_name="日线", index=False)

    # ---------- 图 ----------
    charts(px, sims, bx, sp, yr, crash, spread, roc_summary, tb_val)

    for name, df in [("core", core), ("principal", principal), ("sims", sims), ("spread", spread),
                     ("crash", crash), ("yearly", yr), ("roc", roc_summary), ("dstat", dstat)]:
        res[name] = json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))
    res["bxm_full"] = full
    (ROOT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    print("done")


def charts(px, sims, bx, sp, yr, crash, spread, roc_summary, tb_val):
    # 图1：总回报 vs 价格，每只 ETF 一个小图（上市日 = 100）
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
    for ax, (t, b) in zip(axes.flat, ETFS.items()):
        h = px[t]
        bb = px[b][px[b].index >= h.index[0]]
        lines = [(tr_index(h) * 100, BLUE, "-", f"{t} 总回报"), (h["Close"] / h["Close"].iloc[0] * 100, BLUE, ":", f"{t} 价格"),
                 (tr_index(bb) * 100, ORANGE, "-", f"{b} 总回报"), (bb["Close"] / bb["Close"].iloc[0] * 100, ORANGE, ":", f"{b} 价格")]
        for s, c, ls, lab in lines:
            ax.plot(s.index, s, color=c, ls=ls, label=lab)
        ax.axhline(100, color=MUTED, lw=1)
        ax.set_title(f"{t} vs {b}（上市日 = 100）")
        ax.xaxis.set_major_formatter(matplotlib.dates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
        ax.legend(loc="upper left", fontsize=8)
    axes.flat[-1].axis("off")
    axes.flat[-1].text(0, 0.5, "实线 = 分红再投资的总回报\n虚线 = 只看价格（本金）\n\n虚线在 100 以下 = 价格比上市时低",
                       fontsize=12, color=INK, va="center")
    fig.suptitle("上市以来：总回报与价格", fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(CHARTS / "1_总回报与价格.png", dpi=130)
    plt.close(fig)

    # 图2：模拟取息（10 万美元）
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = range(len(sims))
    w = 0.27
    bars = [(sims["累计领取分红($)"], AQUA, "ETF 累计领取的分红"), (sims["ETF剩余本金($)"], BLUE, "ETF 剩余本金"),
            (sims["基准同样取钱后剩余本金($)"], ORANGE, "SPY/QQQ 每次卖出同样金额后剩余本金")]
    for i, (v, c, lab) in enumerate(bars):
        pos = [j + (i - 1) * w for j in x]
        ax.bar(pos, v / 1000, width=w - 0.02, color=c, label=lab)
        for p_, val in zip(pos, v):
            ax.text(p_, val / 1000 + 1, f"{val / 1000:.0f}", ha="center", fontsize=8, color=MUTED)
    ax.axhline(100, color=INK, lw=1, ls="--")
    ax.text(-0.45, 104, "投入 100", ha="left", fontsize=9, color=INK)
    ax.set_xticks(list(x), [f"{r.代码}\n({r.投入日} 起, 对照 {r.对照})" for r in sims.itertuples()])
    ax.set_ylabel("千美元")
    ax.set_title("上市那天投 10 万美元，分红全部取出花掉，到今天")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS / "2_模拟取息.png", dpi=130)
    plt.close(fig)

    # 图3：BXM vs 标普500全收益，累计（对数坐标）+ 年度
    both = pd.concat([bx, sp], axis=1, keys=["BXM", "SP500TR"]).dropna()
    norm = both / both.iloc[0] * 100
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 9), gridspec_kw={"height_ratios": [1, 1]})
    a1.plot(norm.index, norm["BXM"], color=BLUE, label="BXM（标普500 备兑看涨）")
    a1.plot(norm.index, norm["SP500TR"], color=ORANGE, label="标普500 全收益")
    a1.set_yscale("log")
    for k, (a, z) in CRASHES.items():
        a1.axvspan(pd.Timestamp(a), pd.Timestamp(z), color="#e7e6e1", lw=0)
        a1.text(pd.Timestamp(a), norm.max().max() * 0.9, k, fontsize=8, color=MUTED)
    a1.set_title(f"{both.index[0].date()} = 100（对数坐标，阴影 = 三次大跌）")
    a1.legend(loc="upper left")
    y = yr[yr["说明"] == ""]
    xs = range(len(y))
    a2.bar([i - 0.2 for i in xs], y["BXM"] * 100, width=0.38, color=BLUE, label="BXM")
    a2.bar([i + 0.2 for i in xs], y["SP500TR"] * 100, width=0.38, color=ORANGE, label="标普500 全收益")
    a2.axhline(0, color=INK, lw=1)
    a2.set_xticks(list(xs), y["年份"], rotation=45)
    a2.set_ylabel("年回报 %")
    a2.set_title("每个完整年份的回报")
    a2.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(CHARTS / "3_BXM对比标普500.png", dpi=130)
    plt.close(fig)

    # 图4：每次分红金额
    fig, axes = plt.subplots(5, 1, figsize=(11, 12), sharex=False)
    for ax, t in zip(axes, ETFS):
        d = px[t].loc[px[t]["Dividends"] > 0, "Dividends"]
        ax.bar(d.index, d, width=20, color=BLUE)
        ax.set_title(f"{t} 每次分红（美元/股）", loc="left")
    fig.tight_layout()
    fig.savefig(CHARTS / "4_每次分红.png", dpi=130)
    plt.close(fig)

    # 图5：近 12 个月分红率 vs 3 个月国债
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(spread["代码"], spread["近12个月分红率"] * 100, color=BLUE, width=0.55)
    for i, v in enumerate(spread["近12个月分红率"] * 100):
        ax.text(i, v + 0.3, f"{v:.1f}%", ha="center", color=INK)
    ax.axhline(tb_val, color=ORANGE, lw=2)
    ax.text(-0.45, tb_val + 0.3, f"3 个月国债 {tb_val:.2f}%", ha="left", color=INK, backgroundcolor="#fcfcfb")
    ax.set_ylabel("%")
    ax.set_title("近 12 个月分红率 vs 3 个月美国国债收益率")
    fig.tight_layout()
    fig.savefig(CHARTS / "5_分红率vs国债.png", dpi=130)
    plt.close(fig)

    # 图6：返还本金占比（发行商 Form 8937 / 1099 / 19a）
    r = roc_summary.dropna(subset=["返还本金占比"]).copy()
    r = r[r["Source"] != "年度1099补充表"]
    r["order"] = r["Fund"].map({"SPYI": 0, "QQQI": 1, "QYLD": 2})
    r["est"] = ~r["Period"].str.startswith("FYE")
    r = r.sort_values(["order", "est", "Period"]).reset_index(drop=True)
    per = [f"财年止\n{p[4:11]}" if p.startswith("FYE") else "2026年至今\n(估计)" for p in r["Period"]]
    r["标签"] = [f"{f}\n{p}" for f, p in zip(r["Fund"], per)]
    fig, ax = plt.subplots(figsize=(14, 5))
    colors = {"SPYI": BLUE, "QQQI": ORANGE, "QYLD": AQUA}
    ax.bar(range(len(r)), r["返还本金占比"] * 100, color=[colors[f] for f in r["Fund"]], width=0.7)
    for i, v in enumerate(r["返还本金占比"] * 100):
        ax.text(i, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(r)), r["标签"], fontsize=8)
    ax.set_ylim(0, 112)
    ax.set_ylabel("返还本金占分红 %")
    ax.set_title("分红里被税务标为'返还本金'的比例（发行商官网；JEPI/JEPQ 未取得）")
    fig.tight_layout()
    fig.savefig(CHARTS / "6_返还本金占比.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
