export const tasks = [
  { id: "TSK-20260520-018", title: "跟进华东医院输注泵报警异常", type: "设备异常", hospital: "华东大学附属医院", product: "SmartPump X3", owner: "陈思远", due: "今天 16:00", status: "待审核", risk: "critical", priority: "紧急", source: "企业微信", progress: 42 },
  { id: "TSK-20260520-017", title: "补充康宁医院季度回访记录", type: "客户跟进", hospital: "康宁医院", product: "监护系统 M8", owner: "赵清", due: "今天 18:30", status: "进行中", risk: "low", priority: "普通", source: "内部系统", progress: 68 },
  { id: "TSK-20260520-014", title: "核查呼吸机传感器投诉批次", type: "投诉处理", hospital: "市立第二医院", product: "VentCare V5", owner: "陈思远", due: "明天 10:00", status: "进行中", risk: "high", priority: "高", source: "企业微信", progress: 35 },
  { id: "TSK-20260519-046", title: "整理 AED 设备异常知识补充材料", type: "知识维护", hospital: "仁济中心医院", product: "AED Pro", owner: "周然", due: "05-23 17:00", status: "待处理", risk: "medium", priority: "普通", source: "智能体", progress: 8 },
  { id: "TSK-20260519-041", title: "完成消毒产品宣传物料合规复核", type: "合规审核", hospital: "-", product: "CleanGuard 消毒液", owner: "林悦", due: "05-21 12:00", status: "已完成", risk: "medium", priority: "高", source: "内部系统", progress: 100 },
  { id: "TSK-20260518-035", title: "跟进血糖仪试纸供货反馈", type: "产品反馈", hospital: "和美医院", product: "GlucoFit S2", owner: "赵清", due: "昨天 15:00", status: "已逾期", risk: "low", priority: "普通", source: "企业微信", progress: 75 },
];

export const riskItems = [
  { id: "RSK-20260520-006", taskId: "TSK-20260520-018", title: "输注泵持续报警，疑似输液中断", hospital: "华东大学附属医院", category: "患者安全", risk: "critical", status: "待审核", owner: "陈思远", time: "今天 09:42", reason: "涉及住院患者输注过程，设备连续报警且现场暂未确认是否导致给药中断。", suggestion: "立即联系现场护士确认患者状态；暂停同批次设备使用；升级至质控负责人和医学支持。" },
  { id: "RSK-20260520-004", taskId: "TSK-20260520-014", title: "呼吸机传感器同批次重复投诉", hospital: "市立第二医院", category: "设备异常", risk: "high", status: "待审核", owner: "陈思远", time: "今天 08:18", reason: "同型号传感器近 30 天出现 3 次相似投诉，需要排查批次质量风险。", suggestion: "收集设备 SN 和传感器批次；创建质量调查工单；通知区域产品经理。" },
  { id: "RSK-20260519-016", taskId: "TSK-20260519-041", title: "消毒产品物料缺少适用范围说明", hospital: "-", category: "合规风险", risk: "medium", status: "已通过", owner: "林悦", time: "昨天 14:30", reason: "宣传物料中适用范围表述不完整，可能造成误解。", suggestion: "补充限制条件后重新提交合规审核。" },
  { id: "RSK-20260518-021", taskId: "TSK-20260518-029", title: "客户投诉升级：监护仪频繁断连", hospital: "仁济中心医院", category: "投诉升级", risk: "high", status: "已升级", owner: "赵清", time: "05-18 16:40", reason: "投诉已连续两次未解决，科室要求区域负责人介入。", suggestion: "建立升级工单，由区域服务负责人牵头处理。" },
];

