package com.jobpilot.controller;

import com.jobpilot.model.CareerProfile;
import com.jobpilot.model.ResumeRecord;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ResumeController {
    private final MongoTemplate mongo;
    private final RestClient workerClient;
    private final Path resumeDirectory;

    public ResumeController(
            MongoTemplate mongo,
            @Value("${jobpilot.worker-url:http://localhost:8000}") String workerUrl,
            @Value("${jobpilot.storage-dir:../storage/resumes}") String storageDir) {
        this.mongo = mongo;
        this.workerClient = RestClient.builder().baseUrl(workerUrl).build();
        this.resumeDirectory = Path.of(storageDir).toAbsolutePath().normalize();
    }

    @PostMapping(value = "/resumes", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> uploadResume(@RequestPart("file") MultipartFile file) {
        if (file.isEmpty() || file.getSize() > 5 * 1024 * 1024) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "PDF must be non-empty and 5 MB or smaller.");
        }
        String original = file.getOriginalFilename() == null
            ? "resume.pdf" : file.getOriginalFilename();
        if (!original.toLowerCase().endsWith(".pdf")) {
            throw new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE, "Only PDF resumes are supported.");
        }

        String id = UUID.randomUUID().toString();
        String safeName = id + ".pdf";
        Path destination = resumeDirectory.resolve(safeName);
        try {
            Files.createDirectories(resumeDirectory);
            Files.write(destination, file.getBytes());
        } catch (IOException ex) {
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR, "Could not store resume.");
        }

        Map extracted;
        try {
            MultipartBodyBuilder body = new MultipartBodyBuilder();
            byte[] bytes = file.getBytes();
            body.part("file", new ByteArrayResource(bytes) {
                @Override public String getFilename() { return safeName; }
            }).contentType(MediaType.APPLICATION_PDF);

            extracted = workerClient.post()
                .uri("/resume/parse")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(body.build())
                .retrieve()
                .body(Map.class);
        } catch (Exception ex) {
            try { Files.deleteIfExists(destination); } catch (IOException ignored) {}
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Resume extraction failed. Check the Python worker and OpenRouter configuration.");
        }

        ResumeRecord resume = new ResumeRecord();
        resume.setId(id);
        resume.setFileName(original);
        resume.setStoragePath(destination.toString());
        resume.setSizeBytes(file.getSize());
        mongo.save(resume);

        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null) profile = new CareerProfile();
        profile.setResumeId(id);
        profile.setExtracted(extracted);
        profile.setVerified(false);
        profile.setUpdatedAt(Instant.now());
        mongo.save(profile);

        return Map.of(
            "resumeId", id,
            "fileName", original,
            "profile", extracted,
            "verified", false
        );
    }

    @GetMapping("/profile")
    public Map<String, Object> getProfile() {
        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null) return Map.of("configured", false);
        return Map.of(
            "configured", true,
            "resumeId", profile.getResumeId() == null ? "" : profile.getResumeId(),
            "verified", profile.isVerified(),
            "profile", profile.getExtracted() == null ? Map.of() : profile.getExtracted(),
            "updatedAt", profile.getUpdatedAt().toString()
        );
    }

    @PutMapping("/profile")
    public Map<String, Object> updateProfile(@RequestBody Map<String, Object> updatedProfile) {
        CareerProfile profile = mongo.findById("default", CareerProfile.class);
        if (profile == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Upload a resume before editing the profile.");
        }
        profile.setExtracted(updatedProfile);
        profile.setVerified(true);
        profile.setUpdatedAt(Instant.now());
        mongo.save(profile);
        return Map.of("configured", true, "verified", true, "profile", updatedProfile);
    }
}
