# -*- coding: utf-8 -*-
"""组织库 ES 索引 mapping：领英公司画像 + 需求文档一级组织类型。"""

ORG_INDEX = "dw_org_info_lk_company"

# 文件名类别 → 规范化一级类型（对齐《组织查询》分类表）
ORG_TYPE_NORMALIZE = {
    "军工": "军工",
    "军队": "军队",
    "卡脖子高科技公司": "卡脖子高科技公司",
    "台在美团体如FAPA": "台在美团体",
    "国会下属机构": "国会下属机构",
    "国防部军方情报机构": "国防部军方情报机构",
    "基金会": "基金会",
    "多边组织": "多边组织",
    "媒体机构": "媒体机构",
    "宗教类，如基督教组织": "宗教类组织",
    "律所、咨询机构": "律所咨询机构",
    "情报外包机构": "情报外包机构",
    "政府机构": "政府机构",
    "智库": "智库",
    "涉稀土、矿产类公司": "涉稀土矿产类公司",
    "游说机构": "游说机构",
    "行业协会工作表数据": "行业协会",
    "非政府组织": "非政府组织",
    "高校": "高校",
}

MAPPING = {
    "settings": {
        "number_of_shards": 3,
        "number_of_replicas": 0,
        "refresh_interval": "30s",
        "analysis": {
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase", "asciifolding"],
                }
            }
        },
    },
    "mappings": {
        "dynamic": False,
        "properties": {
            "org_id": {"type": "keyword"},
            "org_linkedin_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "normalizer": "lowercase_normalizer",
                        "ignore_above": 256,
                    }
                },
            },
            "name_raw": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "website": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "linkedin_url": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "facebook_url": {"type": "keyword"},
            "twitter_url": {"type": "keyword"},
            "industry": {
                "type": "text",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "normalizer": "lowercase_normalizer",
                        "ignore_above": 256,
                    }
                },
            },
            "size": {"type": "keyword"},
            "founded": {"type": "keyword"},
            "description": {"type": "text"},
            "org_types": {"type": "keyword"},
            "org_type_primary": {"type": "keyword"},
            "org_type_l2": {"type": "keyword"},
            "biz_tags": {"type": "keyword"},
            "tag_method": {"type": "keyword"},
            "tag_time": {"type": "date"},
            "location_country": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
            },
            "location_region": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
            },
            "location_locality": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
            },
            "location_metro": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "location_continent": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
            },
            "location_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "location_postal_code": {"type": "keyword"},
            "location_street_address": {"type": "keyword", "ignore_above": 512},
            "location_address_line_2": {"type": "keyword", "ignore_above": 256},
            "location_geo": {"type": "geo_point"},
            # 保留原始领英字段，便于与人员库 job_company_* 对齐
            "job_company_id": {"type": "keyword"},
            "job_company_linkedin_id": {"type": "keyword"},
            "job_company_name": {
                "type": "text",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "normalizer": "lowercase_normalizer",
                        "ignore_above": 256,
                    }
                },
            },
            "source_categories": {"type": "keyword"},
            "source_files": {"type": "keyword"},
            "ingest_time": {"type": "date"},
        },
    },
}
