package com.example.lixian.service;

import com.example.lixian.entity.Result;
import org.elasticsearch.action.index.IndexRequest;
import org.elasticsearch.action.index.IndexResponse;
import org.elasticsearch.action.search.SearchRequest;
import org.elasticsearch.action.search.SearchResponse;
import org.elasticsearch.action.update.UpdateRequest;
import org.elasticsearch.action.update.UpdateResponse;
import org.elasticsearch.client.RequestOptions;
import org.elasticsearch.client.RestHighLevelClient;
import org.elasticsearch.common.xcontent.XContentType;
import org.elasticsearch.index.query.BoolQueryBuilder;
import org.elasticsearch.index.query.QueryBuilders;
import org.elasticsearch.index.reindex.BulkByScrollResponse;
import org.elasticsearch.index.reindex.DeleteByQueryRequest;
import org.elasticsearch.search.SearchHit;
import org.elasticsearch.search.aggregations.AggregationBuilders;
import org.elasticsearch.search.aggregations.bucket.terms.Terms;
import org.elasticsearch.search.aggregations.metrics.Cardinality;
import org.elasticsearch.search.builder.SearchSourceBuilder;
import org.elasticsearch.search.collapse.CollapseBuilder;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 问答历史写入 ES 索引 sz_lixian_xw。
 */
@Service
public class ChatHistoryEsService {

    private static final Logger log = LoggerFactory.getLogger(ChatHistoryEsService.class);

    /** 会话详情最多返回的轮数 */
    private static final int DETAIL_MAX_TURNS = 1000;

    private final RestHighLevelClient restHighLevelClient5602;

    @Value("${es.index:sz_lixian_xw}")
    private String indexName;

    public ChatHistoryEsService(@Qualifier("restHighLevelClient5602") RestHighLevelClient restHighLevelClient5602) {
        this.restHighLevelClient5602 = restHighLevelClient5602;
    }

    /**
     * 写入一条已完成（status=end）的问答记录。文档 _id = taskId，重复写入会覆盖。
     */
    public void save(String userId, String taskId, String sessionId, String question, String content) {
        saveWithStatus(userId, taskId, sessionId, question, content, "end");
    }

    /**
     * 创建任务时插入一条 status=running 的记录（content 为空），add_date 为创建时间。
     */
    public void saveRunning(String userId, String taskId, String sessionId, String question) {
        saveWithStatus(userId, taskId, sessionId, question, "", "running");
    }

    private void saveWithStatus(String userId, String taskId, String sessionId, String question,
                                String content, String status) {
        if (taskId == null || taskId.trim().isEmpty()) {
            log.warn("跳过 ES 入库：taskId 为空");
            return;
        }
        try {
            IndexRequest request = new IndexRequest(indexName)
                    .id(taskId)
                    .source(buildDoc(userId, taskId, sessionId, question, content, status), XContentType.JSON);

            IndexResponse response = restHighLevelClient5602.index(request, RequestOptions.DEFAULT);
            log.info("ES 入库成功 index={} id={} status={} result={}", indexName, taskId, status, response.getResult());
        } catch (Exception e) {
            // ES 8.x + RestHighLevelClient 7.x：写入常已成功(201)，仅响应体解析失败
            if (isEsVersionParseNoise(e)) {
                log.info("ES 入库成功(兼容模式，忽略响应解析异常) index={} id={} status={}", indexName, taskId, status);
                return;
            }
            // 真正失败不影响主流程
            log.error("ES 入库失败 taskId={}", taskId, e);
        }
    }

    /**
     * 任务进入终态时更新状态：局部更新 status / content（add_date 保持创建时间不变）。
     * 若创建时的插入失败导致文档不存在，则以完整文档 upsert 补写。
     * status：end / cancelled / failed。
     */
    public void updateStatus(String userId, String taskId, String sessionId, String question,
                             String content, String status) {
        if (taskId == null || taskId.trim().isEmpty()) {
            log.warn("跳过 ES 状态更新：taskId 为空");
            return;
        }
        try {
            Map<String, Object> partial = new HashMap<String, Object>();
            partial.put("status", status);
            partial.put("content", content == null ? "" : content);

            UpdateRequest request = new UpdateRequest(indexName, taskId)
                    .doc(partial, XContentType.JSON)
                    .upsert(buildDoc(userId, taskId, sessionId, question, content, status), XContentType.JSON)
                    .retryOnConflict(3);

            UpdateResponse response = restHighLevelClient5602.update(request, RequestOptions.DEFAULT);
            log.info("ES 更新任务状态成功 index={} id={} status={} result={}",
                    indexName, taskId, status, response.getResult());
        } catch (Exception e) {
            // ES 8.x + RestHighLevelClient 7.x：更新常已成功，仅响应体解析失败
            if (isEsVersionParseNoise(e)) {
                log.info("ES 更新任务状态成功(兼容模式，忽略响应解析异常) index={} id={} status={}",
                        indexName, taskId, status);
                return;
            }
            // 真正失败不影响主流程
            log.error("ES 更新任务状态失败 taskId={} status={}", taskId, status, e);
        }
    }

