package com.jobpilot.controller;

import com.jobpilot.model.ApplicationRecord;
import com.jobpilot.model.CareerProfile;
import com.jobpilot.model.JobRecord;
import com.jobpilot.model.TailoredResumeRecord;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.io.IOException;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ApplicationController {

    private final MongoTemplate mongo;
    private final RestClient workerClient;
    private final Path tailoredDirectory;

    public ApplicationController(
            MongoTemplate mongo,
            @Value("${jobpilot.worker-url:http://localhost:8000}") String workerUrl,
            @Value("${jobpilot.tailored-dir:../storage/tailored}") String tailoredDir) {
        this.mongo = mongo;
        this.workerClient = RestClient.builder()
            .baseUrl(workerUrl)
            .requestFactory(new JdkClientHttpRequestFactory(
                HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build()
            ))
            .build();
        this.tailoredDirectory = Path.of(tailoredDir).toAbsolutePath().normalize();
    }

    public record PrepareApplicationRequest(@NotBlank String tailoredResumeId) {}
    public record SubmitApplicationRequest(boolean confirmSubmit) {}

    @PostMapping("/jobs/{jobId}/applications")
    public Map<String, Object> prepare(
            @PathVariable String jobId,
            @Valid @RequestBody PrepareApplicationRequest request) {
        JobRecord job = mongo.findById(jobId, JobRecord.class);
        if (job == null || job.getJob() == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Analyze this job before applying.");
        }
        if (!"GREENHOUSE".equals(job.getSource())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Only Greenhouse applications are supported.");
        }

        TailoredResumeRecord tailored = mongo.findById(request.tailoredResumeId(), TailoredResumeRecord.class);
        if (tailored == null || !jobId.equals(tailored.getJobId())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT,
                "Generate a tailored resume for this job before starting an application."
            );
        }

        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null || !profile.isVerified() || profile.getExtracted() == null
                || profile.getExtracted().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Verify your career profile before applying.");
        }

        Path pdfPath = Path.of(tailored.getPdfPath()).toAbsolutePath().normalize();
        if (!pdfPath.startsWith(tailoredDirectory)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Invalid tailored resume storage path.");
        }

        byte[] pdfBytes;
        try {
            pdfBytes = Files.readAllBytes(pdfPath);
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "The tailored PDF is missing. Generate it again.", ex);
        }
        if (pdfBytes.length == 0 || pdfBytes.length > 12 * 1024 * 1024
                || !(pdfBytes.length >= 4 && pdfBytes[0] == '%' && pdfBytes[1] == 'P'
                    && pdfBytes[2] == 'D' && pdfBytes[3] == 'F')) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "The tailored resume PDF is invalid or too large.");
        }

        ApplicationRecord record = new ApplicationRecord();
        record.setId(UUID.randomUUID().toString());
        record.setJobId(jobId);
        record.setTailoredResumeId(tailored.getId());
        record.setJobTitle(String.valueOf(job.getJob().getOrDefault("title", "Target role")));
        record.setCompany(String.valueOf(job.getJob().getOrDefault("company", "")));
        record.setStatus("CREATED");
        record.setCreatedAt(Instant.now());
        record.setUpdatedAt(Instant.now());
        mongo.save(record);

        Map<String, Object> workerRequest = new LinkedHashMap<>();
        workerRequest.put("application_id", record.getId());
        workerRequest.put("job_url", job.getJobUrl());
        workerRequest.put("career_profile", profile.getExtracted());
        workerRequest.put("tailored_resume_pdf_base64", Base64.getEncoder().encodeToString(pdfBytes));

        try {
            Map<String, Object> workerResult = workerClient.post()
                .uri("/applications/prepare")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(workerRequest)
                .retrieve()
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
            applyWorkerResult(record, workerResult);
            mongo.save(record);
            return toResponse(record);
        } catch (RestClientResponseException ex) {
            record.setStatus("FAILED");
            record.setMessage("The browser worker could not prepare this application: " + safeWorkerMessage(ex));
            record.setUpdatedAt(Instant.now());
            mongo.save(record);
            throw new ResponseStatusException(
                ex.getStatusCode().is4xxClientError()
                    ? HttpStatus.valueOf(ex.getStatusCode().value())
                    : HttpStatus.BAD_GATEWAY,
                record.getMessage(),
                ex
            );
        } catch (Exception ex) {
            record.setStatus("FAILED");
            record.setMessage("Could not communicate with the local browser worker. Confirm it is running on this computer.");
            record.setUpdatedAt(Instant.now());
            mongo.save(record);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, record.getMessage(), ex);
        }
    }

    @GetMapping("/jobs/{jobId}/applications")
    public List<Map<String, Object>> listForJob(@PathVariable String jobId) {
        Query query = new Query(Criteria.where("jobId").is(jobId))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);
        return mongo.find(query, ApplicationRecord.class).stream().map(this::toResponse).toList();
    }

    @GetMapping("/applications/{id}")
    public Map<String, Object> get(@PathVariable String id) {
        return toResponse(findOrThrow(id));
    }

    @PostMapping("/applications/{id}/refresh")
    public Map<String, Object> refresh(@PathVariable String id) {
        ApplicationRecord record = findOrThrow(id);
        Map<String, Object> result = callWorker("/applications/" + record.getBrowserSessionId() + "/refresh", Map.of());
        applyWorkerResult(record, result);
        mongo.save(record);
        return toResponse(record);
    }

    @PostMapping("/applications/{id}/submit")
    public Map<String, Object> submit(
            @PathVariable String id,
            @RequestBody SubmitApplicationRequest request) {
        if (request == null || !request.confirmSubmit()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Explicit confirmation is required before JobPilot submits an application."
            );
        }
        ApplicationRecord record = findOrThrow(id);
        if (!"READY_FOR_REVIEW".equals(record.getStatus())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT,
                "Refresh the application and complete every required field before submitting."
            );
        }
        // Persist the approval gate before contacting the worker. A retry or timeout
        // cannot turn the same application record back into a second submit attempt.
        record.setStatus("SUBMITTING");
        record.setApprovedAt(Instant.now());
        record.setUpdatedAt(Instant.now());
        mongo.save(record);

        try {
            Map<String, Object> result = callWorker(
                "/applications/" + record.getBrowserSessionId() + "/submit",
                Map.of("confirm_submit", true)
            );
            applyWorkerResult(record, result);
            if ("SUBMITTED".equals(record.getStatus())) {
                record.setSubmittedAt(Instant.now());
            }
            mongo.save(record);
            return toResponse(record);
        } catch (ResponseStatusException ex) {
            record.setStatus("SUBMISSION_UNKNOWN");
            record.setMessage(
                "JobPilot could not confirm the submit result. Check Greenhouse and your email before taking any further action."
            );
            record.setUpdatedAt(Instant.now());
            mongo.save(record);
            throw ex;
        }
    }

    @PostMapping("/applications/{id}/cancel")
    public Map<String, Object> cancel(@PathVariable String id) {
        ApplicationRecord record = findOrThrow(id);
        Map<String, Object> result = callWorker(
            "/applications/" + record.getBrowserSessionId() + "/cancel",
            Map.of()
        );
        applyWorkerResult(record, result);
        mongo.save(record);
        return toResponse(record);
    }

    private Map<String, Object> callWorker(String path, Map<String, Object> body) {
        try {
            Map<String, Object> result = workerClient.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
            if (result == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Browser worker returned an empty response.");
            }
            return result;
        } catch (RestClientResponseException ex) {
            String message = safeWorkerMessage(ex);
            throw new ResponseStatusException(
                ex.getStatusCode().is4xxClientError() ? HttpStatus.valueOf(ex.getStatusCode().value()) : HttpStatus.BAD_GATEWAY,
                message,
                ex
            );
        } catch (ResponseStatusException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not communicate with the local browser worker.",
                ex
            );
        }
    }

    private void applyWorkerResult(ApplicationRecord record, Map<String, Object> result) {
        if (result == null) {
            record.setStatus("FAILED");
            record.setMessage("Browser worker returned no application state.");
            record.setUpdatedAt(Instant.now());
            return;
        }
        record.setBrowserSessionId(String.valueOf(result.getOrDefault("session_id", record.getId())));
        record.setApplicationUrl(String.valueOf(result.getOrDefault("application_url", "")));
        record.setStatus(String.valueOf(result.getOrDefault("status", "FAILED")));
        record.setMessage((String) result.get("message"));
        record.setFields(toMapList(result.get("fields")));
        record.setMissingRequiredFields(toStringList(result.get("missing_required_fields")));
        record.setUpdatedAt(Instant.now());
    }

    private ApplicationRecord findOrThrow(String id) {
        ApplicationRecord record = mongo.findById(id, ApplicationRecord.class);
        if (record == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Application not found.");
        }
        if (record.getBrowserSessionId() == null || record.getBrowserSessionId().isBlank()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "This application does not have an active browser session.");
        }
        return record;
    }

    private List<Map<String, Object>> toMapList(Object value) {
        List<Map<String, Object>> items = new ArrayList<>();
        if (value instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map) {
                    Map<String, Object> copy = new LinkedHashMap<>();
                    map.forEach((key, val) -> copy.put(String.valueOf(key), val));
                    items.add(copy);
                }
            }
        }
        return items;
    }

    private List<String> toStringList(Object value) {
        if (!(value instanceof List<?> list)) return List.of();
        return list.stream().map(String::valueOf).toList();
    }

    private String safeWorkerMessage(RestClientResponseException ex) {
        String body = ex.getResponseBodyAsString();
        if (body == null || body.isBlank()) return "The browser worker returned HTTP " + ex.getStatusCode().value() + ".";
        try {
            if (body.startsWith("{") && body.contains("\"detail\"")) {
                int start = body.indexOf("\"detail\"");
                int colon = body.indexOf(':', start);
                int end = body.indexOf('}', colon);
                if (colon >= 0 && end > colon) return body.substring(colon + 1, end).replace("\"", "").trim();
            }
        } catch (Exception ignored) {}
        return body.length() > 500 ? body.substring(0, 500) : body;
    }

    private Map<String, Object> toResponse(ApplicationRecord record) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("id", record.getId());
        response.put("jobId", record.getJobId());
        response.put("tailoredResumeId", record.getTailoredResumeId());
        response.put("jobTitle", record.getJobTitle());
        response.put("company", record.getCompany());
        response.put("applicationUrl", record.getApplicationUrl());
        response.put("status", record.getStatus());
        response.put("fields", record.getFields() == null ? List.of() : record.getFields());
        response.put("missingRequiredFields",
            record.getMissingRequiredFields() == null ? List.of() : record.getMissingRequiredFields());
        response.put("message", record.getMessage());
        response.put("createdAt", record.getCreatedAt());
        response.put("updatedAt", record.getUpdatedAt());
        response.put("approvedAt", record.getApprovedAt());
        response.put("submittedAt", record.getSubmittedAt());
        return response;
    }
}
