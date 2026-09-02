package com.lgcollege.dto.system;

import java.util.List;

public record SystemCapabilities(
        String mode,
        boolean mysqlEnabled,
        boolean bigDataEnabled,
        List<String> profiles) {
}
