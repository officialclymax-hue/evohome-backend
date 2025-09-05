// admin_static/app.js — CMS + Page Builder + uploads
const API_BASE = window.location.origin;
let token = localStorage.getItem("ADMIN_JWT") || null;

const CONTENT_KEYS = ["homepage","header","about","contact","footer","coverage","seo","request-quote","forms","chatbot","floating-buttons"];
const DATA_KEYS = ["services","blogs","gallery"];

const $ = id => document.getElementById(id);

// ---------- API ----------
async function api(path, options = {}) {
  const headers = options.headers || {};
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) { alert("Not authorized. Please log in again."); logout(); throw new Error("401"); }
  return res;
}

// ---------- AUTH ----------
async function login() {
  const email = $("email").value.trim();
  const password = $("password").value.trim();
  const res = await fetch(API_BASE + "/auth/login", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email,password}) });
  if (!res.ok){ $("loginMsg").innerText="Login failed"; return; }
  const j = await res.json();
  token = j.access_token; localStorage.setItem("ADMIN_JWT", token);
  $("loginView").style.display="none"; $("appView").style.display="grid"; buildLists(); loadPages();
}
function logout(){ token=null; localStorage.removeItem("ADMIN_JWT"); $("appView").style.display="none"; $("builderView").style.display="none"; $("loginView").style.display="block"; }
$("btnLogin").onclick = login; $("btnLogout").onclick = logout;

// ---------- NAV between CMS and Builder ----------
$("btnBuilder").onclick = ()=>{
  const showBuilder = $("builderView").style.display === "none";
  $("appView").style.display = showBuilder ? "none" : "grid";
  $("builderView").style.display = showBuilder ? "grid" : "none";
  if (showBuilder) loadPages();
};

// ---------- SIDEBAR (CMS) ----------
function buildLists(){
  $("listContent").innerHTML = CONTENT_KEYS.map(k=>`<li data-k="${k}">${k}</li>`).join("");
  $("listData").innerHTML = DATA_KEYS.map(k=>`<li data-k="${k}">${k}</li>`).join("");
  document.querySelectorAll("#listContent li, #listData li").forEach(li=>{
    li.onclick = ()=> loadCollection(li.getAttribute("data-k"));
  });
}
$("btnRefresh").onclick = buildLists;

// ---------- STATE (CMS) ----------
let currentKey = null;
let currentData = null;
let easyMode = true;

$("modeEasy").onclick = ()=>{ easyMode=true; renderView(); };
$("modeJson").onclick = ()=>{ easyMode=false; renderView(); };

// ---------- LOAD (CMS) ----------
async function loadCollection(k){
  currentKey = k; $("colTitle").innerText = k;
  try{
    if (DATA_KEYS.includes(k)) {
      const res = await api("/"+k); const raw = res.ok ? await res.json() : [];
      currentData = normalizeArray(k, raw);
      $("jsonBox").value = JSON.stringify(currentData, null, 2);
    } else {
      const res = await api("/content/"+k);
      currentData = res.ok ? await res.json() : {};
      $("jsonBox").value = res.ok ? JSON.stringify(currentData, null, 2) : "// Not found. Use Save to create content.";
    }
  }catch(e){ console.error(e); currentData = DATA_KEYS.includes(k) ? [] : {}; $("jsonBox").value="// Error loading"; }
  renderView();
}

// ---------- RENDER (CMS) ----------
function renderView(){
  $("easyMode").style.display = easyMode ? "block" : "none";
  $("jsonBox").style.display = easyMode ? "none" : "block";
  $("btnSaveJson").style.display = easyMode ? "none" : "inline-flex";

  $("formSingleton").style.display = "none";
  $("cardsList").style.display = "none";
  $("galleryGrid").style.display = "none";
  $("btnAddItem").style.display = "none";
  if (!currentKey) return;

  if (DATA_KEYS.includes(currentKey)) {
    if (currentKey === "gallery") renderGalleryGrid();
    else renderCardsList();
  } else {
    renderSingletonForm();
  }
}

