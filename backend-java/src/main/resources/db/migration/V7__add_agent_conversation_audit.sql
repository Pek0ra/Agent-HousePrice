SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

ALTER TABLE agent_query_audit
    ADD COLUMN thread_id VARCHAR(64) NULL COMMENT '多轮会话编号' AFTER trace_id,
    ADD COLUMN used_history BOOLEAN NOT NULL DEFAULT FALSE COMMENT '本轮是否继承历史上下文' AFTER error_summary,
    ADD COLUMN inherited_fields VARCHAR(1000) NULL COMMENT '继承的上下文字段JSON' AFTER used_history,
    ADD COLUMN overridden_fields VARCHAR(1000) NULL COMMENT '覆盖的上下文字段JSON' AFTER inherited_fields,
    ADD COLUMN context_resolution_duration_ms BIGINT NOT NULL DEFAULT 0 COMMENT '上下文解析耗时，毫秒' AFTER overridden_fields,
    ADD KEY idx_agent_audit_thread_created (thread_id, created_at);
