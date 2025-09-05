// admin_static/app.js
const API_BASE = window.location.origin;
let token = localStorage.getItem("ADMIN_JWT") || null;

const contentCollections = [
  "homepage", "header", "about", "contact", "footer",
  "coverage", "seo", "request-quote", "forms",
  "chatbot", "floating-buttons"
];
const dataCollections = ["services", "blogs", "gallery"];

function $(id){ return document.getElementById(id); }

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (token) headers["Authorization"] = "Bearer " + token;
  if (!options.body && options.method && options.method !== "GET" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) {
    alert("Not authorized. Please login again.");
    logout();
    throw new Error("Unauthorized");
  }
  return res;
}

// ----- Auth -----
async function login(){
  const email = $("email").value.trim();
  const password = $("password").value.trim();
  const res = await fetch(API_BASE + "/auth/login", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ email, password })
  });
  if(!res.ok){
    $("loginMsg").innerText = "Login failed";
    return;
  }
  const data = await res.json();
  token = data.access_token;
  localStorage.setItem("ADMIN_JWT", token);
  $("login").style.display = "none";
  $("main").style.display = "";
  initCollections();
}

function logout(){
  token = null;
  localStorage.removeItem("ADMIN_JWT");
  $("main").style.display = "none";
  $("login").style.display = "";
}

// ----- UI -----
function initCollections(){
  const ul = $("collections");
  ul.innerHTML = "";

  const addSection = (title, list) => {
    const header = document.createElement("h4");
    header.innerText = title;
    ul.appendChild(header);
    list.forEach(c=>{
      const li = document.createElement("li");
      li.innerText = c;
      li.onclick = ()=>loadCollection(c);
      ul.appendChild(li);
    });
  };

  addSection("Page Content", contentCollections);
  addSection("Data Collections", dataCollections);
}

async function loadCollection(k){
  try{
    let res;
    if(dataCollections.includes(k)){
      res = await api("/" + k);
    } else {
      res = await api("/content/" + k);
    }
    if(!res.ok){
      $("editor").value = "// Not found. Use Save to create content.";
      $("colTitle").innerText = k;
      return;
    }
    const data = await res.json();
    $("editor").value = JSON.stringify(data, null, 2);
    $("colTitle").innerText = k;
  }catch(e){
    console.error(e);
    $("editor").value = "// Error loading collection";
  }
}

async function saveCollection(){
  const key = $("colTitle").innerText;
  if(!key) return alert("Select a collection first");

  let parsed;
  try { parsed = JSON.parse($("editor").value); }
  catch(e){ return alert("Invalid JSON: " + e.message); }

  let url, method = "POST";
  if(dataCollections.includes(key)){
    url = "/" + key;            // POST /services|blogs|gallery
  } else {
    url = "/content/" + key;    // POST /content/{key}
  }

  const res = await api(url, { method, body: JSON.stringify(parsed) });
  if(!res.ok) alert("Save failed: " + res.status);
  else alert("Saved!");
}

async function runSeed(){
  const res = await api("/seed", { method: "POST" });
  if(!res.ok) alert("Seed failed: " + res.status);
  else {
    const j = await res.json();
    alert("Seeded: " + JSON.stringify(j));
  }
}

window.onload = ()=>{
  $("btnLogin").onclick = login;
  $("btnLogout").onclick = logout;
  $("btnSave").onclick = saveCollection;
  $("btnRefresh").onclick = ()=>initCollections();
  $("btnSeed").onclick = runSeed;

  // auto-show if token already exists
  if (token) {
    $("login").style.display = "none";
    $("main").style.display = "";
    initCollections();
  }
};
