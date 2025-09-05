// admin_static/app.js
const API_BASE = window.location.origin;
let token = localStorage.getItem("ADMIN_JWT") || null;

const CONTENT_KEYS = ["homepage","header","about","contact","footer","coverage","seo","request-quote","forms","chatbot","floating-buttons"];
const DATA_KEYS = ["services","blogs","gallery"];

const $ = (id)=>document.getElementById(id);

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) { alert("Not authorized. Please log in again."); logout(); throw new Error("401"); }
  return res;
}

// ---------- Auth ----------
async function login(){
  const email = $("email").value.trim();
  const password = $("password").value.trim();
  const res = await fetch(API_BASE + "/auth/login", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ email, password })
  });
  if(!res.ok){ $("loginMsg").innerText="Login failed"; return; }
  const j = await res.json();
  token = j.access_token; localStorage.setItem("ADMIN_JWT", token);
  $("login").style.display="none"; $("app").style.display="grid";
  buildLists();
}
function logout(){ token=null; localStorage.removeItem("ADMIN_JWT"); $("app").style.display="none"; $("login").style.display="block"; }

// ---------- Lists ----------
function buildLists(){
  $("listContent").innerHTML = CONTENT_KEYS.map(k=>`<li data-k="${k}">${k}</li>`).join("");
  $("listData").innerHTML = DATA_KEYS.map(k=>`<li data-k="${k}">${k}</li>`).join("");
  document.querySelectorAll("#listContent li, #listData li").forEach(li=>{
    li.onclick = ()=>load(li.getAttribute("data-k"));
  });
}

let currentKey = null;
let currentData = null;
let easyMode = true;

$("modeEasy").onclick = ()=>{ easyMode=true; renderEditor(); };
$("modeJson").onclick = ()=>{ easyMode=false; renderEditor(); };

async function load(key){
  currentKey = key;
  $("colTitle").innerText = key;
  try{
    const res = DATA_KEYS.includes(key) ? await api("/"+key) : await api("/content/"+key);
    if(!res.ok){ currentData = DATA_KEYS.includes(key) ? [] : {}; $("jsonBox").value="// Not found. Use Save to create content."; renderEditor(); return; }
    currentData = await res.json();
    $("jsonBox").value = JSON.stringify(currentData, null, 2);
    renderEditor();
  }catch(e){
    currentData = DATA_KEYS.includes(key) ? [] : {};
    $("jsonBox").value="// Error loading collection";
    renderEditor();
  }
}

function renderEditor(){
  $("jsonBox").style.display = easyMode ? "none" : "block";
  $("btnSaveJson").style.display = easyMode ? "none" : "inline-block";
  $("easyMode").style.display = easyMode ? "block" : "none";

  if(!easyMode) return;

  const root = $("easyForm");
  root.innerHTML = "";
  const data = currentData ?? {};

  // Simple form generator
  const makeField = (k, val, path=[])=>{
    const wrap = document.createElement("div"); wrap.className="field";

    // primitives
    if (typeof val !== "object" || val === null) {
      const label = document.createElement("label"); label.textContent = k;
      const input = document.createElement("input"); input.value = val ?? "";
      input.oninput = ()=> setValue(path.concat(k), input.value);
      wrap.appendChild(label); wrap.appendChild(input);
      return wrap;
    }

    // arrays of objects/strings
    if (Array.isArray(val)) {
      const label = document.createElement("label"); label.textContent = k + " (list)";
      const box = document.createElement("div"); box.className="listWrap";
      val.forEach((item, idx)=>{
        const row = document.createElement("div"); row.className="listRow";
        const itemInput = document.createElement("input");
        itemInput.value = typeof item === "object" ? JSON.stringify(item) : (item ?? "");
        itemInput.oninput = ()=> {
          try {
            const parsed = itemInput.value.trim() ? JSON.parse(itemInput.value) : "";
            setArrayValue(path.concat(k), idx, parsed);
          } catch { setArrayValue(path.concat(k), idx, itemInput.value); }
        };
        const del = document.createElement("button"); del.textContent="×"; del.type="button";
        del.onclick = ()=>{ removeArrayValue(path.concat(k), idx); renderEditor(); };
        row.appendChild(itemInput); row.appendChild(del); box.appendChild(row);
      });
      const add = document.createElement("button"); add.textContent="+ Add item"; add.type="button";
      add.onclick = ()=>{ pushArrayValue(path.concat(k), ""); renderEditor(); };
      wrap.appendChild(label); wrap.appendChild(box); wrap.appendChild(add);
      return wrap;
    }

    // objects
    const legend = document.createElement("div"); legend.className="groupTitle"; legend.textContent = k;
    wrap.appendChild(legend);
    Object.keys(val).forEach(subkey=>{
      wrap.appendChild(makeField(subkey, val[subkey], path.concat(k)));
    });
    return wrap;
  };

  const setValue = (path, v)=>{
    let ref = currentData;
    for (let i=0;i<path.length-1;i++) ref = ref[path[i]] ?? (ref[path[i]] = {});
    ref[path[path.length-1]] = v;
    $("jsonBox").value = JSON.stringify(currentData, null, 2);
  };
  const setArrayValue = (path, idx, v)=>{
    let ref = currentData;
    for (let i=0;i<path.length;i++) ref = ref[path[i]];
    ref[idx] = v;
    $("jsonBox").value = JSON.stringify(currentData, null, 2);
  };
  const removeArrayValue = (path, idx)=>{
    let ref = currentData;
    for (let i=0;i<path.length;i++) ref = ref[path[i]];
    ref.splice(idx,1);
  };
  const pushArrayValue = (path, v)=>{
    let ref = currentData;
    for (let i=0;i<path.length;i++) ref = ref[path[i]] ?? (ref[path[i]] = []);
    ref.push(v);
  };

  // Build form
  if (DATA_KEYS.includes(currentKey) && !Array.isArray(currentData)) currentData = [];
  if (!DATA_KEYS.includes(currentKey) && (typeof currentData !== "object" || Array.isArray(currentData))) currentData = {};

  if (DATA_KEYS.includes(currentKey)) {
    root.appendChild(makeField(currentKey, currentData));
  } else {
    Object.keys(currentData).forEach(k=> root.appendChild(makeField(k, currentData[k])));
  }
}

