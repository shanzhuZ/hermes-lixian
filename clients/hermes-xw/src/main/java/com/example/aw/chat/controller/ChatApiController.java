package com.example.aw.chat.controller;

import com.example.aw.chat.service.ChatService;
import com.example.aw.chat.service.SkillRouter;
import com.example.aw.chat.service.TaskStreamHub;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 对话 REST：session / task 分离；Ask 预建任务，stream 仅转发；过程/终稿由 Hook 写库。
 *
 * <pre>
 * POST /api/chat/sessions
 * POST /api/chat/ask
 * GET  /api/chat/tasks/{taskId}
 * GET  /api/chat/tasks/{taskId}/stream
 * GET  /api/chat/tasks/{taskId}/tools
 * GET  /api/chat/tasks/{taskId}/hits
 * GET  /api/chat/tasks/{taskId}/phases
 * GET  /api/chat/sessions/{id}/messages
 * GET  /api/chat/sessions/{id}/tasks
 * GET  /api/chat/skills
 * </pre>
 */
@RestController
@RequestMapping("/api/chat")
public class ChatApiController {

    private final ChatService chatService;
    private final SkillRouter skillRouter;
    private final TaskStreamHub streamHub;
    private final ExecutorService sseExecutor = Executors.newCachedThreadPool();

    public ChatApiController(ChatService chatService, SkillRouter skillRouter,
                             TaskStreamHub streamHub) {
        this.chatService = chatService;
        this.skillRouter = skillRouter;
        this.streamHub = streamHub;
    }

    @PostMapping("/sessions")
    public ResponseEntity<Map<String, Object>> createSession(@RequestBody(required = false) Map<String, Object> body) {
        try {
            String title = body == null ? null : str(body.get("title"));
            if (title == null || title.isEmpty()) {
                title = "新对话";
            }
            return ResponseEntity.ok(ok(chatService.createSession(title)));
        } catch (Exception e) {
            return fail(e);
        }
    }

    /** sessionId / skill 可省略；wait=true 阻塞到终态 */
    @PostMapping("/ask")
    public ResponseEntity<Map<String, Object>> ask(@RequestBody Map<String, Object> body) {
        try {
            String sessionId = str(body.get("sessionId"));
            if (sessionId == null || sessionId.isEmpty()) {
                sessionId = str(body.get("session_id"));
            }
            String message = str(body.get("message"));
            if (message == null || message.isEmpty()) {
                message = str(body.get("question"));
            }
            String skill = str(body.get("skill"));
            if (skill == null || skill.isEmpty()) {
                skill = str(body.get("skillName"));
            }
            boolean wait = bool(body.get("wait"));
            long waitTimeoutMs = longVal(body.get("waitTimeoutMs"), 0L);
            return ResponseEntity.ok(ok(chatService.ask(sessionId, message, skill, wait, waitTimeoutMs)));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(err(400, e.getMessage()));
        } catch (Exception e) {
            return fail(e);
        }
    }

    @GetMapping("/tasks/{taskId}")
    public ResponseEntity<Map<String, Object>> getTask(@PathVariable("taskId") String taskId) {
        Map<String, Object> task = chatService.getTask(taskId);
        if (task == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(err(404, "task 不存在"));
        }
        return ResponseEntity.ok(ok(task));
    }

