package com.jobpilot.controller;

import java.time.Instant;
import java.util.Map;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    private final MongoTemplate mongoTemplate;

    public HealthController(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        String mongo = "UP";
        try {
            mongoTemplate.getDb().runCommand(new org.bson.Document("ping", 1));
        } catch (Exception ex) {
            mongo = "DOWN";
        }
        return Map.of("service", "jobpilot-backend", "status",
                "UP".equals(mongo) ? "UP" : "DEGRADED",
                "mongodb", mongo, "timestamp", Instant.now().toString());
    }
}
