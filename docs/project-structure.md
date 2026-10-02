# 项目目录指南

根目录只保留项目入口、许可证、忽略规则和模块目录。页面、接口、测试、文档与本地数据各有固定位置，方便后续升级时定位文件，也避免把真实投资数据加入版本控制。

| 目录 | 用途 | Git |
| --- | --- | --- |
| `backend/app/api/` | FastAPI 路由与请求边界 | 跟踪 |
| `backend/app/services/` | 行情、新闻、持仓估值和 Agent 分析逻辑 | 跟踪 |
| `backend/tests/`、`backend/scripts/` | 后端测试和维护脚本 | 跟踪 |
| `backend/data/` | SQLite、知识库、复盘和私人标签配置 | 忽略整个目录 |
| `backend/tag_overrides.example.json` | 私人标签配置格式示例 | 跟踪 |
| `frontend/src/pages/`、`components/`、`hooks/` | 页面、组件和 React Query 数据请求 | 跟踪 |
| `frontend/src/styles/` | 全局与各页面样式；导入顺序由 `frontend/src/main.tsx` 控制 | 跟踪 |
| `frontend/scripts/` | 浏览器回归检查 | 跟踪 |
| `launcher/` | Windows 启动器 | 跟踪源码，忽略构建产物 |
| `docs/`、`.agents/skills/` | 工作流、目录说明和项目技能 | 跟踪现行文档 |
| `agent_data/` | 可选的独立行情导出工具 | 跟踪脚本与示例，忽略私有清单及导出结果 |
| `reports/`、`logs/`、`local/` | 研究报告、运行日志和个人临时材料 | 忽略 |

新后端功能把路由放在 `backend/app/api/`，业务处理放在 `backend/app/services/`，测试放在 `backend/tests/`。新前端页面放在 `frontend/src/pages/`，共享请求逻辑放在 `frontend/src/hooks/`；样式放在 `frontend/src/styles/` 并从 `frontend/src/main.tsx` 引入。维护脚本放在所属模块的 `scripts/`，生成文件写入对应的数据或本地输出目录。

`backend/data/` 可能包含正在使用的数据库和真实复盘，整理文件时不要移动或清空它。`backend/data/tag_overrides.json` 可由仓库中的示例复制，保存个人标的代码与新闻标签的映射。`agent_data/watchlist.json` 是独立导出工具的个人配置，可复制 `agent_data/watchlist.example.json` 创建；`agent_data/exports/` 是导出结果。`local/` 用于本机临时材料和归档，不进入公开仓库。
