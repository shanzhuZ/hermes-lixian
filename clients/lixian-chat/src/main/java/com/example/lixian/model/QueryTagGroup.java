package com.example.lixian.model;

import java.util.ArrayList;
import java.util.List;

/**
 * 一级下的类目分块（对应 Word「二级类目」），仅作展示分组。
 */
public class QueryTagGroup {

    private String name;
    private List<QueryTagItem> tags = new ArrayList<QueryTagItem>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<QueryTagItem> getTags() {
        return tags;
    }

    public void setTags(List<QueryTagItem> tags) {
        this.tags = tags;
    }
}
