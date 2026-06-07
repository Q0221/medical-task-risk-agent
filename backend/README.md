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
#cd D:\github_project\medical-task-risk-agent
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

# 方式 A：最小种子（7 员工 + 3 医院 + 3 产品），适合快速冒烟
python -m scripts.seed

# 方式 B（推荐）：每张业务表补齐 50 条标准虚拟数据，写入 MySQL 后长期可用，无需每次重启再灌
python -m scripts.seed_bulk

# 若 DEMO_ 虚拟数据乱了，可先清空再重灌
python -m scripts.seed_bulk --reset
python -m scripts.seed_bulk --count 50
```

`seed_bulk` 会保留「张客服 / 示例三甲医院A」等内置数据，并用 `DEMO_` 前缀补齐到目标条数；任务类数据的 `trace_id` 以 `demo-trace-` 开头，便于 `--reset` 清理。

常用 Alembic 命令：

```bash
alembic current               # 查看当前数据库版本
alembic history --verbose     # 查看迁移历史
alembic downgrade -1          # 回退一个版本
alembic downgrade base        # 回退到空库
alembic revision --autogenerate -m "add xxx"   # 修改 ORM 后生成新迁移
```

### 5. 启动 rag_sys 真实 RAG 服务（可选，推荐）

本项目的 RAG 子智能体支持对接 `rag_sys`（真实向量 RAG：Milvus + BGE-M3 + bge-reranker），用于替代内置关键词兜底检索。

> 跳过此步骤时，RAG 自动回落到内置 SOP 关键词检索模式，功能不受影响。

```powershell
# 步骤 1：启动 Milvus 向量数据库
cd D:\github_project\rag_sys
docker compose up -d

# 步骤 2：启动 rag_sys 服务（端口 8001，使用专用 conda 环境）
& "D:\envs\rag_sys\python.exe" scripts/run_api.py
# 等待日志出现：Uvicorn running on http://0.0.0.0:8001
```

`.env` 已配置好 RAG 地址（无需修改）：

```dotenv
RAG_BASE_URL=http://localhost:8001
RAG_API_KEY=
```

### 6. 启动本服务

```bash
#conda activate D:/envs/agent_env
uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- Swagger UI： <http://localhost:8000/docs>
- OpenAPI JSON： <http://localhost:8000/openapi.json>
- 健康检查： <http://localhost:8000/api/v1/healthz>
- 就绪检查： <http://localhost:8000/api/v1/readyz>

### 7. 运行测试

```bash
pytest -q
```

### 8. 端到端验证：自然语言建任务（Phase 2 + 3 闭环）

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
    "retry_count": 0,
    "risk_assessment": { "level": "low", "requires_review": false, ... }
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

### 8. 端到端验证：高风险任务自动转人工审核（Phase 4 闭环）

发一条带"不良事件 / 设备故障 / 患者ICU"等关键词的需求，Risk Agent 会：

1. 在 `tasks` 表写回 `risk_level / risk_reason / risk_suggested_action`；
2. high / critical 自动 `review_status=pending`、`status=awaiting_review`；
3. 同事务里在 `risk_records` 写一条明细，在 `task_events` 写一条 `risk_review_request`。

```powershell
$body = @{ user_input = "李医学今天下午紧急跟进示例三甲医院B的不良事件，疑似严重并发症" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/chat `
    -ContentType "application/json; charset=utf-8" -Body $body
```

预期返回（节选）：

```json
{
  "code": 0,
  "data": {
    "intent": "create_todo",
    "task": {
      "id": 2,
      "status": "awaiting_review",
      "risk_level": "critical",
      "review_status": "pending",
      ...
    },
    "risk_assessment": {
      "level": "critical",
      "requires_review": true,
      "rules_level": "critical",
      "type_baseline": "high",
      "matched_keywords": ["不良事件", "严重并发症", "紧急"],
      "rule_hits": ["rule_type_baseline:adverse_event->high", "rule_keyword_hit", ...],
      "llm": { "level": "critical", "confidence": 0.9, ... },
      "llm_failed": false
    },
    "messages": [
      "任务已创建：id=2",
      "风险等级 critical，已转入人工审核（review_status=pending）"
    ]
  }
}
```

直连数据库再验一刀：

```bash
docker exec -it medical-agent-mysql mysql -uroot -proot \
    -e "SELECT id,risk_level,reason,review_status FROM medical_agent.risk_records ORDER BY id DESC LIMIT 3;"
