import 'dotenv/config';
import express from 'express';
import helmet from 'helmet';
import morgan from 'morgan';
import cors from 'cors';
import { PrismaClient } from '@prisma/client';
import bodyParser from 'body-parser';
import path from 'path';
import { fileURLToPath } from 'url';

const prisma = new PrismaClient();
const app = express();

// security + logs + cors
app.use(helmet());
app.use(morgan('tiny'));
app.use(cors({
  origin: (process.env.CORS_ORIGIN || '*').split(','),
  credentials: true
}));
app.use(bodyParser.json());

// simple admin-key middleware for write routes
const requireAdmin = (req, res, next) => {
  const key = req.headers['x-admin-key'] || req.query.key;
  if (!process.env.ADMIN_KEY) return res.status(500).json({ error: 'ADMIN_KEY not set' });
  if (key !== process.env.ADMIN_KEY) return res.status(401).json({ error: 'Unauthorized' });
  next();
};

// health
app.get('/api/health', (_, res) => res.json({ ok: true }));

/** ====== Services ====== */
app.get('/api/services', async (req, res) => {
  const { category, featured } = req.query;
  const where = {};
  if (category) where.category = category;
  if (featured === 'true') where.featured = true;
  const items = await prisma.service.findMany({ where, orderBy: { name: 'asc' } });
  res.json(items);
});

app.get('/api/services/:slug', async (req, res) => {
  const item = await prisma.service.findUnique({ where: { slug: req.params.slug } });
  if (!item) return res.status(404).json({ error: 'Not found' });
  res.json(item);
});

app.post('/api/services', requireAdmin, async (req, res) => {
  const item = await prisma.service.create({ data: req.body });
  res.json(item);
});
app.put('/api/services/:id', requireAdmin, async (req, res) => {
  const item = await prisma.service.update({ where: { id: req.params.id }, data: req.body });
  res.json(item);
});
app.delete('/api/services/:id', requireAdmin, async (req, res) => {
  await prisma.service.delete({ where: { id: req.params.id } });
  res.json({ ok: true });
});

/** ====== Counties ====== */
app.get('/api/counties', async (req, res) => {
  const isPrimary = req.query.isPrimary === 'true' ? true : undefined;
  const where = typeof isPrimary === 'boolean' ? { isPrimary } : {};
  const items = await prisma.county.findMany({ where, orderBy: { name: 'asc' } });
  res.json(items);
});

app.get('/api/counties/:slug', async (req, res) => {
  const item = await prisma.county.findUnique({ where: { slug: req.params.slug } });
  if (!item) return res.status(404).json({ error: 'Not found' });
  res.json(item);
});

app.post('/api/counties', requireAdmin, async (req, res) => {
  const item = await prisma.county.create({ data: req.body });
  res.json(item);
});
app.put('/api/counties/:id', requireAdmin, async (req, res) => {
  const item = await prisma.county.update({ where: { id: req.params.id }, data: req.body });
  res.json(item);
});
app.delete('/api/counties/:id', requireAdmin, async (req, res) => {
  await prisma.county.delete({ where: { id: req.params.id } });
  res.json({ ok: true });
});

/** ====== Blog ====== */
app.get('/api/blog-posts', async (req, res) => {
  const { category } = req.query;
  const where = category ? { category } : undefined;
  const items = await prisma.blogPost.findMany({ where, orderBy: { date: 'desc' } });
  res.json(items);
});

app.get('/api/blog-posts/:slug', async (req, res) => {
  const item = await prisma.blogPost.findUnique({ where: { slug: req.params.slug } });
  if (!item) return res.status(404).json({ error: 'Not found' });
  res.json(item);
});

app.post('/api/blog-posts', requireAdmin, async (req, res) => {
  const item = await prisma.blogPost.create({ data: req.body });
  res.json(item);
});
app.put('/api/blog-posts/:id', requireAdmin, async (req, res) => {
  const item = await prisma.blogPost.update({ where: { id: req.params.id }, data: req.body });
  res.json(item);
});
app.delete('/api/blog-posts/:id', requireAdmin, async (req, res) => {
  await prisma.blogPost.delete({ where: { id: req.params.id } });
  res.json({ ok: true });
});

/** ====== Gallery ====== */
app.get('/api/gallery-images', async (req, res) => {
  const { category } = req.query;
  const where = category ? { category } : undefined;
  const items = await prisma.galleryImage.findMany({ where, orderBy: { createdAt: 'desc' } });
  res.json(items);
});

app.post('/api/gallery-images', requireAdmin, async (req, res) => {
  const item = await prisma.galleryImage.create({ data: req.body });
  res.json(item);
});
app.put('/api/gallery-images/:id', requireAdmin, async (req, res) => {
  const item = await prisma.galleryImage.update({ where: { id: req.params.id }, data: req.body });
  res.json(item);
});
app.delete('/api/gallery-images/:id', requireAdmin, async (req, res) => {
  await prisma.galleryImage.delete({ where: { id: req.params.id } });
  res.json({ ok: true });
});

/** ====== Testimonials ====== */
app.get('/api/testimonials', async (_req, res) => {
  const items = await prisma.testimonial.findMany({ orderBy: { date: 'desc' } });
  res.json(items);
});

app.post('/api/testimonials', requireAdmin, async (req, res) => {
  const item = await prisma.testimonial.create({ data: req.body });
  res.json(item);
});
app.put('/api/testimonials/:id', requireAdmin, async (req, res) => {
  const item = await prisma.testimonial.update({ where: { id: req.params.id }, data: req.body });
  res.json(item);
});
app.delete('/api/testimonials/:id', requireAdmin, async (req, res) => {
  await prisma.testimonial.delete({ where: { id: req.params.id } });
  res.json({ ok: true });
});

