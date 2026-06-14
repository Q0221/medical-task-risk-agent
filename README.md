# 医疗企业任务协同与风险跟进智能体（Medical Task Risk Agent）

面向医疗企业内部客服、医学支持、产品运营、质控与合规人员的任务协同与风险跟进智能体系统。用户可通过自然语言创建/查询任务，系统自动完成风险分级、知识检索、提醒调度、通知推送与统计报告生成。

## 核心能力

| 模块 | 说明 |
|------|------|
| **智能协同** | 自然语言建任务、多轮追问补全、任务查询、草稿确认落库 |
| **任务中心** | 任务 CRUD、筛选、批量操作、生命周期（完成/取消/分配）、评论与附件 |
| **风险中心** | 规则 + LLM 混合分级、高风险自动转人工审核、风险工单与规则管理 |
| **知识中心** | SOP 知识问答、文档管理、知识空缺任务闭环 |
| **统计报告** | 日报/周报生成、趋势图表、Word/PDF 导出 |
| **业务档案** | 医院、产品主数据管理与统计 |
| **通知提醒** | Redis ZSet 到期提醒、站内消息、企业微信/邮件多渠道 |
| **系统管理** | 人员角色、业务字典、通知渠道配置 |
| **链路审计** | Agent 执行轨迹持久化、思考过程实时展示 |

## 系统架构

```mermaid
flowchart TB
  subgraph frontend [前端 task_risk_vue]
    pages[Vue3页面]
    apiClient[API客户端]
  end

  subgraph backend [后端 FastAPI]
    router[REST API]
    graph[LangGraph编排]
    workers[Reminder/Notify Worker]
  end

  subgraph agents [专家Agent]
    supervisor[Supervisor]
    taskAgent[Task Agent]
    riskAgent[Risk Agent]
    ragAgent[RAG Agent]
    summaryAgent[Summary Agent]
    notifyAgent[Notify Agent]
  end

  subgraph infra [基础设施]
    mysql[(MySQL8)]
    redis[(Redis7)]
    llm[DashScope LLM]
    ragExt[外部RAG服务_可选]
  end

  pages --> apiClient
  apiClient -->|"/api/v1"| router
  router --> graph
  graph --> supervisor
  supervisor --> taskAgent
  supervisor --> riskAgent
  supervisor --> ragAgent
  supervisor --> summaryAgent
  taskAgent --> mysql
  riskAgent --> mysql
  ragAgent --> ragExt
  graph --> workers
  workers --> redis
  workers --> notifyAgent
  taskAgent --> llm
  riskAgent --> llm
  router --> mysql
  router --> redis
```

### LangGraph 编排流程

```
START → supervisor
          ├─ merge   → clarify / task
          ├─ clarify → END
          ├─ task    → risk → [rag] → remind → done → END
          ├─ summary → END
          ├─ query   → END
          └─ done    → END
```

Supervisor 负责意图识别与路由；Task / Risk / RAG / Summary 等专家 Agent 在各自节点内完成结构化抽取、风险评估、知识检索与报告汇总。详见 [backend/app/graph/builder.py](backend/app/graph/builder.py)。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11、FastAPI、LangGraph、LangChain OpenAI 兼容接口 |
| 数据库 | MySQL 8、SQLAlchemy 2.0（async）+ asyncmy、Alembic 迁移 |
| 缓存 | Redis 7（提醒 ZSet、会话历史） |
| 大模型 | 阿里云百炼 DashScope（`qwen-plus`，OpenAI 兼容端点） |
| RAG | 内置 SOP 关键词检索；可选对接外部 `rag_sys`（Milvus + 向量检索） |
| 前端 | Vue 3、Vite 6、Vue Router、Element Plus |
| 测试 | pytest、pytest-asyncio |

## 目录结构

```text
medical-task-risk-agent/
├── backend/                    # FastAPI 后端（详见 backend/README.md）
│   ├── app/
│   │   ├── api/v1/endpoints/   # REST 接口（agent、tasks、risk、reports …）
│   │   ├── agents/             # 专家 Agent（task / risk / rag / summary / notify）
│   │   ├── graph/              # LangGraph 状态与节点编排
│   │   ├── models/             # SQLAlchemy ORM（11+ 张业务表）
│   │   ├── services/           # 业务服务层
│   │   ├── workers/            # 后台 Worker（提醒、通知）
│   │   └── core/               # 配置、数据库、Redis、日志、统一响应
│   ├── alembic/                # 数据库迁移
│   ├── scripts/                # 种子数据（seed / seed_bulk）
│   └── tests/
├── task_risk_vue/              # Vue 3 前端
│   ├── src/
│   │   ├── pages/              # 各业务页面
│   │   ├── api/                # 后端 API 封装
│   │   ├── components/         # 通用组件
│   │   └── router/             # 路由与权限守卫
│   └── vite.config.js          # 开发代理 /api → localhost:8000
├── docker-compose.yml          # 本地依赖：MySQL + Redis
├── 部署.md                      # 云服务器 Docker 部署计划
└── README.md
```

## 前端页面

| 路由 | 页面 | 权限 |
|------|------|------|
| `/dashboard` | 总览工作台 | 全部角色 |
| `/assistant` | 智能协同（对话 + 思考过程） | 全部角色 |
| `/tasks` | 任务中心 | 全部角色 |
| `/risk` | 风险中心 | manager、admin |
| `/records` | 业务档案（医院/产品） | 全部角色 |
| `/knowledge` | 知识中心（SOP / 知识空缺） | 全部角色 |
| `/reports` | 统计报告（图表 + 导出） | 全部角色 |
| `/admin` | 系统管理 | admin |