// ---------- SINGLETON FORM ----------
function renderSingletonForm(){
  const form = $("formSingleton"); form.innerHTML=""; $("formSingleton").style.display="block";
  buildObjectForm(form, currentData, []);
}
function buildObjectForm(root, obj, path){
  Object.keys(obj||{}).forEach(key=>{
    const value = obj[key]; const fieldPath=[...path,key];
    if (Array.isArray(value) && value.length && typeof value[0] === "string") {
      const wrap = el('div','field'); wrap.appendChild(el('label',null,key+" (images)"));
      const list = el('div'); list.style.display="grid"; list.style.gridTemplateColumns="repeat(auto-fill,minmax(120px,1fr))"; list.style.gap="8px";
      value.forEach((url,idx)=>{
        const item=el('div'); const img=el('img'); img.src=url; img.style.width="100%"; img.style.height="80px"; img.style.objectFit="cover"; img.style.borderRadius="8px";
        const input=el('input'); input.type="text"; input.value=url; input.oninput=()=> setValue(fieldPath,idx,input.value);
        const row=el('div','row'); const up=btn('↑',()=> moveArray(fieldPath,idx,idx-1)); const down=btn('↓',()=> moveArray(fieldPath,idx,idx+1));
        const del=btn('Delete',()=>{ removeArray(fieldPath,idx); renderView(); }); del.className="ghost";
        row.append(up,down,del); item.append(img,input,row); list.appendChild(item);
      });
      const add=btn('+ Add image',()=>{ const url=prompt("Paste image URL, or leave blank to upload"); if(url){ pushArray(fieldPath,url); renderView(); } else openUpload(u=>{ pushArray(fieldPath,u); renderView(); }); });
      wrap.append(list,add); root.appendChild(wrap); return;
    }
    if (typeof value!=="object" || value===null){
      const wrap=el('div','field'); let input;
      if (typeof value==="boolean"){ input=el('input'); input.type="checkbox"; input.checked=value===true; input.onchange=()=> setPrimitive(fieldPath,input.checked); const row=el('div','switch'); row.append(el('span',null,key),input); wrap.append(row); }
      else if(typeof value==="number"){ wrap.append(el('label',null,key)); input=el('input'); input.type="number"; input.value=value; input.oninput=()=> setPrimitive(fieldPath,parseFloat(input.value||"0")); wrap.append(input); }
      else { wrap.append(el('label',null,key)); const long=(value && String(value).length>120)||String(value).includes("\n"); input=long?el('textarea'):el('input'); if(!long) input.type="text"; input.value=value??""; input.oninput=()=> setPrimitive(fieldPath,input.value); wrap.append(input); }
      root.appendChild(wrap); return;
    }
    const group=el('div','field'); group.append(el('div','badge',key)); root.appendChild(group); buildObjectForm(root,value,fieldPath);
  });
  function setPrimitive(path,val){ let ref=currentData; for(let i=0;i<path.length-1;i++){ if(!ref[path[i]]||typeof ref[path[i]]!=='object') ref[path[i]]={}; ref=ref[path[i]];} ref[path.at(-1)]=val; $("jsonBox").value=JSON.stringify(currentData,null,2); }
  function setValue(path,idx,val){ let ref=currentData; for(let i=0;i<path.length;i++) ref=ref[path[i]]; ref[idx]=val; $("jsonBox").value=JSON.stringify(currentData,null,2); }
  function pushArray(path,val){ let ref=currentData; for(let i=0;i<path.length;i++) ref=ref[path[i]]; ref.push(val); $("jsonBox").value=JSON.stringify(currentData,null,2); }
  function removeArray(path,idx){ let ref=currentData; for(let i=0;i<path.length;i++) ref=ref[path[i]]; ref.splice(idx,1); $("jsonBox").value=JSON.stringify(currentData,null,2); }
  function moveArray(path,from,to){ let ref=currentData; for(let i=0;i<path.length;i++) ref=ref[path[i]]; if(to<0||to>=ref.length) return; const [it]=ref.splice(from,1); ref.splice(to,0,it); $("jsonBox").value=JSON.stringify(currentData,null,2); renderView(); }
}

