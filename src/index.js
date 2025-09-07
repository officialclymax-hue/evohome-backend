import 'dotenv/config';
import express from 'express';
import helmet from 'helmet';
import morgan from 'morgan';
import cors from 'cors';
import { PrismaClient } from '@prisma/client';
import bodyParser from 'body-parser';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const prisma = new PrismaClient();
const app = express();

app.use(helmet());
app.use(morgan('tiny'));
app.use(cors({ origin: (process.env.CORS_ORIGIN || '*').split(','), credentials: true }));
app.use(bodyParser.json());

const requireAdmin = (req, res, next) => {
  const key = req.headers['x-admin-key'] || req.query.key;
  if (!process.env.ADMIN_KEY) return res.status(500).json({ error: 'ADMIN_KEY not set' });
  if (key !== process.env.ADMIN_KEY) return res.status(401).json({ error: 'Unauthorized' });
  next();
};

app.get('/api/health', (_, res) => res.json({ ok: true }));

/* Services */
app.get('/api/services', async (req, res) => {
  const { category, featured } = req.query;
  const where = {};
  if (category) where.category = category;
  if (featured === 'true') where.featured = true;
  res.json(await prisma.service.findMany({ where, orderBy: { name: 'asc' } }));
});
app.get('/api/services/:slug', async (req, res) => {
  const s = await prisma.service.findUnique({ where: { slug: req.params.slug } });
  if (!s) return res.status(404).json({ error: 'Not found' });
  res.json(s);
});
app.post('/api/services', requireAdmin, async (req, res) => res.json(await prisma.service.create({ data: req.body })));
app.put('/api/services/:id', requireAdmin, async (req, res) => res.json(await prisma.service.update({ where: { id: req.params.id }, data: req.body })));
app.delete('/api/services/:id', requireAdmin, async (req, res) => { await prisma.service.delete({ where: { id: req.params.id } }); res.json({ ok: true }); });

/* Counties */
app.get('/api/counties', async (req, res) => {
  const isPrimary = req.query.isPrimary === 'true' ? true : undefined;
  const where = typeof isPrimary === 'boolean' ? { isPrimary } : {};
  res.json(await prisma.county.findMany({ where, orderBy: { name: 'asc' } }));
});
app.get('/api/counties/:slug', async (req, res) => {
  const c = await prisma.county.findUnique({ where: { slug: req.params.slug } });
  if (!c) return res.status(404).json({ error: 'Not found' });
  res.json(c);
});

/* Blog */
app.get('/api/blog-posts', async (req, res) => {
  const { category } = req.query;
  const where = category ? { category } : undefined;
  res.json(await prisma.blogPost.findMany({ where, orderBy: { date: 'desc' } }));
});
app.get('/api/blog-posts/:slug', async (req, res) => {
  const p = await prisma.blogPost.findUnique({ where: { slug: req.params.slug } });
  if (!p) return res.status(404).json({ error: 'Not found' });
  res.json(p);
});

/* Gallery */
app.get('/api/gallery-images', async (req, res) => {
  const { category } = req.query;
  const where = category ? { category } : undefined;
  res.json(await prisma.galleryImage.findMany({ where, orderBy: { createdAt: 'desc' } }));
});

/* Testimonials */
app.get('/api/testimonials', async (_req, res) => {
  res.json(await prisma.testimonial.findMany({ orderBy: { date: 'desc' } }));
});

/* Company (singleton) */
app.get('/api/company', async (_req, res) => {
  const company = await prisma.companyInfo.findFirst();
  if (!company) return res.status(404).json({ error: 'Not found' });
  res.json(company);
});
app.put('/api/company', requireAdmin, async (req, res) => {
  const existing = await prisma.companyInfo.findFirst();
  const data = req.body;
  if (!existing) return res.json(await prisma.companyInfo.create({ data }));
  return res.json(await prisma.companyInfo.update({ where: { id: existing.id }, data }));
});

/* Public form submissions */
app.post('/api/form-submissions', async (req, res) => {
  const created = await prisma.formSubmission.create({ data: req.body });
  res.json({ ok: true, id: created.id });
});

/* Admin list of leads */
app.get('/api/form-submissions', requireAdmin, async (req, res) => {
  const page = parseInt(req.query.page || '1', 10);
  const limit = parseInt(req.query.limit || '20', 10);
  const [items, total] = await Promise.all([
    prisma.formSubmission.findMany({ orderBy: { submissionDate: 'desc' }, skip: (page-1)*limit, take: limit }),
    prisma.formSubmission.count()
  ]);
  res.json({ items, total, page, pages: Math.ceil(total/limit) });
});

