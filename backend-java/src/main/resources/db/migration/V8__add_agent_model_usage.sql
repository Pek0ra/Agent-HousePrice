SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

ALTER TABLE agent_query_audit
    ADD COLUMN model_calls INT NOT NULL DEFAULT 0 COMMENT '本轮模型调用次数' AFTER context_resolution_duration_ms,
    ADD COLUMN prompt_tokens BIGINT NULL COMMENT '本轮输入Token总数' AFTER model_calls,
    ADD COLUMN completion_tokens BIGINT NULL COMMENT '本轮输出Token总数' AFTER prompt_tokens,
    ADD COLUMN total_tokens BIGINT NULL COMMENT '本轮Token总数' AFTER completion_tokens;
