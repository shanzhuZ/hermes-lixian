# -*- coding: utf-8 -*-
"""
组织规则打标：根据一级类型 + 名称/行业/简介关键词，生成二级类型与业务标签。

不调用大模型；入库时在 transform / merge 后调用。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from org_taxonomy import BIZ_TAGS, ORG_TYPE_L2_BY_L1

TAG_METHOD = "rule_v1"

# 各一级类型下：关键词（小写）→ 二级类型；按顺序优先匹配
_L2_RULES: Dict[str, List[Tuple[List[str], str]]] = {
    "多边组织": [
        (["united nations", " un ", "unesco", "who ", "world bank", "imf", "wto"], "国际组织"),
        (["g7", "g20", "asean", "nato", "aukus", "quad", "brics"], "多边合作机制"),
        (["alliance", "coalition", "league"], "国际联盟"),
    ],
    "情报外包机构": [
        (["defense intelligence", "national security", "intel contractor"], "国防情报服务"),
        (["intelligence analysis", "osint", "sigint", "all-source"], "情报分析"),
        (["intelligence consult", "strategic intelligence"], "情报咨询"),
        (["booz allen", "caci", "leidos", "mantech", "palantir"], "战略情报承包商"),
    ],
    "非政府组织": [
        (["human rights", "amnesty", "hrw", "人权"], "人权组织"),
        (["foreign policy", "international affairs", "world affairs"], "国际事务组织"),
        (["ngo", "nonprofit", "non-profit", "civil society"], "NGO"),
        (["community", "social service", "慈善", "公益"], "社会组织"),
    ],
    "高校": [
        (["military academy", "naval academy", "air force academy", "war college"], "军事院校"),
        (["institute of technology", "polytechnic", "medical school", "law school", "business school"], "专业学院"),
        (["research university", "r1 ", "graduate school"], "研究型大学"),
        (["university", "college", "大学", "学院"], "综合大学"),
    ],
    "国防部军方情报机构": [
        (["dia", "defense intelligence agency"], "国防情报"),
        (["military intelligence", "army intelligence", "naval intelligence"], "军事情报"),
        (["dod", "department of defense", "pentagon"], "军方情报部门"),
    ],
    "国会下属机构": [
        (["committee", "subcommittee", "委员会"], "国会委员会"),
        (["gao", "congressional research", "crs ", "cbo "], "研究机构"),
        (["investigation", "oversight", "inspector"], "调查机构"),
        (["advisory", "commission"], "咨询机构"),
    ],
    "基金会": [
        (["political", "partisan", "pac "], "政治基金会"),
        (["public policy", "policy foundation"], "公共政策基金会"),
        (["research foundation", "think"], "研究基金会"),
        (["charit", "philanthrop", "慈善", "捐赠"], "慈善基金会"),
    ],
    "军队": [
        (["marine corps", "marines", "海军陆战"], "海军陆战队"),
        (["special forces", "special operations", "green beret", "navy seal", "delta"], "特种部队"),
        (["air force", "usaf", "空军"], "空军"),
        (["navy", "naval", "usn", "海军"], "海军"),
        (["army", "usa ", "陆军"], "陆军"),
    ],
    "军工": [
        (["aerospace", "space system", "lockheed", "boeing", "northrop", "raytheon"], "航空航天企业"),
        (["weapon", "missile", "ammunition", "ordnance", "firearm"], "武器装备企业"),
        (["defense", "defence", "军工", "国防承包"], "国防军工企业"),
    ],
    "卡脖子高科技公司": [
        (["semiconductor", "chip", "foundry", "tsmc", "nvidia", "intel", "amd", "asml", "芯片", "半导体"], "芯片"),
        (["artificial intelligence", "machine learning", " deep learning", " llm", "ai "], "AI"),
        (["telecom", "5g", "6g", "huawei", "qualcomm", "ericsson", "nokia", "通信"], "通信"),
        (["operating system", "windows", "android", "ios ", "linux kernel"], "操作系统"),
        (["advanced manufacturing", "cnc", "lithography", "euv"], "先进制造"),
        (["semiconductor", "wafer", "fab "], "半导体"),
    ],
    "律所咨询机构": [
        (["law firm", "llp", "attorney", "legal", "律师"], "律所"),
        (["mckinsey", "bain", "bcg", "strategy consult", "战略咨询"], "战略咨询"),
        (["public affairs", "government relation"], "公共事务咨询"),
        (["risk consult", "compliance", "due diligence"], "风险咨询"),
    ],
    "媒体机构": [
        (["news agency", "wire service", "reuters", "associated press", "ap ", "通讯社"], "通讯社"),
        (["television", "tv network", "broadcast", "cnn", "fox news", "电视台"], "电视台"),
        (["newspaper", "daily ", "times", "post", "journal", "报纸"], "报纸"),
        (["magazine", "weekly", "杂志"], "杂志"),
        (["online media", "digital media", "website", "podcast", "网络"], "网络媒体"),
    ],
    "涉稀土矿产类公司": [
        (["rare earth", "稀土"], "稀土"),
        (["critical mineral", "critical material", "关键矿产"], "关键矿产"),
        (["mining", "mine ", "mineral", "矿业", "矿产"], "矿业"),
        (["resource develop", "exploration", "资源开发"], "资源开发"),
        (["supply chain", "refining", "processing"], "供应链企业"),
    ],
    "台在美团体": [
        (["fapa", "formosan association"], "FAPA类涉台协会"),
        (["taiwanese american", "taiwan association", "formosan"], "涉台协会"),
        (["overseas chinese", "侨", "diaspora"], "侨团"),
    ],
    "行业协会": [
        (["chamber of commerce", "商会"], "商会"),
        (["industry alliance", "trade alliance", "consortium", "联盟"], "产业联盟"),
        (["professional association", "bar association", "学会"], "专业协会"),
        (["trade association", "industry association", "协会"], "行业协会"),
    ],
    "游说机构": [
        (["lobby", "lobbying", "registered lobbyist", "游说"], "游说公司"),
        (["public affairs", "government affairs"], "公共事务机构"),
        (["political consult", "campaign consult"], "政治咨询机构"),
    ],
    "政府机构": [
        (["federal", "department of", "u.s. ", "us ", "white house", "联邦"], "联邦政府"),
        (["state of ", "state government", "governor", "州政府"], "州政府"),
        (["city of ", "county of ", "municipal", "mayor", "地方"], "地方政府"),
        (["agency", "bureau", "administration", "commission", "office of"], "政府部门及直属机构"),
    ],
    "智库": [
        (["national security", "defense", "military", "战略", "安全"], "安全智库"),
        (["foreign policy", "international relation", "外交", "国际"], "国际关系智库"),
        (["economic", "trade", "finance", "经济", "经贸"], "经济智库"),
        (["strategic", "geopolitic", "战略"], "战略智库"),
    ],
    "宗教类组织": [
        (["christian", "church", "baptist", "catholic", "evangelical", "基督", "教会"], "基督教组织"),
        (["mission", "evangelism", "传教"], "传教组织"),
        (["religious foundation", "faith foundation"], "宗教基金会"),
        (["religious association", "interfaith", "宗教协会"], "宗教协会"),
    ],
}

# 业务标签：关键词命中即打上（可多选）
_BIZ_RULES: List[Tuple[str, List[str]]] = [
    (
        "涉台",
        [
            "taiwan", "taipei", "formosa", "roc ", "kuomintang", "dpp",
            "两岸", "台湾", "台北", "台海", "cross-strait", "cross strait",
        ],
    ),
    (
        "涉港",
        ["hong kong", "hongkong", "hk ", "香港", "一国两制", "umbrella movement"],
    ),
    (
        "涉疆",
        ["xinjiang", "uyghur", "uighur", "新疆", "维吾尔"],
    ),
    (
        "涉藏",
        ["tibet", "tibetan", "dalai", "西藏", "藏人"],
    ),
    (
        "南海议题",
        [
            "south china sea", "scs ", "spratly", "paracel",
            "南海", "西沙", "南沙", "九段线", "nine-dash",
        ],
    ),
    (
        "半导体/科技竞争",
        [
            "semiconductor", "chip war", "export control", "entity list",
            "chips act", "先进制程", "芯片", "半导体", "technology competition",
            "tech rivalry", "decoupling",
        ],
    ),
    (
        "关键矿产",
        [
            "rare earth", "critical mineral", "critical material",
            "稀土", "关键矿产", "lithium", "cobalt", "graphite",
        ],
    ),
    (
        "经贸议题",
        [
            "trade war", "tariff", "wto", "supply chain", "belt and road",
            "贸易战", "关税", "一带一路", "经贸", "sanction", "embargo",
        ],
    ),
    (
        "人权议题",
        [
            "human rights", "forced labor", "genocide", "democracy",
            "人权", "强迫劳动", "民主", "civil liberty",
        ],
    ),
    (
        "军事安全议题",
        [
            "military", "defense", "defence", "security threat", "indo-pacific",
            "军事", "国防", "安全威胁", "印太", "deterrence", "arms race",
        ],
    ),
    (
        "涉华",
        [
            "china", "chinese", "prc", "beijing", "ccp", "communist party of china",
            "中国", "中共", "北京", "对华", "sino-", "china-related", "china related",
        ],
    ),
    (
        "涉华-政治",
        ["ccp", "communist party", "political warfare", "united front", "统战", "中共"],
    ),
    (
        "涉华-经济",
        ["china trade", "china economy", "belt and road", "对华经济", "中美贸易"],
    ),
    (
        "涉华-科技",
        [
            "china tech", "china semiconductor", "china ai", "huawei",
            "对华科技", "科技脱钩", "china chip",
        ],
    ),
    (
        "涉华-军事",
        ["pla", "people's liberation army", "china military", "解放军", "对华军事"],
    ),
    (
        "涉华-外交",
        ["china foreign policy", "china diplomacy", "对华外交", "中美关系"],
    ),
    (
        "涉华-人权",
        ["china human rights", "xinjiang", "tibet", "hong kong", "对华人权"],
    ),
    (
        "涉华-台湾",
        ["taiwan", "cross-strait", "cross strait", "两岸", "台海", "one china"],
    ),
]

# 允许的业务标签集合（防写出口径外标签）
_ALLOWED_BIZ = set(BIZ_TAGS)


def _text_blob(doc: Dict[str, Any]) -> str:
    parts = [
        doc.get("name") or "",
        doc.get("industry") or "",
        (doc.get("description") or "")[:4000],
        " ".join(doc.get("org_types") or []),
        doc.get("org_type_primary") or "",
    ]
    return " ".join(parts).lower()


def _default_l2(l1: str) -> str:
    allowed = ORG_TYPE_L2_BY_L1.get(l1) or []
    for cand in allowed:
        if cand.startswith("其他"):
            return cand
    return allowed[-1] if allowed else "其他"


def infer_org_type_l2(l1: str, text: str) -> str:
    rules = _L2_RULES.get(l1) or []
    for kws, l2 in rules:
        for kw in kws:
            if kw in text:
                # 校验落在词表内
                allowed = ORG_TYPE_L2_BY_L1.get(l1) or []
                if not allowed or l2 in allowed:
                    return l2
                break
    return _default_l2(l1)


def infer_biz_tags(text: str, l1: Optional[str] = None) -> List[str]:
    tags: List[str] = []
    seen = set()
    for tag, kws in _BIZ_RULES:
        if tag not in _ALLOWED_BIZ:
            continue
        hit = False
        for kw in kws:
            if kw in text:
                hit = True
                break
        if hit and tag not in seen:
            seen.add(tag)
            tags.append(tag)

    # 一级类型本身强相关议题：补默认弱标签（仅当正文无任何业务标签时）
    if not tags and l1:
        defaults = {
            "台在美团体": ["涉台", "涉华-台湾"],
            "涉稀土矿产类公司": ["关键矿产"],
            "卡脖子高科技公司": ["半导体/科技竞争"],
            "国防部军方情报机构": ["军事安全议题"],
            "军队": ["军事安全议题"],
            "军工": ["军事安全议题"],
        }
        for t in defaults.get(l1, []):
            if t in _ALLOWED_BIZ and t not in seen:
                seen.add(t)
                tags.append(t)
    return tags


def tag_org_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """就地写入 org_type_l2 / biz_tags / tag_*，并返回 doc。"""
    l1_list: Sequence[str] = doc.get("org_types") or []
    l1 = (doc.get("org_type_primary") or (l1_list[0] if l1_list else "") or "").strip()
    text = _text_blob(doc)

    l2 = infer_org_type_l2(l1, text) if l1 else "其他"
    # 多一级类型时：取首个 L1 的 L2；biz_tags 用全文一次判定
    biz = infer_biz_tags(text, l1=l1)

    doc["org_type_l2"] = l2
    doc["biz_tags"] = biz
    doc["tag_method"] = TAG_METHOD
    doc["tag_time"] = datetime.now(timezone.utc).isoformat()
    return doc
