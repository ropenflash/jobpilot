package com.jobpilot.model;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("applications")
public class ApplicationRecord {
    @Id
    private String id;
    private String jobId;
    private String tailoredResumeId;
    private String resumeFormat = "pdf";
    private String jobTitle;
    private String company;
    private String applicationUrl;
    private String browserSessionId;
    private String status;
    private List<Map<String, Object>> fields;
    private List<String> missingRequiredFields;
    private String message;
    private List<String> automationNotes;
    private Map<String, Object> formVerification = Map.of();
    private Map<String, Object> questionReview = Map.of();
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();
    private Instant approvedAt;
    private Instant submittedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getJobId() { return jobId; }
    public void setJobId(String jobId) { this.jobId = jobId; }
    public String getTailoredResumeId() { return tailoredResumeId; }
    public void setTailoredResumeId(String tailoredResumeId) { this.tailoredResumeId = tailoredResumeId; }
    public String getResumeFormat() { return resumeFormat; }
    public void setResumeFormat(String resumeFormat) { this.resumeFormat = resumeFormat; }
    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public String getCompany() { return company; }
    public void setCompany(String company) { this.company = company; }
    public String getApplicationUrl() { return applicationUrl; }
    public void setApplicationUrl(String applicationUrl) { this.applicationUrl = applicationUrl; }
    public String getBrowserSessionId() { return browserSessionId; }
    public void setBrowserSessionId(String browserSessionId) { this.browserSessionId = browserSessionId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public List<Map<String, Object>> getFields() { return fields; }
    public void setFields(List<Map<String, Object>> fields) { this.fields = fields; }
    public List<String> getMissingRequiredFields() { return missingRequiredFields; }
    public void setMissingRequiredFields(List<String> missingRequiredFields) { this.missingRequiredFields = missingRequiredFields; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public List<String> getAutomationNotes() { return automationNotes; }
    public void setAutomationNotes(List<String> automationNotes) { this.automationNotes = automationNotes; }
    public Map<String, Object> getFormVerification() { return formVerification; }
    public void setFormVerification(Map<String, Object> formVerification) {
        this.formVerification = formVerification == null ? Map.of() : formVerification;
    }
    public Map<String, Object> getQuestionReview() { return questionReview; }
    public void setQuestionReview(Map<String, Object> questionReview) {
        this.questionReview = questionReview == null ? Map.of() : questionReview;
    }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
    public Instant getApprovedAt() { return approvedAt; }
    public void setApprovedAt(Instant approvedAt) { this.approvedAt = approvedAt; }
    public Instant getSubmittedAt() { return submittedAt; }
    public void setSubmittedAt(Instant submittedAt) { this.submittedAt = submittedAt; }
}
