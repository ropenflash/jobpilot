package com.jobpilot.model;

import java.time.Instant;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("jobs")
public class JobRecord {
    @Id
    private String id;
    private String source;
    private String sourceJobId;
    private String boardToken;
    private String jobUrl;
    private Map<String, Object> job;
    private Map<String, Object> requirements;
    private Map<String, Object> match;
    private Map<String, Object> visualInspection;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getSourceJobId() { return sourceJobId; }
    public void setSourceJobId(String sourceJobId) { this.sourceJobId = sourceJobId; }
    public String getBoardToken() { return boardToken; }
    public void setBoardToken(String boardToken) { this.boardToken = boardToken; }
    public String getJobUrl() { return jobUrl; }
    public void setJobUrl(String jobUrl) { this.jobUrl = jobUrl; }
    public Map<String, Object> getJob() { return job; }
    public void setJob(Map<String, Object> job) { this.job = job; }
    public Map<String, Object> getRequirements() { return requirements; }
    public void setRequirements(Map<String, Object> requirements) { this.requirements = requirements; }
    public Map<String, Object> getMatch() { return match; }
    public void setMatch(Map<String, Object> match) { this.match = match; }
    public Map<String, Object> getVisualInspection() { return visualInspection; }
    public void setVisualInspection(Map<String, Object> visualInspection) { this.visualInspection = visualInspection; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
