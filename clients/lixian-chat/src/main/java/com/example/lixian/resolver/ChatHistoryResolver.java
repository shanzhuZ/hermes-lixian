package com.example.lixian.resolver;

import com.coxautodev.graphql.tools.GraphQLQueryResolver;
import com.example.lixian.entity.Result;
import com.example.lixian.service.ChatHistoryEsService;
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

    /**
     * 分页查询历史。
     * userId / sessionId / taskId 精确过滤；keyword 模糊匹配 question/content。
     */
    public Result getChatHistory(String userId, String sessionId, String taskId,
                                 String keyword, Integer pageNo, Integer pageSize) {
        return chatHistoryEsService.getChatHistory(userId, sessionId, taskId, keyword, pageNo, pageSize);
    }
}
