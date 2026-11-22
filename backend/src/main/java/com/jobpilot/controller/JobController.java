package com.jobpilot.controller;

import com.jobpilot.model.CareerProfile;
import com.jobpilot.model.JobRecord;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;
import java.net.http.HttpClient;

@RestController
@RequestMapping("/api/jobs")
public class JobController {

    private final MongoTemplate mongo;
    private final RestClient workerClient;

    public JobController(
            MongoTemplate mongo,
            @Value("${jobpilot.worker-url:http://localhost:8000}") String workerUrl) {
        this.mongo = mongo;
        HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();
        this.workerClient = RestClient.builder()
            .baseUrl(workerUrl)
            .requestFactory(new JdkClientHttpRequestFactory(httpClient))
            .build();
    }

    public record AnalyzeJobRequest(@NotBlank String url) {}

    @PostMapping(value = "/analyze", consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> analyzeJob(@Valid @RequestBody AnalyzeJobRequest request) {
        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null || !profile.isVerified() || profile.getExtracted() == null
                || profile.getExtracted().isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT,
                "Please upload, review and verify your career profile before analyzing jobs."
            );
        }

        Map<String, Object> workerRequest = new LinkedHashMap<>();
        workerRequest.put("url", request.url().trim());
        workerRequest.put("career_profile", profile.getExtracted());

        Map<String, Object> result;
        try {
            result = workerClient.post()
                .uri("/jobs/analyze")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(workerRequest)
                .retrieve()
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
        } catch (RestClientResponseException ex) {
            HttpStatus status = ex.getStatusCode().is4xxClientError()
                ? HttpStatus.valueOf(ex.getStatusCode().value())
                : HttpStatus.BAD_GATEWAY;
            String body = ex.getResponseBodyAsString();
            throw new ResponseStatusException(
                status,
                body == null || body.isBlank()
                    ? "Job analysis worker failed."
                    : body,
                ex
            );
        } catch (Exception ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not communicate with the Python worker: " + ex.getMessage(),
                ex
            );
        }

        if (result == null
                || !(result.get("job") instanceof Map<?, ?>)
                || !(result.get("requirements") instanceof Map<?, ?>)
                || !(result.get("match") instanceof Map<?, ?>)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Worker returned an incomplete job analysis."
            );
        }

        Map<String, Object> job = asMap(result.get("job"));
        Map<String, Object> requirements = asMap(result.get("requirements"));
        Map<String, Object> match = asMap(result.get("match"));
        Map<String, Object> visualInspection = result.get("visual_inspection") instanceof Map<?, ?>
            ? asMap(result.get("visual_inspection"))
            : new LinkedHashMap<>();
        String boardToken = String.valueOf(job.get("board_token"));
        String sourceJobId = String.valueOf(job.get("job_id"));
        String stableId = "greenhouse-" + boardToken + "-" + sourceJobId;

        JobRecord record = mongo.findById(stableId, JobRecord.class);
        if (record == null) {
            record = new JobRecord();
            record.setId(stableId);
            record.setCreatedAt(Instant.now());
        }

        record.setSource("GREENHOUSE");
        record.setSourceJobId(sourceJobId);
        record.setBoardToken(boardToken);
        record.setJobUrl(String.valueOf(job.get("job_url")));
        record.setJob(job);
        record.setRequirements(requirements);
        record.setMatch(match);
        record.setVisualInspection(visualInspection);
        record.setUpdatedAt(Instant.now());
        mongo.save(record);

        return toResponse(record);
    }

    @GetMapping
    public List<Map<String, Object>> listJobs() {
        Query query = new Query()
            .with(Sort.by(Sort.Direction.DESC, "updatedAt"))
            .limit(50);
        List<JobRecord> records = mongo.find(query, JobRecord.class);
        return records.stream().map(this::toResponse).toList();
    }

    @GetMapping("/{id}")
    public Map<String, Object> getJob(@PathVariable String id) {
        JobRecord record = mongo.findById(id, JobRecord.class);
        if (record == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Job analysis not found.");
        }
        return toResponse(record);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object value) {
        return new LinkedHashMap<>((Map<String, Object>) value);
    }

    private Map<String, Object> toResponse(JobRecord record) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("id", record.getId());
        response.put("source", record.getSource());
        response.put("sourceJobId", record.getSourceJobId());
        response.put("jobUrl", record.getJobUrl());
        response.put("job", record.getJob());
        response.put("requirements", record.getRequirements());
        response.put("match", record.getMatch());
        response.put("visual_inspection", record.getVisualInspection());
        response.put("createdAt", record.getCreatedAt());
        response.put("updatedAt", record.getUpdatedAt());
        return response;
    }
}
