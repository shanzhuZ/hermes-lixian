package com.example.lixian.resolver;

import com.coxautodev.graphql.tools.GraphQLQueryResolver;
import com.example.lixian.entity.Result;
import com.example.lixian.service.ChatHistoryEsService;
import com.example.lixian.service.ChatService;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.CrossOrigin;

import javax.annotation.Resource;

/**
 * 问答历史 GraphQL 查询（风格对齐 aw）。
 */
@Component
@CrossOrigin
public class ChatHistoryResolver implements GraphQLQueryResolver {

    @Resource
    private ChatHistoryEsService chatHistoryEsService;

    @Resource
    private ChatService chatService;

    /**
     * 分页查询历史：按 sessionId 聚合，每个会话返回最新一轮 + turnCount，按 add_date 倒序。
     * userId 精确过滤；keyword 模糊匹配 question/content。
     */
    public Result getChatHistory(String userId, String keyword, Integer pageNo, Integer pageSize) {
        return chatHistoryEsService.getChatHistory(userId, keyword, pageNo, pageSize);
    }

    /**
     * 会话详情：按 sessionId 聚合该会话全部问答，按 add_date 升序。
     */
    public Result getChatSessionDetail(String sessionId) {
        return chatHistoryEsService.getChatSessionDetail(sessionId);
    }

    /**
     * 按 sessionId 删除该会话的全部历史任务（ES: sz_lixian_xw）。
     * 会话仍有进行中任务时返回 code=409，需先取消。
     */
    public Result deleteChatSession(String sessionId) {
        return chatService.deleteChatHistory(sessionId);
    }
}