// save (JSON mode)
$("btnSaveJson").onclick = async ()=>{
  if(!currentKey) return alert("Select a collection first");
  let parsed; try { parsed = JSON.parse($("jsonBox").value); } catch(e) { return alert("Invalid JSON: "+e.message); }
  const url = DATA_KEYS.includes(currentKey) ? ("/"+currentKey) : ("/content/"+currentKey);
  const res = await api(url, {method:"POST", body: JSON.stringify(parsed)});
  alert(res.ok ? "Saved!" : "Save failed: "+res.status);
};

// save (Easy mode)
$("btnSaveEasy").onclick = ()=> $("btnSaveJson").click();

// export
$("btnExport").onclick = ()=>{
  if (!currentKey) return alert("Select a collection first");
  const blob = new Blob([$("jsonBox").value], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = currentKey + ".json";
  a.click();
};

// import
$("fileImport").onchange = async (e)=>{
  if (!currentKey) return alert("Select a collection first");
  const file = e.target.files[0]; if (!file) return;
  const text = await file.text();
  try { currentData = JSON.parse(text); $("jsonBox").value = JSON.stringify(currentData, null, 2); renderEditor(); }
  catch(err){ alert("Invalid JSON file: " + err.message); }
};

// seed modal
$("btnSeed").onclick = ()=> $("seedDlg").showModal();
$("closeSeed").onclick = ()=> $("seedDlg").close();
$("doSeed").onclick = async ()=>{
  $("seedOut").textContent = "Seeding...";
  const res = await api("/seed", {method:"POST"});
  try {
    const j = await res.json();
    $("seedOut").textContent = JSON.stringify(j.report, null, 2);
  } catch {
    $("seedOut").textContent = "Seed failed: " + res.status;
  }
};

// upload modal
$("btnUpload").onclick = ()=> $("uploadDlg").showModal();
$("closeUpload").onclick = ()=> $("uploadDlg").close();
$("doUpload").onclick = async ()=>{
  const file = $("fileUpload").files[0]; if(!file) return alert("Choose a file");
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch(API_BASE + "/upload-image", { method:"POST", body: fd, headers: token ? {"Authorization":"Bearer "+token} : {} });
  const j = await res.json();
  $("uploadedUrl").value = j.url || "Upload failed";
};

// init
$("btnLogin").onclick = login;
$("btnLogout").onclick = logout;
$("btnRefresh").onclick = buildLists;

if (token) { $("login").style.display="none"; $("app").style.display="grid"; buildLists(); }
