<div align="center">

# cn-stock-quant 📈

> *A股个股全面量化分析 — 十维一体，数据驱动*

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-Skill-green)](https://openclaw.ai)

<br>

输入一只股票代码，输出一份专业量化报告<br>
覆盖估值、现金流、因子、风控、动量、资金面、事件、回测、同行对比

[快速开始](#快速开始) · [分析模块](#分析模块) · [输出示例](#输出示例) · [安装](#安装) · [详细方法论](#详细方法论)

</div>

---

## 一句话说清楚

> 给我一个 6 位股票代码，我给你十个维度的量化结论。

```
用户  ❯  帮我分析 600900

cn-stock-quant ❯  
  📊 历史PE分位：3年 72% / 5年 65% / 10年 58%
  💰 FCF分红模型：隐含估值 28.5 元，当前溢价 12%
  📐 因子信号：动量+ ★★★★☆  反转− ★★☆☆☆
  ⚠️  风险指标：夏普 0.82  最大回撤 -18.3%
  🏭 同行对比：PE低于行业中位，股息率排名前 20%
  ✅ 综合评分：73/100 — 估值合理偏高，关注回调买入
```

---

## 分析模块

十维量化体系，可独立调用也可组合运行：

| 模块 | 参数 | 说明 |
|:----:|:----:|------|
| 📏 估值分位 | `-m valuation` | PE/PB 历史分位数（3 / 5 / 10 年） |
| 💰 现金流 | `-m fcf` | 自由现金流、分红率、DDM 隐含估值 |
| 📐 因子信号 | `-m factors` | 9 因子评分（反转 / 动量 / 量能 / 波动） |
| ⚠️ 风险指标 | `-m risk` | 夏普 / Sortino / Calmar / 最大回撤 / VaR |
| 🚀 动量反转 | `-m momentum` | 动量分组回测、反转规则 |
| 💹 资金面 | `-m capital` | 量价关系、筹码分布、OBV |
| 📅 事件日历 | `-m events` | 财报日、除权除息、季节性统计 |
| 🔄 交易回测 | `-m trading` | 量化交易规则历史回测 |
| 🏭 同行对比 | `--peer-compare` | 同行业 PE / PB / 股息率 / 技术面对比 |

**默认运行全部模块。**

---

## 快速开始

```bash
# 一行命令，全量分析
cd skills/cn-stock-quant/scripts && python3 quant_analysis.py 600900

# 只跑估值和因子
python3 quant_analysis.py 600900 --modules valuation,factors

# JSON 输出（方便下游处理）
python3 quant_analysis.py 600900 --format json

# 加上同行对比
python3 quant_analysis.py 600900 --peer-compare
```

---

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 日线行情 | [akshare](https://github.com/akfamily/akshare) `stock_zh_a_hist` | A 股日线，2015 年起 |
| 财务报表 | akshare `stock_financial_*_ths` | 同花顺财务数据 |
| 实时行情 | 腾讯 API `qt.gtimg.cn` | PE / PB / 市值 / 股息率 |
| 同行识别 | 行业自动匹配 | 见 `references/peer_groups.md` |

**依赖：** `pip install akshare pandas numpy`

---

## 输出示例

报告按十大模块结构化输出：

```
一、历史估值分位数（PE/PB分位）
二、自由现金流 & 分红量化模型
三、因子信号系统（9因子评分）
四、风险指标量化（夏普/回撤/VaR）
五、动量与反转量化规则
六、资金面量化（量价/筹码/OBV）
七、事件驱动日历 & 季节性
八、量化交易规则回测
九、同行横向对比
十、综合量化评分 & 操作建议
```

可选输出到**飞书文档**，一键分享。

---

## 安装

### Claude Code

```bash
# 克隆到项目 skills 目录
git clone <repo-url> .claude/skills/cn-stock-quant
```

### OpenClaw

```bash
git clone <repo-url> ~/.openclaw/workspace/skills/cn-stock-quant
```

### 依赖安装

```bash
pip install akshare pandas numpy
```

---

## 项目结构

```
cn-stock-quant/
├── SKILL.md                          # Skill 入口 & 完整文档
├── scripts/
│   └── quant_analysis.py             # 主分析脚本
├── references/
│   ├── factor_definitions.md         # 因子定义与计算方法
│   ├── trading_rules.md              # 交易规则模板与回测方法
│   └── peer_groups.md                # 行业同行分组
└── README.md
```

---

## 详细方法论

- [因子定义与计算](references/factor_definitions.md) — 9 因子的数学定义与信号逻辑
- [交易规则模板](references/trading_rules.md) — 回测框架与策略模板
- [同行分组](references/peer_groups.md) — 行业分类与对标逻辑

---

## 注意事项

- 财务数据仅在年报 / 半年报 / 季报披露后更新
- PE 分位用年度 EPS 计算，年末切换，非实时滚动
- 腾讯 API 字段映射可能变化，需定期验证
- akshare 偶有限流，内置自动重试（最多 3 次）

---

<div align="center">

MIT License © [Eric](https://github.com)

</div>
