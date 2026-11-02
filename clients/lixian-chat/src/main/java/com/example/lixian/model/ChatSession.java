package com.example.lixian.model;

/**
 * 业务会话（本阶段仅内存；后续可落库）。
 */
public class ChatSession {

    private String sessionId;
    private String hermesSessionId;
    private long createdAt;
    private String title;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getHermesSessionId() {
        return hermesSessionId;
    }

    public void setHermesSessionId(String hermesSessionId) {
        this.hermesSessionId = hermesSessionId;
    }

    public long getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(long createdAt) {
        this.createdAt = createdAt;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
