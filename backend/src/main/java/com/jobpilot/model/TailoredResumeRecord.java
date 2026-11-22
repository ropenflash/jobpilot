package com.jobpilot.model;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("tailored_resumes")
public class TailoredResumeRecord {
    @Id
    private String id;
    private String jobId;
    private String jobTitle;
    private String company;
    private String resumeStyle = "classic";
    private String profileResumeId;
    private Instant profileUpdatedAt;
    private Map<String, Object> resume;
    private List<Map<String, Object>> changeLog;
    private String docxPath;
    private String pdfPath;
    private Instant createdAt = Instant.now();

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getJobId() { return jobId; }
    public void setJobId(String jobId) { this.jobId = jobId; }
    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public String getCompany() { return company; }
    public void setCompany(String company) { this.company = company; }
    public String getResumeStyle() { return resumeStyle; }
    public void setResumeStyle(String resumeStyle) { this.resumeStyle = resumeStyle; }
    public String getProfileResumeId() { return profileResumeId; }
    public void setProfileResumeId(String profileResumeId) { this.profileResumeId = profileResumeId; }
    public Instant getProfileUpdatedAt() { return profileUpdatedAt; }
    public void setProfileUpdatedAt(Instant profileUpdatedAt) { this.profileUpdatedAt = profileUpdatedAt; }
    public Map<String, Object> getResume() { return resume; }
    public void setResume(Map<String, Object> resume) { this.resume = resume; }
    public List<Map<String, Object>> getChangeLog() { return changeLog; }
    public void setChangeLog(List<Map<String, Object>> changeLog) { this.changeLog = changeLog; }
    public String getDocxPath() { return docxPath; }
    public void setDocxPath(String docxPath) { this.docxPath = docxPath; }
    public String getPdfPath() { return pdfPath; }
    public void setPdfPath(String pdfPath) { this.pdfPath = pdfPath; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
