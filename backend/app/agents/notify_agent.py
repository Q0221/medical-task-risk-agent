"""Notify Agent 通知专家节点（占位）。

职责：
- 任务创建通知、到期提醒、高风险审核通知、知识补充任务通知、日报周报。
- 通过企业微信 / 邮件 / 站内消息触达责任人、协作人、主管、合规人员。
"""


async def run(state: dict) -> dict:
    # TODO: 接入 MQ + 企业微信 / 邮件 SDK。
    raise NotImplementedError
