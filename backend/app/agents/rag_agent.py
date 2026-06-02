"""RAG Agent 知识库专家节点（占位）。

职责：
- 根据 task_draft 构造 SOP 检索 Query，调用现有 RAG 服务。
- 生成处理建议附加到任务说明；置信度低时触发 Knowledge Gap 流程。
"""


async def run(state: dict) -> dict:
    # TODO: 调用 app/rag/client.py 完成 SOP 检索与建议生成。
    raise NotImplementedError
