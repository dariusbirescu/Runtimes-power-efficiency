package org.example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

@RestController
public class TestController {

    // 1️⃣ CPU-bound (reduced for Raspberry Pi)
    @GetMapping("/cpu")
    public long cpu() {
        long count = 0;
        for (long i = 2; i < 500_000; i++) {  // Reduced from 2M to 500K
            boolean prime = true;
            for (long j = 2; j * j <= i; j++) {
                if (i % j == 0) { prime = false; break; }
            }
            if (prime) count++;
        }
        return count;
    }

    // 2️⃣ Memory-bound (reduced for Raspberry Pi)
    @GetMapping("/memory")
    public int memory() {
        List<byte[]> list = new ArrayList<>();
        for (int i = 0; i < 25; i++) {  // Reduced from 50 to 25
            list.add(new byte[1_000_000]); // ~25MB total
        }
        return list.size();
    }

    // 3️⃣ I/O-bound
    @GetMapping("/io")
    public String io() throws Exception {
        for (int i = 0; i < 10; i++) {
            Files.readString(Path.of("testfile.txt"));
        }
        return "IO done";
    }

    // 4️⃣ Mixed (reduced for Raspberry Pi)
    @PostMapping("/mixed")
    public int mixed(@RequestBody Map<String, Object> body) {
        int sum = body.toString().chars().sum();
        List<Integer> list = new ArrayList<>();
        for (int i = 0; i < 25_000; i++) list.add(i);  // Reduced from 100K to 25K
        Collections.shuffle(list);
        return sum + list.get(0);
    }
}
