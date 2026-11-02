package com.example.lixian.service;

import com.example.lixian.model.ChatSession;
import com.example.lixian.model.ChatTask;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 本阶段内存存储；后续可替换为 MyBatis/MySQL。
 */
@Component
public class MemoryStore {

    private final ConcurrentHashMap<String, ChatSession> sessions = new ConcurrentHashMap<String, ChatSession>();
    private final ConcurrentHashMap<String, ChatTask> tasks = new ConcurrentHashMap<String, ChatTask>();

    public void putSession(ChatSession session) {
        sessions.put(session.getSessionId(), session);
    }

    public ChatSession getSession(String sessionId) {
        if (sessionId == null) {
            return null;
        }
        return sessions.get(sessionId);
    }

    public void putTask(ChatTask task) {
        tasks.put(task.getTaskId(), task);
    }

    public ChatTask getTask(String taskId) {
        if (taskId == null) {
            return null;
        }
        return tasks.get(taskId);
    }

    public List<ChatTask> listTasksBySession(String sessionId) {
        List<ChatTask> list = new ArrayList<ChatTask>();
        if (sessionId == null) {
            return list;
        }
        for (ChatTask t : tasks.values()) {
            if (sessionId.equals(t.getSessionId())) {
                list.add(t);
            }
        }
        return list;
    }
}
