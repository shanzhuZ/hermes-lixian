package com.example.lixian.model;

import java.util.ArrayList;
import java.util.List;

/**
 * 一级标签：人员信息查询 / 组织信息查询。
 */
public class QueryTagLevel1 {

    private String id;
    private String name;
    private List<QueryTagGroup> groups = new ArrayList<QueryTagGroup>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<QueryTagGroup> getGroups() {
        return groups;
    }

    public void setGroups(List<QueryTagGroup> groups) {
        this.groups = groups;
    }
}
