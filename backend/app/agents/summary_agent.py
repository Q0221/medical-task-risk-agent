"""Summary Agent 任务总结专家节点（占位）。

职责：
- 按员工 / 部门 / 任务类型 / 风险等级 / 完成状态统计当日新增、已完成、未完成、逾期、
  高风险、待审核、知识补充等数据。
- 通过大模型生成日报或周报。
"""


async def run(state: dict) -> dict:
    # TODO: 实现日报 / 周报统计与生成。
    raise NotImplementedError
