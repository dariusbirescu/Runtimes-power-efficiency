package org.example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;

@RestController
public class TestController {

    // 1. Idle / baseline
    @GetMapping("/health")
    public String health() {
        return "OK";
    }

    // 2. I/O bound
    @GetMapping("/io")
    public String io() throws Exception {
        Files.readString(Path.of("testfile.txt"));
        return "IO done";
    }

    // 3. CPU bound
    @GetMapping("/cpu")
    public String cpu() {
        double result = 0;
        for (int i = 0; i < 50_000_000; i++) {
            result += Math.sqrt(i);
        }
        return "CPU done";
    }

    // 4. Mixed
    @GetMapping("/mixed")
    public String mixed() throws Exception {
        double result = 0;
        for (int i = 0; i < 20_000_000; i++) {
            result += Math.sqrt(i);
        }
        Files.readString(Path.of("testfile.txt"));
        return "Mixed done";
    }
}
