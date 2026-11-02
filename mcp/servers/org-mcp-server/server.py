#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组织信息 MCP Server — 离线组织库检索

工具：
  list_org_types       一级/二级类型与业务标签及数量
  lookup_org_by_name   按名称查组织（含别名消歧）
  lookup_org_by_id     按 org_id / linkedin_id 查组织
  search_orgs          结构化检索（L1/L2/biz_tags 展开/分页/置信度）
  org_cluster_health   集群与索引健康
"""

import asyncio
import json

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent

from org_client import (
    ORG_INDEX_NAME,
    cluster_health,
    list_org_types,
    lookup_org_by_id,
    lookup_org_by_name,
    search_orgs,
)

server = Server("org-mcp")

_SIZE_PROP = {
    "type": "integer",
    "description": "返回条数（最大 20）",
    "default": 20,
    "minimum": 1,
    "maximum": 20,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_org_types",
            description=(
                "列出组织库一级类型、二级类型 top、业务标签 top、tag_method 分布及文档数。"
                "biz_tags 以 llm_deepseek 精标为主；查「涉华」会展开 涉华-*。"
                f"\n索引: {ORG_INDEX_NAME}"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="lookup_org_by_name",
            description=(
                "按组织名称查询（短语+分词 AND；短名别名如 FAPA/Brookings 自动展开）。"
                "可附加国家、组织类型收窄。返回含 org_type_l2 / biz_tags / "
                "tag_confidence / evidence_brief；得分接近时带 disambiguation_hint。"
                f"\n索引: {ORG_INDEX_NAME}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "组织名称，如 Brookings Institution / FAPA",
                    },
                    "location_country": {
                        "type": "string",
                        "description": "国家，如 united states",
                    },
                    "org_type": {
                        "type": "string",
                        "description": "一级类型，如 智库 / 高校 / think tank",
                    },
                    "size": _SIZE_PROP,
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="lookup_org_by_id",
            description=(
                "按 org_id、job_company_id 或 linkedin 数字 id 精确查组织。"
                f"\n索引: {ORG_INDEX_NAME}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "org_id": {
                        "type": "string",
                        "description": "组织 ID（领英 company id 或文档 _id）",
                    },
                    "size": _SIZE_PROP,
                },
                "required": ["org_id"],
            },
        ),
        Tool(
            name="search_orgs",
            description=(
                "结构化组织检索。支持一级类型 org_type、二级类型 org_type_l2、"
                "业务标签 biz_tag（llm 精标；涉华自动展开 涉华-*）、国家/地区、"
                "名称/行业、topic、成立年份、min_tag_confidence、has_biz_tags，"
                "以及 include_ids(≤500)/exclude_ids 二次筛选与 search_after 翻页。"
                f"\n索引: {ORG_INDEX_NAME}"
                "\n注意：过宽时 is_sample=true；翻页用 next_search_after。"
                "\n组织—人员关联请再用 identity-mcp 的 search_by_company / search_persons。"
                "\n组织—组织关系边、事件库 V1 未入库。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "org_type": {
                        "type": "string",
                        "description": "一级类型：智库/高校/军工/非政府组织/台在美团体 等",
                    },
                    "org_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多个一级类型（OR）",
                    },
                    "org_type_l2": {
                        "type": "string",
                        "description": "二级类型，如 安全智库 / 律所 / 芯片 / NGO",
                    },
                    "org_type_l2s": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多个二级类型（OR）",
                    },
                    "location_country": {
                        "type": "string",
                        "description": "总部/所在国家，如 united states",
                    },
                    "location_region": {
                        "type": "string",
                        "description": "州/省，如 california / district of columbia",
                    },
                    "name_keyword": {
                        "type": "string",
                        "description": "名称关键词",
                    },
                    "industry_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "行业关键词，如 think tanks / defense / semiconductors",
                    },
                    "description_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "简介/名称关键词（自定义弱匹配）",
                    },
                    "biz_tag": {
                        "type": "string",
                        "description": (
                            "业务标签强过滤（推荐）：涉华/涉台/涉港/涉疆/涉藏/"
                            "南海议题/半导体/科技竞争/关键矿产/经贸议题/人权议题/"
                            "军事安全议题，或 涉华-政治/经济/科技/军事/外交/人权/台湾。"
                            "传「涉华」时自动 OR 命中 涉华-*"
                        ),
                    },
                    "biz_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多个业务标签（AND；各自可展开）",
                    },
                    "topic": {
                        "type": "string",
                        "description": (
                            "议题别名，映射到 biz_tags："
                            "涉华/china_related、涉台、涉港、半导体、科技竞争 等；"
                            "默认只打标签字段，不扫全文"
                        ),
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多议题（AND）",
                    },
                    "topic_fallback_text": {
                        "type": "boolean",
                        "description": "true 时 topic 额外弱匹配 description/name（噪声更大）",
                        "default": False,
                    },
                    "exclude_org_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除的一级类型",
                    },
                    "include_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "仅在这些 org_id 中筛选（二次查询，≤500）",
                    },
                    "exclude_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除这些 org_id",
                    },
                    "founded_from": {
                        "type": "string",
                        "description": "成立年份下界，如 2000",
                    },
                    "founded_to": {
                        "type": "string",
                        "description": "成立年份上界，如 2020",
                    },
                    "min_tag_confidence": {
                        "type": "number",
                        "description": "最低标签置信度 0~1（llm 精标字段 tag_confidence）",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "has_biz_tags": {
                        "type": "boolean",
                        "description": "true=仅有业务标签的组织；false=仅无标签",
                    },
                    "search_after": {
                        "type": "array",
                        "description": (
                            "翻页游标：传入上一页返回的 next_search_after；"
                            "同条件继续拉下一批"
                        ),
                    },
                    "size": _SIZE_PROP,
                },
            },
        ),
        Tool(
            name="org_cluster_health",
            description="检查组织库 ES 集群与索引文档数",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments or {})
        text = json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        text = json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    return [TextContent(type="text", text=text)]


async def _dispatch(name: str, args: dict) -> dict:
    size = args.get("size", 20)

    if name == "list_org_types":
        return list_org_types()
    if name == "lookup_org_by_name":
        return lookup_org_by_name(
            args["name"],
            location_country=args.get("location_country"),
            org_type=args.get("org_type"),
            size=size,
        )
    if name == "lookup_org_by_id":
        return lookup_org_by_id(args["org_id"], size=size)
    if name == "search_orgs":
        return search_orgs(
            org_type=args.get("org_type"),
            org_types=args.get("org_types"),
            org_type_l2=args.get("org_type_l2"),
            org_type_l2s=args.get("org_type_l2s"),
            location_country=args.get("location_country"),
            location_region=args.get("location_region"),
            name_keyword=args.get("name_keyword"),
            industry_keywords=args.get("industry_keywords"),
            description_keywords=args.get("description_keywords"),
            biz_tag=args.get("biz_tag"),
            biz_tags=args.get("biz_tags"),
            topic=args.get("topic"),
            topics=args.get("topics"),
            topic_fallback_text=bool(args.get("topic_fallback_text") or False),
            exclude_org_types=args.get("exclude_org_types"),
            include_ids=args.get("include_ids"),
            exclude_ids=args.get("exclude_ids"),
            founded_from=args.get("founded_from"),
            founded_to=args.get("founded_to"),
            min_tag_confidence=args.get("min_tag_confidence"),
            has_biz_tags=args.get("has_biz_tags"),
            search_after=args.get("search_after"),
            size=size,
        )
    if name == "org_cluster_health":
        return cluster_health()
    raise ValueError(f"未知工具: {name}")


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="org-mcp",
                server_version="1.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
