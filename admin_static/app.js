// admin_static/app.js — Non-technical “Easy mode” admin with image thumbnails
const API = location.origin;
let token = null;           // JWT from /auth/login
let current = null;         // { type: 'content'|'data', key: string }
let model = null;           // current JSON object/array shown in Easy mode

// Left sidebar lists
const CONTENT_KEYS = [
  "homepage","header","about","contact","footer","coverage",
  "seo","request-quote","forms","chatbot","floating-buttons"
];
const DATA_KEYS = ["services","blogs","gallery"];

// ----------------- small helpers -----------------
function $(id){ return document.getElementById(id); }
function el(tag, props={}, children=[]) {
  const n = document.createElement(tag);
  Object.assign(n, props);
  if(!Array.isArray(children)) children=[children];
  children.forEach(c => c!=null && n.appendChild(typeof c==="string" ? document.createTextNode(c) : c));
  return n;
}
async function api(path, options={}) {
  const headers = options.headers || {};
  if(token) headers.Authorization = "Bearer " + token;
  if(options.body && !(options.body instanceof FormData) && !headers["Content-Type"])
    headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, {...options, headers});
  return res;
}
function labelFor(path){
  const key = String(path[path.length-1] ?? "field");
  return key.replace(/[-_]/g, " ").replace(/\b\w/g, m=>m.toUpperCase());
}
function keyName(path){ return String(path[path.length-1] ?? ""); }
function setAtPath(obj, path, v){
  let cur = obj;
  for(let i=0;i<path.length-1;i++){
    const k = path[i];
    if(cur[k]==null || typeof cur[k]!=="object") cur[k] = (typeof path[i+1]==="number" ? [] : {});
    cur = cur[k];
  }
  cur[path[path.length-1]] = v;
}
function getAtPath(obj, path){ return path.reduce((o,k)=> (o==null?undefined:o[k]), obj); }

// Image helpers
function isImageUrl(s){
  if(!s || typeof s !== "string") return false;
  return /\.(png|jpe?g|gif|webp|avif|svg)(\?.*)?$/i.test(s);
}
function isImagesKey(path){
  const k = keyName(path).toLowerCase();
  return k === "images" || k === "photos" || k === "gallery";
}

// ----------------- auth -----------------
$("btnLogin").onclick = async ()=>{
  const email = $("email").value.trim();
  const password = $("password").value;
  const r = await fetch(API+"/auth/login", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({email,password})
  });
  if(!r.ok){ $("msg").textContent = "Login failed"; return; }
  const j = await r.json(); token = j.access_token;
  initUI();
};
$("btnLogout").onclick = ()=>{ token=null; current=null; model=null; $("auth").style.display=""; $("main").style.display="none"; };
$("btnRefresh").onclick = ()=> initLists();

// ----------------- UI scaffold -----------------
function initUI(){
  $("auth").style.display="none";
  $("main").style.display="";
  initLists();
  // tabs
  $("tabEasy").onclick = ()=>{ $("tabEasy").classList.add("active"); $("tabJSON").classList.remove("active"); $("easyPanel").style.display=""; $("jsonPanel").style.display="none"; };
  $("tabJSON").onclick = ()=>{ $("tabJSON").classList.add("active"); $("tabEasy").classList.remove("active"); $("easyPanel").style.display="none"; $("jsonPanel").style.display=""; syncEditorFromModel(); };
}
function initLists(){
  const cl = $("contentList"), dl = $("dataList");
  cl.innerHTML=""; dl.innerHTML="";
  CONTENT_KEYS.forEach(k=>{
    const li = el("li", {className:"item", onclick: ()=>loadContent(k)}, [k]);
    cl.appendChild(li);
  });
  DATA_KEYS.forEach(k=>{
    const li = el("li", {className:"item", onclick: ()=>loadData(k)}, [k]);
    dl.appendChild(li);
  });
}

