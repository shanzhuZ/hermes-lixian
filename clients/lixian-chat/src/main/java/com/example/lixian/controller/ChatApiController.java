package com.example.lixian.controller;

import com.alibaba.fastjson.JSON;
import com.example.lixian.model.ChatSession;
import com.example.lixian.model.ChatTask;
import com.example.lixian.service.ChatService;
import com.example.lixian.service.TaskStreamHub;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.Map;

/**
 * 流式问答接口（本阶段无鉴权；结束后写入 ES sz_lixian_xw）。
 * <p>
 * POST /api/chat/sessions
 * POST /api/chat/ask
 * POST /api/chat/cancel          body: {taskId?} {sessionId?} 至少其一
 * GET  /api/chat/tasks/{taskId}
 * GET  /api/chat/tasks/{taskId}/stream
 * GET  /api/chat/sessions/{sessionId}
 * <p>
 * 历史查询走 GraphQL（与 aw 一致）：POST /graphql ，Query.getChatHistory；调试页 /graphiql
 */


//目前无用接口  api/chat/sessions/{sessionId}、api/chat/tasks/{taskId}
@RestController
@RequestMapping("/api/chat")
public class ChatApiController {

    private static final Logger log = LoggerFactory.getLogger(ChatApiController.class);

    private final ChatService chatService;
    private final TaskStreamHub streamHub;

    public ChatApiController(ChatService chatService, TaskStreamHub streamHub) {
        this.chatService = chatService;
        this.streamHub = streamHub;
    }

    @PostMapping("/sessions")
    public Map<String, Object> createSession(@RequestBody(required = false) Map<String, Object> body) {
        try {
            String title = body == null ? null : asString(body.get("title"));
            return chatService.createSession(title);
        } catch (Exception e) {
            log.error("创建 session 失败", e);
            return error(e.getMessage());
        }
    }

    @GetMapping("/sessions/{sessionId}")
    public Map<String, Object> getSession(@PathVariable("sessionId") String sessionId) {
        ChatSession session = chatService.getSession(sessionId);
        if (session == null) {
            return error("session 不存在");
        }
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("sessionId", session.getSessionId());
        out.put("hermesSessionId", session.getHermesSessionId());
        out.put("title", session.getTitle());
        out.put("createdAt", Long.valueOf(session.getCreatedAt()));
        return out;
    }

    /**
     * 发起问答。body: { "sessionId": "可选", "userId": "可选", "message": "必填" }
     * 未传 sessionId 时自动建会话。任务结束后写入 ES。
     */
    @PostMapping("/ask")
    public Map<String, Object> ask(@RequestBody Map<String, Object> body) {
        try {
            if (body == null) {
                return error("body 不能为空");
            }
            String sessionId = asString(body.get("sessionId"));
            String userId = asString(body.get("userId"));
            String message = asString(body.get("message"));
            return chatService.ask(sessionId, message, userId);
        } catch (IllegalArgumentException e) {
            return error(e.getMessage());
        } catch (Exception e) {
            log.error("ask 失败", e);
            return error(e.getMessage());
        }
    }

    /**
     * 取消执行中的任务。body: { "taskId": "可选", "sessionId": "可选" }，至少传一个。
     * 传 sessionId 时取消该会话下所有 running 任务。
     */
    @PostMapping("/cancel")
    public Map<String, Object> cancel(@RequestBody(required = false) Map<String, Object> body) {
        try {
            String taskId = body == null ? null : asString(body.get("taskId"));
            String sessionId = body == null ? null : asString(body.get("sessionId"));
            return chatService.cancel(taskId, sessionId);
        } catch (IllegalArgumentException e) {
            return error(e.getMessage());
        } catch (Exception e) {
            log.error("cancel 失败", e);
            return error(e.getMessage());
        }
    }

