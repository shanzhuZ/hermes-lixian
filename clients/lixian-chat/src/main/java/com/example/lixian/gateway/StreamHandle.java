package com.example.lixian.gateway;

import java.net.HttpURLConnection;

/**
 * 一次 Hermes chat/stream 的可取消句柄：断开连接以触发 Hermes 侧 agent.interrupt。
 */
public class StreamHandle {

    private volatile boolean cancelled;
    private volatile HttpURLConnection connection;

    public boolean isCancelled() {
        return cancelled;
    }

    /** 是否已挂上 Hermes 连接（开始拉流） */
    public boolean hasConnection() {
        return connection != null;
    }

    public void attach(HttpURLConnection connection) {
        this.connection = connection;
        if (cancelled && connection != null) {
            try {
                connection.disconnect();
            } catch (Exception ignore) {
                // ignore
            }
        }
    }

    public void cancel() {
        cancelled = true;
        HttpURLConnection conn = connection;
        if (conn != null) {
            try {
                conn.disconnect();
            } catch (Exception ignore) {
                // ignore
            }
        }
    }
}
