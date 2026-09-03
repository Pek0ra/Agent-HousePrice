package com.lgcollege.controller;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.dto.system.SystemCapabilities;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;

@RestController
@RequestMapping("/api/system")
public class SystemController {
    private final Environment environment;
    private final boolean bigDataEnabled;

    public SystemController(
            Environment environment,
            @Value("${app.big-data.enabled:false}") boolean bigDataEnabled) {
        this.environment = environment;
        this.bigDataEnabled = bigDataEnabled;
    }

    @GetMapping("/capabilities")
    public ApiResponse<SystemCapabilities> capabilities() {
        String[] profiles = environment.getActiveProfiles();
        if (profiles.length == 0) {
            profiles = environment.getDefaultProfiles();
        }
        return ApiResponse.success(new SystemCapabilities(
                bigDataEnabled ? "bigdata" : "local",
                true,
                bigDataEnabled,
                Arrays.asList(profiles)));
    }
}
