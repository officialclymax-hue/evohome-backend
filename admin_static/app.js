const API_BASE = window.location.origin; // same origin when served from the backend
let token = localStorage.getItem("evo_token") || null;

function setToken(t){
  token = t;
  if(t) localStorage.setItem("evo_token", t);
  else localStorage.removeItem("evo_token");
  document.getElementById("token-display").textContent = token ? "Logged in" : "";
}

async function postJSON(path, body){
  const res = await fetch(API_BASE + path, {
    method:"POST",
    headers:{
      "Content-Type":"application/json",
      ...(token ? {"Authorization":"Bearer " + token} : {})
    },
    body: JSON.stringify(body)
  });
  return res.json();
}

async function fetchJSON(path, opts={}){
  const headers = opts.headers || {};
  if(token) headers["Authorization"]="Bearer " + token;
  const res = await fetch(API_BASE + path, {...opts, headers});
  const txt = await res.text();
  try{ return JSON.parse(txt); } catch(e){ return txt; }
}

document.getElementById("btn-login").addEventListener("click", async ()=>{
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  if(!email || !password){ document.getElementById("login-status").textContent = "Enter both fields"; return; }
  const data = await postJSON("/admin/login", {email, password});
  if(data.access_token){ setToken(data.access_token); document.getElementById("login").style.display="none"; document.getElementById("main").style.display="block"; loadTab("services"); }
  else { document.getElementById("login-status").textContent = data.detail || "Login failed"; }
});

document.getElementById("btn-logout").addEventListener("click", ()=>{ setToken(null); document.getElementById("main").style.display="none"; document.getElementById("login").style.display="block"; });

document.querySelectorAll(".tab-btn").forEach(btn=>btn.addEventListener("click", ()=>loadTab(btn.dataset.tab)));

function el(tag, attrs={}, ...children){
  const e = document.createElement(tag);
  Object.assign(e, attrs);
  for(const c of children) if(typeof c === "string") e.appendChild(document.createTextNode(c)); else if(c) e.appendChild(c);
  return e;
}