export const records = [
  { id: 1, name: "华东大学附属医院", level: "战略客户", city: "上海", owner: "陈思远", tasks: 18, risks: 3, open: 5, trend: "+12%", risk: "high", products: ["SmartPump X3", "监护系统 M8"], last: "今天 09:42" },
  { id: 2, name: "市立第二医院", level: "重点客户", city: "杭州", owner: "赵清", tasks: 12, risks: 2, open: 3, trend: "-8%", risk: "medium", products: ["VentCare V5", "AED Pro"], last: "今天 08:18" },
  { id: 3, name: "仁济中心医院", level: "重点客户", city: "苏州", owner: "陈思远", tasks: 15, risks: 1, open: 2, trend: "+5%", risk: "medium", products: ["AED Pro", "监护系统 M8"], last: "昨天 16:40" },
  { id: 4, name: "康宁医院", level: "普通客户", city: "南京", owner: "赵清", tasks: 8, risks: 0, open: 1, trend: "-15%", risk: "low", products: ["监护系统 M8"], last: "05-19 11:20" },
  { id: 5, name: "和美医院", level: "普通客户", city: "无锡", owner: "赵清", tasks: 6, risks: 0, open: 1, trend: "-4%", risk: "low", products: ["GlucoFit S2"], last: "05-18 15:00" },
];

export const sopDocs = [
  { id: "SOP-EQ-023", title: "输注泵报警异常现场处理规范", category: "设备异常", version: "v3.2", dept: "医学支持部", updated: "2026-04-18", match: 96, tags: ["输注泵", "报警", "患者安全"] },
  { id: "SOP-QA-011", title: "医疗设备投诉升级与质量调查流程", category: "投诉处理", version: "v2.6", dept: "质量管理部", updated: "2026-03-05", match: 91, tags: ["投诉升级", "批次", "质量调查"] },
  { id: "SOP-AE-004", title: "疑似不良事件识别与上报指引", category: "不良事件", version: "v4.1", dept: "合规部", updated: "2026-05-08", match: 88, tags: ["不良事件", "上报", "审核"] },
  { id: "SOP-CP-017", title: "产品宣传材料合规审核清单", category: "合规审核", version: "v1.9", dept: "合规部", updated: "2026-02-12", match: 82, tags: ["宣传物料", "合规", "审核"] },
];

export const gaps = [
  { id: "KG-20260520-003", title: "补充 AED 电极片异常升级路径", query: "AED 电极片脱落如何处理，是否需要上报？", confidence: 42, owner: "周然", status: "待补充", source: "客户问答", time: "今天 10:06" },
  { id: "KG-20260519-012", title: "更新监护仪断连排查步骤", query: "监护仪网络反复断开，排查顺序是什么？", confidence: 56, owner: "周然", status: "处理中", source: "风险任务", time: "昨天 16:52" },
  { id: "KG-20260518-008", title: "补充输注泵历史报警码说明", query: "SmartPump X3 E107 报警码含义", confidence: 61, owner: "刘晨", status: "已完成", source: "内部检索", time: "05-18 09:20" },
];

export const traces = [
  { id: "tr_8F2A91C4", scene: "创建高风险任务", user: "陈思远", route: "Supervisor → Task Agent → Risk Agent → RAG Agent → HITL", duration: "2.84s", status: "等待审核", time: "今天 09:42:18", retries: 1 },
  { id: "tr_7B3E14D9", scene: "查询个人逾期任务", user: "赵清", route: "Supervisor → Task Agent", duration: "0.68s", status: "成功", time: "今天 09:16:04", retries: 0 },
  { id: "tr_6D9C20A1", scene: "SOP 检索与建议生成", user: "陈思远", route: "Supervisor → RAG Agent", duration: "1.42s", status: "成功", time: "今天 08:53:27", retries: 0 },
  { id: "tr_5A1F88E6", scene: "字段抽取异常重试", user: "赵清", route: "Supervisor → Task Agent → Self-Reflection", duration: "3.12s", status: "重试成功", time: "昨天 17:22:12", retries: 2 },
];

export const reportList = [
  { id: 1, title: "客户服务部任务日报", period: "2026-05-20", scope: "客户服务部", generated: "今天 18:00", status: "已生成" },
  { id: 2, title: "医疗风险事项周报", period: "2026-W20", scope: "全公司", generated: "05-18 09:00", status: "已生成" },
  { id: 3, title: "知识库优化周报", period: "2026-W20", scope: "产品运营部", generated: "05-18 09:05", status: "已生成" },
];
