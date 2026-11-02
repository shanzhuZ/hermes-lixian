package com.example.aw.chat.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface TaskToolEventMapper {

    int upsertEvent(@Param("taskId") String taskId,
                    @Param("toolCallId") String toolCallId,
                    @Param("toolName") String toolName,
                    @Param("mcpServer") String mcpServer,
                    @Param("toolArgs") String toolArgs,
                    @Param("toolOutput") String toolOutput,
                    @Param("status") String status,
                    @Param("durationMs") Integer durationMs);

    List<Map<String, Object>> selectByTaskId(@Param("taskId") String taskId,
                                             @Param("limit") int limit);
}
