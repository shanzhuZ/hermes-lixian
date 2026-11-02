package com.example.aw.gateway;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.function.BiConsumer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 调用 Hermes Agent API Server：创建 session、同步 chat、流式 chat/stream。
 * 多轮续聊靠同一 hermes_session_id。
 */
@Component
public class HermesGatewayClient {

    private static final Logger log = LoggerFactory.getLogger(HermesGatewayClient.class);

    /** 从 POST /api/sessions 响应里抠 id / session_id */
    private static final Pattern SESSION_ID_PATTERN =
            Pattern.compile("\"(?:id|session_id)\"\\s*:\\s*\"([^\"]+)\"");

    @Value("${hermes.base-url:http://127.0.0.1:8642}")
    private String baseUrl;

    @Value("${hermes.api-key:}")
    private String apiKey;

    @Value("${hermes.connect-timeout-ms:10000}")
    private int connectTimeoutMs;

    @Value("${hermes.read-timeout-ms:1800000}")
    private int readTimeoutMs;

    /** 在 Hermes 侧新建空会话，返回 hermes_session_id */
    public String createSession() throws Exception {
        String body = httpJson("POST", trimSlash(baseUrl) + "/api/sessions", "{}");
        Matcher m = SESSION_ID_PATTERN.matcher(body);
        if (!m.find()) {
            throw new RuntimeException("无法解析 session_id: " + body);
        }
        return m.group(1);
    }

    /**
     * 在已有 Hermes session 上跑一轮同步对话，返回助手正文。
     * Hermes 负责加载该 session 历史；业务 task_id 与 Hermes 原生 session 无关。
     */
    public String chatSync(String hermesSessionId, String userMessage) throws Exception {
        if (hermesSessionId == null || hermesSessionId.trim().isEmpty()) {
            throw new IllegalArgumentException("hermesSessionId 不能为空");
        }
        if (userMessage == null || userMessage.trim().isEmpty()) {
            throw new IllegalArgumentException("userMessage 不能为空");
        }
        JSONObject req = new JSONObject();
        req.put("message", userMessage);
        String url = trimSlash(baseUrl) + "/api/sessions/" + hermesSessionId.trim() + "/chat";
        String body = httpJson("POST", url, req.toJSONString());
        return extractAssistantText(body);
    }

    /**
     * 流式对话：消费 Hermes SSE /api/sessions/{id}/chat/stream，逐事件回调。
     * <p>
     * Hermes SSE 格式：每行 "event: xxx\ndata: {...}\n\n"
     * 常见事件名：assistant.delta / tool_call / tool_result / done / error
     *
     * @param hermesSessionId Hermes 会话 ID
     * @param userMessage     发给 Hermes 的用户消息（含 skill 提示）
     * @param onEvent         回调 (eventName, dataJson)；在 IO 线程中同步调用
     * @return 最终拼接的完整 assistant 文本（可能为空串；落库由 Hook 负责）
     */
    public String chatStream(String hermesSessionId, String userMessage,
                             BiConsumer<String, String> onEvent) throws Exception {
        if (hermesSessionId == null || hermesSessionId.trim().isEmpty()) {
            throw new IllegalArgumentException("hermesSessionId 不能为空");
        }
        JSONObject req = new JSONObject();
        req.put("message", userMessage);
        String url = trimSlash(baseUrl) + "/api/sessions/" + hermesSessionId.trim() + "/chat/stream";

        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(connectTimeoutMs);
        conn.setReadTimeout(readTimeoutMs);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("Accept", "text/event-stream");
        if (apiKey != null && !apiKey.trim().isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + apiKey.trim());
        }

        byte[] bytes = userMessage == null ? new byte[0] : req.toJSONString().getBytes(StandardCharsets.UTF_8);
        OutputStream os = conn.getOutputStream();
        try {
            os.write(bytes);
            os.flush();
        } finally {
            os.close();
        }

        int code = conn.getResponseCode();
        if (code < 200 || code >= 300) {
            String errBody = readAll(code < 400 ? conn.getInputStream() : conn.getErrorStream());
            throw new RuntimeException("Hermes stream HTTP " + code + ": " + errBody);
        }

        // 逐行读 SSE
        StringBuilder fullText = new StringBuilder();
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
        try {
            String currentEvent = "message";
            String line;
            while ((line = reader.readLine()) != null) {
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
                    // 拼接 assistant delta 文本
                    if ("assistant.delta".equals(currentEvent) || "delta".equals(currentEvent)) {
                        try {
                            JSONObject d = JSON.parseObject(data);
                            String text = null;
                            if (d != null) {
                                // Hermes 原生字段是 delta；兼容 text/content
                                text = d.getString("delta");
                                if (text == null) {
                                    text = d.getString("text");
                                }
                                if (text == null) {
                                    text = d.getString("content");
                                }
                            }
                            if (text != null) {
                                fullText.append(text);
                            }
                        } catch (Exception ignore) {
                            fullText.append(data);
                        }
                    } else if ("assistant.completed".equals(currentEvent)) {
                        try {
                            JSONObject d = JSON.parseObject(data);
                            String content = d != null ? d.getString("content") : null;
                            if (content != null && !content.isEmpty() && fullText.length() == 0) {
                                fullText.append(content);
                            }
                        } catch (Exception ignore) {
                        }
                    }
                }
                // 空行：SSE 事件边界，重置 event
                if (line.isEmpty()) {
                    currentEvent = "message";
                }
            }
        } finally {
            reader.close();
        }
        return fullText.toString();
    }

    /** 兼容多种响应字段名：final_response / message.content / content / response */
    private String extractAssistantText(String body) {
        if (body == null || body.isEmpty()) {
            return "";
        }
        try {
            JSONObject obj = JSON.parseObject(body);
            if (obj == null) {
                return body;
            }
            if (obj.containsKey("final_response")) {
                return obj.getString("final_response");
            }
            if (obj.containsKey("message") && obj.get("message") instanceof JSONObject) {
                JSONObject msg = obj.getJSONObject("message");
                if (msg != null && msg.containsKey("content")) {
                    return msg.getString("content");
                }
            }
            if (obj.containsKey("content")) {
                return obj.getString("content");
            }
            if (obj.containsKey("response")) {
                return obj.getString("response");
            }
            return body;
        } catch (Exception e) {
            log.warn("解析 Hermes 响应失败，返回原文: {}", e.getMessage());
            return body;
        }
    }

    /** JSON POST；有 api-key 则带 Bearer（需与 Hermes API_SERVER_KEY 一致） */
    private String httpJson(String method, String url, String jsonBody) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod(method);
        conn.setDoOutput(true);
        conn.setConnectTimeout(connectTimeoutMs);
        conn.setReadTimeout(readTimeoutMs);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        if (apiKey != null && !apiKey.trim().isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + apiKey.trim());
        }

        byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
        OutputStream os = conn.getOutputStream();
        try {
            os.write(bytes);
            os.flush();
        } finally {
            os.close();
        }

        int code = conn.getResponseCode();
        InputStream in = code < 400 ? conn.getInputStream() : conn.getErrorStream();
        String resp = readAll(in);
        if (code < 200 || code >= 300) {
            throw new RuntimeException("Hermes HTTP " + code + ": " + resp);
        }
        return resp;
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) {
            return "";
        }
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) >= 0) {
            bos.write(buf, 0, n);
        }
        in.close();
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String trimSlash(String url) {
        if (url == null) {
            return "";
        }
        String u = url.trim();
        while (u.endsWith("/")) {
            u = u.substring(0, u.length() - 1);
        }
        return u;
    }
}