## 快速开始（本地开发）

### 前置要求

- Python 3.11+
- Node.js 18+（前端）
- Docker Desktop（MySQL + Redis）

### 1. 启动依赖服务

在项目根目录执行：

```powershell
docker compose up -d
```

将启动 MySQL（`3306`）和 Redis（`6379`），数据持久化在 `.data/` 目录。

### 2. 配置并启动后端

```powershell
cd backend

# 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 在 backend/ 下创建 .env，至少配置 LLM_API_KEY
# 参考 backend/app/core/config.py 中的环境变量说明

# 数据库迁移与种子数据
alembic upgrade head
python -m scripts.seed_bulk

# 启动 API 服务
uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- Swagger UI：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/healthz>
- 就绪检查：<http://localhost:8000/api/v1/readyz>

### 3. 启动前端

```powershell
cd task_risk_vue
npm install
npm run dev
```

浏览器访问 <http://localhost:5173>，使用演示账号登录（默认密码见 `backend/.env` 中的 `AUTH_DEMO_PASSWORD`，未配置时为 `123456`）。

### 4. 可选：对接外部 RAG 服务

若不配置 `RAG_BASE_URL`，RAG Agent 自动回落到内置 SOP 关键词检索，主流程不受影响。对接真实向量 RAG 的步骤见 [backend/README.md](backend/README.md)。

## 主要 API 模块

所有接口前缀为 `/api/v1`，统一响应格式 `{ code, message, data, trace_id }`，`code === 0` 表示成功。

| 模块 | 路径前缀 | 主要能力 |
|------|----------|----------|
| 认证 | `/auth` | 登录、当前用户信息 |
| 智能体 | `/agent` | 对话、草稿确认、候选项搜索、思考过程、会话历史 |
| 任务 | `/tasks` | 列表/详情、审核、提醒、生命周期、批量操作 |
| 风险 | `/risk` | 风险记录、统计、规则 CRUD、工单 |
| 知识 | `/knowledge` | SOP 管理、知识问答、知识空缺闭环 |
| 报告 | `/reports` | 图表、历史报告、Word/PDF 导出 |
| 档案 | `/records` | 医院/产品主数据 |
| 通知 | `/notifications` | 通知列表、已读、重试 |
| 摘要 | `/agent/summary` | 日报/周报生成 |
| 链路 | `/agent/traces` | Agent 执行轨迹查询 |
| 管理 | `/admin` | 人员、字典、通知渠道 |
| 健康 | `/healthz`、`/readyz` | 存活与依赖就绪检查 |

完整接口文档与端到端验证示例见 [backend/README.md](backend/README.md)。

## 环境变量（关键项）

在 `backend/.env` 中配置，完整列表见 [backend/app/core/config.py](backend/app/core/config.py)：

| 变量 | 说明 | 必填 |
|------|------|------|
| `LLM_API_KEY` | 百炼 API Key（`sk-` 开头） | 是（Agent 对话） |
| `MYSQL_*` | 数据库连接 | 是 |
| `REDIS_*` | Redis 连接 | 是 |
| `AUTH_SECRET_KEY` | JWT 签名密钥 | 生产必改 |
| `AUTH_DEMO_PASSWORD` | 演示登录密码 | 建议修改 |
| `CORS_ORIGINS` | 跨域白名单 | 生产按域名配置 |
| `RAG_BASE_URL` | 外部 RAG 服务地址 | 否 |
| `WXWORK_WEBHOOK_URL` | 企业微信通知 | 否 |
| `SMTP_*` | 邮件通知 | 否 |

## 数据库表一览

| 表 | 说明 |
|----|------|
| `roles` / `users` / `user_roles` | 角色、员工、多对多绑定 |
| `hospitals` / `products` | 医院客户、产品主数据 |
| `tasks` / `task_events` | 任务主表、流转事件流 |
| `risk_records` | 风险审核记录 |
| `sop_documents` | SOP 知识文档 |
| `knowledge_gap_tasks` | 知识空缺任务 |
| `notifications` | 通知发送记录 |
| `agent_traces` | Agent 链路审计 |
| `risk_rules` / `system_config` | 风险规则、系统配置 |

## 后台任务

后端启动时自动拉起两个异步 Worker（见 [backend/app/main.py](backend/app/main.py)），无需单独部署：

- **ReminderWorker**：扫描 Redis ZSet，到期触发任务提醒
- **NotifyWorker**：消费通知队列，支持站内消息 / 企业微信 / 邮件重试

## 测试

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## 云服务器部署

生产环境全 Docker 化部署步骤（安全组、环境变量、Nginx 反代、HTTPS 等）见 [部署.md](部署.md)。

## 相关文档

- [backend/README.md](backend/README.md) — 后端详细启动说明、Phase 路线图、端到端验证
- [部署.md](部署.md) — 云服务器 Docker 部署计划

## 开发进度

后端 Phase 1–10 已完成（工程骨架 → Task/Risk/RAG Agent → 人工审核 → 提醒通知 → LangGraph 编排 → 统计报告）。前端各业务页面已对接真实 API，智能协同支持思考过程实时轮询展示。
