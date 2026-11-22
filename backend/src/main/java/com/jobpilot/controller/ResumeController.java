
package com.jobpilot.controller;

import com.jobpilot.model.CareerProfile;
import com.jobpilot.model.ResumeRecord;

import java.io.IOException;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.FileSystemResource;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ResumeController {

    private static final Logger log =
        LoggerFactory.getLogger(ResumeController.class);

    private static final long MAX_FILE_SIZE = 5 * 1024 * 1024;

    private final MongoTemplate mongo;
    private final RestClient workerClient;
    private final Path resumeDirectory;

    public ResumeController(
            MongoTemplate mongo,
            @Value("${jobpilot.worker-url:http://localhost:8000}")
            String workerUrl,
            @Value("${jobpilot.storage-dir:../storage/resumes}")
            String storageDir) {

        this.mongo = mongo;

        // The JDK client advertises an h2c upgrade by default. Uvicorn rejects
        // that upgrade and then drops the multipart body, so FastAPI reports
        // the file field as missing. Pin HTTP/1.1 for the worker call.
        HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();

        this.workerClient = RestClient.builder()
            .baseUrl(workerUrl)
            .requestFactory(new JdkClientHttpRequestFactory(httpClient))
            .build();

        this.resumeDirectory =
            Path.of(storageDir).toAbsolutePath().normalize();
    }

    @PostMapping(
        value = "/resumes",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Map<String, Object> uploadResume(
            @RequestPart("file") MultipartFile file) {

        log.info("Received resume upload: {}", file.getOriginalFilename());

        // 1. Validate file
        if (file.isEmpty() || file.getSize() > MAX_FILE_SIZE) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "PDF must be non-empty and 5 MB or smaller."
            );
        }

        String original = file.getOriginalFilename() == null
            ? "resume.pdf"
            : file.getOriginalFilename();

        if (!original.toLowerCase(Locale.ROOT).endsWith(".pdf")) {
            throw new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only PDF resumes are supported."
            );
        }

        // 2. Store PDF locally
        String id = UUID.randomUUID().toString();
        String safeName = id + ".pdf";

        Path destination = resumeDirectory.resolve(safeName);

        try {
            Files.createDirectories(resumeDirectory);
            file.transferTo(destination.toFile());

        } catch (IOException | IllegalStateException ex) {

            deleteFile(destination);

            log.error("Could not store resume", ex);

            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Could not store resume."
            );
        }

        log.info("Resume stored at: {}", destination);

        // 3. Forward PDF to Python worker
        Map<String, Object> extracted;

        try {

            FileSystemResource pdfResource =
                new FileSystemResource(destination.toFile());

            MultiValueMap<String, Object> multipart =
                new LinkedMultiValueMap<>();

            // Must match FastAPI parameter: file
            multipart.add("file", pdfResource);

            log.info(
                "Forwarding resume to Python worker: {}",
                destination.getFileName()
            );

            extracted = workerClient.post()
                .uri("/resume/parse")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .accept(MediaType.APPLICATION_JSON)
                .body(multipart)
                .retrieve()
                .body(
                    new ParameterizedTypeReference<
                        Map<String, Object>
                    >() {}
                );

        } catch (RestClientResponseException ex) {

            deleteFile(destination);

            log.error(
                "Python worker returned HTTP {}: {}",
                ex.getStatusCode(),
                ex.getResponseBodyAsString(),
                ex
            );

            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Python worker returned HTTP "
                    + ex.getStatusCode()
                    + ": "
                    + ex.getResponseBodyAsString(),
                ex
            );

        } catch (RestClientException ex) {

            deleteFile(destination);

            log.error("Python worker communication failed", ex);

            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not communicate with Python worker: "
                    + ex.getMessage(),
                ex
            );
        }

        // 4. Validate worker response
        if (extracted == null) {

            deleteFile(destination);

            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Python worker returned an empty response."
            );
        }

        log.info("Resume successfully parsed by Python worker");

        // 5. Persist resume metadata
        ResumeRecord resume = new ResumeRecord();

        resume.setId(id);
        resume.setFileName(original);
        resume.setStoragePath(destination.toString());
        resume.setSizeBytes(file.getSize());

        mongo.save(resume);

        // 6. Persist extracted career profile
        CareerProfile profile =
            mongo.findById("default", CareerProfile.class);

        if (profile == null) {
            profile = new CareerProfile();
        }

        profile.setResumeId(id);
        profile.setExtracted(extracted);
        profile.setVerified(false);
        profile.setUpdatedAt(Instant.now());

        mongo.save(profile);

        log.info("Career profile saved successfully: {}", id);

        // 7. Return response to frontend
        return Map.of(
            "resumeId", id,
            "fileName", original,
            "profile", extracted,
            "verified", false
        );
    }

    @GetMapping("/profile")
    public Map<String, Object> getProfile() {

        CareerProfile profile =
            mongo.findById("default", CareerProfile.class);

        if (profile == null) {
            return Map.of("configured", false);
        }

        return Map.of(
            "configured", true,
            "resumeId",
                profile.getResumeId() == null
                    ? ""
                    : profile.getResumeId(),
            "verified", profile.isVerified(),
            "profile",
                profile.getExtracted() == null
                    ? Map.of()
                    : profile.getExtracted(),
            "updatedAt", profile.getUpdatedAt().toString()
        );
    }

    @PutMapping("/profile")
    public Map<String, Object> updateProfile(
            @RequestBody Map<String, Object> updatedProfile) {

        CareerProfile profile =
            mongo.findById("default", CareerProfile.class);

        if (profile == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Upload a resume before editing the profile."
            );
        }

        profile.setExtracted(updatedProfile);
        profile.setVerified(true);
        profile.setUpdatedAt(Instant.now());

        mongo.save(profile);

        return Map.of(
            "configured", true,
            "verified", true,
            "profile", updatedProfile
        );
    }

    private void deleteFile(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            log.warn("Could not clean up temporary resume file: {}", path, ex);
        }
    }
}
