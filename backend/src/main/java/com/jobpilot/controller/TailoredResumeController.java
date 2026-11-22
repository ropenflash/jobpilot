package com.jobpilot.controller;

import com.jobpilot.model.CareerProfile;
import com.jobpilot.model.JobRecord;
import com.jobpilot.model.TailoredResumeRecord;
import java.io.IOException;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class TailoredResumeController {

    private static final MediaType DOCX_MEDIA_TYPE =
        MediaType.parseMediaType("application/vnd.openxmlformats-officedocument.wordprocessingml.document");

    private final MongoTemplate mongo;
    private final RestClient workerClient;
    private final Path tailoredDirectory;

    public TailoredResumeController(
            MongoTemplate mongo,
            @Value("${jobpilot.worker-url:http://localhost:8000}") String workerUrl,
            @Value("${jobpilot.tailored-dir:../storage/tailored}") String tailoredDir) {
        this.mongo = mongo;
        HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();
        this.workerClient = RestClient.builder()
            .baseUrl(workerUrl)
            .requestFactory(new JdkClientHttpRequestFactory(httpClient))
            .build();
        this.tailoredDirectory = Path.of(tailoredDir).toAbsolutePath().normalize();
    }

    @PostMapping("/jobs/{jobId}/tailored-resumes")
    public Map<String, Object> generate(
            @PathVariable String jobId,
            @RequestBody(required = false) Map<String, Object> request) {
        String style = request == null ? "classic"
            : String.valueOf(request.getOrDefault("style", "classic")).toLowerCase(Locale.ROOT);
        if (!Set.of("classic", "modern", "compact").contains(style)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Resume style must be classic, modern or compact."
            );
        }
        JobRecord job = mongo.findById(jobId, JobRecord.class);
        if (job == null || job.getJob() == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Analyze this job before tailoring a resume."
            );
        }

        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null || !profile.isVerified()
                || profile.getExtracted() == null || profile.getExtracted().isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT,
                "Verify your career profile before generating a tailored resume."
            );
        }

        Map<String, Object> careerFacts = new LinkedHashMap<>(profile.getExtracted());
        careerFacts.put("_profile_updated_at",
            profile.getUpdatedAt() == null ? null : profile.getUpdatedAt().toString());

        Map<String, Object> workerRequest = new LinkedHashMap<>();
        workerRequest.put("job", job.getJob());
        workerRequest.put("requirements", job.getRequirements() == null ? Map.of() : job.getRequirements());
        workerRequest.put("match", job.getMatch() == null ? Map.of() : job.getMatch());
        workerRequest.put("career_profile", careerFacts);
        workerRequest.put("style", style);

        Map<String, Object> result;
        try {
            result = workerClient.post()
                .uri("/resumes/tailor")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(workerRequest)
                .retrieve()
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
        } catch (RestClientResponseException ex) {
            String responseBody = ex.getResponseBodyAsString();
            throw new ResponseStatusException(
                ex.getStatusCode().is4xxClientError()
                    ? HttpStatus.valueOf(ex.getStatusCode().value())
                    : HttpStatus.BAD_GATEWAY,
                responseBody == null || responseBody.isBlank()
                    ? "Resume tailoring worker failed."
                    : responseBody,
                ex
            );
        } catch (Exception ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not communicate with the Python worker: " + ex.getMessage(),
                ex
            );
        }

        if (result == null || !(result.get("resume") instanceof Map<?, ?>)
                || !(result.get("documents") instanceof Map<?, ?>)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Worker returned an incomplete tailored resume."
            );
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> resume = new LinkedHashMap<>((Map<String, Object>) result.get("resume"));
        @SuppressWarnings("unchecked")
        Map<String, Object> documents = (Map<String, Object>) result.get("documents");

        byte[] docxBytes = decodeDocument(documents.get("docx_base64"), "DOCX");
        byte[] pdfBytes = decodeDocument(documents.get("pdf_base64"), "PDF");

        String id = UUID.randomUUID().toString();
        Path docxPath = tailoredDirectory.resolve(id + ".docx").normalize();
        Path pdfPath = tailoredDirectory.resolve(id + ".pdf").normalize();
        if (!docxPath.startsWith(tailoredDirectory) || !pdfPath.startsWith(tailoredDirectory)) {
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Invalid document storage path."
            );
        }

        try {
            Files.createDirectories(tailoredDirectory);
            Files.write(docxPath, docxBytes);
            Files.write(pdfPath, pdfBytes);
        } catch (IOException ex) {
            deleteQuietly(docxPath);
            deleteQuietly(pdfPath);
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Could not store the generated resume files.",
                ex
            );
        }

        TailoredResumeRecord record = new TailoredResumeRecord();
        record.setId(id);
        record.setJobId(jobId);
        record.setJobTitle(String.valueOf(job.getJob().getOrDefault("title", "Target role")));
        record.setCompany(String.valueOf(job.getJob().getOrDefault("company", "")));
        record.setResumeStyle(style);
        record.setProfileResumeId(profile.getResumeId());
        record.setProfileUpdatedAt(profile.getUpdatedAt());
        record.setResume(resume);
        record.setChangeLog(toMapList(resume.get("change_log")));
        record.setDocxPath(docxPath.toString());
        record.setPdfPath(pdfPath.toString());
        record.setCreatedAt(Instant.now());

        try {
            mongo.save(record);
        } catch (Exception ex) {
            deleteQuietly(docxPath);
            deleteQuietly(pdfPath);
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Could not save tailored resume metadata.",
                ex
            );
        }

        return toResponse(record);
    }

    @GetMapping("/jobs/{jobId}/tailored-resumes")
    public List<Map<String, Object>> listForJob(@PathVariable String jobId) {
        Query query = new Query(Criteria.where("jobId").is(jobId))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);
        List<TailoredResumeRecord> records = mongo.find(query, TailoredResumeRecord.class);
        return records.stream().map(this::toResponse).toList();
    }

    @GetMapping("/tailored-resumes/{id}")
    public Map<String, Object> get(@PathVariable String id) {
        return toResponse(findOrThrow(id));
    }

    @GetMapping("/tailored-resumes/{id}/download")
    public ResponseEntity<byte[]> download(
            @PathVariable String id,
            @RequestParam(defaultValue = "pdf") String format) {
        TailoredResumeRecord record = findOrThrow(id);
        String normalized = format.toLowerCase(Locale.ROOT);
        Path path;
        MediaType mediaType;
        String extension;

        if ("pdf".equals(normalized)) {
            path = Path.of(record.getPdfPath()).toAbsolutePath().normalize();
            mediaType = MediaType.APPLICATION_PDF;
            extension = "pdf";
        } else if ("docx".equals(normalized)) {
            path = Path.of(record.getDocxPath()).toAbsolutePath().normalize();
            mediaType = DOCX_MEDIA_TYPE;
            extension = "docx";
        } else {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Format must be pdf or docx.");
        }

        if (!path.startsWith(tailoredDirectory)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Invalid document path.");
        }
        try {
            byte[] bytes = Files.readAllBytes(path);
            String filename = safeFilename(record.getJobTitle())
                + "-resume-" + id.substring(0, 8) + "." + extension;
            return ResponseEntity.ok()
                .contentType(mediaType)
                .contentLength(bytes.length)
                .header(
                    HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment().filename(filename).build().toString()
                )
                .body(bytes);
        } catch (IOException ex) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Generated resume file is missing.",
                ex
            );
        }
    }

    private TailoredResumeRecord findOrThrow(String id) {
        TailoredResumeRecord record = mongo.findById(id, TailoredResumeRecord.class);
        if (record == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Tailored resume not found.");
        }
        return record;
    }

    private byte[] decodeDocument(Object encoded, String type) {
        if (!(encoded instanceof String value) || value.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Worker did not return a " + type + " document."
            );
        }
        try {
            return Base64.getDecoder().decode(value);
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Worker returned an invalid " + type + " document."
            );
        }
    }

    private List<Map<String, Object>> toMapList(Object value) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (value instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map) {
                    Map<String, Object> copy = new LinkedHashMap<>();
                    map.forEach((key, val) -> copy.put(String.valueOf(key), val));
                    result.add(copy);
                }
            }
        }
        return result;
    }

    private Map<String, Object> toResponse(TailoredResumeRecord record) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("id", record.getId());
        response.put("jobId", record.getJobId());
        response.put("jobTitle", record.getJobTitle());
        response.put("company", record.getCompany());
        response.put("resumeStyle", record.getResumeStyle() == null ? "classic" : record.getResumeStyle());
        response.put("profileResumeId", record.getProfileResumeId());
        response.put("profileUpdatedAt", record.getProfileUpdatedAt());
        response.put("resume", record.getResume());
        response.put("changeLog", record.getChangeLog());
        response.put("createdAt", record.getCreatedAt());
        response.put("downloads", Map.of(
            "pdf", "/api/tailored-resumes/" + record.getId() + "/download?format=pdf",
            "docx", "/api/tailored-resumes/" + record.getId() + "/download?format=docx"
        ));
        return response;
    }

    private String safeFilename(String value) {
        String safe = value == null
            ? "jobpilot"
            : value.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-");
        safe = safe.replaceAll("^-|-$", "");
        return safe.isBlank() ? "jobpilot" : safe;
    }

    private void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Best-effort cleanup for incomplete generation.
        }
    }
}
