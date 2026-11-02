package com.example.aw.chat.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface TaskHitMapper {

    int upsertHit(@Param("taskId") String taskId,
                  @Param("skillName") String skillName,
                  @Param("hitType") String hitType,
                  @Param("platform") String platform,
                  @Param("title") String title,
                  @Param("summary") String summary,
                  @Param("dedupeKey") String dedupeKey,
                  @Param("payloadJson") String payloadJson,
                  @Param("sourceTool") String sourceTool,
                  @Param("toolEventId") String toolEventId);

    List<Map<String, Object>> selectByTaskId(@Param("taskId") String taskId,
                                             @Param("hitType") String hitType,
                                             @Param("platform") String platform,
                                             @Param("limit") int limit);
}
