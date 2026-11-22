package com.jobpilot.model;

import java.time.Instant;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("career_profiles")
public class CareerProfile {
    @Id
    private String id = "default";
    private String resumeId;
    private Map<String, Object> extracted;
    private boolean verified;
    private Instant updatedAt = Instant.now();

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getResumeId() { return resumeId; }
    public void setResumeId(String resumeId) { this.resumeId = resumeId; }
    public Map<String, Object> getExtracted() { return extracted; }
    public void setExtracted(Map<String, Object> extracted) { this.extracted = extracted; }
    public boolean isVerified() { return verified; }
    public void setVerified(boolean verified) { this.verified = verified; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
