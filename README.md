# The Observatory / 观象台

观象台是面向 **Windows x64 单用户本机运行**的投资工作台，用于记录持仓和交易、观察股票与基金走势、聚合市场新闻，并向用户自行配置的 AI Agent 提供分析上下文。

持仓、交易、知识库和复盘保存在本机 SQLite 与文件中，仓库只提供源码和空白示例。行情、新闻和网页字体会请求第三方服务；使用云端 AI Agent 时，分析上下文也可能发送给所选模型服务商。本项目仅供个人学习与记录，不构成投资建议。

## 功能

- 总览、持仓、操作、走势、信号、前沿新闻和 Agent 七个页面，支持追踪列表、走势详情与搜索。
- 买卖流水同步持仓；流水撤回保留审计记录；持仓修正不生成交易流水。
- 基金估值和新闻采用多个免费数据源，提供来源、时间与回退状态提示。
- Agent 分析包汇集本机持仓、行情质量、历史复盘及外部检索要求；复盘可以追加到用户指定的 Markdown 文件。

## 运行要求

- Windows 10/11 x64。
- Python 3.11+（建议为项目创建独立虚拟环境）。Windows 安装会通过项目依赖获取 IANA 时区数据。
- Node.js `^20.19.0` 或 `>=22.12.0`，以及随附的 npm；推荐 Node.js 22 LTS。
- 可选：构建系统托盘启动器需 .NET 8 SDK；启动器仅适用于 Windows x64。

## 首次安装与启动

克隆或下载仓库后，在仓库根目录打开两个 PowerShell 窗口。先在第一个窗口安装并启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在第二个窗口安装并启动前端：

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开 <http://127.0.0.1:5173>。后端健康检查地址为 <http://127.0.0.1:8000/api/health>。首次启动会在 `backend/data/` 创建空 SQLite 数据库；可在页面中添加自己的标的、持仓和操作。

依赖安装完成后，也可以从仓库根目录运行 `start_finance.bat`。它优先使用 `backend/.venv/Scripts/python.exe`，只负责启动服务，不会替你安装依赖。后端端口为 8000、前端端口为 5173；若端口被其他程序占用，请先处理冲突。

需要托盘启动器时，在仓库根目录运行：

```powershell
dotnet publish launcher/FinanceLauncher/FinanceLauncher.csproj -c Release -o launcher/publish
.\launcher\publish\FinanceLauncher.exe
```

启动器会向上查找仓库根目录，也可使用 `FINANCE_ROOT` 环境变量或 `--root` 参数指定。它同样优先使用后端虚拟环境。

## 本机数据与可选配置

`backend/data/` 整个目录、`agent_data/watchlist.json`、导出文件、日志和本机报告均被 Git 忽略。新用户从空数据库开始，无需复制原作者的任何数据。项目文件位置见 [目录指南](docs/project-structure.md)。

独立行情导出脚本 `agent_data/export_daily.py` 是可选工具。使用前复制 [空白清单示例](agent_data/watchlist.example.json) 为 `agent_data/watchlist.json`，再填写自己的标的。新闻与持仓的专属代码标签也可选：将 [标签示例](backend/tag_overrides.example.json) 复制到 `backend/data/tag_overrides.json`，把示例代码换成自己的六位代码，标签须使用前沿新闻页已有的主题名称。未配置时，系统仍按标的名称和主题字段识别标签。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `FINANCE_DB_PATH` | `backend/data/finance.db` | SQLite 数据库文件 |
| `FINANCE_KNOWLEDGE_PATH` | `backend/data/knowledge.md` | 可选知识库；文件不存在时跳过 |
| `FINANCE_REVIEW_PATH` | `backend/data/reviews/每日复盘.md` | Agent 复盘追加目标；首次追加时创建 |
| `FINANCE_TAG_OVERRIDES_PATH` | `backend/data/tag_overrides.json` | 可选的私人代码标签映射 |
| `FINANCE_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许的本机前端来源 |
| `FINANCE_ROOT` | 自动查找 | 托盘启动器的仓库根目录 |
| `VITE_API_BASE` | `http://127.0.0.1:8000/api` | 前端构建时的 API 地址 |

其余行情、新闻超时与缓存参数见 [后端配置](backend/app/config.py)。`VITE_*` 变量会进入浏览器代码，不能放密码或令牌。环境变量可在当前 PowerShell 会话中设置，例如 `$env:FINANCE_REVIEW_PATH = 'D:\Notes\review.md'`，然后启动后端。

## 安全与备份

本项目的 API 没有用户认证，只应绑定 `127.0.0.1` 供本人使用。不要把后端端口、前端开发服务器或反向代理直接开放到公网；CORS 不是身份验证。外部 Agent 获取分析包后，私有持仓可能进入所选模型服务商，使用前请确认其数据处理方式。

备份前先退出观象台，再将 `backend/data/`、独立导出工具的 `agent_data/watchlist.json`，以及你通过环境变量指定在项目外的知识库和复盘文件复制到**加密**的本地或异地备份位置。不要把明文数据库、清单、复盘或备份包提交到 GitHub；私有仓库也不建议作为唯一备份。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest tests -q

cd ../frontend
npm run check
```

Agent 分析包与复盘接口格式见 [Agent 工作流](docs/agent-workflow.md)。免费行情与新闻接口可能限流、延迟或改变格式，项目不保证数据的实时性、完整性和准确性。

## 许可证

[MIT](LICENSE)