/** ====== Company (singleton) ====== */
app.get('/api/company', async (_req, res) => {
  const item = await prisma.companyInfo.findFirst();
  if (!item) return res.status(404).json({ error: 'Not found' });
  res.json(item);
});

app.put('/api/company', requireAdmin, async (req, res) => {
  const existing = await prisma.companyInfo.findFirst();
  const data = req.body;
  if (!existing) {
    const created = await prisma.companyInfo.create({ data });
    res.json(created);
  } else {
    const updated = await prisma.companyInfo.update({ where: { id: existing.id }, data });
    res.json(updated);
  }
});

/** ====== Forms (public submit) ====== */
app.post('/api/form-submissions', async (req, res) => {
  const data = req.body;
  const created = await prisma.formSubmission.create({ data });
  res.json({ ok: true, id: created.id });
});

app.get('/api/form-submissions', requireAdmin, async (req, res) => {
  const page = parseInt(req.query.page || '1', 10);
  const limit = parseInt(req.query.limit || '20', 10);
  const [items, total] = await Promise.all([
    prisma.formSubmission.findMany({ orderBy: { submissionDate: 'desc' }, skip: (page-1)*limit, take: limit }),
    prisma.formSubmission.count()
  ]);
  res.json({ items, total, page, pages: Math.ceil(total/limit) });
});

/** ====== Seed route (one-click import from JSON) ====== */
app.post('/api/seed', requireAdmin, async (_req, res) => {
  // reads /src/seed/*.json from the deployed image
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const read = (name) => JSON.parse(
    Buffer.from(
      // note: __dirname points to dist at runtime, seed files are copied to dist/seed in build script
      // we’ll place them under dist/seed/*.json
      require('fs').readFileSync(path.join(__dirname, 'seed', name), 'utf-8')
    ).toString()
  );

  const company = read('companyInfo.json');
  const services = read('services.json');
  const counties = read('counties.json');
  const posts = read('blogPosts.json');
  const gallery = read('galleryImages.json');
  const testimonials = read('testimonials.json');

  if (company) {
    await prisma.companyInfo.upsert({ where: { id: company.id }, update: company, create: company });
  }
  for (const s of services || []) {
    await prisma.service.upsert({ where: { slug: s.slug }, update: s, create: s });
  }
  for (const c of counties || []) {
    await prisma.county.upsert({ where: { slug: c.slug }, update: c, create: c });
  }
  for (const b of posts || []) {
    await prisma.blogPost.upsert({ where: { slug: b.slug }, update: b, create: b });
  }
  for (const g of gallery || []) {
    await prisma.galleryImage.upsert({ where: { id: g.id }, update: g, create: g });
  }
  for (const t of testimonials || []) {
    await prisma.testimonial.upsert({ where: { id: t.id }, update: t, create: t });
  }

  res.json({ ok: true });
});

/** ====== Admin Lite (static page) ====== */
const adminKeyGuard = (req, res, next) => {
  const key = req.query.key;
  if (!process.env.ADMIN_KEY) return res.status(500).send('ADMIN_KEY not set');
  if (key !== process.env.ADMIN_KEY) return res.status(401).send('Unauthorized');
  next();
};

app.get('/admin', adminKeyGuard, (_req, res) => {
  // very simple admin panel with fetches (minimal quick tool)
  res.send(`
<!doctype html><html><head><meta charset="utf-8">
<title>EvoHome Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:system-ui,Arial;padding:20px;max-width:900px;margin:auto}input,textarea,select{width:100%;padding:8px;margin:4px 0}button{padding:8px 12px;margin:6px 0}pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto}</style>
</head><body>
<h1>EvoHome Admin (Lite)</h1>
<p>Authenticated with ?key=YOUR_ADMIN_KEY</p>

<section>
<h2>Seed database</h2>
<button onclick="seed()">Import from seed JSON</button>
<pre id="seedlog"></pre>
</section>

<section>
<h2>Company Info</h2>
<button onclick="loadCompany()">Load</button>
<form id="companyForm" onsubmit="saveCompany();return false;">
  <textarea id="companyJson" rows="12" placeholder="CompanyInfo JSON"></textarea>
  <button type="submit">Save Company</button>
</form>
</section>

<section>
<h2>Services</h2>
<button onclick="loadServices()">Load</button>
<pre id="servicesOut"></pre>
</section>

<script>
const key = new URLSearchParams(location.search).get('key');
function seed(){
  fetch('/api/seed?key='+key,{method:'POST'}).then(r=>r.json()).then(j=>{
    document.getElementById('seedlog').textContent = JSON.stringify(j,null,2);
  }).catch(e=>alert(e));
}
function loadCompany(){
  fetch('/api/company').then(r=>r.json()).then(j=>{
    document.getElementById('companyJson').value = JSON.stringify(j,null,2);
  });
}
function saveCompany(){
  const data = JSON.parse(document.getElementById('companyJson').value || '{}');
  fetch('/api/company?key='+key,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(r=>r.json()).then(j=>alert('Saved')).catch(e=>alert(e));
}
function loadServices(){
  fetch('/api/services').then(r=>r.json()).then(j=>{
    document.getElementById('servicesOut').textContent = JSON.stringify(j,null,2);
  });
}
</script>
</body></html>
  `);
});

const port = process.env.PORT || 8080;
app.listen(port, () => {
  console.log('EvoHome backend running on port', port);
});
