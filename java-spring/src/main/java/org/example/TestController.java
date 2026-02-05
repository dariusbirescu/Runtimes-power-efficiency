package org.example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;

@RestController
public class TestController {

    // 1️⃣ CPU-bound
    @GetMapping("/cpu")
    public long cpu() {
        long count = 0;
        for (long i = 2; i < 2_000_000; i++) {
            boolean prime = true;
            for (long j = 2; j * j <= i; j++) {
                if (i % j == 0) { prime = false; break; }
            }
            if (prime) count++;
        }
        return count;
    }

    // 2️⃣ Memory-bound
    @GetMapping("/memory")
    public int memory() {
        List<byte[]> list = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            list.add(new byte[1_000_000]); // ~50MB total
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

    // 4️⃣ Mixed
    @PostMapping("/mixed")
    public int mixed(@RequestBody Map<String, Object> body) {
        int sum = body.toString().chars().sum();
        List<Integer> list = new ArrayList<>();
        for (int i = 0; i < 100_000; i++) list.add(i);
        Collections.shuffle(list);
        return sum + list.get(0);
    }
}
