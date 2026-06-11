"""HTML 回测报告生成器。

使用 Plotly（纯 JS，无需服务器）生成单文件可交互 HTML 报告，
数据全部来自 BacktestResult 中的 portfolio 和 metrics。

用法：
    result = engine.run()
    from aquant.analytics.report import render_html
    render_html(result, path="report.html")
    # 或直接在浏览器打开
    render_html(result, open_browser=True)
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aquant.core.engine import BacktestResult


# ---------------------------------------------------------------------------
# 指标中文名映射
# ---------------------------------------------------------------------------
_METRIC_LABELS: dict[str, str] = {
    "total_return": "总收益率",
    "annualized_return": "年化收益率",
    "annualized_volatility": "年化波动率",
    "sharpe": "夏普比率",
    "max_drawdown": "最大回撤",
    "max_drawdown_duration_days": "最大回撤持续天数",
    "calmar": "卡玛比率",
    "avg_position_count": "平均持仓数",
    "win_rate": "胜率",
    "profit_loss_ratio": "盈亏比",
    "turnover": "年化换手率",
    "alpha": "年化 Alpha",
    "beta": "Beta",
    "information_ratio": "信息比率",
    "benchmark_annualized_return": "基准年化收益率",
    "excess_annualized_return": "超额年化收益率",
    "sharpe_on_benchmark_dates": "夏普（基准日期段）",
    "benchmark_coverage": "基准日期覆盖率",
}

# 需要格式化为百分比的指标
_PCT_METRICS = {
    "total_return", "annualized_return", "annualized_volatility",
    "max_drawdown", "alpha", "benchmark_annualized_return",
    "excess_annualized_return", "win_rate", "benchmark_coverage",
}


def _fmt(key: str, val: float | int) -> str:
    if key in _PCT_METRICS:
        return f"{val * 100:.2f}%"
    if key == "max_drawdown_duration_days":
        return f"{int(val)} 天"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


# ---------------------------------------------------------------------------
# 数据提取
# ---------------------------------------------------------------------------

def _extract_nav(result: BacktestResult) -> tuple[list[str], list[float], list[float]]:
    """返回 (dates, nav_values, cash_values)。"""
    nav_records = result.portfolio._daily_nav
    dates = [str(r.date) for r in nav_records]
    navs = [r.total for r in nav_records]
    cash = [r.cash for r in nav_records]
    return dates, navs, cash


def _extract_drawdown(nav_values: list[float]) -> list[float]:
    """从净值序列计算逐日回撤（负数，%）。"""
    drawdowns = []
    peak = nav_values[0] if nav_values else 1.0
    for v in nav_values:
        if v > peak:
            peak = v
        drawdowns.append((v - peak) / peak * 100)
    return drawdowns


def _extract_trades(result: BacktestResult) -> list[dict]:
    trades = []
    for t in result.portfolio.trade_log:
        trades.append({
            "date": str(t.date),
            "symbol": t.symbol,
            "side": "买入" if t.side == "buy" else "卖出",
            "shares": t.shares,
            "price": round(t.price, 4),
            "commission": round(t.commission, 2),
            "stamp_duty": round(t.stamp_duty, 2),
            "pnl": round(t.pnl, 2),
        })
    return trades


def _extract_position_count(result: BacktestResult) -> tuple[list[str], list[int]]:
    nav_records = result.portfolio._daily_nav
    dates = [str(r.date) for r in nav_records]
    counts = [r.position_count for r in nav_records]
    return dates, counts


# ---------------------------------------------------------------------------
# HTML 模板
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>回测报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f0f2f5; color: #1a1a2e;
  }}
  header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #e2e8f0; padding: 24px 40px;
    display: flex; align-items: center; justify-content: space-between;
  }}
  header h1 {{ margin: 0; font-size: 1.6rem; font-weight: 600; letter-spacing: .5px; }}
  header span {{ font-size: .85rem; opacity: .7; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 24px; }}
  /* 指标卡片 */
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px; margin-bottom: 32px;
  }}
  .metric-card {{
    background: #fff; border-radius: 12px;
    padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
    transition: transform .15s, box-shadow .15s;
  }}
  .metric-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.12); }}
  .metric-card .label {{ font-size: .72rem; color: #64748b; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .4px; }}
  .metric-card .value {{ font-size: 1.35rem; font-weight: 700; color: #1e293b; }}
  .metric-card .value.pos {{ color: #16a34a; }}
  .metric-card .value.neg {{ color: #dc2626; }}
  /* 图表区域 */
  .chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px; margin-bottom: 20px;
  }}
  .chart-row.full {{ grid-template-columns: 1fr; }}
  .card {{
    background: #fff; border-radius: 12px;
    padding: 20px 20px 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
  }}
  .card h2 {{
    margin: 0 0 16px; font-size: .95rem;
    font-weight: 600; color: #334155;
    border-left: 3px solid #6366f1; padding-left: 10px;
  }}
  /* 交易明细表 */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
  thead tr {{ background: #f1f5f9; }}
  th {{ padding: 10px 12px; text-align: left; color: #475569; font-weight: 600; white-space: nowrap; }}
  tbody tr {{ border-bottom: 1px solid #f1f5f9; transition: background .1s; }}
  tbody tr:hover {{ background: #f8fafc; }}
  td {{ padding: 9px 12px; color: #334155; white-space: nowrap; }}
  .buy {{ color: #dc2626; font-weight: 600; }}
  .sell {{ color: #16a34a; font-weight: 600; }}
  .pnl-pos {{ color: #16a34a; }}
  .pnl-neg {{ color: #dc2626; }}
  /* 筛选栏 */
  .filter-bar {{ display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }}
  .filter-bar input, .filter-bar select {{
    padding: 7px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
    font-size: .82rem; outline: none; background: #f8fafc;
  }}
  .filter-bar input:focus, .filter-bar select:focus {{ border-color: #6366f1; }}
  .page-ctrl {{ display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: .82rem; color: #64748b; }}
  .page-ctrl button {{
    padding: 5px 12px; border: 1px solid #e2e8f0; border-radius: 6px;
    background: #fff; cursor: pointer; font-size: .82rem;
  }}
  .page-ctrl button:disabled {{ opacity: .4; cursor: default; }}
  footer {{ text-align: center; padding: 24px; font-size: .75rem; color: #94a3b8; }}
</style>
</head>
<body>
<header>
  <h1>📈 回测报告</h1>
  <span id="header-range"></span>
</header>
<div class="container">

  <!-- 指标卡片 -->
  <div class="metrics-grid" id="metrics-grid"></div>

  <!-- 净值 + 回撤 -->
  <div class="chart-row full">
    <div class="card">
      <h2>累计净值曲线</h2>
      <div id="chart-nav" style="height:340px"></div>
    </div>
  </div>
  <div class="chart-row full">
    <div class="card">
      <h2>回撤曲线</h2>
      <div id="chart-dd" style="height:220px"></div>
    </div>
  </div>

  <!-- 持仓数 + 日收益 -->
  <div class="chart-row">
    <div class="card">
      <h2>每日持仓数量</h2>
      <div id="chart-pos" style="height:240px"></div>
    </div>
    <div class="card">
      <h2>日收益率分布</h2>
      <div id="chart-ret-hist" style="height:240px"></div>
    </div>
  </div>

  <!-- 交易明细 -->
  <div class="card" style="margin-bottom:20px">
    <h2>交易明细（共 <span id="trade-total">0</span> 笔）</h2>
    <div class="filter-bar">
      <input type="text" id="f-symbol" placeholder="代码搜索…" oninput="applyFilter()">
      <select id="f-side" onchange="applyFilter()">
        <option value="">全部方向</option>
        <option value="买入">买入</option>
        <option value="卖出">卖出</option>
      </select>
      <input type="date" id="f-date-from" onchange="applyFilter()">
      <span style="line-height:32px;color:#94a3b8">—</span>
      <input type="date" id="f-date-to" onchange="applyFilter()">
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th onclick="sortBy('date')" style="cursor:pointer">日期 ⇅</th>
            <th onclick="sortBy('symbol')" style="cursor:pointer">代码 ⇅</th>
            <th>方向</th>
            <th onclick="sortBy('shares')" style="cursor:pointer">股数 ⇅</th>
            <th onclick="sortBy('price')" style="cursor:pointer">成交价 ⇅</th>
            <th>佣金</th>
            <th>印花税</th>
            <th onclick="sortBy('pnl')" style="cursor:pointer">盈亏 ⇅</th>
          </tr>
        </thead>
        <tbody id="trade-tbody"></tbody>
      </table>
    </div>
    <div class="page-ctrl">
      <button id="btn-prev" onclick="changePage(-1)">‹ 上一页</button>
      <span id="page-info">1 / 1</span>
      <button id="btn-next" onclick="changePage(1)">下一页 ›</button>
      <span style="margin-left:12px">每页
        <select onchange="pageSize=+this.value;currentPage=1;renderTable()" style="padding:3px 6px;border:1px solid #e2e8f0;border-radius:5px">
          <option value="20" selected>20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
      条</span>
    </div>
  </div>

</div>
<footer>aquant · 由 Python 生成</footer>

<script>
// ---- 注入数据 ----
const DATA = __DATA_JSON__;

// ---- 指标卡片 ----
const LABELS = __LABELS_JSON__;
const PCT_KEYS = __PCT_KEYS_JSON__;
function fmtMetric(key, val) {{
  if (PCT_KEYS.includes(key)) return (val * 100).toFixed(2) + '%';
  if (key === 'max_drawdown_duration_days') return parseInt(val) + ' 天';
  if (Number.isInteger(val)) return val.toString();
  return val.toFixed(4);
}}
(function renderMetrics() {{
  const grid = document.getElementById('metrics-grid');
  for (const [k, v] of Object.entries(DATA.metrics)) {{
    const label = LABELS[k] || k;
    const fmt = fmtMetric(k, v);
    let cls = '';
    if (['total_return','annualized_return','sharpe','calmar','alpha','information_ratio',
         'excess_annualized_return','win_rate','profit_loss_ratio'].includes(k)) {{
      cls = v >= 0 ? 'pos' : 'neg';
    }}
    if (['max_drawdown','annualized_volatility'].includes(k)) cls = 'neg';
    grid.innerHTML += `<div class="metric-card"><div class="label">${{label}}</div><div class="value ${{cls}}">${{fmt}}</div></div>`;
  }}
}})();

// ---- 日期范围 header ----
if (DATA.dates.length) {{
  document.getElementById('header-range').textContent =
    DATA.dates[0] + '  ～  ' + DATA.dates[DATA.dates.length - 1];
}}

// ---- 颜色 ----
const C = {{ nav:'#6366f1', bench:'#f59e0b', cash:'#94a3b8', dd:'#ef4444', pos:'#22c55e' }};
const layout_base = {{
  margin: {{t:10, r:20, b:40, l:60}},
  paper_bgcolor:'transparent', plot_bgcolor:'transparent',
  font: {{family:'-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif', size:12, color:'#475569'}},
  xaxis: {{gridcolor:'#f1f5f9', linecolor:'#e2e8f0'}},
  yaxis: {{gridcolor:'#f1f5f9', linecolor:'#e2e8f0'}},
  hovermode:'x unified',
  legend: {{orientation:'h', y:-0.18, x:0}},
}};

// ---- 净值图 ----
(function() {{
  const traces = [{{
    x: DATA.dates, y: DATA.nav,
    name: '策略净值', type: 'scatter', mode: 'lines',
    line: {{color: C.nav, width: 2}},
    hovertemplate: '%{{y:,.0f}}<extra>策略</extra>'
  }}];
  if (DATA.bench_dates && DATA.bench_nav) {{
    traces.push({{
      x: DATA.bench_dates, y: DATA.bench_nav,
      name: '基准', type: 'scatter', mode: 'lines',
      line: {{color: C.bench, width: 1.5, dash: 'dot'}},
      hovertemplate: '%{{y:.4f}}<extra>基准</extra>'
    }});
  }}
  traces.push({{
    x: DATA.dates, y: DATA.cash,
    name: '现金', type: 'scatter', mode: 'lines',
    line: {{color: C.cash, width: 1, dash: 'dot'}},
    visible: 'legendonly',
    hovertemplate: '%{{y:,.0f}}<extra>现金</extra>'
  }});
  Plotly.newPlot('chart-nav', traces,
    Object.assign({{}, layout_base, {{yaxis: {{...layout_base.yaxis, tickformat:',.0f'}}}}),
    {{responsive:true, displayModeBar:true, modeBarButtonsToRemove:['lasso2d','select2d']}});
}})();

// ---- 回撤图 ----
(function() {{
  Plotly.newPlot('chart-dd', [{{
    x: DATA.dates, y: DATA.drawdown,
    name: '回撤', type: 'scatter', mode: 'lines', fill: 'tozeroy',
    line: {{color: C.dd, width: 1.5}},
    fillcolor: 'rgba(239,68,68,0.15)',
    hovertemplate: '%{{y:.2f}}%<extra>回撤</extra>'
  }}],
  Object.assign({{}, layout_base, {{
    yaxis: {{...layout_base.yaxis, ticksuffix:'%'}},
    showlegend: false,
    margin: {{t:10, r:20, b:40, l:55}}
  }}),
  {{responsive:true, displayModeBar:false}});
}})();

// ---- 持仓数 ----
(function() {{
  Plotly.newPlot('chart-pos', [{{
    x: DATA.dates, y: DATA.pos_count,
    name: '持仓数', type: 'bar',
    marker: {{color: C.pos, opacity: .8}},
    hovertemplate: '%{{y}} 只<extra></extra>'
  }}],
  Object.assign({{}}, layout_base, {{
    showlegend: false,
    margin: {{t:10, r:20, b:40, l:45}}
  }}),
  {{responsive:true, displayModeBar:false}});
}})();

// ---- 日收益率分布 ----
(function() {{
  const nav = DATA.nav;
  const rets = [];
  for (let i = 1; i < nav.length; i++) rets.push((nav[i] / nav[i-1] - 1) * 100);
  Plotly.newPlot('chart-ret-hist', [{{
    x: rets, type: 'histogram', nbinsx: 50,
    name: '日收益率',
    marker: {{color: C.nav, opacity: .75}},
    hovertemplate: '%{{x:.2f}}%: %{{y}} 天<extra></extra>'
  }}],
  Object.assign({{}}, layout_base, {{
    xaxis: {{...layout_base.xaxis, ticksuffix:'%'}},
    showlegend: false,
    margin: {{t:10, r:20, b:40, l:45}}
  }}),
  {{responsive:true, displayModeBar:false}});
}})();

// ---- 交易明细 ----
let allTrades = DATA.trades.slice();
let filtered = allTrades;
let currentPage = 1;
let pageSize = 20;
let sortKey = 'date';
let sortAsc = false;

document.getElementById('trade-total').textContent = allTrades.length;

function applyFilter() {{
  const sym = document.getElementById('f-symbol').value.trim().toUpperCase();
  const side = document.getElementById('f-side').value;
  const from = document.getElementById('f-date-from').value;
  const to = document.getElementById('f-date-to').value;
  filtered = allTrades.filter(t => {{
    if (sym && !t.symbol.includes(sym)) return false;
    if (side && t.side !== side) return false;
    if (from && t.date < from) return false;
    if (to && t.date > to) return false;
    return true;
  }});
  currentPage = 1;
  renderTable();
}}

function sortBy(key) {{
  if (sortKey === key) sortAsc = !sortAsc; else {{ sortKey = key; sortAsc = true; }}
  filtered.sort((a, b) => {{
    const va = a[key], vb = b[key];
    return sortAsc ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
  }});
  renderTable();
}}

function changePage(delta) {{
  const total = Math.max(1, Math.ceil(filtered.length / pageSize));
  currentPage = Math.max(1, Math.min(total, currentPage + delta));
  renderTable();
}}

function renderTable() {{
  const total = Math.max(1, Math.ceil(filtered.length / pageSize));
  document.getElementById('page-info').textContent = currentPage + ' / ' + total;
  document.getElementById('btn-prev').disabled = currentPage <= 1;
  document.getElementById('btn-next').disabled = currentPage >= total;
  const start = (currentPage - 1) * pageSize;
  const rows = filtered.slice(start, start + pageSize);
  const tbody = document.getElementById('trade-tbody');
  tbody.innerHTML = rows.map(t => {{
    const sideCls = t.side === '买入' ? 'buy' : 'sell';
    const pnlCls = t.pnl > 0 ? 'pnl-pos' : t.pnl < 0 ? 'pnl-neg' : '';
    const pnlFmt = t.pnl === 0 ? '-' : (t.pnl > 0 ? '+' : '') + t.pnl.toFixed(2);
    return `<tr>
      <td>${{t.date}}</td>
      <td><code>${{t.symbol}}</code></td>
      <td class="${{sideCls}}">${{t.side}}</td>
      <td>${{t.shares.toLocaleString()}}</td>
      <td>${{t.price.toFixed(4)}}</td>
      <td>${{t.commission.toFixed(2)}}</td>
      <td>${{t.stamp_duty.toFixed(2)}}</td>
      <td class="${{pnlCls}}">${{pnlFmt}}</td>
    </tr>`;
  }}).join('');
}}

renderTable();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def render_html(result: BacktestResult, path: str = "backtest_report.html", open_browser: bool = False) -> str:
    """生成 HTML 回测报告。

    参数
    ----
    result       : Engine.run() 的返回值（须已 compute_metrics）
    path         : 输出文件路径，默认 backtest_report.html
    open_browser : 生成后自动在浏览器打开

    返回
    ----
    写入的文件路径（绝对路径）。
    """
    from pathlib import Path

    dates, navs, cash = _extract_nav(result)
    drawdown = _extract_drawdown(navs)
    pos_dates, pos_count = _extract_position_count(result)
    trades = _extract_trades(result)

    # 基准净值（若有 benchmark_df，按基准日期段重建累计净值）
    bench_dates: list[str] | None = None
    bench_nav: list[float] | None = None
    bdf = result._benchmark_df
    if bdf is not None and "date" in bdf.columns and "return" in bdf.columns:
        import polars as pl
        bdf_sorted = bdf.sort("date")
        bench_dates = [str(d) for d in bdf_sorted["date"].to_list()]
        rets = bdf_sorted["return"].to_list()
        nav_b = [1.0]
        for r in rets:
            nav_b.append(nav_b[-1] * (1 + r))
        bench_nav = nav_b[1:]  # 去掉前置 1.0，与 dates 对齐

    data = {
        "metrics": result.metrics,
        "dates": dates,
        "nav": navs,
        "cash": cash,
        "drawdown": drawdown,
        "pos_count": pos_count,
        "trades": trades,
        "bench_dates": bench_dates,
        "bench_nav": bench_nav,
    }

    html = _HTML_TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, default=str))
    html = html.replace("__LABELS_JSON__", json.dumps(_METRIC_LABELS, ensure_ascii=False))
    html = html.replace("__PCT_KEYS_JSON__", json.dumps(list(_PCT_METRICS), ensure_ascii=False))

    out_path = Path(path).expanduser().resolve()
    out_path.write_text(html, encoding="utf-8")

    if open_browser:
        import webbrowser
        webbrowser.open(out_path.as_uri())

    return str(out_path)
