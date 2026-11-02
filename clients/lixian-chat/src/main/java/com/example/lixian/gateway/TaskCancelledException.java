package com.example.lixian.gateway;

/**
 * 任务被主动取消（断开 Hermes 流）。
 */
public class TaskCancelledException extends RuntimeException {

    public TaskCancelledException(String message) {
        super(message);
    }
}
