import express from 'express';
import fs from 'fs';

const app = express();
const PORT = 3000;

// 1. Idle / baseline
app.get('/health', (req, res) => {
  res.send('OK');
});

// 2. I/O bound (file read)
app.get('/io', async (req, res) => {
  fs.readFile('./testfile.txt', 'utf8', (err, data) => {
    if (err) return res.status(500).send('Error');
    res.send('IO done');
  });
});

// 3. CPU bound
app.get('/cpu', (req, res) => {
  let result = 0;
  for (let i = 0; i < 50_000_000; i++) {
    result += Math.sqrt(i);
  }
  res.send('CPU done');
});

// 4. Mixed
app.get('/mixed', async (req, res) => {
  let result = 0;
  for (let i = 0; i < 20_000_000; i++) {
    result += Math.sqrt(i);
  }

  fs.readFile('./testfile.txt', 'utf8', (err) => {
    if (err) return res.status(500).send('Error');
    res.send('Mixed done');
  });
});

app.listen(PORT, () => {
  console.log(`Node server running on port ${PORT}`);
});
