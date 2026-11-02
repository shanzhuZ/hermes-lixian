#!/usr/bin/env python3
"""
身份信息 MCP Server — 全球领英身份库专用检索

工具列表：
  lookup_by_linkedin   领英 URL / username / id 精确查人
  lookup_by_work_email 工作邮箱反查
  lookup_by_phone      手机号反查
  lookup_by_name       姓名 + 国家/公司/职位
  search_by_company    按公司查人
  search_by_profile    按行业/地理/技能/兴趣组合查人
  search_persons       结构化检索（涉华/经历/二次筛选）
  get_by_unique_id     按 unique_id 取详情
"""

import asyncio
import json

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent

from identity_client import (
    IDENTITY_INDEX,
    cluster_health,
    get_by_unique_id,
    lookup_by_linkedin,
    lookup_by_name,
    lookup_by_phone,
    lookup_by_work_email,
    search_by_company,
    search_by_profile,
    search_persons,
)

server = Server("identity-mcp")

_SIZE_PROP = {
    "type": "integer",
    "description": "返回条数（最大 50）",
    "default": 20,
    "minimum": 1,
    "maximum": 50,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="lookup_by_linkedin",
            description=(
                "通过领英 URL、username 或 linkedin_id 精确查人。"
                f"\n索引: {IDENTITY_INDEX}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "linkedin_input": {
                        "type": "string",
                        "description": "领英链接、username 或数字 id，如 linkedin.com/in/sgolchha",
                    },
                    "size": _SIZE_PROP,
                },
                "required": ["linkedin_input"],
            },
        ),
        Tool(
            name="lookup_by_work_email",
            description=f"通过工作邮箱或个人邮箱反查身份。索引: {IDENTITY_INDEX}",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "邮箱地址"},
                    "size": _SIZE_PROP,
                },
                "required": ["email"],
            },
        ),
        Tool(
            name="lookup_by_phone",
            description=f"通过手机号反查身份。索引: {IDENTITY_INDEX}",
            inputSchema={
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "手机号（自动去除空格和符号）"},
                    "size": _SIZE_PROP,
                },
                "required": ["phone"],
            },
        ),
        Tool(
            name="lookup_by_name",
            description=(
                "按姓名查人，必须同时提供 country、company、job_title 中至少一项。"
                f"\n索引: {IDENTITY_INDEX}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "姓名（支持中英文）"},
                    "country": {"type": "string", "description": "国家，如 nepal、united states"},
                    "company": {"type": "string", "description": "当前公司名称"},
                    "job_title": {"type": "string", "description": "职位名称"},
                    "size": _SIZE_PROP,
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="search_by_company",
            description=(
                "按公司名称查人，可限定国家、职位、职级。"
                f"\n索引: {IDENTITY_INDEX}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "公司名称"},
                    "country": {"type": "string", "description": "国家过滤"},
                    "job_title": {"type": "string", "description": "职位过滤"},
                    "job_title_level": {
                        "type": "string",
                        "description": "职级，如 director、owner",
                    },
                    "current_only": {
                        "type": "boolean",
                        "description": "true=仅当前主职公司，false=含历史经历",
                        "default": True,
                    },
                    "size": _SIZE_PROP,
                },
                "required": ["company_name"],
            },
        ),
        Tool(
            name="search_by_profile",
            description=(
                "按行业、地理位置、技能、兴趣等画像条件组合查人。"
                "至少提供 2 个条件；命中超过 10000 条时拒绝返回。"
                f"\n索引: {IDENTITY_INDEX}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "industry": {"type": "string", "description": "行业"},
                    "location_country": {"type": "string", "description": "国家"},
                    "location_region": {"type": "string", "description": "省/州"},
                    "location_locality": {"type": "string", "description": "城市"},
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "技能列表",
                    },
                    "interests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "兴趣列表",
                    },
                    "job_title": {"type": "string", "description": "职位"},
                    "min_years_experience": {
                        "type": "integer",
                        "description": "最低工作年限",
                    },
                    "size": _SIZE_PROP,
                },
            },
        ),
        Tool(
            name="search_persons",
            description=(
                "结构化人员检索（V1.1）。支持业务标签推导（涉华/涉台/涉港，仅查询展开不写库）、"
                "在某地工作/求学、现居国家、公司/学校关键词、行业与职位关键词、"
                "exclude_edu_country / exclude_work_country / exclude_retired、"
                "include_ids/exclude_ids 二次筛选、condition_logic=and|or、"
                "search_after 分页攒池。"
                f"\n索引: {IDENTITY_INDEX}"
                "\n返回含 education_brief/experience_brief/evidence_flags；已去掉 skills 等大字段。"
                "\nsize 最大 20；include_ids 最多 500。"
                "\n分页：若 has_more=true，把 next_search_after 原样传入下一轮 search_after。"
                "\n行业词默认只匹配当前 industry 字段；location_country 默认只匹配现居。"
                "\n过宽时 is_sample=true；include_ids 时以 returned/candidate_pool_size 为准。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "biz_tag": {
                        "type": "string",
                        "description": "china_related/涉华 | taiwan_related/涉台 | hongkong_related/涉港",
                    },
                    "work_country": {
                        "type": "string",
                        "description": "工作经历国家，如 china / hong kong / taiwan / nepal",
                    },
                    "edu_country": {
                        "type": "string",
                        "description": "教育经历国家，如 china",
                    },
                    "location_country": {
                        "type": "string",
                        "description": "现居国家（默认仅 location_country 字段）",
                    },
                    "company_keyword": {
                        "type": "string",
                        "description": "公司名关键词（当前或历史；strict 时仅当前主职公司）",
                    },
                    "school_keyword": {
                        "type": "string",
                        "description": "学校名关键词",
                    },
                    "industry_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "行业关键词（默认仅当前 industry 字段；由模型按用户口语自行展开）",
                    },
                    "title_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "职位关键词（由模型生成，如 senator / ceo）",
                    },
                    "exclude_industry_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除的行业关键词",
                    },
                    "exclude_title_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除的职位关键词",
                    },
                    "exclude_edu_country": {
                        "type": "string",
                        "description": "硬排除该国教育经历（如 china），用于「涉华但非在华教育」",
                    },
                    "exclude_work_country": {
                        "type": "string",
                        "description": "硬排除该国工作经历（如 china），用于「有在华教育但无在华工作」等",
                    },
                    "exclude_retired": {
                        "type": "boolean",
                        "description": "true=排除职位含 retired 的人。默认 false",
                        "default": False,
                    },
                    "include_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "仅在这些 unique_id 中筛选（二次查询，最多 500）",
                    },
                    "exclude_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除这些 unique_id（最多 500）",
                    },
                    "strict": {
                        "type": "boolean",
                        "description": (
                            "true=硬匹配：关闭公司/学校名弱信号；行业/职位仅当前主职；"
                            "location 不并入 countries[]；仅 biz_tag 会被拒绝。默认 false"
                        ),
                        "default": False,
                    },
                    "include_countries_history": {
                        "type": "boolean",
                        "description": (
                            "true=location_country 同时匹配历史 countries[]；"
                            "strict=true 时忽略本参数。默认 false"
                        ),
                        "default": False,
                    },
                    "include_experience_industry": {
                        "type": "boolean",
                        "description": (
                            "true=行业词扩展到经历段 industry（易跨段误配）。默认 false"
                        ),
                        "default": False,
                    },
                    "condition_logic": {
                        "type": "string",
                        "enum": ["and", "or"],
                        "description": (
                            "and（默认）=业务/经历/地域/机构/行业/职位条件全部成立；"
                            "or=业务标签/工作教育/公司学校/行业职位满足任一；"
                            "location_country 与 include_ids 始终 AND；exclude_* 始终排除。"
                        ),
                        "default": "and",
                    },
                    "search_after": {
                        "type": "array",
                        "description": (
                            "分页游标：上一页返回的 next_search_after 原样传入；"
                            "用于翻页合并 unique_id（每页仍最多 20 条）"
                        ),
                    },
                    "size": {
                        "type": "integer",
                        "description": "返回条数（search_persons 最大 20）",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
            },
        ),
        Tool(
            name="get_by_unique_id",
            description=f"按 unique_id 获取完整档案。索引: {IDENTITY_INDEX}",
            inputSchema={
                "type": "object",
                "properties": {
                    "unique_id": {"type": "string", "description": "人物唯一 ID"},
                    "include_detail": {
                        "type": "boolean",
                        "description": "是否返回完整字段（含 experience/education）",
                        "default": True,
                    },
                },
                "required": ["unique_id"],
            },
        ),
        Tool(
            name="identity_cluster_health",
            description="检查身份库 ES 集群健康状态",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        text = json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        text = json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    return [TextContent(type="text", text=text)]


async def _dispatch(name: str, args: dict) -> dict:
    size = args.get("size", 20)

    if name == "lookup_by_linkedin":
        return lookup_by_linkedin(args["linkedin_input"], size=size)
    if name == "lookup_by_work_email":
        return lookup_by_work_email(args["email"], size=size)
    if name == "lookup_by_phone":
        return lookup_by_phone(args["phone"], size=size)
    if name == "lookup_by_name":
        return lookup_by_name(
            args["name"],
            country=args.get("country"),
            company=args.get("company"),
            job_title=args.get("job_title"),
            size=size,
        )
    if name == "search_by_company":
        return search_by_company(
            args["company_name"],
            country=args.get("country"),
            job_title=args.get("job_title"),
            job_title_level=args.get("job_title_level"),
            current_only=args.get("current_only", True),
            size=size,
        )
    if name == "search_by_profile":
        return search_by_profile(
            industry=args.get("industry"),
            location_country=args.get("location_country"),
            location_region=args.get("location_region"),
            location_locality=args.get("location_locality"),
            skills=args.get("skills"),
            interests=args.get("interests"),
            job_title=args.get("job_title"),
            min_years_experience=args.get("min_years_experience"),
            size=size,
        )
    if name == "search_persons":
        return search_persons(
            biz_tag=args.get("biz_tag"),
            work_country=args.get("work_country"),
            edu_country=args.get("edu_country"),
            location_country=args.get("location_country"),
            company_keyword=args.get("company_keyword"),
            school_keyword=args.get("school_keyword"),
            industry_keywords=args.get("industry_keywords"),
            title_keywords=args.get("title_keywords"),
            exclude_industry_keywords=args.get("exclude_industry_keywords"),
            exclude_title_keywords=args.get("exclude_title_keywords"),
            exclude_edu_country=args.get("exclude_edu_country"),
            exclude_work_country=args.get("exclude_work_country"),
            exclude_retired=bool(args.get("exclude_retired", False)),
            include_ids=args.get("include_ids"),
            exclude_ids=args.get("exclude_ids"),
            strict=bool(args.get("strict", False)),
            include_countries_history=bool(
                args.get("include_countries_history", False)
            ),
            include_experience_industry=bool(
                args.get("include_experience_industry", False)
            ),
            condition_logic=str(args.get("condition_logic") or "and"),
            search_after=args.get("search_after"),
            size=size,
        )
    if name == "get_by_unique_id":
        return get_by_unique_id(
            args["unique_id"],
            include_detail=args.get("include_detail", True),
        )
    if name == "identity_cluster_health":
        return cluster_health()
    raise ValueError(f"未知工具: {name}")


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="identity-mcp",
                server_version="1.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
