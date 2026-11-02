package com.example.aw.chat.service;

import com.example.aw.chat.mapper.ChatMessageMapper;
import com.example.aw.chat.mapper.ChatSessionMapper;
import com.example.aw.chat.mapper.ChatTaskMapper;
import com.example.aw.chat.mapper.TaskHitMapper;
import com.example.aw.chat.mapper.TaskPhaseMapper;
import com.example.aw.chat.mapper.TaskToolEventMapper;
import com.example.aw.gateway.HermesGatewayClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.BiConsumer;

/**
 * 对话业务：session / task 分离。
 * Ask 预建任务后异步消费 Hermes SSE（仅转发，不写库）；
 * 状态 / tool / hit / 终稿由 Hermes 插件 xw-ingest 直连 MySQL 写入。
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    private final ChatSessionMapper sessionMapper;
    private final ChatTaskMapper taskMapper;
    private final ChatMessageMapper messageMapper;
    private final TaskToolEventMapper toolEventMapper;
    private final TaskHitMapper hitMapper;
    private final TaskPhaseMapper phaseMapper;
    private final HermesGatewayClient hermesGatewayClient;
    private final SkillRouter skillRouter;
    private final TaskStreamHub streamHub;
    private final ExecutorService executor = Executors.newCachedThreadPool();

    public ChatService(ChatSessionMapper sessionMapper,
                       ChatTaskMapper taskMapper,
                       ChatMessageMapper messageMapper,
                       TaskToolEventMapper toolEventMapper,
                       TaskHitMapper hitMapper,
                       TaskPhaseMapper phaseMapper,
                       HermesGatewayClient hermesGatewayClient,
                       SkillRouter skillRouter,
                       TaskStreamHub streamHub) {
        this.sessionMapper = sessionMapper;
        this.taskMapper = taskMapper;
        this.messageMapper = messageMapper;
        this.toolEventMapper = toolEventMapper;
        this.hitMapper = hitMapper;
        this.phaseMapper = phaseMapper;
        this.hermesGatewayClient = hermesGatewayClient;
        this.skillRouter = skillRouter;
        this.streamHub = streamHub;
    }

    public Map<String, Object> createSession(String title) throws Exception {
        String hermesSessionId = hermesGatewayClient.createSession();
        String sessionId = "sess_" + UUID.randomUUID().toString().replace("-", "");
        sessionMapper.insertSession(sessionId, hermesSessionId, title);
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("sessionId", sessionId);
        out.put("hermesSessionId", hermesSessionId);
        out.put("title", title);
        return out;
    }

    /**
     * 提问：建 task → 异步消费 Hermes SSE（只转发）。
     * 显式 skillName 且为四大业务之一 → 直接入库该名；
     * 未传 / 无法规范 → 入库 research-router，由模型 xw_set_skill 写回业务名（不用触发词猜）。
     */
    public Map<String, Object> ask(String sessionId, String message, String skill,
                                   boolean wait, long waitTimeoutMs) throws Exception {
        if (message == null || message.trim().isEmpty()) {
            throw new IllegalArgumentException("message 不能为空");
        }
        // 仅认请求体显式 skill；不靠文案触发词决定 skill_name
        String skillName = skillRouter.normalize(skill);
        if (skillName == null || SkillRouter.ROUTER.equals(skillName)) {
            skillName = SkillRouter.ROUTER;
        }

        Map<String, Object> session = ensureSession(sessionId, message);
        String sid = String.valueOf(session.get("sessionId"));
        String hermesSid = String.valueOf(session.get("hermesSessionId"));

        String taskId = "task_" + UUID.randomUUID().toString().replace("-", "");
        String dbSkill = skillName;
        taskMapper.insertTask(taskId, sid, dbSkill, message.trim());
        messageMapper.insertMessage(sid, taskId, "user", message.trim(), "user_input");
        sessionMapper.touchUpdatedAt(sid);

        final String prompt = skillRouter.buildPrompt(skillName, message.trim());
        executor.submit(new Runnable() {
            @Override
            public void run() {
                runTaskStream(taskId, hermesSid, prompt);
            }
        });

        if (wait) {
            long timeout = waitTimeoutMs > 0 ? waitTimeoutMs : 1_800_000L;
            Map<String, Object> done = waitTaskTerminal(taskId, timeout);
            if (done != null) {
                return done;
            }
            Map<String, Object> timedOut = getTask(taskId);
            if (timedOut == null) {
                timedOut = new HashMap<String, Object>();
                timedOut.put("taskId", taskId);
                timedOut.put("sessionId", sid);
            }
            timedOut.put("waitTimedOut", Boolean.TRUE);
            return timedOut;
        }

        Map<String, Object> out = new HashMap<String, Object>();
        out.put("sessionId", sid);
        out.put("hermesSessionId", hermesSid);
        out.put("taskId", taskId);
        out.put("skill", dbSkill);
        out.put("status", "pending");
        out.put("hint", "流式输出：GET /api/chat/tasks/" + taskId + "/stream");
        return out;
    }

    public Map<String, Object> waitTaskTerminal(String taskId, long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            Map<String, Object> task = getTask(taskId);
            if (task != null) {
                Object st = task.get("status");
                if ("done".equals(st) || "failed".equals(st)) {
                    return task;
                }
            }
            Thread.sleep(2000L);
        }
        return null;
    }

    /**
     * 消费 Hermes SSE，仅转发给前端；不写 status / answer（由 xw-ingest 写库）。
     */
    private void runTaskStream(final String taskId, String hermesSessionId, String prompt) {
        try {
            streamHub.dispatch(taskId, "status", "{\"status\":\"running\"}");

            hermesGatewayClient.chatStream(hermesSessionId, prompt,
                    new BiConsumer<String, String>() {
                        @Override
                        public void accept(String event, String data) {
                            if (!"run.completed".equals(event) && !"run.started".equals(event)
                                    && !"message.started".equals(event)) {
                                streamHub.dispatch(taskId, event, data);
                            }
                        }
                    });

            // 终态由 Hook 落库；这里只通知前端 stream 消费结束
            streamHub.dispatch(taskId, "stream_end", "{\"ok\":true}");
            streamHub.complete(taskId);
        } catch (Exception e) {
            log.error("task {} 流式转发失败（不改任务状态）", taskId, e);
            String err = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            streamHub.dispatch(taskId, "error", "{\"message\":\"" + err.replace("\"", "'") + "\"}");
            streamHub.complete(taskId);
        }
    }

    private Map<String, Object> ensureSession(String sessionId, String message) throws Exception {
        if (sessionId != null && !sessionId.trim().isEmpty()) {
            Map<String, Object> row = sessionMapper.selectById(sessionId.trim());
            if (row == null || row.isEmpty()) {
                throw new IllegalArgumentException("session 不存在: " + sessionId);
            }
            Map<String, Object> m = new HashMap<String, Object>();
            m.put("sessionId", row.get("sessionId") != null ? row.get("sessionId") : row.get("session_id"));
            Object hs = row.get("hermesSessionId") != null ? row.get("hermesSessionId") : row.get("hermes_session_id");
            m.put("hermesSessionId", hs);
            return m;
        }
        String title = message.trim();
        if (title.length() > 40) {
            title = title.substring(0, 40) + "...";
        }
        return createSession(title);
    }

    public Map<String, Object> getTask(String taskId) {
        Map<String, Object> row = taskMapper.selectById(taskId);
        if (row == null || row.isEmpty()) {
            return null;
        }
        return camelTask(row);
    }

    public List<Map<String, Object>> listTasks(String sessionId) {
        return taskMapper.selectBySessionId(sessionId);
    }

    public List<Map<String, Object>> listMessages(String sessionId, int limit) {
        int lim = limit <= 0 ? 200 : Math.min(limit, 1000);
        return messageMapper.selectBySessionId(sessionId, lim);
    }

    public List<Map<String, Object>> listTools(String taskId, int limit) {
        int lim = limit <= 0 ? 200 : Math.min(limit, 1000);
        return toolEventMapper.selectByTaskId(taskId, lim);
    }

    public List<Map<String, Object>> listHits(String taskId, String hitType, String platform, int limit) {
        int lim = limit <= 0 ? 200 : Math.min(limit, 1000);
        String ht = (hitType == null || hitType.trim().isEmpty()) ? null : hitType.trim();
        String pf = (platform == null || platform.trim().isEmpty()) ? null : platform.trim();
        return hitMapper.selectByTaskId(taskId, ht, pf, lim);
    }

    public List<Map<String, Object>> listPhases(String taskId) {
        return phaseMapper.selectByTaskId(taskId);
    }

    public Map<String, Object> getSession(String sessionId) {
        return sessionMapper.selectById(sessionId);
    }

    private Map<String, Object> camelTask(Map<String, Object> row) {
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("taskId", first(row, "taskId", "task_id"));
        out.put("sessionId", first(row, "sessionId", "session_id"));
        out.put("skill", first(row, "skillName", "skill_name"));
        out.put("status", row.get("status"));
        out.put("currentPhase", first(row, "currentPhase", "current_phase"));
        out.put("userMessage", first(row, "userMessage", "user_message"));
        out.put("answerMarkdown", first(row, "answerMarkdown", "answer_markdown"));
        out.put("errorMessage", first(row, "errorMessage", "error_message"));
        out.put("startedAt", first(row, "startedAt", "started_at"));
        out.put("finishedAt", first(row, "finishedAt", "finished_at"));
        out.put("createdAt", first(row, "createdAt", "created_at"));
        return out;
    }

    private static Object first(Map<String, Object> row, String a, String b) {
        if (row.containsKey(a) && row.get(a) != null) {
            return row.get(a);
        }
        return row.get(b);
    }
}
