package com.example.lixian.service;

import com.example.lixian.gateway.HermesGatewayClient;
import com.example.lixian.gateway.StreamHandle;
import com.example.lixian.gateway.TaskCancelledException;
import com.example.lixian.model.ChatSession;
import com.example.lixian.model.ChatTask;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.function.BiConsumer;

@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    /** 进行中 */
    public static final String STATUS_RUNNING = "running";
    /** 流正常结束 */
    public static final String STATUS_END = "end";
    /** 用户取消 */
    public static final String STATUS_CANCELLED = "cancelled";
    /** 意外失败 */
    public static final String STATUS_FAILED = "failed";

    private final HermesGatewayClient hermesGatewayClient;
    private final MemoryStore memoryStore;
    private final TaskStreamHub streamHub;
    private final ChatHistoryEsService chatHistoryEsService;
    private final Executor chatTaskExecutor;
    /** 运行中任务的可取消句柄 */
    private final ConcurrentHashMap<String, StreamHandle> activeHandles =
            new ConcurrentHashMap<String, StreamHandle>();

    public ChatService(HermesGatewayClient hermesGatewayClient,
                       MemoryStore memoryStore,
                       TaskStreamHub streamHub,
                       ChatHistoryEsService chatHistoryEsService,
                       @Qualifier("chatTaskExecutor") Executor chatTaskExecutor) {
        this.hermesGatewayClient = hermesGatewayClient;
        this.memoryStore = memoryStore;
        this.streamHub = streamHub;
        this.chatHistoryEsService = chatHistoryEsService;
        this.chatTaskExecutor = chatTaskExecutor;
    }

    /**
     * 创建业务会话，并同步创建 Hermes session。
     */
    public Map<String, Object> createSession(String title) throws Exception {
        String sessionId = "sess_" + UUID.randomUUID().toString().replace("-", "");
        String hermesSessionId = hermesGatewayClient.createSession(null, title);
        long now = System.currentTimeMillis();

        ChatSession session = new ChatSession();
        session.setSessionId(sessionId);
        session.setHermesSessionId(hermesSessionId);
        session.setTitle(title);
        session.setCreatedAt(now);
        memoryStore.putSession(session);

        Map<String, Object> out = new HashMap<String, Object>();
        out.put("sessionId", sessionId);
        out.put("hermesSessionId", hermesSessionId);
        out.put("createdAt", Long.valueOf(now));
        return out;
    }

    /**
     * 发起问答：立即返回 taskId（status=running）；后台拉 Hermes 流并广播 SSE；结束后写入 ES。
     */
    public Map<String, Object> ask(String sessionId, String message, String userId) throws Exception {
        if (message == null || message.trim().isEmpty()) {
            throw new IllegalArgumentException("message 不能为空");
        }

        ChatSession session = ensureSession(sessionId);
        String taskId = "task_" + UUID.randomUUID().toString().replace("-", "");
        long now = System.currentTimeMillis();
        String uid = userId == null ? "" : userId.trim();

        ChatTask task = new ChatTask();
        task.setTaskId(taskId);
        task.setSessionId(session.getSessionId());
        task.setUserId(uid);
        task.setHermesSessionId(session.getHermesSessionId());
        task.setMessage(message.trim());
        task.setStatus(STATUS_RUNNING);
        task.setCreatedAt(now);
        task.setUpdatedAt(now);
        memoryStore.putTask(task);

        final StreamHandle handle = new StreamHandle();
        activeHandles.put(taskId, handle);

        // 创建即推 running，方便先订阅 stream 的客户端立刻看到状态
        streamHub.dispatch(taskId, "status", "{\"status\":\"running\"}");

        final String hermesSid = session.getHermesSessionId();
        final String prompt = message.trim();
        chatTaskExecutor.execute(new Runnable() {
            @Override
            public void run() {
                runTaskStream(taskId, hermesSid, prompt, handle);
            }
        });

        Map<String, Object> out = new HashMap<String, Object>();
        out.put("sessionId", session.getSessionId());
        out.put("hermesSessionId", session.getHermesSessionId());
        out.put("taskId", taskId);
        out.put("userId", uid);
        out.put("status", STATUS_RUNNING);
        out.put("hint", "流式输出：GET /api/chat/tasks/" + taskId + "/stream");
        return out;
    }

    /**
     * 取消任务。taskId / sessionId 至少传一个：
     * - 传 taskId：取消该任务
     * - 传 sessionId：取消该会话下所有 running 任务
     * - 都传：以 taskId 为准（且校验归属 session）
     */
    public Map<String, Object> cancel(String taskId, String sessionId) {
        String tid = taskId == null ? "" : taskId.trim();
        String sid = sessionId == null ? "" : sessionId.trim();
        if (tid.isEmpty() && sid.isEmpty()) {
            throw new IllegalArgumentException("taskId 与 sessionId 至少传一个");
        }

        List<ChatTask> targets = new ArrayList<ChatTask>();
        if (!tid.isEmpty()) {
            ChatTask t = memoryStore.getTask(tid);
            if (t == null) {
                throw new IllegalArgumentException("task 不存在: " + tid);
            }
            if (!sid.isEmpty() && !sid.equals(t.getSessionId())) {
                throw new IllegalArgumentException("task 不属于该 session");
            }
            targets.add(t);
        } else {
            ChatSession session = memoryStore.getSession(sid);
            if (session == null) {
                throw new IllegalArgumentException("session 不存在: " + sid);
            }
            for (ChatTask t : memoryStore.listTasksBySession(sid)) {
                if (isActiveStatus(t.getStatus())) {
                    targets.add(t);
                }
            }
        }

        List<Map<String, Object>> cancelled = new ArrayList<Map<String, Object>>();
        List<Map<String, Object>> skipped = new ArrayList<Map<String, Object>>();
        for (ChatTask t : targets) {
            Map<String, Object> one = cancelOne(t);
            if (Boolean.TRUE.equals(one.get("cancelled"))) {
                cancelled.add(one);
            } else {
                skipped.add(one);
            }
        }

        Map<String, Object> out = new HashMap<String, Object>();
        out.put("ok", Boolean.TRUE);
        out.put("cancelledCount", Integer.valueOf(cancelled.size()));
        out.put("skippedCount", Integer.valueOf(skipped.size()));
        out.put("cancelled", cancelled);
        out.put("skipped", skipped);
        return out;
    }

    private Map<String, Object> cancelOne(ChatTask task) {
        Map<String, Object> one = new HashMap<String, Object>();
        one.put("taskId", task.getTaskId());
        one.put("sessionId", task.getSessionId());
        one.put("statusBefore", task.getStatus());

        if (!isActiveStatus(task.getStatus())) {
            one.put("cancelled", Boolean.FALSE);
            one.put("reason", "任务已结束，无需取消");
            return one;
        }

        StreamHandle handle = activeHandles.get(task.getTaskId());
        if (handle != null) {
            handle.cancel();
        }

        // 尚未连上 Hermes 流时：直接落 cancelled，便于接口立刻返回
        if (handle == null || !isHermesStreamAttached(handle)) {
            markCancelled(task, "用户取消");
            activeHandles.remove(task.getTaskId());
            dispatchTerminal(task.getTaskId(), STATUS_CANCELLED, "任务已取消");
        }
        // 已在拉流：断开连接后由 runTaskStream 的 cancel/异常分支收尾

        one.put("cancelled", Boolean.TRUE);
        one.put("status", STATUS_CANCELLED);
        return one;
    }

    /**
     * StreamHandle 是否已挂上 HttpURLConnection（开始读 Hermes 流）。
     * 未挂上时 cancel 需在本处直接落终态。
     */
    private static boolean isHermesStreamAttached(StreamHandle handle) {
        // 通过是否已 cancel + 是否还在 active 且可能未 attach：
        // attach 后 cancel 主要靠 disconnect；未 attach 时 connection 为空。
        // 这里用反射不安全；改为 StreamHandle 提供 hasConnection。
        return handle.hasConnection();
    }

    private static boolean isActiveStatus(String status) {
        return STATUS_RUNNING.equals(status);
    }

    private void markCancelled(ChatTask task, String reason) {
        task.setStatus(STATUS_CANCELLED);
        task.setError(reason);
        task.setUpdatedAt(System.currentTimeMillis());
    }

    private void markFailed(ChatTask task, String reason) {
        task.setStatus(STATUS_FAILED);
        task.setError(reason);
        task.setUpdatedAt(System.currentTimeMillis());
    }

    private void markEnd(ChatTask task, String answer) {
        task.setStatus(STATUS_END);
        task.setAnswer(answer);
        task.setError(null);
        task.setUpdatedAt(System.currentTimeMillis());
    }

    private void dispatchTerminal(String taskId, String status, String message) {
        streamHub.dispatch(taskId, "status", "{\"status\":\"" + status + "\"}");
        if (STATUS_CANCELLED.equals(status)) {
            String safe = message == null ? "任务已取消" : message.replace("\\", "\\\\").replace("\"", "'");
            streamHub.dispatch(taskId, "cancelled", "{\"ok\":true,\"message\":\"" + safe + "\"}");
            streamHub.dispatch(taskId, "stream_end", "{\"ok\":true,\"cancelled\":true}");
        } else if (STATUS_FAILED.equals(status)) {
            String safe = message == null ? "failed" : message.replace("\\", "\\\\").replace("\"", "'");
            streamHub.dispatch(taskId, "error", "{\"message\":\"" + safe + "\"}");
            streamHub.dispatch(taskId, "stream_end", "{\"ok\":false,\"failed\":true}");
        } else if (STATUS_END.equals(status)) {
            streamHub.dispatch(taskId, "stream_end", "{\"ok\":true}");
        }
        streamHub.complete(taskId);
    }

    public ChatTask getTask(String taskId) {
        return memoryStore.getTask(taskId);
    }

    public ChatSession getSession(String sessionId) {
        return memoryStore.getSession(sessionId);
    }

    /** 是否终态：end / cancelled / failed */
    public static boolean isTerminalStatus(String status) {
        return STATUS_END.equals(status)
                || STATUS_CANCELLED.equals(status)
                || STATUS_FAILED.equals(status);
    }

    private ChatSession ensureSession(String sessionId) throws Exception {
        if (sessionId != null && !sessionId.trim().isEmpty()) {
            ChatSession existing = memoryStore.getSession(sessionId.trim());
            if (existing != null) {
                return existing;
            }
            throw new IllegalArgumentException("session 不存在: " + sessionId);
        }
        Map<String, Object> created = createSession(null);
        return memoryStore.getSession(String.valueOf(created.get("sessionId")));
    }

    private void runTaskStream(final String taskId, String hermesSessionId, String prompt, StreamHandle handle) {
        ChatTask task = memoryStore.getTask(taskId);
        // 已被 cancel 抢先落终态：不再重复推送
        if (task != null && isTerminalStatus(task.getStatus())) {
            activeHandles.remove(taskId);
            return;
        }
        if (handle != null && handle.isCancelled()) {
            if (task != null) {
                markCancelled(task, "用户取消");
            }
            dispatchTerminal(taskId, STATUS_CANCELLED, "任务已取消");
            activeHandles.remove(taskId);
            return;
        }

        try {
            String answer = hermesGatewayClient.chatStream(hermesSessionId, prompt,
                    new BiConsumer<String, String>() {
                        @Override
                        public void accept(String event, String data) {
                            if ("run.completed".equals(event) || "run.started".equals(event)
                                    || "message.started".equals(event)) {
                                return;
                            }
                            streamHub.dispatch(taskId, event, data);
                        }
                    },
                    handle);

            ChatTask done = memoryStore.getTask(taskId);
            if (done != null) {
                if (handle != null && handle.isCancelled()) {
                    markCancelled(done, "用户取消");
                    dispatchTerminal(taskId, STATUS_CANCELLED, "任务已取消");
                    return;
                }
                markEnd(done, answer);
                chatHistoryEsService.save(
                        done.getUserId(),
                        done.getTaskId(),
                        done.getSessionId(),
                        done.getMessage(),
                        answer);
            }
            streamHub.dispatch(taskId, "status", "{\"status\":\"end\"}");
            streamHub.dispatch(taskId, "stream_end", "{\"ok\":true}");
            streamHub.complete(taskId);
        } catch (TaskCancelledException e) {
            log.info("task {} 已取消", taskId);
            ChatTask cancelled = memoryStore.getTask(taskId);
            if (cancelled != null) {
                markCancelled(cancelled, "用户取消");
                chatHistoryEsService.save(
                        cancelled.getUserId(),
                        cancelled.getTaskId(),
                        cancelled.getSessionId(),
                        cancelled.getMessage(),
                        "任务已取消");
            }
            dispatchTerminal(taskId, STATUS_CANCELLED, "任务已取消");
        } catch (Exception e) {
            if (handle != null && handle.isCancelled()) {
                log.info("task {} 取消过程中断开: {}", taskId, e.getMessage());
                ChatTask cancelled = memoryStore.getTask(taskId);
                if (cancelled != null) {
                    markCancelled(cancelled, "用户取消");
                }
                dispatchTerminal(taskId, STATUS_CANCELLED, "任务已取消");
                return;
            }
            log.error("task {} 流式转发失败", taskId, e);
            String err = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            ChatTask failed = memoryStore.getTask(taskId);
            if (failed != null) {
                markFailed(failed, err);
                chatHistoryEsService.save(
                        failed.getUserId(),
                        failed.getTaskId(),
                        failed.getSessionId(),
                        failed.getMessage(),
                        err);
            }
            dispatchTerminal(taskId, STATUS_FAILED, err);
        } finally {
            activeHandles.remove(taskId);
        }
    }
}
