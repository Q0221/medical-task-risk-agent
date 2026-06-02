"""RAG 适配层：对接已有的企业 RAG 知识库系统（占位）。

后续将通过 HTTP / SDK 调用现有 RAG 服务，实现：
- retrieve(query, top_k): 检索 SOP 文档与命中片段
- ask(query, context):    基于检索结果的回答生成
- 置信度评估、Knowledge Gap 识别
"""


class RagClient:
    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        self.base_url = base_url
        self.api_key = api_key

    async def retrieve(self, query: str, top_k: int = 5):
        # TODO: 调用现有 RAG 服务并返回标准化结果。
        raise NotImplementedError
