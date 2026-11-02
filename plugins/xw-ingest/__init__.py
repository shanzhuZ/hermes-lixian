# -*- coding: utf-8 -*-
"""xw-ingest：直连 MySQL 写 tool/hit/状态/终稿；四类 research Skill 共用粗进度工具。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import db
from . import normalize as hit_builder
from . import store

logger = logging.getLogger(__name__)

_lock_cache: Dict[str, str] = {}


def _resolve_task(session_id: str = "", **_: Any) -> Optional[Dict[str, Any]]:
    """仿 xa：用 Hermes session_id 找活跃任务。"""
    sid = (session_id or "").strip()
    if not sid:
        return None
    if sid in _lock_cache:
        row = store.get_task(_lock_cache[sid])
        if row and str(row.get("status") or "") in ("pending", "running"):
            return row
    try:
        row = store.get_active_task_by_hermes_session(sid)
    except db.DbError as e:
        logger.debug("xw-ingest resolve skip: %s", e)
        return None
    except Exception as e:
        logger.warning("xw-ingest resolve failed: %s", e)
        return None
    if row and row.get("task_id"):
        _lock_cache[sid] = str(row["task_id"])
    return row


def _require_plan_task(session_id: str = "", **kwargs: Any) -> Dict[str, Any]:
    """粗进度工具：必须已是四大业务 Skill（路由态须先 xw_set_skill）。"""
    row = _resolve_task(session_id, **kwargs)
    if not row:
        return {"ok": False, "error": "no_active_task"}
    skill = str(row.get("skill_name") or "")
    if store.is_router_skill(skill):
        return {
            "ok": False,
            "error": "skill_not_bound",
            "message": "当前仍为 research-router/auto，请先调用 xw_set_skill 写入四大业务 Skill 之一，再 submit_plan / phase_done",
            "skill": skill,
        }
    if not store.is_business_skill(skill):
        return {
            "ok": False,
            "error": "skill_not_supported",
            "message": "粗进度规划仅支持 bill/org/account/event 四大业务 Skill",
            "skill": skill,
        }
    return {"ok": True, "task": row}


def _require_set_skill_task(session_id: str = "", **kwargs: Any) -> Dict[str, Any]:
    """xw_set_skill：路由态或已是 research 任务均可写回。"""
    row = _resolve_task(session_id, **kwargs)
    if not row:
        return {"ok": False, "error": "no_active_task"}
    if not store.is_research_skill(str(row.get("skill_name") or "")):
        return {
            "ok": False,
            "error": "skill_not_supported",
            "message": "仅 research 任务可调用 xw_set_skill",
            "skill": row.get("skill_name"),
        }
    return {"ok": True, "task": row}


def on_pre_llm_call(session_id: str = "", **kwargs: Any) -> None:
    try:
        row = _resolve_task(session_id)
        if not row:
            return
        store.mark_running(str(row["task_id"]))
        # research Skill 且尚无计划：标记 current_phase=planning
        if store.is_research_skill(str(row.get("skill_name") or "")):
            phases = store.list_phases(str(row["task_id"]))
            if not phases and not row.get("current_phase"):
                store.set_current_phase(str(row["task_id"]), "planning")
        logger.debug("xw-ingest running task=%s session=%s", row["task_id"], session_id)
    except db.DbError as e:
        logger.debug("xw-ingest pre_llm skip: %s", e)
    except Exception as e:
        logger.warning("xw-ingest pre_llm_call: %s", e)


def on_post_tool_call(
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    duration_ms: int = 0,
    status: str = "",
    error_message: str = "",
    mcp_server: str = "",
    **_: Any,
) -> None:
    try:
        row = _resolve_task(session_id)
        if not row:
            return
        xw_task = str(row["task_id"])
        skill = str(row.get("skill_name") or "")

        # 规划工具本身已写库，这里仍记一条 tool_event 便于审计
        tcid = tool_call_id or ("tc_" + hashlib.sha1(
            (tool_name + str(time.time())).encode("utf-8")
        ).hexdigest()[:24])
        failed = (status or "").lower() in ("error", "failed", "blocked") or bool(error_message)

        store.save_tool_event(
            task_id=xw_task,
            tool_call_id=tcid,
            tool_name=tool_name,
            mcp_server=mcp_server or "",
            tool_args=args,
            tool_output=error_message or result,
            status="error" if failed else "success",
            duration_ms=duration_ms or None,
        )
        if failed:
            return
        if tool_name in ("xw_submit_plan", "xw_phase_done", "xw_set_skill"):
            return

        hits = hit_builder.build_hits(tool_name, args, result, tcid)
        if hits:
            store.upsert_hits(xw_task, skill, hits)
    except db.DbError as e:
        logger.debug("xw-ingest post_tool skip: %s", e)
    except Exception as e:
        logger.warning("xw-ingest post_tool_call: %s", e)


def on_post_llm_call(
    session_id: str = "",
    assistant_response: str = "",
    user_message: str = "",
    **_: Any,
) -> None:
    try:
        text = (assistant_response or "").strip()
        if not text or text == "(empty)":
            return
        row = _resolve_task(session_id)
        if not row:
            return
        store.save_answer(str(row["task_id"]), text)
    except db.DbError as e:
        logger.debug("xw-ingest post_llm skip: %s", e)
    except Exception as e:
        logger.warning("xw-ingest post_llm_call: %s", e)


def _load_assistant_from_state(session_id: str) -> Optional[str]:
    if not session_id:
        return None
    home = (os.environ.get("HERMES_HOME") or "").strip()
    if not home:
        home = str(Path.home() / ".hermes")
    db_path = Path(home) / "state.db"
    if not db_path.is_file():
        return None
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT content FROM messages
            WHERE session_id=? AND role='assistant'
              AND content IS NOT NULL AND TRIM(content) != ''
              AND TRIM(content) != '(empty)'
            ORDER BY id DESC
            LIMIT 20
            """,
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    for row in rows:
        text = str(row[0] or "").strip()
        if len(text) >= 200 or text.startswith("#") or "\n#" in text:
            return text
    return str(rows[0][0] or "").strip() or None


