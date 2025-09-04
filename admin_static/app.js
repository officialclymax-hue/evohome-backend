// admin_static/app.js
const API_BASE = window.location.origin; // same origin as backend
let token = null;
const collections = ["homepage","header","about","services","blogs","gallery","contact","footer","coverage","seo","request-quote","forms","chatbot","floating-buttons"];

function $(id){return document.getElementById(id)}
async function api(path, options={}){
  const headers = options.headers || {};
  if(token) headers["Authorization"]="Bearer "+token;
  const res = await fetch(API_BASE + path, {...options, headers});
  if(res.status===401) {
    alert("Not authorized. Please login again.")
    logout();
    throw new Error("Unauthorized");
  }
  return res;
}

async function login(){
  const email = $("email").value;
  const password = $("password").value;
  const res = await fetch(API_BASE+"/admin/login", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({email, password})
  });
  if(!res.ok){
    $("loginMsg").innerText = "Login failed";
    return;
  }
  const data = await res.json();
  token = data.access_token;
  $("login").style.display="none";
  $("main").style.display="";
  initCollections();
}

function logout(){
  token = null;
  $("main").style.display="none";
  $("login").style.display="";
}

function initCollections(){
  const ul = $("collections");
  ul.innerHTML="";
  collections.forEach(c=>{
    const li = document.createElement("li");
    li.innerText = c;
    li.onclick = ()=>loadCollection(c);
    ul.appendChild(li);
  });
}

async function loadCollection(k){
  try{
    const res = await api("/content/"+k);
    if(!res.ok){
      const text = await res.text();
      $("editor").value = "// Not found. Use Save to create content.\n"+text;
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
  try{ parsed = JSON.parse($("editor").value); }catch(e){ return alert("Invalid JSON: " + e.message) }
  const res = await api("/content/"+key, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(parsed)
  });
  if(!res.ok) alert("Save failed: " + res.status);
  else alert("Saved!");
}

async function runSeed(){
  const res = await api("/seed", {method:"POST"});
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
}
