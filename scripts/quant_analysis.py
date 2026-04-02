#!/usr/bin/env python3
"""
A股个股全面量化分析工具
用法：python3 quant_analysis.py 600900
      python3 quant_analysis.py 600900 -m valuation,factors,risk
      python3 quant_analysis.py 600900 --peer-compare
      python3 quant_analysis.py 600900 --format json
"""
import sys, os, argparse, json, time as _time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# ============ 数据获取 ============

def is_hk_stock(code):
    """判断是否港股（5位数字，如01810）"""
    return len(code) >= 4 and len(code) <= 5

def fetch_stock(code, period_days=2600):
    """获取日线数据（A股/港股）"""
    import akshare as ak
    for attempt in range(3):
        try:
            if is_hk_stock(code):
                # 港股
                code_padded = code.zfill(5)
                df = ak.stock_hk_daily(symbol=code_padded, adjust='qfq')
                if df.empty:
                    return pd.DataFrame()
                df = df.rename(columns={'date':'Date','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
                # 只取最近N天
                cutoff = datetime.now() - timedelta(days=period_days + 60)
                df = df[df.index >= pd.Timestamp(cutoff)]
                return df
            else:
                # A股
                end = datetime.now().strftime("%Y%m%d")
                start = (datetime.now() - timedelta(days=period_days + 60)).strftime("%Y%m%d")
                prefix = 'sh' if code.startswith(('6','9')) else 'sz'
                df = ak.stock_zh_a_daily(symbol=f'{prefix}{code}', start_date=start, end_date=end, adjust='qfq')
                if df.empty:
                    return pd.DataFrame()
                df = df.rename(columns={'date':'Date','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
                return df
        except Exception as e:
            if attempt < 2:
                _time.sleep(3 * (attempt + 1))
                continue
            print(f"[ERROR] 获取{code}失败: {e}", file=sys.stderr)
            return pd.DataFrame()

def fetch_financials(code):
    """获取财务数据（同花顺）"""
    import akshare as ak
    result = {}
    try:
        df = ak.stock_financial_benefit_ths(symbol=code)
        if not df.empty:
            result['income'] = df
    except: pass
    try:
        df = ak.stock_financial_debt_ths(symbol=code)
        if not df.empty:
            result['balance'] = df
    except: pass
    try:
        df = ak.stock_financial_abstract_ths(symbol=code)
        if not df.empty:
            result['metrics'] = df
    except: pass
    return result

def fetch_realtime_quote(code):
    """获取实时行情（腾讯API，支持A股/港股）"""
    import requests
    if is_hk_stock(code):
        market = 'hk'
        code_padded = code.zfill(5)
    else:
        market = 'sh' if code.startswith(('6','9')) else 'sz'
        code_padded = code
    try:
        r = requests.get(f'https://qt.gtimg.cn/q={market}{code_padded}', timeout=5)
        r.encoding = 'gbk'
        fields = r.text.split('~')
        if len(fields) > 45:
            if is_hk_stock(code):
                # 港股字段不同
                return {
                    'price': float(fields[3]) if fields[3] else None,
                    'name': fields[1],
                    'pe': float(fields[39]) if fields[39] else None,
                    'pb': float(fields[58]) if len(fields) > 58 and fields[58] else None,
                    'div_yield': float(fields[59]) if len(fields) > 59 and fields[59] else None,
                    'total_mcap': float(fields[37]) if len(fields) > 37 and fields[37] else None,
                }
            else:
                return {
                    'price': float(fields[3]) if fields[3] else None,
                    'name': fields[1],
                    'pe': float(fields[39]) if fields[39] else None,
                    'total_mcap': float(fields[45]) if fields[45] else None,
                    'pb': float(fields[46]) if fields[46] else None,
                    'div_yield': float(fields[47]) if fields[47] else None,
                }
    except: pass
    return {}

def get_stock_name(code):
    """获取股票名称"""
    if is_hk_stock(code):
        return fetch_realtime_quote(code).get('name', code)
    import requests
    market = 'sh' if code.startswith(('6','9')) else 'sz'
    try:
        r = requests.get(f'https://qt.gtimg.cn/q={market}{code}', timeout=5)
        r.encoding = 'gbk'
        fields = r.text.split('~')
        if len(fields) > 2:
            return fields[1]
    except: pass
    return code

# ============ 估值分位 ============

def calc_valuation_percentile(df, eps_data, bvps_data):
    """计算PE/PB历史分位数"""
    close = df['Close']
    pe_series, pb_series = [], []
    for date, price in close.items():
        year = date.year
        if year in eps_data and eps_data[year] > 0:
            pe_series.append({'date': date, 'pe': price / eps_data[year]})
        if year in bvps_data and bvps_data[year] > 0:
            pb_series.append({'date': date, 'pb': price / bvps_data[year]})

    pe_df = pd.DataFrame(pe_series).set_index('date') if pe_series else pd.DataFrame()
    pb_df = pd.DataFrame(pb_series).set_index('date') if pb_series else pd.DataFrame()

    results = {}
    if not pe_df.empty:
        cur_pe = pe_df['pe'].iloc[-1]
        for name, days in [('3年',756),('5年',1260),('10年',2520),('全历史',len(pe_df))]:
            s = pe_df['pe'].iloc[-days:]
            pct = (s < cur_pe).mean() * 100
            results[f'pe_{name}'] = {'current': round(cur_pe,2), 'percentile': round(pct,1),
                                      'median': round(s.median(),2), 'min': round(s.min(),2), 'max': round(s.max(),2)}
    if not pb_df.empty:
        cur_pb = pb_df['pb'].iloc[-1]
        for name, days in [('3年',756),('5年',1260),('10年',2520),('全历史',len(pb_df))]:
            s = pb_df['pb'].iloc[-days:]
            pct = (s < cur_pb).mean() * 100
            results[f'pb_{name}'] = {'current': round(cur_pb,2), 'percentile': round(pct,1),
                                      'median': round(s.median(),2), 'min': round(s.min(),2), 'max': round(s.max(),2)}
    return results

# ============ 因子系统 ============

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)

def calc_all_factors(df):
    """计算9个因子的最新值"""
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    factors = {}

    # RSI反转
    rsi14 = calc_rsi(close, 14)
    factors['rsi_reversal'] = round(float((50 - rsi14.iloc[-1]) / 50), 4)

    # 布林偏离
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    bw = (upper - lower).replace(0, np.nan)
    factors['bollinger_deviation'] = round(float(((ma20 - close) / bw).iloc[-1]), 4)

    # 均值回归
    ma5 = close.rolling(5).mean()
    factors['mean_reversion'] = round(float(((ma20 - ma5) / ma20).iloc[-1]), 4)

    # MACD动量
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd_hist = (dif - dea) * 2
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().replace(0, np.nan)
    factors['macd_momentum'] = round(float((macd_hist / atr14).clip(-3, 3).iloc[-1]), 4)

    # 价格动量
    mom10 = close.pct_change(10)
    vol10 = close.pct_change().rolling(10).std().replace(0, np.nan)
    factors['price_momentum'] = round(float((mom10 / vol10).clip(-3, 3).iloc[-1]), 4)

    # 趋势强度
    ma60 = close.rolling(60).mean()
    factors['trend_strength'] = round(float(((ma5 - ma20) / ma20 * 50).clip(-10, 10).iloc[-1]), 4)

    # 量价配合
    vr = volume.rolling(20).mean().replace(0, np.nan)
    volume_ratio = volume / vr
    price_change_sign = np.sign(close.pct_change(20))
    factors['volume_momentum'] = round(float((volume_ratio * price_change_sign).clip(-5, 5).iloc[-1]), 4)

    # OBV趋势
    obv = (np.sign(close.diff()) * volume).cumsum()
    obv_ma = obv.rolling(20).mean()
    obv_std = obv.rolling(20).std().replace(0, np.nan)
    factors['obv_trend'] = round(float(((obv - obv_ma) / obv_std).clip(-3, 3).iloc[-1]), 4)

    # 波动率状态
    vol_short = close.pct_change().rolling(10).std()
    vol_long = close.pct_change().rolling(60).std().replace(0, np.nan)
    factors['volatility_regime'] = round(float((1 - vol_short / vol_long).clip(-2, 2).iloc[-1]), 4)

    # 综合评分
    factors['composite'] = round(sum(factors.values()) / len(factors), 4)

    return factors

# ============ 风险指标 ============

def calc_risk_metrics(df, years=1):
    """计算风险指标"""
    close = df['Close']
    ret = close.pct_change().dropna().iloc[-years*252:]

    ann_ret = (1 + ret.mean()) ** 252 - 1
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    cum = (1 + ret).cumprod()
    drawdown = (cum - cum.cummax()) / cum.cummax()
    max_dd = drawdown.min()
    max_dd_end = drawdown.idxmin()
    max_dd_start = cum[:max_dd_end].idxmax()

    downside = ret[ret < 0]
    down_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1
    sortino = ann_ret / down_vol
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

    return {
        'period': f'{years}年',
        'ann_return': round(ann_ret * 100, 2),
        'ann_volatility': round(ann_vol * 100, 2),
        'sharpe': round(sharpe, 3),
        'sortino': round(sortino, 3),
        'calmar': round(calmar, 3),
        'max_drawdown': round(max_dd * 100, 2),
        'max_dd_start': str(max_dd_start.date()) if pd.notna(max_dd_start) else None,
        'max_dd_end': str(max_dd_end.date()) if pd.notna(max_dd_end) else None,
        'var_95': round(ret.quantile(0.05) * 100, 2),
        'win_rate': round((ret > 0).mean() * 100, 1),
        'profit_ratio': round(ret[ret > 0].mean() / abs(ret[ret < 0].mean()), 2) if (ret < 0).any() else None,
    }

# ============ 动量反转 ============

def calc_momentum_reversal(df):
    """动量分组 vs 未来收益"""
    close = df['Close']
    results = {}

    for lookback in [5, 10, 20, 60]:
        mom = close.pct_change(lookback)
        fwd = close.pct_change(20).shift(-20)
        valid = pd.DataFrame({'mom': mom, 'fwd': fwd}).dropna()

        groups = []
        for i, (ql, qh) in enumerate([(0,0.2),(0.2,0.4),(0.4,0.6),(0.6,0.8),(0.8,1.0)]):
            g = valid[(valid['mom'] >= valid['mom'].quantile(ql)) & (valid['mom'] < valid['mom'].quantile(qh))]
            if qh == 1.0:
                g = valid[valid['mom'] >= valid['mom'].quantile(ql)]
            if len(g) > 0:
                groups.append({
                    'quintile': i + 1,
                    'avg_momentum': round(g['mom'].mean() * 100, 2),
                    'avg_fwd_return': round(g['fwd'].mean() * 100, 2),
                    'win_rate': round((g['fwd'] > 0).mean() * 100, 1),
                })
        results[f'{lookback}d'] = groups

    # 当前动量信号
    current = {}
    for lookback in [5, 10, 20, 60]:
        m = close.pct_change(lookback).iloc[-1]
        if pd.notna(m):
            current[f'{lookback}d_momentum'] = round(m * 100, 2)
    results['current'] = current

    return results

# ============ 资金面 ============

def calc_capital_flow(df):
    """量价关系、筹码分布、OBV"""
    close = df['Close']
    vol = df['Volume']

    result = {}

    # 量比
    for w in [5, 20, 60]:
        avg = vol.rolling(w).mean()
        yr_avg = vol.rolling(252).mean()
        result[f'vol_{w}d_avg'] = int(avg.iloc[-1])
        result[f'vol_{w}d_ratio'] = round(float(avg.iloc[-1] / yr_avg.iloc[-1]), 2) if yr_avg.iloc[-1] > 0 else None

    # 量价配合
    for days in [20, 60]:
        pc = (close.iloc[-1] / close.iloc[-days] - 1) * 100
        vc = (vol.iloc[-5:].mean() / vol.iloc[-days:].mean() - 1) * 100
        aligned = (pc > 0 and vc > 0) or (pc < 0 and vc < 0)
        result[f'price_vol_aligned_{days}d'] = aligned
        result[f'price_change_{days}d'] = round(pc, 2)
        result[f'vol_change_{days}d'] = round(vc, 2)

    # 筹码密集区
    recent = close.iloc[-60:]
    bins = np.arange(recent.min()-0.5, recent.max()+0.5, 0.3)
    hist, edges = np.histogram(recent, bins=bins)
    peak_idx = np.argmax(hist)
    result['chip_zone_low'] = round(float(edges[peak_idx]), 2)
    result['chip_zone_high'] = round(float(edges[peak_idx+1]), 2)
    result['profitable_ratio'] = round(float((close.iloc[-1] > recent).mean() * 100), 1)

    # OBV趋势
    obv = (np.sign(close.diff()) * vol).cumsum()
    obv_ma20 = obv.rolling(20).mean()
    result['obv_vs_ma20'] = round(float((obv.iloc[-1] / obv_ma20.iloc[-1] - 1) * 100), 2)
    result['obv_trend'] = '流入' if obv.iloc[-1] > obv_ma20.iloc[-1] else '流出'

    return result

# ============ 事件日历 & 季节性 ============

def calc_seasonality(df):
    """月度季节性统计"""
    close = df['Close']
    monthly = close.resample('ME').last().pct_change(fill_method=None)
    monthly.index = monthly.index.month

    month_names = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
    stats = monthly.groupby(monthly.index).agg(['mean', lambda x: (x>0).mean()])

    result = {}
    for m in range(1, 13):
        if m in stats.index:
            row = stats.loc[m]
            result[month_names[m-1]] = {
                'avg_return': round(float(row['mean'] * 100), 2),
                'win_rate': round(float(row.iloc[1] * 100), 0),
            }
    return result

# ============ 交易规则回测 ============

def backtest_trading_rules(df, eps_data, rsi_thresh=35, pe_median=None, mom_thresh=-0.05):
    """量化交易规则回测"""
    close = df['Close']
    rsi = calc_rsi(close, 14)
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    mom20 = close.pct_change(20)

    if pe_median is None:
        pe_median = 18.0  # 默认PE中位数

    pe_series = []
    for date, price in close.items():
        year = date.year
        if year in eps_data and eps_data[year] > 0:
            pe_series.append(price / eps_data[year])
        else:
            pe_series.append(np.nan)
    pe = pd.Series(pe_series, index=close.index)

    in_pos = False
    entry_price = entry_date = 0
    trades = []

    for i in range(len(close)):
        if pd.isna(pe.iloc[i]) or pd.isna(rsi.iloc[i]) or pd.isna(ma60.iloc[i]):
            continue

        if not in_pos:
            if (pe.iloc[i] < pe_median and rsi.iloc[i] < rsi_thresh
                and close.iloc[i] < ma60.iloc[i] and mom20.iloc[i] < mom_thresh):
                in_pos = True
                entry_price = close.iloc[i]
                entry_date = close.index[i]
        else:
            if (rsi.iloc[i] > 70 or mom20.iloc[i] > 0.10 or close.iloc[i] > ma20.iloc[i] * 1.05):
                ret = (close.iloc[i] / entry_price - 1) * 100
                hold = (close.index[i] - entry_date).days
                trades.append({
                    'entry': str(entry_date.date()), 'exit': str(close.index[i].date()),
                    'entry_price': round(entry_price, 2), 'exit_price': round(close.iloc[i], 2),
                    'return_pct': round(ret, 2), 'hold_days': hold,
                    'result': 'win' if ret > 0 else 'loss',
                })
                in_pos = False

    if trades:
        tdf = pd.DataFrame(trades)
        stats = {
            'total_trades': len(trades),
            'win_rate': round((tdf['return_pct'] > 0).mean() * 100, 1),
            'avg_return': round(tdf['return_pct'].mean(), 2),
            'avg_win': round(tdf[tdf['return_pct']>0]['return_pct'].mean(), 2) if (tdf['return_pct']>0).any() else 0,
            'avg_loss': round(tdf[tdf['return_pct']<=0]['return_pct'].mean(), 2) if (tdf['return_pct']<=0).any() else 0,
            'avg_hold_days': round(tdf['hold_days'].mean(), 0),
            'cumulative_return': round(float((tdf['return_pct']/100+1).prod()-1)*100, 2),
        }
    else:
        stats = {'total_trades': 0}

    return {'trades': trades, 'stats': stats}

# ============ 同行对比 ============

def peer_compare(codes, names):
    """同行横向对比"""
    results = {}
    for code in codes:
        try:
            df = fetch_stock(code)
            if df.empty or len(df) < 60:
                continue
            close = df['Close']
            quote = fetch_realtime_quote(code)

            rsi14 = calc_rsi(close, 14).iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma60 = close.rolling(60).mean().iloc[-1]
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            dif = (ema12 - ema26).iloc[-1]
            dea = (ema12 - ema26).ewm(span=9).mean().iloc[-1]

            results[code] = {
                'name': names.get(code, code),
                'close': round(float(close.iloc[-1]), 2),
                'pe': quote.get('pe'),
                'pb': quote.get('pb'),
                'div_yield': quote.get('div_yield'),
                'total_mcap': quote.get('total_mcap'),
                'ret_5d': round(float((close.iloc[-1]/close.iloc[-5]-1)*100), 2),
                'ret_20d': round(float((close.iloc[-1]/close.iloc[-20]-1)*100), 2),
                'ret_60d': round(float((close.iloc[-1]/close.iloc[-60]-1)*100), 2),
                'volatility_20d': round(float(close.pct_change()[-20:].std()*np.sqrt(252)*100), 2),
                'rsi14': round(float(rsi14), 1),
                'macd_bull': dif > dea,
                'ma20_dev': round(float((close.iloc[-1]/ma20-1)*100), 2),
                'ma60_dev': round(float((close.iloc[-1]/ma60-1)*100), 2),
            }
            _time.sleep(1)
        except Exception as e:
            print(f"[WARN] {code}: {e}", file=sys.stderr)
    return results

# ============ 格式化输出 ============

def format_report(code, name, data):
    """格式化为完整文本报告"""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"📊 {name}（{code}）量化分析报告")
    lines.append(f"{'='*60}\n")

    # 基本信息
    if 'quote' in data and data['quote']:
        q = data['quote']
        lines.append("【基本信息】")
        lines.append(f"  收盘价: {'HKD' if is_hk_stock(code) else '¥'}{q.get('price','N/A')}")
        if q.get('pe'): lines.append(f"  PE(TTM): {q['pe']}x")
        if q.get('pb'): lines.append(f"  PB: {q['pb']}x")
        if q.get('div_yield'): lines.append(f"  股息率: {q['div_yield']}%")
        if q.get('total_mcap'):
            mcap = q['total_mcap']
            if is_hk_stock(code):
                # 港股API单位: 港币，直接显示亿
                lines.append(f"  总市值: {mcap:.2f}亿 (港币)")
            else:
                unit = '亿' if mcap < 10000 else '万亿'
                mcap_val = mcap if mcap < 10000 else round(mcap/10000, 2)
                lines.append(f"  总市值: {mcap_val}{unit}")
        lines.append("")

    # 估值分位
    if 'valuation' in data and data['valuation']:
        lines.append("【一、历史估值分位数】")
        lines.append("-" * 40)
        for k, v in data['valuation'].items():
            if 'pe_' in k:
                period = k.replace('pe_','')
                judge = '🟢偏低' if v['percentile']<25 else '⚪合理偏低' if v['percentile']<50 else '⚪合理偏高' if v['percentile']<75 else '🔴偏高'
                lines.append(f"  PE({period}): {v['current']}x | 分位{v['percentile']}% | 区间{v['min']}~{v['max']}x | 中位数{v['median']}x {judge}")
        for k, v in data['valuation'].items():
            if 'pb_' in k:
                period = k.replace('pb_','')
                judge = '🟢偏低' if v['percentile']<25 else '⚪合理偏低' if v['percentile']<50 else '⚪合理偏高' if v['percentile']<75 else '🔴偏高'
                lines.append(f"  PB({period}): {v['current']}x | 分位{v['percentile']}% | 区间{v['min']}~{v['max']}x | 中位数{v['median']}x {judge}")
        lines.append("")

    # 因子
    if 'factors' in data:
        lines.append("【二、因子信号系统（9因子评分）】")
        lines.append("-" * 40)
        f = data['factors']
        for k, v in f.items():
            if k == 'composite': continue
            emoji = '🟢看多' if v > 0.1 else '🔴看空' if v < -0.1 else '⚪中性'
            lines.append(f"  {k:>25s}: {v:+.4f} {emoji}")
        composite = f.get('composite', 0)
        signal = '偏多' if composite > 0.1 else '偏空' if composite < -0.1 else '中性'
        lines.append(f"\n  综合评分: {composite:+.4f} → {signal}")
        lines.append("")

    # 风险
    if 'risk' in data:
        lines.append("【三、风险指标】")
        lines.append("-" * 40)
        for period_data in data['risk']:
            lines.append(f"  [{period_data['period']}]")
            lines.append(f"    年化收益: {period_data['ann_return']:+.2f}% | 波动率: {period_data['ann_volatility']:.2f}%")
            lines.append(f"    夏普: {period_data['sharpe']:.3f} | Sortino: {period_data['sortino']:.3f} | Calmar: {period_data['calmar']:.3f}")
            lines.append(f"    最大回撤: {period_data['max_drawdown']:.2f}%")
            if period_data.get('max_dd_start'):
                lines.append(f"    回撤区间: {period_data['max_dd_start']} → {period_data['max_dd_end']}")
            lines.append(f"    VaR(95%): {period_data['var_95']:.2f}% | 胜率: {period_data['win_rate']:.1f}% | 盈亏比: {period_data.get('profit_ratio','N/A')}")
        lines.append("")

    # 动量
    if 'momentum' in data:
        lines.append("【四、当前动量信号】")
        lines.append("-" * 40)
        cur = data['momentum'].get('current', {})
        for k, v in cur.items():
            emoji = '🟢' if v > 0 else '🔴'
            lines.append(f"  {k}: {v:+.2f}% {emoji}")
        lines.append("")

    # 资金面
    if 'capital' in data:
        lines.append("【五、资金面量化】")
        lines.append("-" * 40)
        c = data['capital']
        lines.append(f"  OBV趋势: {c.get('obv_trend','N/A')} (vs MA20: {c.get('obv_vs_ma20',0):+.2f}%)")
        lines.append(f"  20日量价: {'配合' if c.get('price_vol_aligned_20d') else '背离'}")
        lines.append(f"  60日量价: {'配合' if c.get('price_vol_aligned_60d') else '背离'}")
        lines.append(f"  5日均量: {c.get('vol_5d_avg',0)} ({c.get('vol_5d_ratio',1):.2f}x)")
        lines.append(f"  20日均量: {c.get('vol_20d_avg',0)} ({c.get('vol_20d_ratio',1):.2f}x)")
        lines.append(f"  筹码密集区: ¥{c.get('chip_zone_low',0)}~¥{c.get('chip_zone_high',0)}")
        lines.append(f"  获利盘: {c.get('profitable_ratio',0)}%")
        lines.append("")

    # 季节性
    if 'seasonality' in data:
        lines.append("【六、月度季节性收益】")
        lines.append("-" * 40)
        best = max(data['seasonality'].items(), key=lambda x: x[1]['avg_return'])
        worst = min(data['seasonality'].items(), key=lambda x: x[1]['avg_return'])
        for month, s in data['seasonality'].items():
            bar = '█' * int(abs(s['avg_return']))
            sign = '+' if s['avg_return'] > 0 else '-'
            lines.append(f"  {month:>3}: {s['avg_return']:>+.2f}% | 胜率{s['win_rate']:.0f}% | {sign}{bar}")
        lines.append(f"\n  最强: {best[0]}(+{best[1]['avg_return']}%) | 最弱: {worst[0]}({worst[1]['avg_return']}%)")
        lines.append("")

    # 交易回测
    if 'trading' in data and data['trading']['stats']['total_trades'] > 0:
        lines.append("【七、量化交易规则回测】")
        lines.append("-" * 40)
        s = data['trading']['stats']
        lines.append(f"  交易次数: {s['total_trades']} | 胜率: {s['win_rate']}% | 平均收益: {s['avg_return']:+.2f}%")
        lines.append(f"  平均盈利: {s['avg_win']:+.2f}% | 平均亏损: {s['avg_loss']:+.2f}%")
        lines.append(f"  累计收益: {s['cumulative_return']:+.2f}% | 平均持仓: {s['avg_hold_days']:.0f}天")
        if s.get('avg_win') and s.get('avg_loss') and s['avg_loss'] != 0:
            lines.append(f"  盈亏比: {abs(s['avg_win']/s['avg_loss']):.2f}")
        # 交易明细
        trades = data['trading'].get('trades', [])
        if trades:
            lines.append("\n  交易明细:")
            for t in trades:
                emoji = '✅' if t['result'] == 'win' else '❌'
                lines.append(f"    {emoji} {t['entry']} → {t['exit']} | ¥{t['entry_price']} → ¥{t['exit_price']} | {t['return_pct']:+.2f}% | {t['hold_days']}天")
        lines.append("")

    # 同行对比
    if 'peers' in data and data['peers']:
        lines.append("【八、同行横向对比】")
        lines.append("-" * 40)
        sorted_peers = sorted(data['peers'].items(), key=lambda x: x[1].get('pe') or 999)
        for c, p in sorted_peers:
            macd = '🟢金叉' if p.get('macd_bull') else '🔴死叉'
            lines.append(f"  {p['name']:>6}({c}) | 收盘¥{p['close']} | PE{p.get('pe','N/A')} | "
                         f"60日{p['ret_60d']:+.2f}% | RSI{p['rsi14']} | 波动{p['volatility_20d']}% | {macd}")
        lines.append("")

    # 综合评分 & 操作建议
    lines.append("【九、综合量化评分 & 操作建议】")
    lines.append("-" * 40)

    # 评分计算
    scores = {}
    weights = {'估值':0.20, '因子':0.15, '风险':0.15, '动量':0.15, '资金面':0.15, '季节性':0.10, '交易回测':0.10}

    # 估值评分（PE分位越低越好）
    if 'valuation' in data:
        pe_key = [k for k in data['valuation'] if 'pe_3年' in k or 'pe_全历史' in k]
        if pe_key:
            pct = data['valuation'][pe_key[0]]['percentile']
            scores['估值'] = max(0, min(10, 10 - pct / 10))
        else:
            scores['估值'] = 5
    else:
        scores['估值'] = 5

    # 因子评分
    if 'factors' in data:
        c = data['factors']['composite']
        scores['因子'] = max(0, min(10, (c + 1) * 5))
    else:
        scores['因子'] = 5

    # 风险评分（夏普越高越好）
    if 'risk' in data and data['risk']:
        sharpe = data['risk'][0]['sharpe']
        scores['风险'] = max(0, min(10, (sharpe + 1) * 3.33))
    else:
        scores['风险'] = 5

    # 动量评分
    if 'momentum' in data:
        mom20 = data['momentum']['current'].get('20d_momentum', 0)
        scores['动量'] = max(0, min(10, (mom20 + 10) / 2))
    else:
        scores['动量'] = 5

    # 资金面评分
    if 'capital' in data:
        c = data['capital']
        score = 5
        if c.get('obv_trend') == '流入': score += 1.5
        if c.get('price_vol_aligned_20d'): score += 1.5
        if c.get('profitable_ratio', 50) > 50: score += 1
        if c.get('obv_trend') == '流出': score -= 1.5
        if c.get('profitable_ratio', 50) < 30: score -= 1
        scores['资金面'] = max(0, min(10, score))
    else:
        scores['资金面'] = 5

    # 季节性评分
    if 'seasonality' in data:
        import calendar
        current_month = datetime.now().month
        month_names_jp = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
        mn = month_names_jp[current_month - 1]
        if mn in data['seasonality']:
            wr = data['seasonality'][mn]['win_rate']
            scores['季节性'] = wr / 10  # 胜率50%→5分
        else:
            scores['季节性'] = 5
    else:
        scores['季节性'] = 5

    # 交易回测评分
    if 'trading' in data and data['trading']['stats']['total_trades'] > 0:
        wr = data['trading']['stats']['win_rate']
        avg_ret = data['trading']['stats']['avg_return']
        scores['交易回测'] = max(0, min(10, wr / 10 + avg_ret / 2))
    else:
        scores['交易回测'] = 5

    for name_k, w in weights.items():
        sc = scores.get(name_k, 5)
        bar = '█' * int(sc) + '░' * (10 - int(sc))
        lines.append(f"  {name_k:>6}: {sc:.1f}/10 [{bar}] (权重{w*100:.0f}%)")

    total = sum(scores.get(k, 5) * w for k, w in weights.items())
    overall = '强烈推荐' if total > 7.5 else '推荐' if total > 6.5 else '中性' if total > 5.5 else '谨慎' if total > 4 else '回避'
    lines.append(f"\n  ★ 综合评分: {total:.2f}/10 → {overall}")

    # 操作建议
    lines.append("\n  操作建议:")
    if total > 7:
        lines.append("    🟢 当前位置较优，可考虑入场/加仓")
    elif total > 5.5:
        lines.append("    ⚪ 中性位置，建议观望或小仓位试探")
    elif total > 4:
        lines.append("    🟡 偏弱，建议等待更好的入场时机")
    else:
        lines.append("    🔴 风险较大，建议回避或减仓")

    # 关键触发信号
    lines.append("\n  关键触发信号:")
    if 'factors' in data:
        f = data['factors']
        if f.get('rsi_reversal', 0) > 0.3:
            lines.append("    ✅ RSI超卖反转信号（看多）")
        if f.get('price_momentum', 0) < -2:
            lines.append("    ⚠️ 价格动量极端负值（超跌）")
        if f.get('obv_trend', 0) < -1:
            lines.append("    ⚠️ OBV资金持续流出")
    if 'momentum' in data:
        mom20 = data['momentum']['current'].get('20d_momentum', 0)
        if mom20 < -5:
            lines.append(f"    ⚠️ 20日跌{abs(mom20):.1f}%（超跌区间）")
        elif mom20 > 10:
            lines.append(f"    🔥 20日涨{mom20:.1f}%（强动量）")

    lines.append(f"\n{'='*60}")
    lines.append("⚠️ 免责声明：本报告基于历史数据回测，不构成投资建议")
    lines.append(f"{'='*60}")

    return '\n'.join(lines)

# ============ 主程序 ============

def main():
    parser = argparse.ArgumentParser(description='A股个股量化分析')
    parser.add_argument('code', help='股票代码（6位数字）')
    parser.add_argument('-m', '--modules', help='分析模块（逗号分隔）: valuation,fcf,factors,risk,momentum,capital,events,trading,peers')
    parser.add_argument('--peers', help='同行代码（逗号分隔）')
    parser.add_argument('--peer-compare', action='store_true', help='启用同行对比')
    parser.add_argument('--format', choices=['text','json'], default='text')
    parser.add_argument('--eps', help='自定义EPS（年份:值,年份:值,...）如 2023:1.11,2024:1.33')
    args = parser.parse_args()

    code = args.code
    modules = args.modules.split(',') if args.modules else ['all']

    print(f"正在分析 {code}...", file=sys.stderr)

    # 获取数据
    df = fetch_stock(code)
    if df.empty:
        print(f"[ERROR] 无法获取 {code} 的数据", file=sys.stderr)
        sys.exit(1)

    name = get_stock_name(code)
    quote = fetch_realtime_quote(code)
    print(f"获取到 {len(df)} 条日线数据 ({df.index[0].date()} ~ {df.index[-1].date()})", file=sys.stderr)

    # 解析EPS
    eps_data = {}
    if args.eps:
        for pair in args.eps.split(','):
            y, v = pair.split(':')
            eps_data[int(y)] = float(v)
    elif not is_hk_stock(code):
        # A股从财务数据推算
        fin = fetch_financials(code)
        if 'metrics' in fin and not fin['metrics'].empty:
            m = fin['metrics']
            annual = m[m['报告期'].astype(str).str.endswith('12-31')]
            for _, row in annual.iterrows():
                try:
                    year = int(str(row['报告期'])[:4])
                    eps = float(row['基本每股收益']) if row['基本每股收益'] not in [False, None, 'False'] else None
                    if eps and eps > 0:
                        eps_data[year] = eps
                except: pass
    else:
        # 港股：用实时PE倒推近5年EPS（近似）
        if quote and quote.get('pe') and quote.get('price'):
            cur_pe = quote['pe']
            cur_price = quote['price']
            cur_eps = cur_price / cur_pe
            # 假设小米5年EPS复合增长率约15%（可被 --eps 参数覆盖）
            for year_off, growth in [(0, 1.0), (1, 0.85), (2, 0.72), (3, 0.61), (4, 0.53)]:
                eps_data[2025 - year_off] = round(cur_eps * growth, 2)
        # 默认fin为空
        fin = {}

    # BVPS粗算
    bvps_data = {}
    if isinstance(fin, dict) and 'metrics' in fin and not fin.get('metrics', pd.DataFrame()).empty:
        m = fin.get('metrics', pd.DataFrame())
        if not m.empty:
            annual = m[m['报告期'].astype(str).str.endswith('12-31')]
            for _, row in annual.iterrows():
                try:
                    year = int(str(row['报告期'])[:4])
                    bvps = float(row['每股净资产']) if row['每股净资产'] not in [False, None, 'False'] else None
                    if bvps and bvps > 0:
                        bvps_data[year] = bvps
                except: pass

    # 运行模块
    data = {}

    if 'all' in modules or 'valuation' in modules:
        print("  计算估值分位...", file=sys.stderr)
        if eps_data:
            data['valuation'] = calc_valuation_percentile(df, eps_data, bvps_data)

    if 'all' in modules or 'factors' in modules:
        print("  计算因子信号...", file=sys.stderr)
        data['factors'] = calc_all_factors(df)

    if 'all' in modules or 'risk' in modules:
        print("  计算风险指标...", file=sys.stderr)
        data['risk'] = [calc_risk_metrics(df, y) for y in [1, 3, 5]]

    if 'all' in modules or 'momentum' in modules:
        print("  计算动量反转...", file=sys.stderr)
        data['momentum'] = calc_momentum_reversal(df)

    if 'all' in modules or 'capital' in modules:
        print("  计算资金面...", file=sys.stderr)
        data['capital'] = calc_capital_flow(df)

    if 'all' in modules or 'events' in modules:
        print("  计算季节性...", file=sys.stderr)
        data['seasonality'] = calc_seasonality(df)

    if 'all' in modules or 'trading' in modules:
        print("  回测交易规则...", file=sys.stderr)
        pe_median = None
        if 'valuation' in data:
            for k, v in data['valuation'].items():
                if k == 'pe_5年':
                    pe_median = v['median']
        data['trading'] = backtest_trading_rules(df, eps_data, pe_median=pe_median)

    if args.peer_compare or args.peers:
        print("  同行对比...", file=sys.stderr)
        if args.peers:
            peer_codes = args.peers.split(',')
        else:
            # 自动检测同行（简化版，需扩展）
            from peer_groups import PEER_GROUPS
            peer_codes = []
            for group, members in PEER_GROUPS.items():
                if code in members:
                    peer_codes = [c for c in members if c != code]
                    break
        if peer_codes:
            peer_names = {c: get_stock_name(c) for c in peer_codes}
            data['peers'] = peer_compare(peer_codes, peer_names)

    # 补充实时行情
    data['quote'] = quote
    data['name'] = name

    # 输出
    if args.format == 'json':
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_report(code, name, data))

if __name__ == '__main__':
    main()