async function loadTab(tab){
  const area = document.getElementById("content-area");
  area.innerHTML = "";
  if(tab === "services"){
    area.appendChild(el("h2", {}, "Services"));
    const create = el("div",{className:"form-row"});
    const title = el("input",{placeholder:"Title", id:"svc-title"});
    const desc = el("textarea",{placeholder:"Description", id:"svc-desc"});
    const img = el("input",{type:"file", id:"svc-image"});
    const btn = el("button",{}, "Create Service");
    btn.addEventListener("click", async ()=>{
      const fd = new FormData();
      fd.append("title", document.getElementById("svc-title").value);
      fd.append("description", document.getElementById("svc-desc").value);
      const file = document.getElementById("svc-image").files[0];
      if(file) fd.append("image", file);
      const res = await fetch(API_BASE + "/services", {method:"POST", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
      await res.json();
      loadTab("services");
    });
    create.appendChild(title); create.appendChild(desc); create.appendChild(img); create.appendChild(btn);
    area.appendChild(create);

    const list = el("div",{});
    const items = await fetchJSON("/services");
    (items || []).forEach(it=>{
      const row = el("div",{className:"list-item"});
      const imgEl = el("img",{src: it.image_url || "", className:"thumb"});
      const content = el("div",{}, el("strong",{}, it.title), el("div",{}, it.description || ""));
      const editBtn = el("button",{}, "Edit");
      editBtn.addEventListener("click", ()=> editService(it));
      const delBtn = el("button",{}, "Delete");
      delBtn.addEventListener("click", async ()=>{ if(confirm("Delete?")){ await fetch(API_BASE + "/services/" + it.id, {method:"DELETE", headers: token ? {"Authorization":"Bearer " + token} : {}}); loadTab("services"); } });
      row.appendChild(imgEl); row.appendChild(content); row.appendChild(editBtn); row.appendChild(delBtn);
      list.appendChild(row);
    });
    area.appendChild(list);
  }

  if(tab === "gallery"){
    area.appendChild(el("h2", {}, "Gallery"));
    const create = el("div",{className:"form-row"});
    const title = el("input",{placeholder:"Title", id:"gal-title"});
    const desc = el("textarea",{placeholder:"Description", id:"gal-desc"});
    const img = el("input",{type:"file", id:"gal-image"});
    const btn = el("button",{}, "Create Image");
    btn.addEventListener("click", async ()=>{
      const fd = new FormData();
      fd.append("title", document.getElementById("gal-title").value);
      fd.append("description", document.getElementById("gal-desc").value);
      const file = document.getElementById("gal-image").files[0];
      if(file) fd.append("image", file);
      const res = await fetch(API_BASE + "/gallery", {method:"POST", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
      await res.json();
      loadTab("gallery");
    });
    create.appendChild(title); create.appendChild(desc); create.appendChild(img); create.appendChild(btn);
    area.appendChild(create);

    const list = el("div",{});
    const items = await fetchJSON("/gallery");
    (items || []).forEach(it=>{
      const row = el("div",{className:"list-item"});
      const imgEl = el("img",{src: it.image_url || "", className:"thumb"});
      const content = el("div",{}, el("strong",{}, it.title), el("div",{}, it.description || ""));
      const editBtn = el("button",{}, "Edit");
      editBtn.addEventListener("click", ()=> editGallery(it));
      const delBtn = el("button",{}, "Delete");
      delBtn.addEventListener("click", async ()=>{ if(confirm("Delete?")){ await fetch(API_BASE + "/gallery/" + it.id, {method:"DELETE", headers: token ? {"Authorization":"Bearer " + token} : {}}); loadTab("gallery"); } });
      row.appendChild(imgEl); row.appendChild(content); row.appendChild(editBtn); row.appendChild(delBtn);
      list.appendChild(row);
    });
    area.appendChild(list);
  }

  if(tab === "blogs"){
    area.appendChild(el("h2", {}, "Blogs"));
    const create = el("div",{className:"form-row"});
    const title = el("input",{placeholder:"Title", id:"blog-title"});
    const desc = el("textarea",{placeholder:"Description", id:"blog-desc"});
    const content = el("textarea",{placeholder:"Content", id:"blog-content"});
    const img = el("input",{type:"file", id:"blog-image"});
    const btn = el("button",{}, "Create Blog");
    btn.addEventListener("click", async ()=>{
      const fd = new FormData();
      fd.append("title", document.getElementById("blog-title").value);
      fd.append("description", document.getElementById("blog-desc").value);
      fd.append("content", document.getElementById("blog-content").value);
      const file = document.getElementById("blog-image").files[0];
      if(file) fd.append("image", file);
      const res = await fetch(API_BASE + "/blogs", {method:"POST", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
      await res.json();
      loadTab("blogs");
    });
    create.appendChild(title); create.appendChild(desc); create.appendChild(content); create.appendChild(img); create.appendChild(btn);
    area.appendChild(create);

    const list = el("div",{});
    const items = await fetchJSON("/blogs");
    (items || []).forEach(it=>{
      const row = el("div",{className:"list-item"});
      const imgEl = el("img",{src: it.image_url || "", className:"thumb"});
      const content = el("div",{}, el("strong",{}, it.title), el("div",{}, it.description || ""), el("div",{}, it.content ? it.content.substring(0,140) : ""));
      const editBtn = el("button",{}, "Edit");
      editBtn.addEventListener("click", ()=> editBlog(it));
      const delBtn = el("button",{}, "Delete");
      delBtn.addEventListener("click", async ()=>{ if(confirm("Delete?")){ await fetch(API_BASE + "/blogs/" + it.id, {method:"DELETE", headers: token ? {"Authorization":"Bearer " + token} : {}}); loadTab("blogs"); } });
      row.appendChild(imgEl); row.appendChild(content); row.appendChild(editBtn); row.appendChild(delBtn);
      list.appendChild(row);
    });
    area.appendChild(list);
  }
}

async function editService(it){
  const title = prompt("Title", it.title) || it.title;
  const desc = prompt("Description", it.description || "") || it.description;
  const fd = new FormData();
  fd.append("title", title);
  fd.append("description", desc);
  const res = await fetch(API_BASE + "/services/" + it.id, {method:"PUT", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
  await res.json();
  loadTab("services");
}

async function editGallery(it){
  const title = prompt("Title", it.title) || it.title;
  const desc = prompt("Description", it.description || "") || it.description;
  const fd = new FormData();
  fd.append("title", title);
  fd.append("description", desc);
  const res = await fetch(API_BASE + "/gallery/" + it.id, {method:"PUT", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
  await res.json();
  loadTab("gallery");
}

async function editBlog(it){
  const title = prompt("Title", it.title) || it.title;
  const desc = prompt("Description", it.description || "") || it.description;
  const content = prompt("Content", it.content || "") || it.content;
  const fd = new FormData();
  fd.append("title", title);
  fd.append("description", desc);
  fd.append("content", content);
  const res = await fetch(API_BASE + "/blogs/" + it.id, {method:"PUT", body:fd, headers: token ? {"Authorization":"Bearer " + token} : {}});
  await res.json();
  loadTab("blogs");
}

// Auto-login if token exists
if(token){
  document.getElementById("login").style.display="none";
  document.getElementById("main").style.display="block";
  document.getElementById("token-display").textContent = "Logged in";
  loadTab("services");
}