// ---------- ARRAYS (services/blogs) ----------
function renderCardsList(){
  $("cardsList").innerHTML=""; $("cardsList").style.display="grid"; $("btnAddItem").style.display="inline-flex"; $("galleryGrid").style.display="none";
  const arr = Array.isArray(currentData) ? currentData : [];
  if (arr.length===0) $("cardsList").innerHTML=`<div class="muted">No ${currentKey} yet. Click “+ Add item”.</div>`;
  arr.forEach((item,idx)=> $("cardsList").appendChild(makeCard(item,idx,currentKey)));
  enableDnD($("cardsList"),(from,to)=>{ if(to<0||to>=currentData.length) return; const [it]=currentData.splice(from,1); currentData.splice(to,0,it); $("jsonBox").value=JSON.stringify(currentData,null,2); renderCardsList(); });
  $("btnAddItem").onclick=()=>{ const blank=currentKey==="services"?{name:"",slug:"",category:"",image:"",images:[]}:{title:"",slug:"",author:"",date:"",excerpt:"",image:"",images:[],content:""}; currentData.push(blank); $("jsonBox").value=JSON.stringify(currentData,null,2); renderCardsList(); };
}
function makeCard(item,idx,type){
  const c=el('div','card'); c.setAttribute("draggable","true"); c.dataset.index=idx;
  const thumb=el('div','thumb'); const firstUrl=type==="blogs"?(item.image||(item.images&&item.images[0])||""):(item.image||(item.images&&item.images[0])||""); const img=el('img'); if(firstUrl) img.src=firstUrl; thumb.append(firstUrl?img:el('div','muted','No image')); c.append(thumb);
  if(type==="services"){ c.append(field("Name",item.name||"",v=>{item.name=v;sync();})); c.append(field("Slug",item.slug||"",v=>{item.slug=v;sync();})); c.append(field("Category",item.category||"",v=>{item.category=v;sync();})); c.append(field("Cover image",item.image||"",v=>{item.image=v;sync();},true,u=>{item.image=u;sync();})); c.append(imagesField(item,v=>{item.images=v;sync();})); }
  else { c.append(field("Title",item.title||"",v=>{item.title=v;sync();})); c.append(field("Slug",item.slug||"",v=>{item.slug=v;sync();})); c.append(field("Author",item.author||"",v=>{item.author=v;sync();})); c.append(field("Date (YYYY-MM-DD)",item.date||"",v=>{item.date=v;sync();})); c.append(textArea("Excerpt",item.excerpt||"",v=>{item.excerpt=v;sync();})); c.append(field("Cover image",item.image||"",v=>{item.image=v;sync();},true,u=>{item.image=u;sync();})); c.append(imagesField(item,v=>{item.images=v;sync();})); c.append(textArea("Content",item.content||"",v=>{item.content=v;sync();})); }
  const row=el('div','row'); const handle=el('span','handle','⠿'); const del=btn('Delete',()=>{currentData.splice(idx,1);sync();renderCardsList();}); del.classList.add('del'); row.append(handle,del); c.append(row);
  function sync(){ $("jsonBox").value=JSON.stringify(currentData,null,2); const u=type==="blogs"?(item.image||(item.images&&item.images[0])||""):(item.image||(item.images&&item.images[0])||""); if(u) img.src=u; }
  return c;
}

// ---------- GALLERY ----------
function renderGalleryGrid(){
  $("galleryGrid").innerHTML=""; $("galleryGrid").style.display="grid"; $("btnAddItem").style.display="inline-flex"; $("cardsList").style.display="none";
  const arr=Array.isArray(currentData)?currentData:[]; if(arr.length===0) $("galleryGrid").innerHTML=`<div class="muted">No gallery items yet. Click “+ Add item”.</div>`;
  arr.forEach((g,idx)=> $("galleryGrid").appendChild(makeGItem(g,idx)));
  enableDnD($("galleryGrid"),(from,to)=>{ if(to<0||to>=currentData.length) return; const [it]=currentData.splice(from,1); currentData.splice(to,0,it); $("jsonBox").value=JSON.stringify(currentData,null,2); renderGalleryGrid(); });
  $("btnAddItem").onclick=()=>{ currentData.push({title:"",category:"",src:"",images:[]}); $("jsonBox").value=JSON.stringify(currentData,null,2); renderGalleryGrid(); };
}
function makeGItem(g,idx){
  const wrap=el('div','g-item'); wrap.setAttribute("draggable","true"); wrap.dataset.index=idx;
  const t=el('div','thumb'); const img=el('img'); if(g.src) img.src=g.src; t.append(g.src?img:el('div','muted','No image'));
  const title=field("Title",g.title||"",v=>{g.title=v;sync();}); const cat=field("Category",g.category||"",v=>{g.category=v;sync();});
  const src=field("Image URL",g.src||"",v=>{g.src=v;sync();},true,u=>{g.src=u;sync();});
  const actions=el('div','actions'); const del=btn('Delete',()=>{currentData.splice(idx,1);sync();renderGalleryGrid();}); del.classList.add('del'); actions.append(del);
  wrap.append(t,title,cat,src,actions);
  function sync(){ $("jsonBox").value=JSON.stringify(currentData,null,2); if(g.src) img.src=g.src; }
  return wrap;
}

