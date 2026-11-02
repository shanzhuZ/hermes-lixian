-- 将旧版 xw_task_hit（hit_id/fields_json）迁移为归一化新结构
USE `hermes-xw1`;

-- 旧表有数据可先备份
RENAME TABLE xw_task_hit TO xw_task_hit_legacy_20260825;

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
