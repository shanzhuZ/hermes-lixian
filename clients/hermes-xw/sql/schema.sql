-- hermes-xw 对话接口表（session / task 分离）+ 共用过程入库
CREATE DATABASE IF NOT EXISTS `hermes-xw1` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `hermes-xw1`;

CREATE TABLE IF NOT EXISTS xw_chat_session (
  session_id          VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT '业务会话ID',
  hermes_session_id   VARCHAR(128) NOT NULL COMMENT 'Hermes /api/sessions 的 id',
  title               VARCHAR(256) NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_hermes_session (hermes_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话会话';

CREATE TABLE IF NOT EXISTS xw_chat_task (
  task_id             VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT '一次提问/一次 skill 执行',
  session_id          VARCHAR(64)  NOT NULL,
  skill_name          VARCHAR(64)  NOT NULL COMMENT 'org-portrait / account-portrait / event-spread-impact / bill-impact-analysis',
  status              VARCHAR(32)  NOT NULL DEFAULT 'pending' COMMENT 'pending,running,done,failed',
  user_message        MEDIUMTEXT   NOT NULL,
  answer_markdown     MEDIUMTEXT   NULL,
  error_message       TEXT         NULL,
  hermes_run_id       VARCHAR(128) NULL COMMENT '若走 /v1/runs 可填',
  current_phase       VARCHAR(64)  NULL COMMENT '当前粗阶段码（法案方案D）',
  started_at          DATETIME     NULL,
  finished_at         DATETIME     NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_session_created (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话内单次任务';

CREATE TABLE IF NOT EXISTS xw_chat_message (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  session_id          VARCHAR(64)  NOT NULL,
  task_id             VARCHAR(64)  NULL,
  role                VARCHAR(16)  NOT NULL COMMENT 'user,assistant,system',
  content             MEDIUMTEXT   NOT NULL,
  msg_type            VARCHAR(32)  NOT NULL DEFAULT 'text' COMMENT 'user_input,answer,error',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_session_id (session_id, id),
  KEY idx_task_id (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息（历史）';

-- 粗阶段计划（方案 D；先法案 Skill 使用）
CREATE TABLE IF NOT EXISTS xw_task_phase (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  phase_code          VARCHAR(64)  NOT NULL,
  phase_name          VARCHAR(128) NULL,
  seq                 INT          NOT NULL DEFAULT 0,
  status              VARCHAR(32)  NOT NULL DEFAULT 'pending' COMMENT 'pending,running,done,skipped,failed',
  message             VARCHAR(512) NULL,
  started_at          DATETIME     NULL,
  finished_at         DATETIME     NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_task_phase (task_id, phase_code),
  KEY idx_task_seq (task_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务粗阶段';

-- 工具审计（四 Skill 共用）
CREATE TABLE IF NOT EXISTS xw_tool_event (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  tool_call_id        VARCHAR(64)  NOT NULL COMMENT '幂等键',
  tool_name           VARCHAR(128) NOT NULL,
  mcp_server          VARCHAR(128) NULL,
  tool_args           MEDIUMTEXT   NULL,
  tool_output         MEDIUMTEXT   NULL,
  status              VARCHAR(32)  NOT NULL DEFAULT 'success' COMMENT 'success,error,started',
  duration_ms         INT          NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tool_call (tool_call_id),
  KEY idx_task_created (task_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工具调用审计';

-- 归一化命中（四 Skill 共用一张表）
CREATE TABLE IF NOT EXISTS xw_task_hit (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  skill_name          VARCHAR(64)  NULL,
  hit_type            VARCHAR(32)  NOT NULL DEFAULT 'other' COMMENT 'profile,post,candidate,search,document,other',
  platform            VARCHAR(64)  NULL,
  title               VARCHAR(512) NULL,
  summary             VARCHAR(1024) NULL,
  dedupe_key          VARCHAR(191) NOT NULL,
  payload_json        MEDIUMTEXT   NOT NULL COMMENT '[{label,value},...] 展示字段',
  source_tool         VARCHAR(128) NULL,
  tool_event_id       VARCHAR(64)  NULL COMMENT '对应 xw_tool_event.tool_call_id',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_task_dedupe (task_id, dedupe_key),
  KEY idx_task_type (task_id, hit_type),
  KEY idx_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='归一化可查询命中';

-- Hook 回调信封幂等（旧 HTTP 入库用；现已改为插件直连 MySQL，可保留空表）
CREATE TABLE IF NOT EXISTS xw_ingest_event (
  event_id            VARCHAR(64)  NOT NULL PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  event_type          VARCHAR(64)  NOT NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='历史 HTTP 回调幂等（可选）';