    private Map<String, Object> buildDoc(String userId, String taskId, String sessionId, String question,
                                         String content, String status) {
        Map<String, Object> doc = new HashMap<String, Object>();
        doc.put("user_id", userId == null ? "" : userId);
        doc.put("task_id", taskId);
        doc.put("session_id", sessionId == null ? "" : sessionId);
        doc.put("question", question == null ? "" : question);
        doc.put("content", content == null ? "" : content);
        doc.put("status", status);
        doc.put("add_date", formatNow());
        return doc;
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
     * 历史分页查询：默认按 session_id 聚合（折叠），每个会话只返回最新一轮问答，
     * 并附带 turnCount（该会话总轮数）；按 add_date 倒序。
     * userId / keyword 为可选过滤条件。
     */
    public Result getChatHistory(String userId, String keyword, Integer pageNo, Integer pageSize) {
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
            // ES 默认 max_result_window=10000
            if ((long) pageNo * pageSize > 10000) {
                throw new IllegalArgumentException("分页过深：pageNo * pageSize 不能超过 10000");
            }

            BoolQueryBuilder bool = QueryBuilders.boolQuery();
            if (userId != null && !userId.trim().isEmpty()) {
                bool.must(QueryBuilders.termQuery("user_id.keyword", userId.trim()));
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
            // 按 session_id 折叠：每个会话取排序第一条（add_date 最新）
            sourceBuilder.collapse(new CollapseBuilder("session_id.keyword"));
            sourceBuilder.sort("add_date.keyword", SortOrder.DESC);
            sourceBuilder.sort("task_id.keyword", SortOrder.DESC);
            // 折叠后 hits.total 仍是原始文档数，会话总数用 cardinality 统计
            sourceBuilder.aggregation(AggregationBuilders.cardinality("session_cnt")
                    .field("session_id.keyword").precisionThreshold(40000));

            SearchRequest searchRequest = new SearchRequest(indexName);
            searchRequest.source(sourceBuilder);

            SearchResponse response = restHighLevelClient5602.search(searchRequest, RequestOptions.DEFAULT);
            Cardinality sessionCnt = response.getAggregations().get("session_cnt");
            long total = sessionCnt.getValue();
            List<Map<String, Object>> records = new ArrayList<Map<String, Object>>();
            List<String> sessionIds = new ArrayList<String>();
            for (SearchHit hit : response.getHits().getHits()) {
                Map<String, Object> row = new HashMap<String, Object>();
                if (hit.getSourceAsMap() != null) {
                    row.putAll(hit.getSourceAsMap());
                }
                row.put("esId", hit.getId());
                records.add(row);
                Object sid = row.get("session_id");
                if (sid != null) {
                    sessionIds.add(String.valueOf(sid));
                }
            }

            // 本页各会话的总轮数（不受 keyword / userId 过滤影响）
            if (!sessionIds.isEmpty()) {
                SearchSourceBuilder cntBuilder = new SearchSourceBuilder();
                cntBuilder.query(QueryBuilders.termsQuery("session_id.keyword", sessionIds));
                cntBuilder.size(0);
                cntBuilder.aggregation(AggregationBuilders.terms("by_session")
                        .field("session_id.keyword").size(sessionIds.size()));
                SearchRequest cntRequest = new SearchRequest(indexName);
                cntRequest.source(cntBuilder);
                SearchResponse cntResp = restHighLevelClient5602.search(cntRequest, RequestOptions.DEFAULT);
                Terms bySession = cntResp.getAggregations().get("by_session");
                Map<String, Long> turnCountMap = new HashMap<String, Long>();
                for (Terms.Bucket b : bySession.getBuckets()) {
                    turnCountMap.put(b.getKeyAsString(), Long.valueOf(b.getDocCount()));
                }
                for (Map<String, Object> row : records) {
                    Long c = turnCountMap.get(String.valueOf(row.get("session_id")));
                    row.put("turnCount", c == null ? Long.valueOf(1L) : c);
                }
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

    /**
     * 会话详情：按 session_id 聚合该会话下所有问答，按 add_date 升序（对话时间线）。
     * records 为单个对象：sessionId / userId / title(首轮问题) / turnCount / firstAddDate / lastAddDate / turns[]。
     */
    public Result getChatSessionDetail(String sessionId) {
        Result result = new Result();
        try {
            if (sessionId == null || sessionId.trim().isEmpty()) {
                throw new IllegalArgumentException("sessionId 不能为空");
            }
            String sid = sessionId.trim();

            SearchSourceBuilder sourceBuilder = new SearchSourceBuilder();
            sourceBuilder.query(QueryBuilders.boolQuery()
                    .filter(QueryBuilders.termQuery("session_id.keyword", sid)));
            sourceBuilder.size(DETAIL_MAX_TURNS);
            sourceBuilder.trackTotalHits(true);
            sourceBuilder.sort("add_date.keyword", SortOrder.ASC);
            sourceBuilder.sort("task_id.keyword", SortOrder.ASC);

            SearchRequest searchRequest = new SearchRequest(indexName);
            searchRequest.source(sourceBuilder);
            SearchResponse response = restHighLevelClient5602.search(searchRequest, RequestOptions.DEFAULT);

            long total = response.getHits().getTotalHits().value;
            List<Map<String, Object>> turns = new ArrayList<Map<String, Object>>();
            for (SearchHit hit : response.getHits().getHits()) {
                Map<String, Object> row = new HashMap<String, Object>();
                if (hit.getSourceAsMap() != null) {
                    row.putAll(hit.getSourceAsMap());
                }
                row.put("esId", hit.getId());
                turns.add(row);
            }

            if (turns.isEmpty()) {
                result.setCode(404);
                result.setMessage("session 不存在: " + sid);
                result.setTotalCount(0);
                result.setTotalPage(0);
                result.setRecords(null);
                return result;
            }

            Map<String, Object> first = turns.get(0);
            Map<String, Object> last = turns.get(turns.size() - 1);
            Map<String, Object> detail = new LinkedHashMap<String, Object>();
            detail.put("sessionId", sid);
            detail.put("userId", first.get("user_id"));
            detail.put("title", first.get("question"));
            detail.put("turnCount", Long.valueOf(total));
            detail.put("firstAddDate", first.get("add_date"));
            detail.put("lastAddDate", last.get("add_date"));
            detail.put("turns", turns);

            result.setCode(200);
            result.setMessage("success");
            result.setTotalCount(turns.size());
            result.setTotalPage(1);
            result.setRecords(detail);
            return result;
        } catch (Exception e) {
            log.error("查询会话详情失败 sessionId={}", sessionId, e);
            result.setCode(500);
            result.setMessage(e.getMessage() == null ? "查询失败" : e.getMessage());
            result.setTotalCount(0);
            result.setTotalPage(0);
            result.setRecords(null);
            return result;
        }
    }

    /**
     * 按 sessionId 删除 ES 中该会话的全部历史问答（delete-by-query）。
     * ES 8.x + RestHighLevelClient 7.x：删除请求常已执行成功，仅响应体解析失败，
     * 此时捕获版本不兼容异常，并以「删除后再统计剩余条数」为准判定结果。
     * records：{sessionId, found(删除前条数), deleted(实际删除条数)}。
     */
    public Result deleteChatSession(String sessionId) {
        Result result = new Result();
        String sid = sessionId == null ? "" : sessionId.trim();
        try {
            if (sid.isEmpty()) {
                throw new IllegalArgumentException("sessionId 不能为空");
            }

            long found = countBySession(sid);
            if (found == 0) {
                result.setCode(404);
                result.setMessage("session 无历史记录或已删除: " + sid);
                result.setTotalCount(0);
                result.setTotalPage(0);
                result.setRecords(null);
                return result;
            }

            try {
                DeleteByQueryRequest request = new DeleteByQueryRequest(indexName);
                request.setQuery(QueryBuilders.termQuery("session_id.keyword", sid));
                // 删完立即刷新，保证随后的统计能反映删除结果
                request.setRefresh(true);
                // 版本冲突（并发写入同一文档）时继续，最后以剩余条数为准
                request.setConflicts("proceed");
                BulkByScrollResponse response = restHighLevelClient5602.deleteByQuery(request, RequestOptions.DEFAULT);
                log.info("ES 删除会话历史 index={} sessionId={} deleted={}", indexName, sid, response.getDeleted());
            } catch (Exception e) {
                if (!isEsVersionParseNoise(e)) {
                    throw e;
                }
                log.info("ES 删除会话历史(兼容模式，忽略响应解析异常) index={} sessionId={}", indexName, sid);
            }

            long remain = countBySession(sid);
            Map<String, Object> detail = new LinkedHashMap<String, Object>();
            detail.put("sessionId", sid);
            detail.put("found", Long.valueOf(found));
            detail.put("deleted", Long.valueOf(found - remain));
            if (remain > 0) {
                result.setCode(500);
                result.setMessage("部分记录删除失败，剩余 " + remain + " 条，请重试");
            } else {
                result.setCode(200);
                result.setMessage("success");
            }
            result.setTotalCount((int) (found - remain));
            result.setTotalPage(1);
            result.setRecords(detail);
            return result;
        } catch (Exception e) {
            log.error("删除会话历史失败 sessionId={}", sid, e);
            result.setCode(500);
            result.setMessage(e.getMessage() == null ? "删除失败" : e.getMessage());
            result.setTotalCount(0);
            result.setTotalPage(0);
            result.setRecords(null);
            return result;
        }
    }

    /** 统计某 session 在索引中的文档数。 */
    private long countBySession(String sid) throws Exception {
        SearchSourceBuilder sourceBuilder = new SearchSourceBuilder();
        sourceBuilder.query(QueryBuilders.boolQuery()
                .filter(QueryBuilders.termQuery("session_id.keyword", sid)));
        sourceBuilder.size(0);
        sourceBuilder.trackTotalHits(true);
        SearchRequest searchRequest = new SearchRequest(indexName);
        searchRequest.source(sourceBuilder);
        SearchResponse response = restHighLevelClient5602.search(searchRequest, RequestOptions.DEFAULT);
        return response.getHits().getTotalHits().value;
    }

    private static String formatNow() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date());
    }
}
