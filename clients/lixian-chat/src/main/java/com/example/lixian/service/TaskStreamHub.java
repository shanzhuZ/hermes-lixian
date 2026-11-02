package com.example.lixian.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * 按 taskId 广播 SSE 事件；支持 ask 之后再订阅 stream。
 * 带简易事件缓冲，降低「先 ask 后订阅」丢前几帧的概率。
 */
@Component
public class TaskStreamHub {

    private static final Logger log = LoggerFactory.getLogger(TaskStreamHub.class);
    private static final int BUFFER_LIMIT = 500;

    private final ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>> subscribers =
            new ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>>();
    private final ConcurrentHashMap<String, CopyOnWriteArrayList<BufferedEvent>> buffers =
            new ConcurrentHashMap<String, CopyOnWriteArrayList<BufferedEvent>>();

    public void subscribe(String taskId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> list = subscribers.get(taskId);
        if (list == null) {
            subscribers.putIfAbsent(taskId, new CopyOnWriteArrayList<SseEmitter>());
            list = subscribers.get(taskId);
        }
        list.add(emitter);

        // 回放已缓冲事件
        CopyOnWriteArrayList<BufferedEvent> buf = buffers.get(taskId);
        if (buf != null) {
            for (BufferedEvent ev : new ArrayList<BufferedEvent>(buf)) {
                try {
                    emitter.send(SseEmitter.event().name(ev.name).data(ev.data));
                } catch (Exception e) {
                    log.debug("SSE 回放失败 task={}: {}", taskId, e.getMessage());
                    completeQuietly(emitter);
                    list.remove(emitter);
                    return;
                }
            }
        }
    }

    public void dispatch(String taskId, String eventName, String dataStr) {
        CopyOnWriteArrayList<BufferedEvent> buf = buffers.get(taskId);
        if (buf == null) {
            buffers.putIfAbsent(taskId, new CopyOnWriteArrayList<BufferedEvent>());
            buf = buffers.get(taskId);
        }
        buf.add(new BufferedEvent(eventName, dataStr));
        while (buf.size() > BUFFER_LIMIT) {
            buf.remove(0);
        }

        CopyOnWriteArrayList<SseEmitter> list = subscribers.get(taskId);
        if (list == null || list.isEmpty()) {
            return;
        }
        for (SseEmitter emitter : list) {
            try {
                emitter.send(SseEmitter.event().name(eventName).data(dataStr));
            } catch (IOException e) {
                log.debug("SSE 发送失败 task={} event={}: {}", taskId, eventName, e.getMessage());
                completeQuietly(emitter);
                list.remove(emitter);
            } catch (Exception e) {
                log.debug("SSE 异常 task={} event={}: {}", taskId, eventName, e.getMessage());
                completeQuietly(emitter);
                list.remove(emitter);
            }
        }
    }

    public void complete(String taskId) {
        CopyOnWriteArrayList<SseEmitter> list = subscribers.remove(taskId);
        if (list != null) {
            for (SseEmitter emitter : list) {
                completeQuietly(emitter);
            }
        }
        // 保留 buffer 一小段时间无必要；任务结束后可删，避免内存涨
        buffers.remove(taskId);
    }

    public void unsubscribe(String taskId, SseEmitter emitter) {
        List<SseEmitter> list = subscribers.get(taskId);
        if (list != null) {
            list.remove(emitter);
        }
    }

    private void completeQuietly(SseEmitter emitter) {
        try {
            emitter.complete();
        } catch (Exception ignore) {
            // ignore
        }
    }

    private static class BufferedEvent {
        private final String name;
        private final String data;

        private BufferedEvent(String name, String data) {
            this.name = name;
            this.data = data;
        }
    }
}