// ----------------- loaders -----------------
async function loadContent(key){
  current = {type:"content", key};
  $("panelTitle").textContent = key;
  const r = await api("/content/"+key);
  model = r.ok ? await r.json() : {};
  renderEasy(model);
  $("editor").value = JSON.stringify(model, null, 2);
}
async function loadData(key){
  current = {type:"data", key};
  $("panelTitle").textContent = key;
  const r = await api("/"+key);
  model = r.ok ? await r.json() : [];
  renderEasy(model);
  $("editor").value = JSON.stringify(model, null, 2);
}

// ----------------- seed -----------------
$("btnSeed").onclick = async ()=>{
  const r = await api("/seed", {method:"POST"});
  const j = await r.json().catch(()=>null);
  alert("Seed result:\n"+JSON.stringify(j, null, 2));
};

// ----------------- save / import / export -----------------
$("btnSave").onclick = async ()=>{
  if(!current) return alert("Pick something on the left.");
  const payload = model;
  let res;
  if(current.type==="content"){
    res = await api("/content/"+current.key, {method:"POST", body: JSON.stringify(payload)});
  }else{
    res = await api("/"+current.key, {method:"POST", body: JSON.stringify(payload)});
  }
  if(!res.ok) return alert("Save failed ("+res.status+")");
  alert("Saved!");
};
$("btnExport").onclick = ()=>{
  if(!current) return;
  const blob = new Blob([JSON.stringify(model, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (current.key || "data") + ".json";
  a.click();
};
$("btnImport").onclick = ()=> $("importFile").click();
$("importFile").onchange = async e=>{
  const f = e.target.files?.[0]; if(!f) return;
  try{
    const text = await f.text();
    model = JSON.parse(text);
    renderEasy(model);
    $("editor").value = JSON.stringify(model, null, 2);
  }catch(err){ alert("Bad JSON file: "+err.message); }
};

// ----------------- JSON helpers -----------------
$("btnFormat").onclick = ()=>{
  try{
    const obj = JSON.parse($("editor").value);
    $("editor").value = JSON.stringify(obj, null, 2);
    model = obj;
    renderEasy(model);
  }catch(e){ alert("Invalid JSON: "+e.message); }
};
function syncEditorFromModel(){
  $("editor").value = model==null ? "" : JSON.stringify(model, null, 2);
}

// ----------------- EASY MODE (auto forms) -----------------
function renderEasy(data){
  const root = $("easyForm");
  root.innerHTML = "";
  if(data==null) { root.appendChild(el("em", {}, ["No data"])); return; }
  const form = buildNode([], data);
  root.appendChild(form);
}

function buildNode(path, value){
  if(typeof value === "string") return renderString(path, value);
  if(typeof value === "number") return renderNumber(path, value);
  if(typeof value === "boolean") return renderBoolean(path, value);
  if(Array.isArray(value)){
    if(value.every(v => typeof v === "string")) return renderStringArray(path, value);
    if(value.every(v => typeof v === "object")) return renderObjectArray(path, value);
    return renderJSONLeaf(path, value); // mixed
  }
  if(typeof value === "object" && value !== null){
    return renderObject(path, value);
  }
  return renderJSONLeaf(path, value);
}

/* ---------- field renderers ---------- */

// String with inline image preview + upload button when relevant
function renderString(path, val){
  const name = keyName(path).toLowerCase();
  const isLong = (val||"").length > 120 || name.includes("description") || name.includes("body") || name.includes("content");
  const wrap = el("div", {className:"field"});
  wrap.appendChild(el("label", {}, [labelFor(path)]));

  const row = el("div", {className:"inline"});
  const input = isLong ? el("textarea", {value: val || "", rows: 4})
                       : el("input", {value: val || "", type:"text"});
  input.oninput = ()=> setAtPath(model, path, input.value);
  row.appendChild(input);

  // Upload button for suspected image/url fields
  if (name.includes("image") || name.includes("img") || name.includes("logo") || name.includes("url")) {
    const up = el("button", {type:"button", className:"btnSmall", onclick:()=>uploadForField(input)}, ["Upload"]);
    row.appendChild(up);
  }

  // Preview if image URL
  if(isImageUrl(val)){
    const preview = el("img", {src: val, className:"thumb"});
    preview.onerror = ()=> preview.style.display="none";
    row.appendChild(preview);
    const open = el("a", {href: val, target:"_blank", className:"btnLink"}, ["Open"]);
    row.appendChild(open);
  }

  wrap.appendChild(row);
  return wrap;
}

function renderNumber(path, val){
  const wrap = el("div", {className:"field"});
  wrap.appendChild(el("label", {}, [labelFor(path)]));
  const input = el("input", {type:"number", value: val});
  input.oninput = ()=> setAtPath(model, path, Number(input.value));
  wrap.appendChild(input);
  return wrap;
}

function renderBoolean(path, val){
  const wrap = el("div", {className:"field"});
  const input = el("input", {type:"checkbox", checked: !!val});
  input.onchange = ()=> setAtPath(model, path, !!input.checked);
  wrap.appendChild(el("label", {}, [input, " ", labelFor(path)]));
  return wrap;
}

// Array<string> — thumbnail grid when the field looks like an images array
function renderStringArray(path, arr){
  const wrap = el("div", {className:"field"});
  wrap.appendChild(el("label", {}, [labelFor(path)]));

  const looksLikeImages = isImagesKey(path) || (arr||[]).every(s=>isImageUrl(s));
  if(!looksLikeImages){
    // simple multi-line textarea
    const ta = el("textarea", {rows: Math.min(10, Math.max(3, (arr||[]).length+1))});
    ta.value = (arr||[]).join("\n");
    ta.oninput = ()=>{
      const lines = ta.value.split("\n").map(s=>s.trim()).filter(Boolean);
      setAtPath(model, path, lines);
    };
    wrap.appendChild(ta);
    return wrap;
  }

  // Thumbnail grid
  const grid = el("div", {className:"thumbGrid"});
  (arr||[]).forEach((url, idx)=>{
    const cell = el("div", {className:"thumbCell"});

    const img  = el("img", {src: url, className:"thumb"});
    img.onerror = ()=> { img.style.display="none"; cell.appendChild(el("div",{className:"thumbBroken"},["Invalid image URL"])); };
    cell.appendChild(img);

    const urlInput = el("input", {type:"text", value: url});
    urlInput.oninput = ()=>{
      const a = getAtPath(model, path) || [];
      a[idx] = urlInput.value;
      setAtPath(model, path, a);
    };
    cell.appendChild(urlInput);

    const actions = el("div", {className:"thumbActions"});
    const open = el("a", {href:url, target:"_blank", className:"btnLink"}, ["Open"]);

    const uploadReplace = el("button", {type:"button", className:"btnSmall", onclick:()=>{
      const picker = $("fileUpload");
      picker.onchange = async e=>{
        const f = e.target.files?.[0]; if(!f) return;
        const fd = new FormData(); fd.append("file", f);
        const r = await api("/upload-image", {method:"POST", body: fd});
        if(!r.ok){ alert("Upload failed"); return; }
        const j = await r.json();
        urlInput.value = j.url || "";
        urlInput.dispatchEvent(new Event("input"));
        picker.value = "";
        alert("Uploaded. Replaced image.");
      };
      picker.click();
    }}, ["Upload"]);

    const del  = el("button", {type:"button", className:"btnSmall danger", onclick:()=>{
      const a = getAtPath(model, path) || [];
      a.splice(idx,1);
      setAtPath(model, path, a);
      renderEasy(model);
      syncEditorFromModel();
    }}, ["Delete"]);

    actions.appendChild(open);
    actions.appendChild(uploadReplace);
    actions.appendChild(del);
    cell.appendChild(actions);

    grid.appendChild(cell);
  });

  // Add new image (URL or upload)
  const addBar = el("div", {className:"thumbAdd"});
  const newUrl = el("input", {type:"text", placeholder:"Paste image URL"});
  const addBtn = el("button", {type:"button", className:"btnSmall", onclick:()=>{
    const a = getAtPath(model, path) || [];
    if(newUrl.value.trim()){
      a.push(newUrl.value.trim());
      setAtPath(model, path, a);
      renderEasy(model);
      syncEditorFromModel();
      newUrl.value="";
    } else {
      alert("Paste an image URL or use Upload.");
    }
  }}, ["Add URL"]);
  const uploadBtn = el("button", {type:"button", className:"btnSmall", onclick:()=>{
    const picker = $("fileUpload");
    picker.onchange = async e=>{
      const f = e.target.files?.[0]; if(!f) return;
      const fd = new FormData(); fd.append("file", f);
      const r = await api("/upload-image", {method:"POST", body: fd});
      if(!r.ok){ alert("Upload failed"); return; }
      const j = await r.json();
      const a = getAtPath(model, path) || [];
      a.push(j.url || "");
      setAtPath(model, path, a);
      renderEasy(model);
      syncEditorFromModel();
      picker.value = "";
    };
    picker.click();
  }}, ["Upload"]);
  addBar.appendChild(newUrl);
  addBar.appendChild(addBtn);
  addBar.appendChild(uploadBtn);

  wrap.appendChild(grid);
  wrap.appendChild(addBar);
  return wrap;
}

// Array<object>
function renderObjectArray(path, arr){
  const wrap = el("div", {className:"field"});
  wrap.appendChild(el("label", {}, [labelFor(path)]));
  const list = el("div", {className:"list"});
  (arr||[]).forEach((item, idx)=>{
    const row = el("div", {className:"card"});
    row.appendChild(el("div", {className:"rowHeader"}, [ (item.title||item.name||`Item ${idx+1}`) ]));
    row.appendChild(buildNode(path.concat(idx), item));
    const del = el("button", {type:"button", className:"danger", onclick:()=>{
      const parent = getAtPath(model, path);
      parent.splice(idx,1);
      renderEasy(model);
      syncEditorFromModel();
    }}, ["Delete"]);
    row.appendChild(del);
    list.appendChild(row);
  });
  const add = el("button", {type:"button", className:"btnSmall", onclick:()=>{
    const parent = getAtPath(model, path) || [];
    parent.push({});
    setAtPath(model, path, parent);
    renderEasy(model);
    syncEditorFromModel();
  }}, ["+ Add item"]);
  wrap.appendChild(list);
  wrap.appendChild(add);
  return wrap;
}

// Object group with ability to add fields
function renderObject(path, obj){
  const wrap = el("div", {className:"objectGroup"});
  Object.keys(obj||{}).forEach(k=>{
    wrap.appendChild(buildNode(path.concat(k), obj[k]));
  });
  const adder = el("div", {className:"addKey"});
  const keyIn = el("input", {placeholder:"Add new field (key)"});
  const btn = el("button", {type:"button", className:"btnSmall", onclick:()=>{
    const key = (keyIn.value||"").trim();
    if(!key) return;
    const tgt = getAtPath(model, path) || {};
    if(!(key in tgt)) tgt[key] = "";
    setAtPath(model, path, tgt);
    renderEasy(model);
    syncEditorFromModel();
    keyIn.value="";
  }}, ["Add field"]);
  adder.appendChild(keyIn);
  adder.appendChild(btn);
  wrap.appendChild(adder);
  return wrap;
}

// Fallback JSON leaf editor
function renderJSONLeaf(path, val){
  const wrap = el("div", {className:"field"});
  wrap.appendChild(el("label", {}, [labelFor(path)]));
  const ta = el("textarea", {rows:4, value: JSON.stringify(val, null, 2)});
  ta.oninput = ()=>{
    try{ setAtPath(model, path, JSON.parse(ta.value)); ta.style.borderColor="#ddd"; }
    catch(e){ ta.style.borderColor="#f33"; }
  };
  wrap.appendChild(ta);
  return wrap;
}

// Per-field upload (string inputs)
function uploadForField(inputEl){
  const picker = $("fileUpload");
  picker.onchange = async e=>{
    const f = e.target.files?.[0];
    if(!f) return;
    const fd = new FormData(); fd.append("file", f);
    const r = await api("/upload-image", {method:"POST", body: fd});
    if(!r.ok){ alert("Upload failed"); return; }
    const j = await r.json();
    inputEl.value = j.url || "";
    inputEl.dispatchEvent(new Event("input"));
    picker.value = "";
    alert("Uploaded. URL inserted.");
  };
  picker.click();
}