/* Seeder (reads dist/seed/*.json) */
app.post('/api/seed', requireAdmin, async (_req, res) => {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const dir = path.join(__dirname, 'seed');
  const read = (fname) => JSON.parse(fs.readFileSync(path.join(dir, fname), 'utf-8'));

  try {
    const company = read('companyInfo.json');
    const services = read('services.json');
    const counties = read('counties.json');
    const posts = read('blogPosts.json');
    const gallery = read('galleryImages.json');
    const testimonials = read('testimonials.json');

    if (company) await prisma.companyInfo.upsert({ where: { id: company.id }, update: company, create: company });
    for (const s of services || []) await prisma.service.upsert({ where: { slug: s.slug }, update: s, create: s });
    for (const c of counties || []) await prisma.county.upsert({ where: { slug: c.slug }, update: c, create: c });
    for (const b of posts || []) await prisma.blogPost.upsert({ where: { slug: b.slug }, update: b, create: b });
    for (const g of gallery || []) await prisma.galleryImage.upsert({ where: { id: g.id }, update: g, create: g });
    for (const t of testimonials || []) await prisma.testimonial.upsert({ where: { id: t.id }, update: t, create: t });

    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

/* Simple Admin UI (no build step, open /admin?key=YOUR_ADMIN_KEY) */
const guard = (req, res, next) => {
  const key = req.query.key;
  if (!process.env.ADMIN_KEY) return res.status(500).send('ADMIN_KEY not set');
  if (key !== process.env.ADMIN_KEY) return res.status(401).send('Unauthorized');
  next();
};

app.get('/admin', guard, (_req, res) => {
  res.send(`<!doctype html><html><head><meta charset="utf-8">
<title>EvoHome Admin</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:system-ui,Arial;padding:20px;max-width:1100px;margin:auto}
h1,h2{color:#2B4C9B}input,textarea,select{width:100%;padding:8px;margin:4px 0}
button{padding:8px 12px;margin:6px 0;background:#2B4C9B;color:#fff;border:none;border-radius:6px;cursor:pointer}
pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:10px 0;background:#fff}
.flex{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.small{font-size:12px;color:#666}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #eee;padding:8px;text-align:left}
</style></head><body>
<h1>EvoHome Admin (Lite)</h1>
<p class="small">Open with <code>/admin?key=YOUR_ADMIN_KEY</code></p>

<div class="card">
  <h2>Seed database</h2>
  <button onclick="seed()">Import Seed JSON</button>
  <pre id="seedlog"></pre>
</div>

<div class="card">
  <h2>Company Info</h2>
  <div class="flex">
    <button onclick="loadCompany()">Load</button>
    <button onclick="saveCompany()">Save</button>
  </div>
  <textarea id="companyJson" rows="12" placeholder="CompanyInfo JSON"></textarea>
</div>

<div class="card">
  <h2>Services</h2>
  <button onclick="loadServices()">Load Services</button>
  <pre id="servicesOut"></pre>
</div>

<div class="card">
  <h2>Leads (Form Submissions)</h2>
  <button onclick="loadLeads()">Refresh</button>
  <table id="leadsTbl"><thead><tr><th>Date</th><th>Name</th><th>Phone</th><th>Service</th><th>Postcode</th></tr></thead><tbody></tbody></table>
</div>

<script>
const key = new URLSearchParams(location.search).get('key');

function seed(){
  fetch('/api/seed?key='+key,{method:'POST'})
    .then(r=>r.json()).then(j=>{
      document.getElementById('seedlog').textContent = JSON.stringify(j,null,2);
      alert('Seeding complete');
    }).catch(e=>alert(e));
}
function loadCompany(){
  fetch('/api/company').then(r=>r.json()).then(j=>{
    document.getElementById('companyJson').value = JSON.stringify(j,null,2);
  }).catch(()=>{ document.getElementById('companyJson').value='{}'; });
}
function saveCompany(){
  let data={}; try{ data = JSON.parse(document.getElementById('companyJson').value||'{}'); }catch(e){return alert('Invalid JSON');}
  fetch('/api/company?key='+key,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(r=>r.json()).then(()=>alert('Saved')).catch(e=>alert(e));
}
function loadServices(){
  fetch('/api/services').then(r=>r.json()).then(j=>{
    document.getElementById('servicesOut').textContent = JSON.stringify(j,null,2);
  });
}
function loadLeads(page=1){
  fetch('/api/form-submissions?page='+page+'&key='+key).then(r=>r.json()).then(j=>{
    const tb=document.querySelector('#leadsTbl tbody'); tb.innerHTML='';
    j.items.forEach(x=>{
      const tr=document.createElement('tr');
      tr.innerHTML='<td>'+new Date(x.submissionDate).toLocaleString()
        +'</td><td>'+x.firstName+' '+x.lastName+'</td><td>'+x.phone+'</td><td>'+x.service+'</td><td>'+x.postcode+'</td>';
      tb.appendChild(tr);
    });
  });
}
</script>
</body></html>`);
});

const port = process.env.PORT || 8080;
app.listen(port, () => console.log('Backend running on', port));
