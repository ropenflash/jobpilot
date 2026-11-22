package com.jobpilot.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {
    @GetMapping
    public Map<String, Object> getProfile() {
        return Map.of("configured", false, "message",
                "Profile creation is planned for Milestone 2.");
    }
}
