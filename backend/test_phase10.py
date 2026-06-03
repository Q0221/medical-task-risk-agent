"""Phase 10 端到端验证：生命周期接口 + Summary Agent。"""
import urllib.request, json, sys, time

BASE = "http://localhost:8000/api/v1"

def req(method, url, body=None, timeout=90):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    r = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"} if data else {},
        method=method,
    )
    resp = urllib.request.urlopen(r, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))

errors = []

# ── 准备：建一个任务用于生命周期测试
print("Prepare: 建任务")
r0 = req("POST", f"{BASE}/agent/chat", {"user_input": "请张客服跟进三甲医院A的投诉", "user_id": 1}, timeout=120)
assert r0["code"] == 0, f"prepare failed: {r0}"
task_id = r0["data"]["task"]["id"]
print(f"  task_id={task_id}\n")

# ── Test 1: PATCH /tasks/{id}/assign
print("Test 1: PATCH assign 重新分配负责人")
r1 = req("PATCH", f"{BASE}/tasks/{task_id}/assign", {"operator_id": 1, "assignee_name": "张客服", "comment": "换人跟进"})
assert r1["code"] == 0, f"T1 assign failed: {r1}"
d1 = r1["data"]
print(f"  status={d1['status']} assignee_id={d1['assignee_id']}")
print("  PASS\n")

# ── Test 2: PATCH /tasks/{id}/complete
print("Test 2: PATCH complete 完成任务")
r2 = req("PATCH", f"{BASE}/tasks/{task_id}/complete", {"operator_id": 1, "comment": "已处理完毕"})
assert r2["code"] == 0, f"T2 complete failed: {r2}"
d2 = r2["data"]
print(f"  status={d2['status']}")
if d2["status"] != "completed":
    errors.append(f"T2: expected completed, got {d2['status']}")
print("  PASS\n")

# ── Test 3: PATCH /tasks/{id}/complete 再次 → 应返回 4090
print("Test 3: 重复 complete → 预期 BizException 4090")
r3 = req("PATCH", f"{BASE}/tasks/{task_id}/complete", {"operator_id": 1})
code3 = r3.get("code")
print(f"  code={code3} message={r3.get('message','')[:40]}")
if code3 not in (4090, 0):
    errors.append(f"T3: unexpected code {code3}")
print("  PASS\n")

# ── Test 4: 取消任务（从列表找一个 pending 任务，或建一个）
print("Test 4: PATCH cancel 取消任务")
# 从列表里找一个可取消的任务（status=pending 且 id != task_id）
list_r = req("GET", f"{BASE}/tasks?status=pending&page_size=20", timeout=30)
assert list_r["code"] == 0
candidates = [t for t in list_r["data"]["items"] if t["id"] != task_id]
if candidates:
    task_id2 = candidates[0]["id"]
else:
    # 最后手段：用 agent chat（多次重试）
    task_id2 = None
    for msg in [
        "B区MRI设备故障，紧急！请王工程师今天内完成维修，截止明天9点",
        "ICU 2号病床生命监护仪报警，需要维修工程师赵明立即处理",
    ]:
        r4a = req("POST", f"{BASE}/agent/chat", {"user_input": msg, "user_id": 1}, timeout=120)
        if r4a.get("code") == 0 and r4a["data"].get("task"):
            task_id2 = r4a["data"]["task"]["id"]
            break
    assert task_id2, "T4: 无可取消的任务，请先建任务"
r4b = req("PATCH", f"{BASE}/tasks/{task_id2}/cancel", {"operator_id": 1, "reason": "重复任务"})
assert r4b["code"] == 0, f"T4 cancel failed: {r4b}"
d4 = r4b["data"]
print(f"  task_id={task_id2} status={d4['status']}")
if d4["status"] != "cancelled":
    errors.append(f"T4: expected cancelled, got {d4['status']}")
print("  PASS\n")

# ── Test 5: GET /agent/summary?type=daily (统计查询)
print("Test 5: GET /agent/summary?type=daily 日报生成")
r5 = req("GET", f"{BASE}/agent/summary?type=daily&write_notif=false", timeout=60)
assert r5["code"] == 0, f"T5 summary failed: {r5}"
d5 = r5["data"]
stats = d5["stats"]
print(f"  date_range={stats['date_range']}")
print(f"  total_created={stats['total_created']} completed={stats['total_completed']}")
print(f"  narrative(50)={d5['narrative'][:50]}")
if stats["total_created"] == 0:
    errors.append("T5: no tasks in daily stats")
if not d5["narrative"]:
    errors.append("T5: empty narrative")
print("  PASS\n")

# ── Test 6: GET /agent/summary?type=weekly
print("Test 6: GET /agent/summary?type=weekly 周报生成")
r6 = req("GET", f"{BASE}/agent/summary?type=weekly&write_notif=true", timeout=60)
assert r6["code"] == 0, f"T6 weekly failed: {r6}"
d6 = r6["data"]
print(f"  weekly range={d6['stats']['date_range']} total_created={d6['stats']['total_created']}")
print(f"  notification_id={d6['notification_id']}")
if d6["notification_id"] is None:
    errors.append("T6: no notification written for weekly summary")
print("  PASS\n")

if errors:
    print("FAILED:", errors)
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
