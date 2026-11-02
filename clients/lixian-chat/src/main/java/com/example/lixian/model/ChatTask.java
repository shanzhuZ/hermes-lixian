package com.example.lixian.model;

/**
 * 单次问答任务（本阶段仅内存；后续可落库）。
 * status: running / end / cancelled / failed
 */
public class ChatTask {

    private String taskId;
    private String sessionId;
    private String userId;
    private String hermesSessionId;
    private String message;
    private String status;
    private String answer;
    private String error;
    private long createdAt;
    private long updatedAt;

    public String getTaskId() {
        return taskId;
    }

    public void setTaskId(String taskId) {
        this.taskId = taskId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getHermesSessionId() {
        return hermesSessionId;
    }

    public void setHermesSessionId(String hermesSessionId) {
        this.hermesSessionId = hermesSessionId;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getAnswer() {
        return answer;
    }

    public void setAnswer(String answer) {
        this.answer = answer;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }

    public long getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(long createdAt) {
        this.createdAt = createdAt;
    }

    public long getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(long updatedAt) {
        this.updatedAt = updatedAt;
    }
}