// ---------- COMMON UI HELPERS ----------
function field(labelText,val,onInput,withUpload=false,onUploaded){ const f=el('div','field'); f.append(el('label',null,labelText)); const row=el('div','kv'); const input=el('input'); input.type="text"; input.value=val??""; input.oninput=()=> onInput(input.value); row.append(input); if(withUpload){ const up=btn('Upload',()=> openUpload(url=>{ input.value=url; onInput(url); if(onUploaded) onUploaded(url); })); row.append(up); } f.append(row); return f; }
function textArea(labelText,val,onInput){ const f=el('div','field'); f.append(el('label',null,labelText)); const ta=el('textarea'); ta.value=val??""; ta.oninput=()=> onInput(ta.value); f.append(ta); return f; }
function imagesField(item,set){ const f=el('div','field'); f.append(el('label',null,"Images (list)")); const cont=el('div'); cont.style.display="grid"; cont.style.gridTemplateColumns="repeat(auto-fill,minmax(120px,1fr))"; cont.style.gap="8px"; const arr=Array.isArray(item.images)?item.images:[]; arr.forEach((url,i)=>{ const box=el('div'); const img=el('img'); img.src=url; img.style.width="100%"; img.style.height="80px"; img.style.objectFit="cover"; img.style.borderRadius="8px"; const inp=el('input'); inp.type="text"; inp.value=url; inp.oninput=()=>{arr[i]=inp.value; set(arr); $("jsonBox").value=JSON.stringify(currentData,null,2);}; const row=el('div','row'); const up=btn('↑',()=>{ if(i>0){const[x]=arr.splice(i,1);arr.splice(i-1,0,x);set(arr);renderView();}}); const down=btn('↓',()=>{ if(i<arr.length-1){const[x]=arr.splice(i,1);arr.splice(i+1,0,x);set(arr);renderView();}}); const del=btn('Delete',()=>{arr.splice(i,1);set(arr);renderView();}); del.className="ghost"; row.append(up,down,del); box.append(img,inp,row); cont.append(box); }); const add=btn('+ Add image',()=>{ const url=prompt("Paste image URL, or leave blank to upload"); if(url){arr.push(url);set(arr);renderView();} else openUpload(u=>{arr.push(u);set(arr);renderView();}); }); f.append(cont,add); return f; }
function enableDnD(container,onMove){ let dragIndex=null; container.querySelectorAll('[draggable="true"]').forEach(el=>{ el.addEventListener('dragstart',()=>{dragIndex=+el.dataset.index; el.classList.add('dragging');}); el.addEventListener('dragend',()=>{el.classList.remove('dragging'); dragIndex=null;}); }); container.addEventListener('dragover',e=> e.preventDefault()); container.addEventListener('drop',e=>{ e.preventDefault(); const target=e.target.closest('[draggable="true"]'); if(!target) return; const to=+target.dataset.index; if(dragIndex===null||isNaN(to)) return; onMove(dragIndex,to); }); }
function el(tag,cls,text){ const n=document.createElement(tag); if(cls) n.className=cls; if(text!=null) n.textContent=text; return n; }
function btn(label,fn){ const b=document.createElement("button"); b.textContent=label; b.className="ghost"; b.type="button"; b.onclick=fn; return b; }
function slugify(s){ s=(s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,""); return s || Math.random().toString(36).slice(2,10); }

// ---------- Upload ----------
function openUpload(onDone){ $("uploadedUrl").value=""; $("fileUpload").value=""; $("uploadDlg").showModal(); $("doUpload").onclick=async()=>{ const file=$("fileUpload").files[0]; if(!file) return alert("Choose a file"); const fd=new FormData(); fd.append("file",file); const headers=token?{"Authorization":"Bearer "+token}:{};
  const res=await fetch(API_BASE+"/upload-image",{method:"POST",body:fd,headers}); const j=await res.json(); $("uploadedUrl").value=j.url||"Upload failed"; if(j.url&&onDone) onDone(j.url); }; $("closeUpload").onclick=()=> $("uploadDlg").close(); }

// ---------- Save (CMS) ----------
$("btnSaveJson").onclick=async()=>{ if(!currentKey) return alert("Select a collection first"); let parsed; try{ parsed=JSON.parse($("jsonBox").value);}catch(e){return alert("Invalid JSON: "+e.message);} const url=DATA_KEYS.includes(currentKey)?"/"+currentKey:"/content/"+currentKey; const res=await api(url,{method:"POST",body:JSON.stringify(parsed)}); alert(res.ok?"Saved!":"Save failed: "+res.status); };
$("btnSaveEasy").onclick=async()=>{ if(!currentKey) return alert("Select a collection first"); const url=DATA_KEYS.includes(currentKey)?"/"+currentKey:"/content/"+currentKey; const res=await api(url,{method:"POST",body:JSON.stringify(currentData)}); alert(res.ok?"Saved!":"Save failed: "+res.status); };
$("btnExport").onclick=()=>{ if(!currentKey) return alert("Select a collection first"); const blob=new Blob([$("jsonBox").value],{type:"application/json"}); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=currentKey+".json"; a.click(); };
$("fileImport").onchange=async e=>{ if(!currentKey) return alert("Select a collection first"); const f=e.target.files[0]; if(!f) return; const text=await f.text(); try{ currentData=JSON.parse(text); $("jsonBox").value=JSON.stringify(currentData,null,2); renderView(); }catch(err){ alert("Invalid JSON file: "+err.message); }};

