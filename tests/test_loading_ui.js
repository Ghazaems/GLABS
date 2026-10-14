const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const {skeleton}=require("../web/loading.js");
for(const kind of ["bar","line","rows"]){const html=skeleton(kind,"Memuat <data>");assert(html.includes('role="status"'));assert(html.includes('aria-label="Memuat &lt;data&gt;"'));assert(!html.includes("Math.random"));assert(html.includes('aria-hidden="true"'));}
assert.equal(skeleton("bar"),skeleton("bar"));
const index=fs.readFileSync("web/index.html","utf8"),ihsg=fs.readFileSync("web/ihsg-card.js","utf8"),css=fs.readFileSync("web/loading.css","utf8");
assert(index.indexOf('src="loading.js"')<index.indexOf('src="ihsg-card.js"'));
assert(index.includes('id="toppick-text"><span class="gl-loading gl-loading-bar"'));
assert(index.includes('id="riwayat-chart-wrap"><span class="gl-loading gl-loading-line"'));
assert(index.includes('if(el?.querySelector(".gl-loading"))el.textContent='));
assert(ihsg.includes('chart.replaceChildren();\n      caption.textContent=session?'));
assert(css.includes("prefers-reduced-motion:reduce"));assert(css.includes("animation:none!important"));
for(const file of ["loading.js","ihsg-card.js","rotation.js","radar.js"])new vm.Script(fs.readFileSync("web/"+file,"utf8"));
for(const match of index.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))if(match[1].trim())new vm.Script(match[1]);
console.log("Loading tests passed: markup, determinism, accessibility, reduced motion, failure cleanup and script syntax");
