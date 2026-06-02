"""Risk Agent 医疗风控专家节点（占位）。

职责：
- 关键词识别 + 业务规则 + 大模型语义分析的混合风险分级。
- 输出风险等级、原因与建议处理动作；触发 Human-in-the-loop 审核。
"""


async def run(state: dict) -> dict:
    # TODO: 实现风险分级与审核挂起逻辑。
    raise NotImplementedError