def on_session_end(session_id: str = "", **_: Any) -> None:
    try:
        row = _resolve_task(session_id)
        if not row:
            try:
                row = db.fetch_one(
                    """
                    SELECT t.task_id, t.session_id, t.skill_name, t.status, t.answer_markdown, t.current_phase
                    FROM xw_chat_session s
                    INNER JOIN xw_chat_task t ON t.session_id = s.session_id
                    WHERE s.hermes_session_id = %s
                    ORDER BY t.created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
            except Exception:
                row = None
        if not row:
            return
        tid = str(row["task_id"])
        st = str(row.get("status") or "")
        if st == "done" and row.get("answer_markdown"):
            return
        assistant = _load_assistant_from_state(session_id)
        if assistant:
            store.save_answer(tid, assistant)
            logger.info("xw-ingest on_session_end 兜底 task=%s len=%d", tid, len(assistant))
    except db.DbError as e:
        logger.debug("xw-ingest session_end skip: %s", e)
    except Exception as e:
        logger.warning("xw-ingest on_session_end: %s", e)


def _handle_set_skill(params: Dict[str, Any], **kwargs: Any) -> str:
    try:
        check = _require_set_skill_task(**kwargs)
        if not check.get("ok"):
            return json.dumps(check, ensure_ascii=False)
        task = check["task"]
        skill = str(
            params.get("skill_name") or params.get("skill") or params.get("name") or ""
        ).strip()
        out = store.set_task_skill(str(task["task_id"]), skill)
        return json.dumps(out, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("xw_set_skill failed: %s", e)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _handle_submit_plan(params: Dict[str, Any], **kwargs: Any) -> str:
    try:
        check = _require_plan_task(**kwargs)
        if not check.get("ok"):
            return json.dumps(check, ensure_ascii=False)
        task = check["task"]
        steps = params.get("steps")
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except Exception:
                steps = None
        if not isinstance(steps, list):
            steps = None
        replace = bool(params.get("replace") or False)
        use_default = bool(params.get("use_default") or False)
        # 仅法案保留 use_default 兼容；其它 Skill 必须传 steps
        if use_default and not steps and store.is_bill_skill(str(task.get("skill_name") or "")):
            steps = list(store.BILL_DEFAULT_PLAN)
        if not steps:
            return json.dumps(
                {
                    "ok": False,
                    "error": "steps_required",
                    "hint": "请按当前 Skill 自行规划并传入 steps=[{phase_code,phase_name,seq},...]；勿依赖默认模板",
                },
                ensure_ascii=False,
            )
        out = store.submit_plan(str(task["task_id"]), steps, replace=replace)
        return json.dumps(out, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("xw_submit_plan failed: %s", e)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _handle_phase_done(params: Dict[str, Any], **kwargs: Any) -> str:
    try:
        check = _require_plan_task(**kwargs)
        if not check.get("ok"):
            return json.dumps(check, ensure_ascii=False)
        task = check["task"]
        code = str(params.get("phase_code") or params.get("code") or "").strip()
        if not code:
            return json.dumps({"ok": False, "error": "phase_code_required"}, ensure_ascii=False)
        msg = str(params.get("message") or "")
        out = store.phase_done(str(task["task_id"]), code, msg)
        return json.dumps(out, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("xw_phase_done failed: %s", e)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("on_session_end", on_session_end)

    ctx.register_tool(
        name="xw_set_skill",
        toolset="xw_ingest",
        schema={
            "name": "xw_set_skill",
            "description": (
                "将当前任务绑定到四大业务 Skill 之一并写回 MySQL skill_name。"
                "research-router 判定完成后必须先调用本工具，再 skill_view / xw_submit_plan。"
                "可选值：bill-impact-analysis、org-portrait、account-portrait、event-spread-impact。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "四大业务 Skill 规范名之一",
                    },
                },
                "required": ["skill_name"],
            },
        },
        handler=_handle_set_skill,
        description="Bind task to a business research skill",
    )

    ctx.register_tool(
        name="xw_submit_plan",
        toolset="xw_ingest",
        schema={
            "name": "xw_submit_plan",
            "description": (
                "research Skill 粗进度：提交粗粒度执行计划并入库。"
                "仅当任务已绑定四大业务 Skill 之一时可调用（路由态须先 xw_set_skill）。"
                "必须传入 steps（按当前业务 Skill 自主规划）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "必填：自主规划的步骤列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "phase_code": {"type": "string"},
                                "phase_name": {"type": "string"},
                                "seq": {"type": "integer"},
                            },
                            "required": ["phase_code", "phase_name"],
                        },
                    },
                    "use_default": {
                        "type": "boolean",
                        "description": "不推荐。仅法案兼容：true 且无 steps 时用内置六步",
                    },
                    "replace": {
                        "type": "boolean",
                        "description": "已有计划时是否覆盖",
                    },
                },
                "required": [],
            },
        },
        handler=_handle_submit_plan,
        description="Submit research skill coarse plan to MySQL",
    )

    ctx.register_tool(
        name="xw_phase_done",
        toolset="xw_ingest",
        schema={
            "name": "xw_phase_done",
            "description": (
                "research Skill 粗进度：标记当前粗阶段完成，并自动激活下一步。"
                "每完成一个计划步骤后调用一次；phase_code 须与 xw_submit_plan 中一致。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phase_code": {
                        "type": "string",
                        "description": "刚完成的阶段码（与计划中 phase_code 一致）",
                    },
                    "message": {
                        "type": "string",
                        "description": "可选备注",
                    },
                },
                "required": ["phase_code"],
            },
        },
        handler=_handle_phase_done,
        description="Mark a research skill phase done",
    )

    cfg = db._cfg()
    logger.info(
        "xw-ingest registered (mysql=%s@%s:%s/%s) tools=xw_set_skill,xw_submit_plan,xw_phase_done",
        cfg["user"],
        cfg["host"],
        cfg["port"],
        cfg["database"],
    )
