package com.example.aw.chat.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface ChatMessageMapper {

    int insertMessage(@Param("sessionId") String sessionId,
                      @Param("taskId") String taskId,
                      @Param("role") String role,
                      @Param("content") String content,
                      @Param("msgType") String msgType);

    List<Map<String, Object>> selectBySessionId(@Param("sessionId") String sessionId,
                                                @Param("limit") int limit);
}
