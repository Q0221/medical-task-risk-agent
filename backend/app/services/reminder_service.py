"""Reminder 服务（占位）：基于 Redis ZSet 的延迟提醒。

后续将实现：
- schedule(task_id, remind_at): 写入 ZSet，score 为提醒时间戳
- cancel(task_id):               移除 ZSet 中的提醒
- Reminder Worker:               扫描到期任务并交由 Notify Agent 发送
"""
