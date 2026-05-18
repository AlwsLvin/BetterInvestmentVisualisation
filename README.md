# BetterInvestDecision

BetterInvestDecision 是一个投资组合决策辅助 Web 应用。项目将行情获取、资产指标计算、FAHP-FTOPSIS 权重决策、滚动定投回测、组合评价、基准比较和前端可视化整合在一起，用于辅助观察不同投资风格下的组合表现。

> 本项目主要由AI开发，初衷为测试AI开发能力，并不保证数据及业务逻辑的正确性！！！不应该将其视为有效的投资决策工具！！！
> 本项目主要由AI开发，初衷为测试AI开发能力，并不保证数据及业务逻辑的正确性！！！不应该将其视为有效的投资决策工具！！！
> 本项目主要由AI开发，初衷为测试AI开发能力，并不保证数据及业务逻辑的正确性！！！不应该将其视为有效的投资决策工具！！！

## 功能特性

- 自选组合管理：在浏览器中维护多个本地组合，添加、删除和编辑标的。
- 行情与详情页：查看股票、ETF、指数和外汇的价格曲线、K 线、分红和基本面快照。
- FAHP-FTOPSIS 分配：根据高回报、低波动等偏好计算资产评分与投资比例。
- 滚动定投回测：按时间窗口滚动训练权重，并模拟定投收益曲线。
- 组合评价：展示持有收益、年化收益、最大回撤、波动率、Beta、Alpha 和 Sharpe 等指标。
- 基准比较：支持默认组合基准，也支持手动搜索并选择对比基准。
- 多币种处理：支持 USD、CNY、HKD、KRW 等资产的 USD 口径折算。
- 外汇面板：展示主要外汇正反向汇率，并提供外汇详情页。

## 技术栈

后端：

- Python
- FastAPI
- Pydantic
- pandas
- numpy
- yfinance
- pytest

前端：

- React 18
- Vite 5
- TypeScript
- Tailwind CSS
- TanStack Query
- Zustand
- ECharts
- Framer Motion

## 项目结构

```text
server/
  app/
    api/          HTTP API 路由
    core/         模糊数学基础类型
    data/         数据源、缓存、符号和市场规则
    services/     指标、FAHP、FTOPSIS、分配、回测和评价逻辑
  tests/          后端测试
  requirements.txt

web/
  src/
    api/          前端 API 封装和类型
    components/   复用组件
    pages/        页面组件
    stores/       本地状态
    utils/        图表、格式化、基准和符号工具
  package.json
```

## 本地运行

### 后端

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

后端默认地址：

```text
http://localhost:8000
```

API 文档：

```text
http://localhost:8000/docs
```

### 前端

```bash
cd web
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

开发环境中，Vite 会把 `/api/*` 请求代理到本地后端。

## 测试与构建

后端测试：

```bash
cd server
python -m pytest tests -q
```

前端类型检查：

```bash
cd web
npm run typecheck
```

前端生产构建：

```bash
cd web
npm run build
```

## 计算口径概览

- 买入持有收益：按窗口起点一次性买入，并以窗口内价格序列估值。
- 定投收益：按用户设置的金额和频率持续投入，并记录现金投入、成交和净值变化。
- 滚动分配：按设置的训练窗口重新计算 FAHP-FTOPSIS 权重，新投入资金使用对应执行段权重。
- Beta/Alpha：按资产所属市场选择基准，并在组合层合成为 composite benchmark。
- 多币种：非 USD 标的按外汇数据折算为 USD 后参与组合净值计算。

## 数据与隐私说明

- 行情和搜索数据来自 Yahoo Finance/yfinance。
- 组合、定投计划和偏好设置保存在浏览器 `localStorage`。
- 后端设置为进程内存储，服务重启后恢复默认值。
- 项目没有用户认证、服务端账户体系或多用户隔离。
- 回测结果依赖历史数据质量、数据源可用性和缓存状态，仅适合作为研究参考。

## 免责声明

本项目主要由AI开发，初衷为测试AI开发能力，并不保证数据及业务逻辑的正确性！！！不应该将其视为有效的投资决策工具！！！
该项目也仅仅是作为普通本科生的大作业基础要求，即简单的“增删改查”