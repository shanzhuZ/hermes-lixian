package com.example.lixian.service;

import com.example.lixian.entity.Result;
import org.elasticsearch.action.index.IndexRequest;
import org.elasticsearch.action.index.IndexResponse;
import org.elasticsearch.action.search.SearchRequest;
import org.elasticsearch.action.search.SearchResponse;
import org.elasticsearch.client.RequestOptions;
import org.elasticsearch.client.RestHighLevelClient;
import org.elasticsearch.common.xcontent.XContentType;
import org.elasticsearch.index.query.BoolQueryBuilder;
import org.elasticsearch.index.query.QueryBuilders;
import org.elasticsearch.search.SearchHit;
import org.elasticsearch.search.builder.SearchSourceBuilder;
import org.elasticsearch.search.sort.SortOrder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 问答历史写入 ES 索引 sz_lixian_xw。
 */
@Service
public class ChatHistoryEsService {

    private static final Logger log = LoggerFactory.getLogger(ChatHistoryEsService.class);

    private final RestHighLevelClient restHighLevelClient5602;

    @Value("${es.index:sz_lixian_xw}")
    private String indexName;

    public ChatHistoryEsService(@Qualifier("restHighLevelClient5602") RestHighLevelClient restHighLevelClient5602) {
        this.restHighLevelClient5602 = restHighLevelClient5602;
    }

    /**
     * 写入一条问答记录。文档 _id = taskId，重复写入会覆盖。
     */
    public void save(String userId, String taskId, String sessionId, String question, String content) {
        if (taskId == null || taskId.trim().isEmpty()) {
            log.warn("跳过 ES 入库：taskId 为空");
            return;
        }
        try {
            Map<String, Object> doc = new HashMap<String, Object>();
            doc.put("user_id", userId == null ? "" : userId);
            doc.put("task_id", taskId);
            doc.put("session_id", sessionId == null ? "" : sessionId);
            doc.put("question", question == null ? "" : question);
            doc.put("content", content == null ? "" : content);
            doc.put("add_date", formatNow());

            IndexRequest request = new IndexRequest(indexName)
                    .id(taskId)
                    .source(doc, XContentType.JSON);

            IndexResponse response = restHighLevelClient5602.index(request, RequestOptions.DEFAULT);
            log.info("ES 入库成功 index={} id={} result={}", indexName, taskId, response.getResult());
        } catch (Exception e) {
            // ES 8.x + RestHighLevelClient 7.x：写入常已成功(201)，仅响应体解析失败
            if (isEsVersionParseNoise(e)) {
                log.info("ES 入库成功(兼容模式，忽略响应解析异常) index={} id={}", indexName, taskId);
                return;
            }
            // 真正失败不影响主流程
            log.error("ES 入库失败 taskId={}", taskId, e);
        }
    }

    /**
     * 判断是否为「HTTP 已成功，客户端解析响应失败」这类版本不兼容噪声。
     */
    private static boolean isEsVersionParseNoise(Throwable e) {
        Throwable cur = e;
        while (cur != null) {
            String msg = cur.getMessage();
            if (msg != null) {
                if (msg.contains("Unable to parse response body")
                        || msg.contains("201 Created")
                        || msg.contains("200 OK")) {
                    return true;
                }
            }
            cur = cur.getCause();
        }
        return false;
    }

    /**
     * 历史分页查询。
     */
    public Result getChatHistory(String userId, String sessionId, String taskId,
                                 String keyword, Integer pageNo, Integer pageSize) {
        Result result = new Result();
        try {
            if (pageNo == null || pageNo < 1) {
                pageNo = 1;
            }
            if (pageSize == null || pageSize < 1) {
                pageSize = 10;
            }
            if (pageSize > 100) {
                pageSize = 100;
            }

            BoolQueryBuilder bool = QueryBuilders.boolQuery();
            if (userId != null && !userId.trim().isEmpty()) {
                bool.must(QueryBuilders.termQuery("user_id.keyword", userId.trim()));
            }
            if (sessionId != null && !sessionId.trim().isEmpty()) {
                bool.must(QueryBuilders.termQuery("session_id.keyword", sessionId.trim()));
            }
            if (taskId != null && !taskId.trim().isEmpty()) {
                bool.must(QueryBuilders.termQuery("task_id.keyword", taskId.trim()));
            }
            if (keyword != null && !keyword.trim().isEmpty()) {
                String kw = keyword.trim();
                bool.must(QueryBuilders.boolQuery()
                        .should(QueryBuilders.matchQuery("question", kw))
                        .should(QueryBuilders.matchQuery("content", kw))
                        .minimumShouldMatch(1));
            }
            if (!bool.hasClauses()) {
                bool.must(QueryBuilders.matchAllQuery());
            }

            int from = (pageNo - 1) * pageSize;
            SearchSourceBuilder sourceBuilder = new SearchSourceBuilder();
            sourceBuilder.query(bool);
            sourceBuilder.from(from);
            sourceBuilder.size(pageSize);
            sourceBuilder.trackTotalHits(true);
            sourceBuilder.sort("add_date.keyword", SortOrder.DESC);

            SearchRequest searchRequest = new SearchRequest(indexName);
            searchRequest.source(sourceBuilder);

            SearchResponse response = restHighLevelClient5602.search(searchRequest, RequestOptions.DEFAULT);
            long total = response.getHits().getTotalHits().value;
            List<Map<String, Object>> records = new ArrayList<Map<String, Object>>();
            for (SearchHit hit : response.getHits().getHits()) {
                Map<String, Object> row = new HashMap<String, Object>();
                if (hit.getSourceAsMap() != null) {
                    row.putAll(hit.getSourceAsMap());
                }
                row.put("esId", hit.getId());
                records.add(row);
            }

            int totalPage = (int) ((total + pageSize - 1) / pageSize);
            result.setCode(200);
            result.setMessage("success");
            result.setTotalCount((int) total);
            result.setTotalPage(totalPage);
            result.setRecords(records);
            return result;
        } catch (Exception e) {
            log.error("查询聊天历史失败", e);
            result.setCode(500);
            result.setMessage(e.getMessage() == null ? "查询失败" : e.getMessage());
            result.setTotalCount(0);
            result.setTotalPage(0);
            result.setRecords(new ArrayList<Map<String, Object>>());
            return result;
        }
    }

    private static String formatNow() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date());
    }
}
