package com.example.aw.chat.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface ChatSessionMapper {

    int insertSession(@Param("sessionId") String sessionId,
                      @Param("hermesSessionId") String hermesSessionId,
                      @Param("title") String title);

    Map<String, Object> selectById(@Param("sessionId") String sessionId);

    int touchUpdatedAt(@Param("sessionId") String sessionId);
}
