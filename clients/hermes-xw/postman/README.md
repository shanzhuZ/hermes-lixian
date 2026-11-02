# Postman 测试说明

## 导入

1. 打开 Postman → **Import**
2. 选择 [`hermes-xw-chat.postman_collection.json`](hermes-xw-chat.postman_collection.json)
3. Collection 变量 `baseUrl` 默认：`http://127.0.0.1:4378`

## 推荐顺序

1. **列出四个 Skill 触发词**
2. **新建会话**（自动把 `sessionId` / `hermesSessionId` 写入 Collection 变量）
3. **Ask - 法案研判**（自动写入 `taskId`）
4. **查询任务（轮询）** 直到 `status=done` 或 `failed`
5. 需要时：**同 Session 追问** / **会话消息历史**

## 请求体速查

新建会话：

```json
{ "title": "Postman 测试会话" }
```

提问：

```json
{
  "sessionId": "{{sessionId}}",
  "message": "研判 H.R.9028 …",
  "skill": "bill-impact-analysis"
}
```

`skill` 可选值：

- `org-portrait`
- `account-portrait`
- `event-spread-impact`
- `bill-impact-analysis`

## 注意

- Ask 是**异步**：先返回 `taskId`，再用 Get Task 拉答案；也可订 SSE `/stream`。
- 过程数据：`/tools`、`/hits`（Hermes 插件直连 MySQL）；终稿在 task `answerMarkdown`（Hook 写）。
- 研判可能较久，轮询间隔建议 5～10 秒。
- 网关与 Hermes API Server、MySQL 需先就绪。
