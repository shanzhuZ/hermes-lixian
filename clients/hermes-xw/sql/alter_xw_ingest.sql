-- 已有 hermes-xw1 库时增量加过程表（幂等：IF NOT EXISTS）
USE `hermes-xw1`;

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

CREATE TABLE IF NOT EXISTS xw_task_hit (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  skill_name          VARCHAR(64)  NULL,
  hit_type            VARCHAR(32)  NOT NULL DEFAULT 'other' COMMENT 'profile,post,candidate,search,document,other',
  platform            VARCHAR(64)  NULL,
  title               VARCHAR(512) NULL,
  summary             VARCHAR(1024) NULL,
  dedupe_key          VARCHAR(191) NOT NULL,
  payload_json        MEDIUMTEXT   NOT NULL,
  source_tool         VARCHAR(128) NULL,
  tool_event_id       VARCHAR(64)  NULL COMMENT '对应 xw_tool_event.tool_call_id',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_task_dedupe (task_id, dedupe_key),
  KEY idx_task_type (task_id, hit_type),
  KEY idx_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='归一化可查询命中';

CREATE TABLE IF NOT EXISTS xw_ingest_event (
  event_id            VARCHAR(64)  NOT NULL PRIMARY KEY,
  task_id             VARCHAR(64)  NOT NULL,
  event_type          VARCHAR(64)  NOT NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Hermes 回调幂等';
