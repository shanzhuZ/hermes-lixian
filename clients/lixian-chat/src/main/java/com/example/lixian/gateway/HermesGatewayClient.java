package com.example.lixian.gateway;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.example.lixian.config.HermesProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.function.BiConsumer;

/**
 * 调用 Hermes Agent API Server：创建 session、流式 chat/stream。
 */
@Component
public class HermesGatewayClient {

    private static final Logger log = LoggerFactory.getLogger(HermesGatewayClient.class);

    private final HermesProperties props;

    public HermesGatewayClient(HermesProperties props) {
        this.props = props;
    }

    /**
     * 创建 Hermes 会话，返回 hermesSessionId。
     */
    public String createSession(String preferredId, String title) throws Exception {
        JSONObject req = new JSONObject();
        if (preferredId != null && !preferredId.trim().isEmpty()) {
            req.put("id", preferredId.trim());
        }
        if (title != null && !title.trim().isEmpty()) {
            req.put("title", title.trim());
        }
        String body = httpJson("POST", trimSlash(props.getBaseUrl()) + "/api/sessions", req.toJSONString());
        JSONObject root = JSON.parseObject(body);
        if (root == null) {
            throw new RuntimeException("创建 Hermes session 返回空");
        }
        JSONObject session = root.getJSONObject("session");
        if (session == null) {
            throw new RuntimeException("创建 Hermes session 无 session 字段: " + body);
        }
        String id = session.getString("id");
        if (id == null || id.trim().isEmpty()) {
            throw new RuntimeException("创建 Hermes session 无 id: " + body);
        }
        return id.trim();
    }

    /**
     * 流式对话：消费 Hermes SSE，逐事件回调 (eventName, dataJson)。
     *
     * @param handle 可空；非空时支持外部 cancel（disconnect 触发 Hermes interrupt）
     * @return 拼接后的完整 assistant 文本
     */
    public String chatStream(String hermesSessionId, String userMessage,
                             BiConsumer<String, String> onEvent,
                             StreamHandle handle) throws Exception {
        if (hermesSessionId == null || hermesSessionId.trim().isEmpty()) {
            throw new IllegalArgumentException("hermesSessionId 不能为空");
        }
        if (handle != null && handle.isCancelled()) {
            throw new TaskCancelledException("任务已取消");
        }
        JSONObject req = new JSONObject();
        req.put("message", userMessage == null ? "" : userMessage);
        String url = trimSlash(props.getBaseUrl()) + "/api/sessions/" + hermesSessionId.trim() + "/chat/stream";

        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(props.getConnectTimeoutMs());
        conn.setReadTimeout(props.getReadTimeoutMs());
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("Accept", "text/event-stream");
        applyAuth(conn);
        if (handle != null) {
            handle.attach(conn);
        }

        byte[] bytes = req.toJSONString().getBytes(StandardCharsets.UTF_8);
        OutputStream os = conn.getOutputStream();
        try {
            os.write(bytes);
            os.flush();
        } finally {
            os.close();
        }
        if (handle != null && handle.isCancelled()) {
            conn.disconnect();
            throw new TaskCancelledException("任务已取消");
        }

        int code;
        try {
            code = conn.getResponseCode();
        } catch (Exception e) {
            if (handle != null && handle.isCancelled()) {
                throw new TaskCancelledException("任务已取消");
            }
            throw e;
        }
        if (code < 200 || code >= 300) {
            String errBody = readAll(code < 400 ? conn.getInputStream() : conn.getErrorStream());
            throw new RuntimeException("Hermes stream HTTP " + code + ": " + errBody);
        }

        StringBuilder fullText = new StringBuilder();
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
        try {
            String currentEvent = "message";
            String line;
            while (true) {
                if (handle != null && handle.isCancelled()) {
                    throw new TaskCancelledException("任务已取消");
                }
                try {
                    line = reader.readLine();
                } catch (Exception e) {
                    if (handle != null && handle.isCancelled()) {
                        throw new TaskCancelledException("任务已取消");
                    }
                    throw e;
                }
                if (line == null) {
                    break;
                }
                if (line.startsWith("event:")) {
                    currentEvent = line.substring(6).trim();
                } else if (line.startsWith("data:")) {
                    String data = line.substring(5).trim();
                    if ("[DONE]".equals(data)) {
                        if (onEvent != null) {
                            onEvent.accept("done", "{}");
                        }
                        break;
                    }
                    if (onEvent != null) {
                        onEvent.accept(currentEvent, data);
                    }
                    if ("assistant.delta".equals(currentEvent) || "delta".equals(currentEvent)) {
                        try {
                            JSONObject d = JSON.parseObject(data);
                            if (d != null) {
                                String text = d.getString("delta");
                                if (text == null) {
                                    text = d.getString("text");
                                }
                                if (text == null) {
                                    text = d.getString("content");
                                }
                                if (text != null) {
                                    fullText.append(text);
                                }
                            }
                        } catch (Exception ignore) {
                            // 非 JSON delta 忽略拼接
                        }
                    }
                } else if (line.isEmpty()) {
                    currentEvent = "message";
                }
            }
        } finally {
            try {
                reader.close();
            } catch (Exception ignore) {
                // ignore
            }
            try {
                conn.disconnect();
            } catch (Exception ignore) {
                // ignore
            }
        }
        if (handle != null && handle.isCancelled()) {
            throw new TaskCancelledException("任务已取消");
        }
        return fullText.toString();
    }

    private void applyAuth(HttpURLConnection conn) {
        String key = props.getApiKey();
        if (key != null && !key.trim().isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + key.trim());
        }
    }

    private String httpJson(String method, String url, String jsonBody) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(props.getConnectTimeoutMs());
        conn.setReadTimeout(props.getReadTimeoutMs());
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("Accept", "application/json");
        applyAuth(conn);
        if (jsonBody != null) {
            conn.setDoOutput(true);
            byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
            OutputStream os = conn.getOutputStream();
            try {
                os.write(bytes);
                os.flush();
            } finally {
                os.close();
            }
        }
        int code = conn.getResponseCode();
        InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
        String body = readAll(in);
        conn.disconnect();
        if (code < 200 || code >= 300) {
            log.warn("Hermes {} {} -> {} {}", method, url, code, body);
            throw new RuntimeException("Hermes HTTP " + code + ": " + body);
        }
        return body;
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) {
            return "";
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
        try {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line);
            }
            return sb.toString();
        } finally {
            reader.close();
        }
    }

    private static String trimSlash(String base) {
        if (base == null) {
            return "";
        }
        String s = base.trim();
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        return s;
    }
}
