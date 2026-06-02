# Backend - Medical Task Risk Agent

医疗企业任务协同与风险跟进智能体的后端服务，基于 FastAPI + LangGraph + SQLAlchemy(async) + Redis 构建。

> 本目录当前为**项目骨架阶段**，仅提供工程结构、配置、统一响应、健康检查与测试入口，业务逻辑（Agent 编排、任务 CRUD、风控、RAG、通知等）将在后续迭代中逐步实现。

## 目录结构

```text
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/                 # HTTP 接口层
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/   # health、tasks ...
│   ├── agents/              # 各专家 Agent（Task / Risk / RAG / Notify / Summary）
│   ├── graph/               # LangGraph 编排（state、builder）
│   ├── rag/                 # 现有 RAG 服务的适配层
│   ├── services/            # 业务服务（task、reminder ...）
│   ├── models/              # SQLAlchemy ORM 模型（含 11 张业务表）
│   ├── schemas/             # Pydantic 请求/响应模型
│   └── core/                # 基础设施：config / db / redis / logger / exceptions / response
├── alembic/                 # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_init.py     # 初始迁移：11 张表
├── scripts/
│   └── seed.py              # 灌入开发期示例数据
├── tests/                   # pytest 测试
├── alembic.ini
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

## 启动说明

### 1. 准备环境变量

在 `backend/` 目录下复制并编辑 `.env`：

```bash
copy .env.example .env      # Windows
# 或
cp .env.example .env        # Mac / Linux
```

> 重要：把 `LLM_API_KEY` 填成你的阿里云百炼（DashScope）API Key（以 `sk-` 开头）。
> `LLM_BASE_URL` 默认指向百炼 OpenAI 兼容端点，无需改动。
> 没填 Key 时调用 `/api/v1/agent/chat` 会返回 5010 错误。

### 2. 启动本地依赖（MySQL + Redis）

回到项目根目录执行：

```bash
docker compose up -d
```

### 3. 创建虚拟环境并安装依赖

```bash
# Windows (PowerShell)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Mac / Linux
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 执行数据库迁移与种子数据

> 首次启动或拉取新代码后需要执行。

```bash
# 建表 / 升级到最新版本
alembic upgrade head

# 灌入开发期示例数据（角色 / 员工 / 医院 / 产品），幂等
python -m scripts.seed
```

常用 Alembic 命令：

```bash
alembic current               # 查看当前数据库版本
alembic history --verbose     # 查看迁移历史
alembic downgrade -1          # 回退一个版本
alembic downgrade base        # 回退到空库
alembic revision --autogenerate -m "add xxx"   # 修改 ORM 后生成新迁移
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- Swagger UI： <http://localhost:8000/docs>
- OpenAPI JSON： <http://localhost:8000/openapi.json>
- 健康检查： <http://localhost:8000/api/v1/healthz>
- 就绪检查： <http://localhost:8000/api/v1/readyz>

### 6. 运行测试

```bash
pytest -q
```

### 7. 端到端验证：自然语言建任务（Phase 2 + 3 闭环）

服务起好后，向 Agent 入口发一条中文需求：

```powershell
$body = @{ user_input = "请张客服明天下午3点提醒回访示例三甲医院A的售后情况" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/chat `
    -ContentType "application/json; charset=utf-8" -Body $body
```

或用 curl（Mac/Linux/Git Bash）：

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
     -H "Content-Type: application/json" \
     -d '{"user_input":"请张客服明天下午3点提醒回访示例三甲医院A的售后情况"}'
```

预期返回（节选）：

```json
{
  "code": 0,
  "data": {
    "intent": "create_todo",
    "task": { "id": 1, "title": "回访示例三甲医院A售后", "assignee_id": 2, ... },
    "draft": { "title": "...", "type": "customer_followup", ... },
    "retry_count": 0
  },
  "trace_id": "..."
}
```

随后用任务详情接口验证落库：

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/tasks/1
```

或直接连数据库看：

```bash
docker exec -it medical-agent-mysql mysql -uroot -proot \
    -e "SELECT id,title,type,assignee_id,hospital_id,remind_at FROM medical_agent.tasks;"
```

## 统一响应结构

所有接口返回均封装为 `ApiResponse`：

```json
{
  "code": 0,
  "message": "ok",
  "data": { },
  "trace_id": "uuid4"
}
```

- `code == 0` 表示成功，其它表示业务/系统错误。
- `trace_id` 由中间件为每次请求生成（uuid4），便于链路排查。

## 数据库表一览（Phase 1 已落地）

| 表 | 说明 |
| --- | --- |
| `roles` | 内置角色（客服 / 医学 / 产品 / 质控 / 合规 / 主管 / admin） |
| `users` | 员工主数据，企业微信/邮箱/工号 |
| `user_roles` | 员工-角色多对多 |
| `hospitals` | 医院客户，含历史风险分 |
| `products` | 产品主数据 |
| `tasks` | 任务主表（类型/状态/优先级/风险/责任人/关联对象/提醒截止/审核） |
| `task_events` | 任务流转事件流（创建/分派/审核/完成等） |
| `risk_records` | 风险审核记录（含 LLM 判断 / 关键词 / 规则命中） |
| `knowledge_gap_tasks` | 知识空缺任务（RAG 置信度低时自动创建） |
| `notifications` | 通知发送记录（多渠道 + 重试） |
| `agent_traces` | Agent 链路本地审计 |

所有业务表统一使用 `BigInteger` 自增主键 + `created_at` / `updated_at` / `deleted_at`（软删除），字符集 `utf8mb4_unicode_ci`。

## 后续规划（非本期骨架内容）

- 在 `app/agents/`、`app/graph/` 下接入 LangGraph 真实实现（Supervisor + 多专家 Agent）。
- 在 `app/services/reminder_service.py` 实现 Redis ZSet 延迟提醒 + Worker 扫描。
- 在 `app/rag/client.py` 接入现有 RAG 服务。
- 接入 LangSmith / Agent Trace 链路观测。
- 接入企业微信、邮件、MQ 等通知与异步基础设施。