```

### 9. 端到端验证：人工审核决策（Phase 5 闭环）

先查看待审核任务列表：

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/tasks/pending-review
```

然后对某个 `review_status=pending` 的任务执行审核决策（以 task_id=2 为例）：

```powershell
# 通过（放行）
$body = @{ action = "approved"; reviewer_id = 1; comment = "已核实，情况属实，放行处理" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/tasks/2/review `
    -ContentType "application/json; charset=utf-8" -Body $body

# 驳回
$body = @{ action = "rejected"; reviewer_id = 1; comment = "信息不完整，暂不立项" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/tasks/2/review `
    -ContentType "application/json; charset=utf-8" -Body $body

# 升级上报
$body = @{ action = "escalated"; reviewer_id = 1; comment = "需上报合规委员会" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/tasks/2/review `
    -ContentType "application/json; charset=utf-8" -Body $body
```

预期返回（approved 示例）：

```json
{
  "code": 0,
  "data": {
    "task_id": 2,
    "review_status": "approved",
    "task_status": "pending",
    "reviewer_id": 1,
    "reviewed_at": "2026-06-03T10:00:00",
    "message": "审核通过，任务已放行"
  }
}
```

状态机：

| action    | review_status | task status        |
| --------- | ------------- | ------------------ |
| approved  | approved      | pending（放行）    |
| rejected  | rejected      | cancelled          |
| escalated | escalated     | awaiting_review    |

### 10. 离线 / 没 LLM Key 时的兜底

把 `.env` 里 `LLM_API_KEY` 留空再发请求，Task Agent 会失败（5010），但是
如果你直接调用业务接口建任务（后续 Phase 接），Risk Agent 会自动回落到**纯规则层**：

- `risk_assessment.llm_failed=true`
- `risk_assessment.llm=null`
- 等级仅来自 `type_baseline` + 关键词 + urgent 加权

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

## Phase 路线图

| Phase | 状态 | 说明 |
| --- | --- | --- |
| 1 | done | 工程骨架 + 11 张表 + 迁移 + 种子 + 健康检查 |
| 2 | done | Task Agent：自然语言 → 结构化 JSON（Self-Reflection 重试） |
| 3 | done | `/agent/chat` 落库 + 任务查询接口 |
| 4 | done | Risk Agent：规则 + LLM 混合分级、高风险自动转人工审核 |
| 5 | done | Human-in-the-loop 审核接口（`POST /tasks/{id}/review` + `GET /tasks/pending-review`） |
| 6 | done | RAG Agent + 内置 SOP 知识库 + Knowledge Gap 自动建任务（`POST /agent/knowledge`） |
| 7 | done | Reminder（Redis ZSet）+ Worker 到期通知（`POST/DELETE /tasks/{id}/remind`） |
| 8 | done | Notify Agent + 企业微信 / 邮件多渠道（`GET /notifications`，`POST /notifications/{id}/retry`） |
| 9 | done | LangGraph StateGraph 真正编排 + agent_traces 持久化（`GET /agent/traces`） |
| **10** | **done** | **Summary Agent 日报/周报（`GET /agent/summary`）+ 生命周期接口（complete / cancel / assign）** |

## Phase 4 实现要点

- 规则层：`app/agents/risk_agent.py`
  - 任务类型基线 `_TYPE_BASELINE`
  - 关键词词典 `_KEYWORD_LEVEL`（critical / high / medium 三档）
  - 优先级 urgent 自动 +1 档
- LLM 层：`prompts.RISK_ASSESSMENT_*` + `schemas.RISK_ASSESSMENT_SCHEMA`
  - 输出失败（JSON / Schema / API 异常）自动回落规则层
- 仲裁：`final = max(rules_level, llm_level)`，保守取高
- 持久化：`app/services/risk_service.py` 在同事务内
  - 反写 `tasks.risk_level/risk_reason/...`
  - 高风险设 `review_status=pending` + `status=awaiting_review`
  - 写 `risk_records` + `task_events(risk_review_request|update)`

## Phase 10 端到端验证：Summary Agent + 任务生命周期

### 任务生命周期

```powershell
# 完成任务
Invoke-RestMethod -Method PATCH -Uri http://localhost:8000/api/v1/tasks/1/complete `
    -ContentType "application/json; charset=utf-8" `
    -Body '{"operator_id":1,"comment":"已处理完毕"}'

# 取消任务
Invoke-RestMethod -Method PATCH -Uri http://localhost:8000/api/v1/tasks/2/cancel `
    -ContentType "application/json; charset=utf-8" `
    -Body '{"operator_id":1,"reason":"重复任务"}'

# 重新分配负责人
Invoke-RestMethod -Method PATCH -Uri http://localhost:8000/api/v1/tasks/3/assign `
    -ContentType "application/json; charset=utf-8" `
    -Body '{"operator_id":1,"assignee_name":"张客服","comment":"换人跟进"}'
```

### 生成日报 / 周报

```powershell
# 今日日报（实时统计 + LLM 生成报告）
Invoke-RestMethod "http://localhost:8000/api/v1/agent/summary?type=daily"

# 指定日期日报
Invoke-RestMethod "http://localhost:8000/api/v1/agent/summary?type=daily&date=2026-06-03"

# 本周周报
Invoke-RestMethod "http://localhost:8000/api/v1/agent/summary?type=weekly"
```

响应包含 `stats`（结构化统计）+ `narrative`（LLM 生成的自然语言报告）+ `notification_id`。

## Phase 9 端到端验证：LangGraph 编排 + agent_traces

### 建任务并查看执行链路

```powershell
# 1. 建任务（响应中会有 trace_id）
$r = Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/chat `
    -ContentType "application/json; charset=utf-8" `
    -Body '{"user_input":"请张客服处理三甲医院A的不良事件上报","user_id":1}'

# 2. 查该 trace_id 的执行链路（需从 HTTP Response Header 中取 X-Trace-Id，或从日志中找）
Invoke-RestMethod "http://localhost:8000/api/v1/agent/traces?trace_id=<trace_id>"

# 3. 按节点过滤
Invoke-RestMethod "http://localhost:8000/api/v1/agent/traces?node=risk_agent&page_size=5"
```

### 验证 LangGraph 节点日志

服务日志中应看到类似：
```
graph.ainvoke: supervisor → task → risk → rag → remind → done
```

### 查看 agent_traces 表

```bash
docker exec -it medical-agent-mysql mysql -uroot -proot \
    -e "SELECT id,trace_id,node,status,duration_ms,created_at FROM medical_agent.agent_traces ORDER BY id DESC LIMIT 10;"
```

## Phase 8 端到端验证：Notify Agent 多渠道通知

### 查询通知列表

```powershell
# 查询最新 5 条通知
Invoke-RestMethod "http://localhost:8000/api/v1/notifications?page_size=5"

# 按 user_id 过滤
Invoke-RestMethod "http://localhost:8000/api/v1/notifications?user_id=1&status=sent"

# 查看某任务的所有通知
Invoke-RestMethod "http://localhost:8000/api/v1/notifications?task_id=1"
```

### 验证任务创建时自动写通知

```powershell
# 通过 agent/chat 创建一个任务，然后查通知表
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/chat `
    -ContentType "application/json; charset=utf-8" `
    -Body '{"user_input":"请张客服处理三甲医院B的投诉","user_id":1}'
# → 创建后查询 /notifications?kind=task_created 应有一条 status=sent 的记录
```

### 手动重试失败通知

```powershell
Invoke-RestMethod -Method POST `
    -Uri http://localhost:8000/api/v1/notifications/1/retry
```

### 配置企业微信 / 邮件（可选，留空默认走站内消息）

在 `.env` 中添加：
```ini
# 企业微信群机器人
WXWORK_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
DEFAULT_NOTIFY_CHANNEL=wxwork

# 邮件（二选一）
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=noreply@example.com
SMTP_PASSWORD=your_password
SMTP_FROM=noreply@example.com
DEFAULT_NOTIFY_CHANNEL=email
```

## Phase 7 端到端验证：提醒设置 + Worker 到期通知

### 设置任务提醒

```powershell
# 对任务 id=1 设置 1 分钟后提醒（测试用）
$remind = (Get-Date).AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss")
$body = @{ remind_at = $remind } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/tasks/1/remind `
    -ContentType "application/json; charset=utf-8" -Body $body
```

### 查看通知记录（Worker 扫描后写入）

```bash
# 等待 ~30 秒让 Worker 扫描到期，然后验证：
docker exec -it medical-agent-mysql mysql -uroot -proot \
    -e "SELECT id,task_id,kind,status,title,created_at FROM medical_agent.notifications ORDER BY id DESC LIMIT 5;"
```

### 取消提醒

```powershell
Invoke-RestMethod -Method DELETE -Uri http://localhost:8000/api/v1/tasks/1/remind
```

### 自然语言建任务时自动注册提醒

含时间信息的建任务请求（如"明天下午3点"），创建后会在响应 `messages` 中看到"提醒已设置"。

## Phase 6 端到端验证：知识库问答 + Knowledge Gap

> **RAG 升级说明**：RAG 子智能体已对接 `rag_sys` 真实向量 RAG 服务（Milvus + BGE-M3 + bge-reranker），替代原有关键词兜底检索。
> - `rag_sys` 运行在 **http://localhost:8001**
> - 召回来源：Milvus 向量库（需提前用 `scripts/build_index.py` 建库）
> - 置信度：由 BGE Reranker 的 `rerank_score` 推导，无命中时为 `0.0`
> - 回落机制：`rag_sys` 不可达时自动回落内置 SOP 关键词检索

### 直接知识问答（高置信度）

```powershell
$body = @{ question = "不良事件发生后应该在多少天内上报？负责人是谁？" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/knowledge `
    -ContentType "application/json; charset=utf-8" -Body $body
```

预期返回（接入 rag_sys 后 `used_builtin` 为 `false`）：
```json
{
  "code": 0,
  "data": {
    "question": "...",
    "answer": "根据 SOP 文档，严重不良事件须在 15 个工作日内上报...",
    "confidence": 0.82,
    "is_gap": false,
    "references": ["parent-xxxx"],
    "used_builtin": false
  }
}
```

### 知识空缺自动建任务（低置信度）

```powershell
$body = @{ question = "新型介入手术机器人出现定位漂移时的紧急处置流程是什么？" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/v1/agent/knowledge `
    -ContentType "application/json; charset=utf-8" -Body $body
```

预期返回（知识库无对应 SOP）：
```json
{
  "code": 0,
  "data": {
    "is_gap": true,
    "confidence": 0.0,
    "gap_reason": "当前知识库中未找到相关 SOP 文档，建议补充。",
    "gap_task_id": 1
  }
}
```

验证 `knowledge_gap_tasks` 表：
```bash
docker exec -it medical-agent-mysql mysql -uroot -proot \
    -e "SELECT id,original_question,confidence,status,assignee_id FROM medical_agent.knowledge_gap_tasks ORDER BY id DESC LIMIT 3;"
```

### 高风险任务创建时自动附加 SOP 建议

高风险任务（`adverse_event`/`device_anomaly`/`complaint` 类型）创建后，`data.rag_result` 字段会自动包含 SOP 检索结果。

## Phase 5 实现要点

- 接口：`app/api/v1/endpoints/tasks.py`
  - `GET  /tasks/pending-review`：分页列出 `review_status=pending` 的待审核任务
  - `POST /tasks/{id}/review`：提交审核决策（approved / rejected / escalated）
- Schema：`app/schemas/task.py`
  - `TaskReviewRequest`：`action` + `reviewer_id` + `comment`
  - `TaskReviewResult`：决策结果摘要
- 服务层：`app/services/task_service.py`
  - `review_task`：校验任务状态 → 更新 `tasks` 字段 → 同步最近一条 `risk_records` → 写 `task_events(risk_review_decide)`
  - `list_pending_review`：分页查询待审核任务
- 前置校验：`review_status` 必须为 `pending`，`reviewer_id` 必须存在，否则返回 409/404
