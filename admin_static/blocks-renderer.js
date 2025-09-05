/* admin_static/blocks-renderer.js — client-side block renderer */
(function(){
  async function start(){
    try{
      const script = document.currentScript;
      const api = (script.getAttribute("data-api") || location.origin).replace(/\/$/,'');
      const slug = script.getAttribute("data-page") || "homepage";
      const targetSel = script.getAttribute("data-target") || "#evo-root";
      const root = document.querySelector(targetSel);
      if(!root){ console.warn("Evo blocks: target not found", targetSel); return; }

      const res = await fetch(api + "/pages/" + slug);
      const j = await res.json().catch(()=>({blocks:[]}));
      const blocks = Array.isArray(j.blocks) ? j.blocks : [];
      root.innerHTML = render(blocks);
      injectStyles();
    }catch(e){ console.error("Evo blocks error:", e); }
  }

  function esc(s){ return (s||"").replace(/[&<>"]/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[m])); }
  function img(url, alt=""){ url=url||""; return url?`<img src="${esc(url)}" alt="${esc(alt)}" loading="lazy" />`:""; }

  function render(blocks){
    return blocks.map(b=>{
      const p = b.props || {};
      switch(b.type){
        case "hero":
          return `
          <section class="evo hero">
            <div class="container">
              <h1>${esc(p.title||"")}</h1>
              ${p.subtitle?`<p class="sub">${esc(p.subtitle)}</p>`:""}
              ${p.ctaHref?`<a class="btn" href="${esc(p.ctaHref)}">${esc(p.ctaLabel||"Get started")}</a>`:""}
            </div>
            ${Array.isArray(p.images)&&p.images[0]?`<div class="hero-img">${img(p.images[0], p.title||"")}</div>`:""}
          </section>`;
        case "text": return `<section class="evo text container">${p.html||""}</section>`;
        case "image": return `<section class="evo image container">${img(p.src, p.alt||"")}</section>`;
        case "columns": return `
          <section class="evo cols container">
            <div class="col">${p.left||""}</div>
            <div class="col">${p.right||""}</div>
          </section>`;
        case "cta": return `
          <section class="evo cta">
            <div class="container row">
              <div class="cta-text">${esc(p.text||"")}</div>
              ${p.href?`<a class="btn" href="${esc(p.href)}">${esc(p.button||"Contact us")}</a>`:""}
            </div>
          </section>`;
        case "features":
          return `
          <section class="evo features container">
            ${p.heading?`<h2>${esc(p.heading)}</h2>`:""}
            <ul class="feat-grid">${(p.items||[]).map(t=>`<li>${esc(t)}</li>`).join("")}</ul>
          </section>`;
        case "faq":
          return `
          <section class="evo faq container">
            ${(p.items||[]).map(q=>`
              <details><summary>${esc(q.q||"")}</summary><div>${esc(q.a||"")}</div></details>
            `).join("")}
          </section>`;
        case "testimonials":
          return `
          <section class="evo testimonials container">
            ${(p.items||[]).map(t=>`
              <figure>
                ${t.image?img(t.image, t.author||""):''}
                <blockquote>${esc(t.quote||"")}</blockquote>
                <figcaption>${esc(t.author||"")} <small>${esc(t.role||"")}</small></figcaption>
              </figure>`).join("")}
          </section>`;
        case "galleryStrip":
          return `
          <section class="evo gallery container">
            <div class="strip">${(p.images||[]).slice(0, p.count||6).map(u=>img(u,"")).join("")}</div>
          </section>`;
        case "spacer": return `<div style="height:${Number(p.size||40)}px"></div>`;
        case "divider": return `<hr class="evo divider" />`;
        case "map": return `<section class="evo map container"><iframe src="${esc(p.src||"")}" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></section>`;
        case "video": return `<section class="evo video container"><iframe src="${esc(p.src||"")}" loading="lazy" allowfullscreen></iframe></section>`;
        case "form": return `
          <section class="evo form container">
            ${p.heading?`<h2>${esc(p.heading)}</h2>`:""}
            <form onsubmit="return window.EvoLead && EvoLead.submit(event)">
              <input name="name" placeholder="Name" required />
              <input name="email" type="email" placeholder="Email" required />
              <input name="phone" placeholder="Phone" />
              <input name="postcode" placeholder="Postcode" />
              <textarea name="message" placeholder="Tell us about your project"></textarea>
              <button type="submit">Send</button>
            </form>
          </section>`;
        default:
          return `<section class="evo unknown container"><pre>${esc(JSON.stringify(b,null,2))}</pre></section>`;
      }
    }).join("");
  }

  // tiny lead helper
  window.EvoLead = {
    async submit(e){
      e.preventDefault();
      const f = e.target;
      const api = (document.currentScript && document.currentScript.getAttribute("data-api")) || location.origin;
      const body = {
        name:f.name.value, email:f.email.value, phone:f.phone.value,
        postcode:f.postcode.value, message:f.message.value, service:"", source:"blocks"
      };
      const res = await fetch(api.replace(/\/$/,'') + "/lead",{
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
      });
      alert(res.ok ? "Thanks! We’ll get back to you." : "Failed to send. Please try again.");
      if (res.ok) f.reset();
      return false;
    }
  };

  function injectStyles(){
    if (document.getElementById("evo-blocks-css")) return;
    const css = `
    .evo.container{max-width:1100px;margin:0 auto;padding:16px}
    .evo.hero{background:#0a84ff0d;padding:32px 0;position:relative}
    .evo.hero .btn,.evo.cta .btn{background:#0a84ff;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none}
    .evo.hero .hero-img{position:absolute;right:20px;bottom:0;opacity:.2}
    .evo.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .evo.features .feat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
    .evo.faq details{border:1px solid #e5e7eb;border-radius:8px;margin:6px 0;padding:8px 12px}
    .evo.testimonials figure{border:1px solid #e5e7eb;border-radius:12px;padding:12px;margin:8px 0}
    .evo.gallery .strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
    .evo.image img,.evo.gallery img{width:100%;height:auto;border-radius:10px}
    .evo.map iframe,.evo.video iframe{width:100%;height:380px;border:0;border-radius:12px}
    .evo.form form{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .evo.form textarea{grid-column:span 2}
    .evo.divider{border:0;border-top:1px solid #e5e7eb;margin:16px 0}
    @media(max-width:840px){ .evo.cols{grid-template-columns:1fr} .evo.form form{grid-template-columns:1fr} .evo.form textarea{grid-column:span 1}}
    `;
    const style = document.createElement("style");
    style.id="evo-blocks-css"; style.textContent = css; document.head.appendChild(style);
  }

  start();
})();
