package com.example.lixian.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.lixian.model.QueryTagGroup;
import com.example.lixian.model.QueryTagItem;
import com.example.lixian.model.QueryTagLevel1;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 加载 classpath:query-tags.json，供页面渲染一级/二级标签；三级 question 点击后发给 ask。
 */
@Service
public class QueryTagService {

    private static final Logger log = LoggerFactory.getLogger(QueryTagService.class);
    private static final String RESOURCE = "query-tags.json";

    private List<QueryTagLevel1> items = Collections.emptyList();
    private String loadError;

    @PostConstruct
    public void init() {
        try {
            ClassPathResource resource = new ClassPathResource(RESOURCE);
            if (!resource.exists()) {
                loadError = "资源不存在: " + RESOURCE;
                log.error(loadError);
                items = Collections.emptyList();
                return;
            }
            String json = readUtf8(resource.getInputStream());
            JSONObject root = JSON.parseObject(json);
            JSONArray arr = root == null ? null : root.getJSONArray("items");
            if (arr == null || arr.isEmpty()) {
                loadError = "query-tags.json 中 items 为空";
                log.error(loadError);
                items = Collections.emptyList();
                return;
            }
            List<QueryTagLevel1> list = new ArrayList<QueryTagLevel1>();
            for (int i = 0; i < arr.size(); i++) {
                JSONObject l1 = arr.getJSONObject(i);
                if (l1 == null) {
                    continue;
                }
                QueryTagLevel1 level1 = new QueryTagLevel1();
                level1.setId(l1.getString("id"));
                level1.setName(l1.getString("name"));
                JSONArray groups = l1.getJSONArray("groups");
                if (groups != null) {
                    for (int g = 0; g < groups.size(); g++) {
                        JSONObject gObj = groups.getJSONObject(g);
                        if (gObj == null) {
                            continue;
                        }
                        QueryTagGroup group = new QueryTagGroup();
                        group.setName(gObj.getString("name"));
                        JSONArray tags = gObj.getJSONArray("tags");
                        if (tags != null) {
                            for (int t = 0; t < tags.size(); t++) {
                                JSONObject tObj = tags.getJSONObject(t);
                                if (tObj == null) {
                                    continue;
                                }
                                QueryTagItem item = new QueryTagItem();
                                item.setId(tObj.getString("id"));
                                item.setLabel(tObj.getString("label"));
                                item.setQuestion(tObj.getString("question"));
                                item.setEnabled(tObj.getBooleanValue("enabled"));
                                group.getTags().add(item);
                            }
                        }
                        level1.getGroups().add(group);
                    }
                }
                list.add(level1);
            }
            items = Collections.unmodifiableList(list);
            loadError = null;
            log.info("已加载查询标签: {} 个一级分类", items.size());
        } catch (Exception e) {
            loadError = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            log.error("加载 {} 失败", RESOURCE, e);
            items = Collections.emptyList();
        }
    }

    public List<QueryTagLevel1> listTags() {
        return items;
    }

    public String getLoadError() {
        return loadError;
    }

    private static String readUtf8(InputStream in) throws Exception {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        int n;
        try {
            while ((n = in.read(chunk)) >= 0) {
                buf.write(chunk, 0, n);
            }
        } finally {
            in.close();
        }
        return new String(buf.toByteArray(), StandardCharsets.UTF_8);
    }
}