// ---------- Seed dialogs ----------
$("btnSeed").onclick=()=> $("seedDlg").showModal(); $("closeSeed").onclick=()=> $("seedDlg").close();
$("doSeed").onclick=async()=>{ $("seedOut").textContent="Seeding..."; const res=await api("/seed",{method:"POST"}); const j=await res.json().catch(()=>null); $("seedOut").textContent = j ? JSON.stringify(j.report,null,2) : "Seed failed: "+res.status; };

// ---------- Normalizer for arrays ----------
function normalizeArray(name, raw){
  if (Array.isArray(raw)) return raw;
  if (!raw || typeof raw !== "object") return [];
  for (const key of [name,"items","data","list","rows","entries","records"]) if (Array.isArray(raw[key])) return raw[key];
  const collect=obj=>{ const out=[]; if(Array.isArray(obj)) out.push(obj); else if(obj&&typeof obj==="object") for(const v of Object.values(obj)) out.push(...collect(v)); return out; };
  const cands=collect(raw); if (cands.length) return cands.sort((a,b)=>b.length-a.length)[0];
  const out=[]; for(const [k,v] of Object.entries(raw)){ if(typeof v==="string"){ if(name==="blogs") out.push({title:v,slug:slugify(k)}); else out.push({name:v,slug:slugify(k)});} else if(v&&typeof v==="object"){ const item={...v}; if(name==="blogs"){ item.title=item.title||item.name||k; item.slug=item.slug||slugify(item.title); item.images=item.images||[]; } else { item.name=item.name||item.title||k; item.slug=item.slug||slugify(item.name); item.images=item.images||[]; } out.push(item);} }
  return out;
}

// -------------------------- PAGE BUILDER --------------------------
let BLOCK_DEFS = {};
let currentPageSlug = "homepage";
let blocks = []; // array of {type, props}

async function loadPages(){
  // list pages
  const list = await api("/pages"); const j = await list.json();
  $("listPages").innerHTML = (j.pages||[]).map(p=>`<li data-p="${p}">${p}</li>`).join("");
  document.querySelectorAll("#listPages li").forEach(li=>{
    li.onclick = ()=> { $("pageSlug").value = li.getAttribute("data-p"); loadPage(); };
  });

  // defs
  const defs = await api("/blocks/definitions"); BLOCK_DEFS = await defs.json();
  renderPalette();
}

function renderPalette(){
  const pal = $("palette"); pal.innerHTML = "";
  Object.entries(BLOCK_DEFS).forEach(([type,def])=>{
    const div = document.createElement("div");
    div.className = "palette-item"; div.setAttribute("draggable","true"); div.dataset.type = type;
    div.textContent = def.label || type;
    pal.appendChild(div);
  });

  // drag start from palette
  pal.querySelectorAll(".palette-item").forEach(el=>{
    el.addEventListener("dragstart", e=>{
      e.dataTransfer.setData("text/plain", el.dataset.type);
    });
  });

  // canvas drop
  const canvas = $("canvas");
  canvas.addEventListener("dragover", e=> e.preventDefault());
  canvas.addEventListener("drop", e=>{
    e.preventDefault();
    const t = e.dataTransfer.getData("text/plain");
    if (!t) return;
    const def = BLOCK_DEFS[t] || {fields:{}};
    const props = defaultPropsFor(def.fields);
    blocks.push({type: t, props});
    renderCanvas();
  });
}

function defaultPropsFor(fields){
  const o = {};
  Object.entries(fields||{}).forEach(([k,v])=>{
    if (v.type === "images") o[k] = [];
    else if (v.type === "number") o[k] = 0;
    else if (v.type === "list") o[k] = [];
    else o[k] = "";
  });
  return o;
}

$("btnLoadPage").onclick = loadPage;
async function loadPage(){
  currentPageSlug = ($("pageSlug").value || "homepage").trim();
  $("builderTitle").innerText = currentPageSlug;
  const res = await api("/pages/"+currentPageSlug);
  const j = await res.json();
  blocks = Array.isArray(j.blocks) ? j.blocks : [];
  renderCanvas();
}

$("btnSavePage").onclick = async ()=>{
  const res = await api("/pages/"+
