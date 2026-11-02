package com.example.aw.chat.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface ChatTaskMapper {

    int insertTask(@Param("taskId") String taskId,
                   @Param("sessionId") String sessionId,
                   @Param("skillName") String skillName,
                   @Param("userMessage") String userMessage);

    int markRunning(@Param("taskId") String taskId);

    int markDone(@Param("taskId") String taskId,
                 @Param("answerMarkdown") String answerMarkdown);

    int markFailed(@Param("taskId") String taskId,
                   @Param("errorMessage") String errorMessage);

    Map<String, Object> selectById(@Param("taskId") String taskId);

    List<Map<String, Object>> selectBySessionId(@Param("sessionId") String sessionId);
}