    /**
     * SSE：实时转发 Hermes 流（assistant.delta / tool.* / done / error）。
     * 不做历史回放；已结束则直接推终态。
     */
    @GetMapping(value = "/tasks/{taskId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamTask(@PathVariable("taskId") String taskId) {
        final SseEmitter emitter = new SseEmitter(1_800_000L);

        Map<String, Object> task = chatService.getTask(taskId);
        if (task == null) {
            sseExecutor.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        emitter.send(SseEmitter.event().name("error").data("{\"message\":\"task 不存在\"}"));
                        emitter.complete();
                    } catch (Exception ignore) {
                    }
                }
            });
            return emitter;
        }

        Object st = task.get("status");
        if ("done".equals(st) || "failed".equals(st)) {
            final Map<String, Object> finalTask = task;
            sseExecutor.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        emitter.send(SseEmitter.event().name("done").data(finalTask));
                        emitter.complete();
                    } catch (Exception ignore) {
                    }
                }
            });
            return emitter;
        }

        try {
            emitter.send(SseEmitter.event().name("connected").data("{\"taskId\":\"" + taskId + "\"}"));
        } catch (Exception e) {
            emitter.completeWithError(e);
            return emitter;
        }

        streamHub.subscribe(taskId, emitter);
        return emitter;
    }

    /** 工具审计列表（Hook 入库） */
    @GetMapping("/tasks/{taskId}/tools")
    public ResponseEntity<Map<String, Object>> listTools(@PathVariable("taskId") String taskId,
                                                         @RequestParam(value = "limit", defaultValue = "200") int limit) {
        if (chatService.getTask(taskId) == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(err(404, "task 不存在"));
        }
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("taskId", taskId);
        data.put("tools", chatService.listTools(taskId, limit));
        return ResponseEntity.ok(ok(data));
    }

    /** 归一化命中列表；可选 hitType / platform 过滤 */
    @GetMapping("/tasks/{taskId}/hits")
    public ResponseEntity<Map<String, Object>> listHits(@PathVariable("taskId") String taskId,
                                                        @RequestParam(value = "hitType", required = false) String hitType,
                                                        @RequestParam(value = "platform", required = false) String platform,
                                                        @RequestParam(value = "limit", defaultValue = "200") int limit) {
        if (chatService.getTask(taskId) == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(err(404, "task 不存在"));
        }
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("taskId", taskId);
        data.put("hits", chatService.listHits(taskId, hitType, platform, limit));
        return ResponseEntity.ok(ok(data));
    }

    /** 粗阶段计划（法案方案 D）；其它 Skill 可能为空列表 */
    @GetMapping("/tasks/{taskId}/phases")
    public ResponseEntity<Map<String, Object>> listPhases(@PathVariable("taskId") String taskId) {
        Map<String, Object> task = chatService.getTask(taskId);
        if (task == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(err(404, "task 不存在"));
        }
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("taskId", taskId);
        data.put("status", task.get("status"));
        data.put("currentPhase", task.get("currentPhase"));
        data.put("phases", chatService.listPhases(taskId));
        return ResponseEntity.ok(ok(data));
    }

    @GetMapping("/sessions/{sessionId}")
    public ResponseEntity<Map<String, Object>> getSession(@PathVariable("sessionId") String sessionId) {
        Map<String, Object> s = chatService.getSession(sessionId);
        if (s == null || s.isEmpty()) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(err(404, "session 不存在"));
        }
        return ResponseEntity.ok(ok(s));
    }

    @GetMapping("/sessions/{sessionId}/tasks")
    public ResponseEntity<Map<String, Object>> listTasks(@PathVariable("sessionId") String sessionId) {
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("sessionId", sessionId);
        data.put("tasks", chatService.listTasks(sessionId));
        return ResponseEntity.ok(ok(data));
    }

    @GetMapping("/sessions/{sessionId}/messages")
    public ResponseEntity<Map<String, Object>> listMessages(@PathVariable("sessionId") String sessionId,
                                                            @RequestParam(value = "limit", defaultValue = "200") int limit) {
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("sessionId", sessionId);
        data.put("messages", chatService.listMessages(sessionId, limit));
        return ResponseEntity.ok(ok(data));
    }

    @GetMapping("/skills")
    public ResponseEntity<Map<String, Object>> skills() {
        Map<String, Object> data = new LinkedHashMap<String, Object>();
        data.put("skills", skillRouter.allTriggers());
        return ResponseEntity.ok(ok(data));
    }

    private static Map<String, Object> ok(Object data) {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        m.put("code", 0);
        m.put("message", "ok");
        m.put("data", data);
        return m;
    }

    private static Map<String, Object> err(int code, String message) {
        Map<String, Object> m = new HashMap<String, Object>();
        m.put("code", code);
        m.put("message", message);
        m.put("data", null);
        return m;
    }

    private ResponseEntity<Map<String, Object>> fail(Exception e) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(err(500, e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage()));
    }

    private static String str(Object o) {
        return o == null ? null : String.valueOf(o).trim();
    }

    private static boolean bool(Object o) {
        if (o == null) {
            return false;
        }
        if (o instanceof Boolean) {
            return ((Boolean) o).booleanValue();
        }
        String s = String.valueOf(o).trim();
        return "true".equalsIgnoreCase(s) || "1".equals(s) || "yes".equalsIgnoreCase(s);
    }

    private static long longVal(Object o, long def) {
        if (o == null) {
            return def;
        }
        try {
            return Long.parseLong(String.valueOf(o).trim());
        } catch (Exception e) {
            return def;
        }
    }
}
