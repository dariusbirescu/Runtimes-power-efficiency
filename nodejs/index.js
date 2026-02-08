import express from 'express';
import { readFile } from 'fs/promises';
import { shuffle } from 'lodash-es';
const app = express();
app.use(express.json());

// 1️⃣ CPU-bound (reduced for Raspberry Pi)
app.get('/cpu', (req, res) => {
  let count = 0;
  for (let i = 2; i < 100_000; i++) {  // Reduced from 500K to 100K
    let prime = true;
    for (let j = 2; j * j <= i; j++) {
      if (i % j === 0) { prime = false; break; }
    }
    if (prime) count++;
  }
  res.send({ count });
});

// 2️⃣ Memory-bound (reduced for Raspberry Pi)
app.get('/memory', (req, res) => {
  const arr = [];
  for (let i = 0; i < 25; i++) {  // Reduced from 50 to 25
    arr.push(Buffer.alloc(1_000_000)); // ~25MB
  }
  res.send({ size: arr.length });
});

// 3️⃣ I/O-bound
app.get('/io', async (req, res) => {
  try {
    await readFile('./testfile.txt', 'utf8');
    res.send('IO done');
  } catch (err) {
    res.status(500).send('Error');
  }
});

// 4️⃣ Mixed (reduced for Raspberry Pi)
app.get('/mixed', (req, res) => {
  // String operations (CPU)
  const str = 'test data for mixed workload';
  let sum = 0;
  for (const c of str) sum += c.charCodeAt(0);

  // Array operations (CPU + Memory)
  let arr = Array.from({ length: 5_000 }, (_, i) => i);
  arr = shuffle(arr);  // Lodash shuffle uses Fisher-Yates, same as Java's Collections.shuffle()

  res.send({ result: sum + arr[0] });
});

app.listen(3000, () => console.log('Node server running'));
