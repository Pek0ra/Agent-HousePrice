package com.lgcollege.dto.analytics;

public record CompactionResult(
        String status,
        long elapsedMillis,
        String targetTable) {
}
