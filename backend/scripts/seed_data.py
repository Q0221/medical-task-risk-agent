"""种子数据常量：基础角色 / 员工 / 医院 / 产品（供 seed.py 与 seed_bulk.py 共用）。"""

from __future__ import annotations

from app.models.enums import RoleCode

ROLES: list[dict] = [
    {"code": RoleCode.CUSTOMER_SERVICE, "name": "客服", "description": "客户跟进与一线沟通"},
    {"code": RoleCode.MEDICAL_SUPPORT, "name": "医学支持", "description": "医学问题与不良事件处理"},
    {"code": RoleCode.PRODUCT_OPS, "name": "产品运营", "description": "产品反馈与运营"},
    {"code": RoleCode.QA, "name": "质控", "description": "质量控制与复核"},
    {"code": RoleCode.COMPLIANCE, "name": "合规", "description": "合规审核"},
    {"code": RoleCode.MANAGER, "name": "主管", "description": "团队主管 / 审批人"},
    {"code": RoleCode.ADMIN, "name": "系统管理员", "description": "系统管理"},
]

USERS: list[dict] = [
    {
        "employee_no": "E0001",
        "name": "管理员",
        "email": "admin@example.com",
        "department": "IT",
        "roles": [RoleCode.ADMIN],
    },
    {
        "employee_no": "E1001",
        "name": "张客服",
        "email": "zhangcs@example.com",
        "department": "客户服务部",
        "roles": [RoleCode.CUSTOMER_SERVICE],
    },
    {
        "employee_no": "E1002",
        "name": "李医学",
        "email": "limedical@example.com",
        "department": "医学事务部",
        "roles": [RoleCode.MEDICAL_SUPPORT],
    },
    {
        "employee_no": "E1003",
        "name": "王产品",
        "email": "wangpm@example.com",
        "department": "产品部",
        "roles": [RoleCode.PRODUCT_OPS],
    },
    {
        "employee_no": "E1004",
        "name": "赵质控",
        "email": "zhaoqa@example.com",
        "department": "质量管理部",
        "roles": [RoleCode.QA],
    },
    {
        "employee_no": "E1005",
        "name": "钱合规",
        "email": "qiancomp@example.com",
        "department": "合规部",
        "roles": [RoleCode.COMPLIANCE],
    },
    {
        "employee_no": "E2001",
        "name": "孙主管",
        "email": "sunmgr@example.com",
        "department": "客户服务部",
        "roles": [RoleCode.MANAGER],
    },
]

HOSPITALS: list[dict] = [
    {"code": "H001", "name": "示例三甲医院A", "level": "三甲", "region": "华北", "risk_score": 15},
    {"code": "H002", "name": "示例三甲医院B", "level": "三甲", "region": "华东", "risk_score": 35},
    {"code": "H003", "name": "示例二甲医院C", "level": "二甲", "region": "华南", "risk_score": 5},
]

PRODUCTS: list[dict] = [
    {"code": "P001", "name": "示例医疗设备 Alpha", "category": "影像设备", "business_unit": "设备事业部"},
    {"code": "P002", "name": "示例耗材 Beta", "category": "耗材", "business_unit": "耗材事业部"},
    {"code": "P003", "name": "示例软件系统 Gamma", "category": "软件", "business_unit": "软件事业部"},
]

DEPARTMENTS = [
    "客户服务部",
    "医学事务部",
    "产品部",
    "质量管理部",
    "合规部",
    "IT",
    "市场部",
    "供应链部",
]

REGIONS = ["华北", "华东", "华南", "华中", "西南", "西北", "东北"]
HOSPITAL_LEVELS = ["三甲", "三乙", "二甲", "二乙", "专科"]
PRODUCT_CATEGORIES = ["影像设备", "耗材", "软件", "体外诊断", "康复设备"]
BUSINESS_UNITS = ["设备事业部", "耗材事业部", "软件事业部", "诊断事业部"]
