package com.example.aw.chat.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * 内存事件总线：按 taskId 管理 SSE 订阅者。
 * <p>
 * 这里只负责“实时转发后续事件”，不做历史缓冲和回放。
 */
@Component
public class TaskStreamHub {

    private static final Logger log = LoggerFactory.getLogger(TaskStreamHub.class);

    /** taskId -> 订阅者列表 */
    private final ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>> subscribers =
            new ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>>();

    /** 前端订阅某个 taskId 的事件流；只接收订阅之后的实时事件 */
    public void subscribe(String taskId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> list = subscribers.get(taskId);
        if (list == null) {
            subscribers.putIfAbsent(taskId, new CopyOnWriteArrayList<SseEmitter>());
            list = subscribers.get(taskId);
        }
        list.add(emitter);

        emitter.onCompletion(new Runnable() {
            @Override
            public void run() {
                remove(taskId, emitter);
            }
        });
        emitter.onTimeout(new Runnable() {
            @Override
            public void run() {
                remove(taskId, emitter);
            }
        });
    }

    /** 向某 taskId 的所有订阅者推送实时事件。 */
    public void dispatch(String taskId, String eventName, Object data) {
        String dataStr = data instanceof String ? (String) data : String.valueOf(data);
        CopyOnWriteArrayList<SseEmitter> list = subscribers.get(taskId);
        if (list == null || list.isEmpty()) {
            return;
        }
        for (SseEmitter emitter : list) {
            try {
                emitter.send(SseEmitter.event().name(eventName).data(dataStr));
            } catch (IOException e) {
                remove(taskId, emitter);
            } catch (Exception e) {
                log.warn("dispatch 事件异常 taskId={}, event={}: {}", taskId, eventName, e.getMessage());
                remove(taskId, emitter);
            }
        }
    }

    /** 标记完成：关闭所有订阅者连接并清理。 */
    public void complete(String taskId) {
        CopyOnWriteArrayList<SseEmitter> list = subscribers.remove(taskId);
        if (list != null) {
            for (SseEmitter emitter : list) {
                try { emitter.complete(); } catch (Exception ignore) {}
            }
        }
    }

    private void remove(String taskId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> list = subscribers.get(taskId);
        if (list != null) {
            list.remove(emitter);
        }
    }

}
