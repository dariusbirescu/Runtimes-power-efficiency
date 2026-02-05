const express = require('express');
const app = express();
app.use(express.json());

// 1️⃣ CPU-bound
app.get('/cpu', (req, res) => {
  let count = 0;
  for (let i = 2; i < 2_000_000; i++) {
    let prime = true;
    for (let j = 2; j * j <= i; j++) {
      if (i % j === 0) { prime = false; break; }
    }
    if (prime) count++;
  }
  res.send({ count });
});

// 2️⃣ Memory-bound
app.get('/memory', (req, res) => {
  const arr = [];
  for (let i = 0; i < 50; i++) {
    arr.push(Buffer.alloc(1_000_000)); // ~50MB
  }
  res.send({ size: arr.length });
});

// 3️⃣ I/O-bound
app.get('/io', (req, res) => {
  let count = 0;
  const readNext = () => {
    if (count >= 10) return res.send('IO done');
    require('fs').readFile('./testfile.txt', 'utf8', (err) => {
      if (err) return res.status(500).send('Error');
      count++;
      readNext();
    });
  };
  readNext();
});

// 4️⃣ Mixed
app.post('/mixed', (req, res) => {
  const json = JSON.stringify(req.body);
  let sum = 0;
  for (const c of json) sum += c.charCodeAt(0);

  const arr = Array.from({ length: 100_000 }, (_, i) => i);
  arr.sort(() => Math.random() - 0.5);

  res.send({ result: sum + arr[0] });
});

app.listen(3000, () => console.log('Node server running'));
