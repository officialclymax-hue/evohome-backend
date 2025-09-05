// admin_static/app.js
const API_BASE = window.location.origin; // backend base URL
let token = null;

// Separate collections
const contentCollections = [
  "homepage", "header", "about", "contact", "footer",
  "coverage", "seo", "request-quote", "forms",
  "chatbot", "floating-buttons"
];
const dataCollections = ["services", "blogs", "gallery"];

function $(id){ return document.getElementById(id); }

// Wrapper for API calls
async function api(path, options={}){
  const headers = options.headers || {};
  if(token) headers["Authorization"]="Bearer "+token;
  const res = await fetch(API_BASE + path, {...options, headers});
  if(res.status===401) {
    alert("Not authorized. Please login again.");
    logout();
    throw new Error("Unauthorized");
  }
  return res;
}

// Login
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

// Logout
function logout(){
  token = null;
  $("main").style.display="none";
  $("login").style.display="";
}

// Build collections list
function initCollections(){
  const ul = $("collections");
  ul.innerHTML="";

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

// Load collection data
async function loadCollection(k){
  try{
    let res;
    if(dataCollections.includes(k)){
      res = await api("/"+k);
    } else {
      res = await api("/content/"+k);
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

// Save changes
async function saveCollection(){
  const key = $("colTitle").innerText;
  if(!key) return alert("Select a collection first");
  let parsed;
  try{ parsed = JSON.parse($("editor").value); }
  catch(e){ return alert("Invalid JSON: " + e.message); }

  let url, method;
  if(dataCollections.includes(key)){
    url = "/"+key; method = "POST"; // Create new item
  } else {
    url = "/content/"+key; method = "POST";
  }

  const res = await api(url, {
    method,
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(parsed)
  });
  if(!res.ok) alert("Save failed: " + res.status);
  else alert("Saved!");
}

// Run seeding from seed_data/
async function runSeed(){
  const res = await api("/seed", {method:"POST"});
  if(!res.ok) alert("Seed failed: " + res.status);
  else {
    const j = await res.json();
    alert("Seeded: " + JSON.stringify(j));
  }
}

// Init
window.onload = ()=>{
  $("btnLogin").onclick = login;
  $("btnLogout").onclick = logout;
  $("btnSave").onclick = saveCollection;
  $("btnRefresh").onclick = ()=>initCollections();
  $("btnSeed").onclick = runSeed;
}
