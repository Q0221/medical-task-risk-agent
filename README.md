# 医疗企业任务协同与风险跟进智能体（Medical Task Risk Agent）

面向医疗企业内部客服、医学支持、产品运营、质控与合规人员的任务协同与风险跟进智能体系统。

基于 LangGraph 设计 Supervisor + 多专家 Agent 架构，覆盖：

- 任务处理（Task Agent）
- 医疗风控（Risk Agent）
- RAG 知识检索（RAG Agent）
- 人工审核（Human-in-the-loop）
- 通知提醒（Notify Agent）
- 日报总结（Summary Agent）

## 技术栈

- 后端：Python 3.11 + FastAPI
- Agent 工作流：LangGraph
- RAG：复用现有 RAG 服务（通过 `app/rag` 适配层接入）
- 缓存与延迟提醒：Redis（含 ZSet）
- 数据库：MySQL 8（异步 SQLAlchemy 2.0 + asyncmy）
- 前端：Vue3 + Element Plus（暂未创建）
- 测试：pytest + pytest-asyncio

## 目录结构

```text
medical-task-risk-agent/
├── backend/                # 后端 FastAPI 服务（详见 backend/README.md）
├── docker-compose.yml      # 本地依赖：MySQL + Redis
└── README.md
```

## 快速开始

1. 启动本地依赖服务：

   ```bash
   docker compose up -d
   ```

2. 进入 `backend/` 目录，参考 [backend/README.md](backend/README.md) 启动后端服务。