    @GetMapping("/tasks/{taskId}")
    public Map<String, Object> getTask(@PathVariable("taskId") String taskId) {
        ChatTask task = chatService.getTask(taskId);
        if (task == null) {
            return error("task 不存在");
        }
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("taskId", task.getTaskId());
        out.put("sessionId", task.getSessionId());
        out.put("userId", task.getUserId());
        out.put("hermesSessionId", task.getHermesSessionId());
        out.put("message", task.getMessage());
        out.put("status", task.getStatus());
        out.put("answer", task.getAnswer());
        out.put("error", task.getError());
        out.put("createdAt", Long.valueOf(task.getCreatedAt()));
        out.put("updatedAt", Long.valueOf(task.getUpdatedAt()));
        return out;
    }

    @GetMapping(value = "/tasks/{taskId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamTask(@PathVariable("taskId") String taskId) {
        final SseEmitter emitter = new SseEmitter(1_800_000L);
        ChatTask task = chatService.getTask(taskId);
        if (task == null) {
            try {
                emitter.send(SseEmitter.event().name("error").data("{\"message\":\"task 不存在\"}"));
            } catch (Exception ignore) {
                // ignore
            }
            emitter.complete();
            return emitter;
        }

        streamHub.subscribe(taskId, emitter);
        emitter.onCompletion(new Runnable() {
            @Override
            public void run() {
                streamHub.unsubscribe(taskId, emitter);
            }
        });
        emitter.onTimeout(new Runnable() {
            @Override
            public void run() {
                streamHub.unsubscribe(taskId, emitter);
                emitter.complete();
            }
        });
        emitter.onError(new java.util.function.Consumer<Throwable>() {
            @Override
            public void accept(Throwable t) {
                streamHub.unsubscribe(taskId, emitter);
            }
        });

        try {
            emitter.send(SseEmitter.event().name("connected")
                    .data("{\"taskId\":\"" + taskId + "\",\"sessionId\":\"" + task.getSessionId() + "\"}"));
            // 若订阅时任务已终态，补发便于调试
            if (ChatService.isTerminalStatus(task.getStatus())) {
                emitter.send(SseEmitter.event().name("status")
                        .data(JSON.toJSONString(taskSnapshot(task))));
                if ("cancelled".equals(task.getStatus())) {
                    emitter.send(SseEmitter.event().name("cancelled")
                            .data("{\"ok\":true,\"message\":\"任务已取消\",\"late\":true}"));
                    emitter.send(SseEmitter.event().name("stream_end")
                            .data("{\"ok\":true,\"cancelled\":true,\"late\":true}"));
                } else if ("failed".equals(task.getStatus())) {
                    String err = task.getError() == null ? "failed" : task.getError();
                    String safe = err.replace("\\", "\\\\").replace("\"", "'");
                    emitter.send(SseEmitter.event().name("error")
                            .data("{\"message\":\"" + safe + "\",\"late\":true}"));
                    emitter.send(SseEmitter.event().name("stream_end")
                            .data("{\"ok\":false,\"failed\":true,\"late\":true}"));
                } else {
                    emitter.send(SseEmitter.event().name("stream_end")
                            .data("{\"ok\":true,\"late\":true}"));
                }
                emitter.complete();
                streamHub.unsubscribe(taskId, emitter);
            }
        } catch (Exception e) {
            log.warn("SSE connected 发送失败 task={}: {}", taskId, e.getMessage());
            emitter.completeWithError(e);
        }
        return emitter;
    }

    private Map<String, Object> taskSnapshot(ChatTask task) {
        Map<String, Object> m = new HashMap<String, Object>();
        m.put("taskId", task.getTaskId());
        m.put("sessionId", task.getSessionId());
        m.put("status", task.getStatus());
        m.put("error", task.getError());
        return m;
    }

    private static String asString(Object o) {
        return o == null ? null : String.valueOf(o).trim();
    }

    private static Map<String, Object> error(String message) {
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("ok", Boolean.FALSE);
        out.put("message", message == null ? "error" : message);
        return out;
    }
}
