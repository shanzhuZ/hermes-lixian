package com.example.aw.chat.service;

import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 将用户提问路由到四大业务 Skill；显式 skill / 触发词优先，未命中则由上层绑定 research-router。
 */
@Component
public class SkillRouter {

    public static final String ORG = "org-portrait";
    public static final String ACCOUNT = "account-portrait";
    public static final String EVENT = "event-spread-impact";
    public static final String BILL = "bill-impact-analysis";
    /** 本地未命中四大类时的默认路由 Skill（由模型再选业务 Skill） */
    public static final String ROUTER = "research-router";

    private static final Map<String, List<String>> TRIGGERS;

    static {
        Map<String, List<String>> m = new LinkedHashMap<String, List<String>>();
        m.put(ORG, Arrays.asList(
                "获取组织画像", "组织画像", "机构画像", "org-portrait", "org portrait"));
        m.put(ACCOUNT, Arrays.asList(
                "社交账号画像", "账号画像", "account-portrait", "账号主页", "account portrait"));
        m.put(EVENT, Arrays.asList(
                "热点事件传播", "传播影响", "事件传播", "event-spread-impact", "舆情时间线"));
        m.put(BILL, Arrays.asList(
                "法案研判", "法案分析", "法案发言", "bill-impact-analysis", "bill-social-stance",
                "h.r.", "h.r ", " s.", "s. "));
        TRIGGERS = Collections.unmodifiableMap(m);
    }

    public String normalize(String skill) {
        if (skill == null) {
            return null;
        }
        String s = skill.trim().toLowerCase(Locale.ROOT);
        if (s.isEmpty()) {
            return null;
        }
        if (ORG.equals(s) || "org".equals(s) || "组织画像".equals(skill.trim())) {
            return ORG;
        }
        if (ACCOUNT.equals(s) || "account".equals(s) || "账号画像".equals(skill.trim())) {
            return ACCOUNT;
        }
        if (EVENT.equals(s) || "event".equals(s) || "事件传播".equals(skill.trim())) {
            return EVENT;
        }
        if (BILL.equals(s) || "bill".equals(s) || "法案".equals(skill.trim())
                || "bill-social-stance".equals(s)) {
            return BILL;
        }
        if (ROUTER.equals(s) || "router".equals(s) || "auto".equals(s) || "路由".equals(skill.trim())) {
            return ROUTER;
        }
        return null;
    }

    /** 显式 skill 优先；否则触发词打分；无法判定返回 null（上层可走模型自主选择） */
    public String route(String explicitSkill, String message) {
        String n = normalize(explicitSkill);
        if (n != null) {
            return n;
        }
        if (message == null || message.trim().isEmpty()) {
            return null;
        }
        String text = message.toLowerCase(Locale.ROOT);
        String best = null;
        int bestScore = 0;
        for (Map.Entry<String, List<String>> e : TRIGGERS.entrySet()) {
            int score = 0;
            for (String t : e.getValue()) {
                if (t == null || t.isEmpty()) {
                    continue;
                }
                String key = t.toLowerCase(Locale.ROOT);
                if (text.contains(key)) {
                    score = Math.max(score, key.length());
                }
            }
            if (BILL.equals(e.getKey())) {
                if (text.matches("(?s).*\\bh\\.?r\\.?\\s*\\d+.*")
                        || text.matches("(?s).*\\bs\\.\\s*\\d{3,5}\\b.*")) {
                    score = Math.max(score, 20);
                }
            }
            if (score > bestScore) {
                bestScore = score;
                best = e.getKey();
            }
        }
        return bestScore > 0 ? best : null;
    }

    public String buildPrompt(String skillName, String userMessage) {
        String base = "请严格按 Hermes Skill「" + skillName + "」执行下列用户请求。"
                + "先用 skill_view（或等价方式）加载该 Skill 的规则与报告模板，再按 Skill 验收标准输出中文 Markdown 终稿。"
                + "不要改用其它无关 Skill。\n\n"
                + "用户请求：\n"
                + userMessage;
        if (ORG.equals(skillName) || ACCOUNT.equals(skillName)
                || EVENT.equals(skillName) || BILL.equals(skillName)) {
            base = base + "\n\n【进度】开始前必须自行规划粗步骤并调用 xw_submit_plan(steps=[...])（禁止 use_default/空 steps）；"
                    + "每完成一阶段按计划 phase_code 调用 xw_phase_done；"
                    + "撰写步：先 xw_phase_done(撰写码)，再输出完整 Markdown 终稿并停止；"
                    + "禁止终稿后再输出速览/概论，禁止终稿同轮或之后再调工具。";
        } else if (ROUTER.equals(skillName)) {
            base = base + "\n\n【路由】先判定应使用 org-portrait / account-portrait / event-spread-impact / bill-impact-analysis 之一，"
                    + "立刻调用 xw_set_skill(skill_name=...) 写回任务分类，"
                    + "再 skill_view 加载该 Skill 并严格按其规则执行（含 xw_submit_plan / xw_phase_done 与中文终稿）。"
                    + "未 xw_set_skill 前禁止 submit_plan；不要只写路由说明替代业务报告。";
        }
        return base;
    }

    public Map<String, List<String>> allTriggers() {
        return TRIGGERS;
    }
}
