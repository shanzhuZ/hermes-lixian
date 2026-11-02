package com.example.aw.resolver;

import com.coxautodev.graphql.tools.GraphQLQueryResolver;
import org.springframework.stereotype.Component;

/**
 * GraphQL 占位查询；对话业务请走 REST：/api/chat/**。
 */
@Component
public class CollectGraphqlPingResolver implements GraphQLQueryResolver {

    public String ping() {
        return "ok";
    }
}
