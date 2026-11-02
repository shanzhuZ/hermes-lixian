-- 法案粗进度（方案 D）增量
USE `hermes-xw1`;

-- 若缺 current_phase 可手动执行：
-- ALTER TABLE xw_chat_task ADD COLUMN current_phase VARCHAR(64) NULL COMMENT '当前粗阶段码' AFTER hermes_run_id;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务粗阶段（方案D）';
