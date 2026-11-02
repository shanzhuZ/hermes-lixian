# -*- coding: utf-8 -*-
"""四 Skill 共用写库门面（仿 xa task_store，但不分业务）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import db

logger = logging.getLogger(__name__)


BILL_SKILL = "bill-impact-analysis"
ROUTER_SKILL = "research-router"

# 四大业务 Skill（分类入库用）
BUSINESS_SKILLS = (
    "bill-impact-analysis",
    "org-portrait",
    "account-portrait",
    "event-spread-impact",
)

# 业务四类 + 最外层路由（路由态可 set_skill；计划仅业务 Skill）
RESEARCH_SKILLS = BUSINESS_SKILLS + (ROUTER_SKILL,)

# 法案内置六步：仅 use_default=true 显式回退；主路径由模型按 Skill 传入 steps
BILL_DEFAULT_PLAN = [
    {"phase_code": "identify", "phase_name": "冻结法案身份与消歧", "seq": 1},
    {"phase_code": "official", "phase_name": "官方内容与立法状态", "seq": 2},
    {"phase_code": "social", "phase_name": "社交发言采样与过滤", "seq": 3},
    {"phase_code": "china_view", "phase_name": "涉华观点（若适用）", "seq": 4},
    {"phase_code": "impact", "phase_name": "影响研判", "seq": 5},
    {"phase_code": "writing", "phase_name": "撰写中文终稿", "seq": 6},
]


def is_bill_skill(skill_name: str) -> bool:
    s = (skill_name or "").strip().lower()
    return s == BILL_SKILL or s in ("bill", "bill-social-stance")


def normalize_business_skill(skill_name: str) -> Optional[str]:
    """别名 → 四大业务 Skill 规范名；无法识别返回 None。"""
    s = (skill_name or "").strip().lower()
    if not s:
        return None
    if s in BUSINESS_SKILLS:
        return s
    aliases = {
        "bill": BILL_SKILL,
        "bill-social-stance": BILL_SKILL,
        "org": "org-portrait",
        "account": "account-portrait",
        "event": "event-spread-impact",
    }
    return aliases.get(s)


def is_business_skill(skill_name: str) -> bool:
    return normalize_business_skill(skill_name) is not None


def is_router_skill(skill_name: str) -> bool:
    s = (skill_name or "").strip().lower()
    return s in (ROUTER_SKILL, "auto", "router")


def is_research_skill(skill_name: str) -> bool:
    s = (skill_name or "").strip().lower()
    if s in RESEARCH_SKILLS:
        return True
    return is_business_skill(s) or is_router_skill(s)


def set_task_skill(task_id: str, skill_name: str) -> Dict[str, Any]:
    """模型选定业务 Skill 后写回 xw_chat_task.skill_name。"""
    if not task_id:
        return {"ok": False, "error": "task_id_empty"}
    canon = normalize_business_skill(skill_name)
    if not canon:
        return {
            "ok": False,
            "error": "invalid_skill",
            "hint": "skill_name 必须是 bill-impact-analysis / org-portrait / account-portrait / event-spread-impact 之一",
            "got": skill_name,
        }
    row = get_task(task_id)
    if not row:
        return {"ok": False, "error": "task_not_found"}
    db.execute(
        """
        UPDATE xw_chat_task
        SET skill_name=%s, updated_at=NOW()
        WHERE task_id=%s
        """,
        (canon, task_id),
    )
    logger.info("xw-ingest set_skill task=%s skill=%s", task_id, canon)
    return {
        "ok": True,
        "task_id": task_id,
        "skill_name": canon,
        "previous_skill": row.get("skill_name"),
    }


def get_active_task_by_hermes_session(hermes_session_id: str) -> Optional[Dict[str, Any]]:
    """Hermes session_id → 业务会话下最新 pending/running 任务。"""
    if not hermes_session_id:
        return None
    return db.fetch_one(
        """
        SELECT t.task_id, t.session_id, t.skill_name, t.status, t.answer_markdown, t.current_phase
        FROM xw_chat_session s
        INNER JOIN xw_chat_task t ON t.session_id = s.session_id
        WHERE s.hermes_session_id = %s
          AND t.status IN ('pending', 'running')
        ORDER BY t.created_at DESC
        LIMIT 1
        """,
        (hermes_session_id,),
    )


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    if not task_id:
        return None
    return db.fetch_one(
        """
        SELECT task_id, session_id, skill_name, status, answer_markdown, error_message, current_phase
        FROM xw_chat_task WHERE task_id=%s LIMIT 1
        """,
        (task_id,),
    )


def set_current_phase(task_id: str, phase_code: str) -> None:
    if not task_id:
        return
    db.execute(
        """
        UPDATE xw_chat_task
        SET current_phase=%s, updated_at=NOW()
        WHERE task_id=%s
        """,
        ((phase_code or "")[:64] or None, task_id),
    )


def list_phases(task_id: str) -> List[Dict[str, Any]]:
    if not task_id:
        return []
    return db.fetch_all(
        """
        SELECT id, task_id, phase_code, phase_name, seq, status, message,
               started_at, finished_at, created_at, updated_at
        FROM xw_task_phase
        WHERE task_id=%s
        ORDER BY seq ASC, id ASC
        """,
        (task_id,),
    )


def submit_plan(task_id: str, steps: List[Dict[str, Any]], replace: bool = False) -> Dict[str, Any]:
    """
    规划入库：写入多行 pending；第 0 步 planning 立刻 done；激活第一步 running。
    steps 由调用方传入（法案主路径为模型自主规划）；不得在此静默套默认模板。
    """
    if not task_id:
        raise ValueError("task_id 为空")
    existing = list_phases(task_id)
    if existing and not replace:
        return {
            "ok": False,
            "error": "plan_already_exists",
            "phases": existing,
            "current_phase": (get_task(task_id) or {}).get("current_phase"),
        }

    norm: List[Dict[str, Any]] = []
    if not steps:
        raise ValueError("steps 为空：须由模型传入规划步骤")
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("phase_code") or raw.get("code") or "").strip()
        if not code:
            continue
        name = str(raw.get("phase_name") or raw.get("name") or code).strip()
        try:
            seq = int(raw.get("seq") if raw.get("seq") is not None else (i + 1))
        except Exception:
            seq = i + 1
        norm.append({"phase_code": code[:64], "phase_name": name[:128], "seq": seq})

    if not norm:
        raise ValueError("steps 为空或无效")

    # 前插规划步（立刻 done）
    plan_step = {"phase_code": "planning", "phase_name": "提交执行计划", "seq": 0}
    all_steps = [plan_step] + norm

    if replace and existing:
        db.execute("DELETE FROM xw_task_phase WHERE task_id=%s", (task_id,))

    for st in all_steps:
        status = "done" if st["phase_code"] == "planning" else "pending"
        db.execute(
            """
            INSERT INTO xw_task_phase
                (task_id, phase_code, phase_name, seq, status, started_at, finished_at)
            VALUES (%s, %s, %s, %s, %s,
                    IF(%s='done', NOW(), NULL),
                    IF(%s='done', NOW(), NULL))
            ON DUPLICATE KEY UPDATE
                phase_name=VALUES(phase_name),
                seq=VALUES(seq),
                status=VALUES(status),
                updated_at=NOW()
            """,
            (
                task_id,
                st["phase_code"],
                st["phase_name"],
                st["seq"],
                status,
                status,
                status,
            ),
        )

    # 激活第一个业务步
    first = norm[0]
    db.execute(
        """
        UPDATE xw_task_phase
        SET status='running', started_at=IFNULL(started_at, NOW()), updated_at=NOW()
        WHERE task_id=%s AND phase_code=%s
        """,
        (task_id, first["phase_code"]),
    )
    set_current_phase(task_id, first["phase_code"])
    mark_running(task_id)

    phases = list_phases(task_id)
    logger.info(
        "submit_plan task=%s steps=%d current=%s",
        task_id,
        len(norm),
        first["phase_code"],
    )
    return {
        "ok": True,
        "task_id": task_id,
        "current_phase": first["phase_code"],
        "phases": phases,
    }


def phase_done(task_id: str, phase_code: str, message: str = "") -> Dict[str, Any]:
    """当前步 done → 自动激活下一步 running；无下一步则 current_phase=writing 等待终稿。"""
    if not task_id or not phase_code:
        raise ValueError("task_id/phase_code 为空")
    code = phase_code.strip()[:64]
    row = db.fetch_one(
        """
        SELECT id, status, seq FROM xw_task_phase
        WHERE task_id=%s AND phase_code=%s LIMIT 1
        """,
        (task_id, code),
    )
    if not row:
        return {"ok": False, "error": "phase_not_found", "phase_code": code}

    msg = (message or "")[:512] or None
    db.execute(
        """
        UPDATE xw_task_phase
        SET status='done',
            message=IFNULL(%s, message),
            finished_at=NOW(),
            updated_at=NOW()
        WHERE task_id=%s AND phase_code=%s
        """,
        (msg, task_id, code),
    )

    nxt = db.fetch_one(
        """
        SELECT phase_code, phase_name, seq FROM xw_task_phase
        WHERE task_id=%s AND status='pending'
        ORDER BY seq ASC, id ASC
        LIMIT 1
        """,
        (task_id,),
    )
    if nxt:
        db.execute(
            """
            UPDATE xw_task_phase
            SET status='running', started_at=IFNULL(started_at, NOW()), updated_at=NOW()
            WHERE task_id=%s AND phase_code=%s
            """,
            (task_id, nxt["phase_code"]),
        )
        set_current_phase(task_id, str(nxt["phase_code"]))
        return {
            "ok": True,
            "done_phase": code,
            "current_phase": nxt["phase_code"],
            "next_phase_name": nxt.get("phase_name"),
            "phases": list_phases(task_id),
        }

    set_current_phase(task_id, "finishing")
    return {
        "ok": True,
        "done_phase": code,
        "current_phase": "finishing",
        "message": "全部步骤已完成，请输出中文 Markdown 终稿",
        "phases": list_phases(task_id),
    }


def skip_open_phases_on_done(task_id: str) -> None:
    """终稿落库时：未完成步骤标 skipped。"""
    if not task_id:
        return
    db.execute(
        """
        UPDATE xw_task_phase
        SET status='skipped', finished_at=IFNULL(finished_at, NOW()), updated_at=NOW()
        WHERE task_id=%s AND status IN ('pending', 'running')
        """,
        (task_id,),
    )
    set_current_phase(task_id, "done")


def mark_running(task_id: str) -> None:
    if not task_id:
        return
    db.execute(
        """
        UPDATE xw_chat_task
        SET status='running',
            started_at=IFNULL(started_at, NOW()),
            updated_at=NOW()
        WHERE task_id=%s AND status IN ('pending', 'running')
        """,
        (task_id,),
    )


def mark_done(task_id: str, answer_markdown: str) -> None:
    if not task_id:
        return
    db.execute(
        """
        UPDATE xw_chat_task
        SET status='done',
            answer_markdown=%s,
            finished_at=NOW(),
            updated_at=NOW()
        WHERE task_id=%s
        """,
        (answer_markdown or "", task_id),
    )


def mark_failed(task_id: str, error_message: str) -> None:
    if not task_id:
        return
    err = (error_message or "")[:2000]
    db.execute(
        """
        UPDATE xw_chat_task
        SET status='failed',
            error_message=%s,
            finished_at=NOW(),
            updated_at=NOW()
        WHERE task_id=%s AND status NOT IN ('done')
        """,
        (err, task_id),
    )


def save_answer_message(session_id: str, task_id: str, content: str) -> bool:
    """写入 assistant answer；同内容不重复插。"""
    text = (content or "").strip()
    if not text or not task_id or not session_id or text == "(empty)":
        return False
    clipped = text[:65535]
    dup = db.fetch_one(
        """
        SELECT id FROM xw_chat_message
        WHERE task_id=%s AND role='assistant' AND msg_type='answer' AND content=%s
        LIMIT 1
        """,
        (task_id, clipped),
    )
    if dup:
        return False
    # 已有 answer 则更新为最新终稿
    existing = db.fetch_one(
        """
        SELECT id FROM xw_chat_message
        WHERE task_id=%s AND role='assistant' AND msg_type='answer'
        ORDER BY id DESC LIMIT 1
        """,
        (task_id,),
    )
    if existing:
        db.execute(
            "UPDATE xw_chat_message SET content=%s WHERE id=%s",
            (clipped, existing["id"]),
        )
        return True
    db.execute(
        """
        INSERT INTO xw_chat_message (session_id, task_id, role, content, msg_type)
        VALUES (%s, %s, 'assistant', %s, 'answer')
        """,
        (session_id, task_id, clipped),
    )
    return True


def save_answer(task_id: str, content: str) -> bool:
    """终稿：写 message + task.answer + done。短回复不标 done（避免误收尾）。"""
    text = (content or "").strip()
    if not text or text == "(empty)":
        return False
    row = get_task(task_id)
    if not row:
        return False
    session_id = str(row.get("session_id") or "")
    if not session_id:
        return False

    save_answer_message(session_id, task_id, text)

    # 较长或含 Markdown 标题视为报告终稿
    looks_final = len(text) >= 200 or ("\n#" in text) or text.startswith("#")
    if looks_final or str(row.get("status") or "") in ("pending", "running"):
        if looks_final:
            mark_done(task_id, text)
            if is_research_skill(str(row.get("skill_name") or "")):
                skip_open_phases_on_done(task_id)
            logger.info("xw-ingest 终稿已落库 task=%s len=%d", task_id, len(text))
            return True
        # 短回复：只更新 answer 字段，不改 status（留给更长终稿）
        db.execute(
            """
            UPDATE xw_chat_task
            SET answer_markdown=%s, updated_at=NOW()
            WHERE task_id=%s AND status IN ('pending', 'running')
            """,
            (text[:65535], task_id),
        )
    return True


def save_tool_event(
    *,
    task_id: str,
    tool_call_id: str,
    tool_name: str,
    mcp_server: str = "",
    tool_args: Any = None,
    tool_output: Any = None,
    status: str = "success",
    duration_ms: Optional[int] = None,
) -> None:
    if not task_id or not tool_call_id or not tool_name:
        return
    args_s = _as_text(tool_args, 20000)
    out_s = _as_text(tool_output, 50000)
    db.execute(
        """
        INSERT INTO xw_tool_event
            (task_id, tool_call_id, tool_name, mcp_server, tool_args, tool_output, status, duration_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            tool_name=VALUES(tool_name),
            mcp_server=IFNULL(VALUES(mcp_server), mcp_server),
            tool_args=IFNULL(VALUES(tool_args), tool_args),
            tool_output=IFNULL(VALUES(tool_output), tool_output),
            status=VALUES(status),
            duration_ms=IFNULL(VALUES(duration_ms), duration_ms),
            updated_at=NOW()
        """,
        (
            task_id,
            tool_call_id[:64],
            tool_name[:128],
            (mcp_server or "")[:128] or None,
            args_s,
            out_s,
            status or "success",
            duration_ms,
        ),
    )


def upsert_hits(task_id: str, skill_name: str, hits: List[Dict[str, Any]]) -> int:
    if not task_id or not hits:
        return 0
    # 延迟导入，避免循环依赖时可用
    try:
        from .normalize import to_label_value_list
    except Exception:
        to_label_value_list = None  # type: ignore
    n = 0
    for h in hits:
        if not isinstance(h, dict):
            continue
        dedupe = str(h.get("dedupeKey") or h.get("dedupe_key") or "").strip()
        if not dedupe:
            continue
        if len(dedupe) > 191:
            dedupe = dedupe[:191]
        hit_type = str(h.get("hitType") or h.get("hit_type") or h.get("type") or "other")
        hit_type = _norm_hit_type(hit_type)

        # 优先 fields；统一落成 [{label,value},...]
        payload = h.get("fields")
        if payload is None:
            payload = h.get("payload")
        if to_label_value_list is not None:
            payload = to_label_value_list(payload)
        elif not isinstance(payload, list):
            payload = [{"label": "内容", "value": _as_text(payload, 2000) or ""}]

        db.execute(
            """
            INSERT INTO xw_task_hit
                (task_id, skill_name, hit_type, platform, title, summary,
                 dedupe_key, payload_json, source_tool, tool_event_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                skill_name=IFNULL(VALUES(skill_name), skill_name),
                hit_type=VALUES(hit_type),
                platform=VALUES(platform),
                title=VALUES(title),
                summary=VALUES(summary),
                payload_json=VALUES(payload_json),
                source_tool=VALUES(source_tool),
                tool_event_id=IFNULL(VALUES(tool_event_id), tool_event_id),
                updated_at=NOW()
            """,
            (
                task_id,
                (skill_name or "")[:64] or None,
                hit_type,
                (str(h.get("platform") or "")[:64] or None),
                _clip(h.get("title"), 512),
                _clip(h.get("summary"), 1024),
                dedupe,
                _as_text(payload, 50000) or "[]",
                _clip(h.get("sourceTool") or h.get("source_tool"), 128),
                _clip(h.get("toolEventId") or h.get("tool_event_id"), 64),
            ),
        )
        n += 1
    return n


def _norm_hit_type(raw: str) -> str:
    t = (raw or "other").strip().lower()
    if t in ("account", "profile", "user"):
        return "profile"
    if t in ("post", "tweet", "video"):
        return "post"
    if t == "candidate":
        return "candidate"
    if t == "search":
        return "search"
    if t in ("document", "doc", "bill", "org", "event"):
        return "document"
    return "other"


def _clip(v: Any, n: int) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s if len(s) <= n else s[:n]


def _as_text(obj: Any, max_len: int) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj if len(obj) <= max_len else obj[:max_len]
    s = db.json_dumps(obj)
    return s if len(s) <= max_len else s[:max_len]
