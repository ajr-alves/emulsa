// Emulsa site: nav state, the look demo, the looks filter and live download links.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  /* ---------- nav border once the page scrolls ---------- */
  const nav = $("#nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 4);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---------- radio groups made of buttons ---------- */
  function radioGroup(group, onPick) {
    const items = $$('[role="radio"]', group);
    const pick = (btn, focus) => {
      items.forEach(b => {
        const on = b === btn;
        b.setAttribute("aria-checked", on);
        b.tabIndex = on ? 0 : -1;
      });
      if (focus) btn.focus();
      onPick(btn);
    };
    items.forEach((b, i) => {
      b.tabIndex = b.getAttribute("aria-checked") === "true" ? 0 : -1;
      b.addEventListener("click", () => pick(b, false));
      b.addEventListener("keydown", e => {
        const d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (!d) return;
        e.preventDefault();
        pick(items[(i + d + items.length) % items.length], true);
      });
    });
  }

  /* ---------- look demo ---------- */
  const stage = $("#stage");
  const range = $("#range");
  const imgOrig = $("#img-orig");
  const imgLook = $("#img-look");
  const tag = $("#look-tag");
  const tagLeft = $(".tag-left");
  const PHOTO_ALT = { coffee: "The espresso cup photo", cat: "The cat photo", rocket: "The launch pad photo" };
  const state = { photo: "cat", look: "kodak-portra-400", name: "Kodak Portra 400" };
  const src = (photo, look) => `assets/img/demo/${photo}-${look}.webp`;

  // Swap an image only once the new file has loaded, so the photo never blinks.
  function swap(img, url) {
    if (img.getAttribute("src") === url) return Promise.resolve();
    return new Promise(res => {
      const next = new Image();
      next.onload = next.onerror = () => { img.src = url; res(); };
      next.src = url;
    });
  }
  function render() {
    tag.textContent = state.name;
    imgLook.alt = `${PHOTO_ALT[state.photo]} in the ${state.name} look`;
    Promise.all([swap(imgOrig, src(state.photo, "original")), swap(imgLook, src(state.photo, state.look))]);
  }
  function setPos(v) {
    stage.style.setProperty("--pos", v + "%");
    tagLeft.classList.toggle("gone", v < 14);
    tag.classList.toggle("gone", v > 80);
  }

  if (stage) {
    range.addEventListener("input", () => setPos(+range.value));

    radioGroup($("#strip"), btn => {
      state.look = btn.dataset.look;
      state.name = btn.dataset.name;
      render();
    });

    radioGroup($("#try .seg"), btn => {
      state.photo = btn.dataset.photo;
      $$("#strip .frame img").forEach(img => {
        img.src = `assets/img/demo/thumbs/${state.photo}-${img.closest(".frame").dataset.look}.webp`;
      });
      render();
    });

    // Hold "\" to see the original, as in the app.
    const typing = e => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) && e.target !== range;
    window.addEventListener("keydown", e => { if (e.key === "\\" && !typing(e)) stage.classList.add("peek"); });
    window.addEventListener("keyup", e => { if (e.key === "\\") stage.classList.remove("peek"); });
    window.addEventListener("blur", () => stage.classList.remove("peek"));

    // Warm the cache for the other looks of this photo once the page is idle.
    const idle = window.requestIdleCallback || (fn => setTimeout(fn, 1500));
    idle(() => $$("#strip .frame").forEach(f => { new Image().src = src("cat", f.dataset.look); }));
  }

  /* ---------- looks grid filter ---------- */
  const grid = $("#grid");
  const more = $("#show-all");
  if (grid) {
    const tiles = $$(".tile-look", grid);
    radioGroup($(".chips"), btn => {
      const f = btn.dataset.filter;
      tiles.forEach(t => { t.hidden = f !== "all" && t.dataset.group !== f; });
      const collapse = f === "all" && !grid.dataset.expanded;
      grid.classList.toggle("collapsed", collapse);
      more.parentElement.hidden = !collapse;
    });
    more.addEventListener("click", () => {
      grid.dataset.expanded = "1";
      grid.classList.remove("collapsed");
      more.parentElement.hidden = true;
      tiles[20] && tiles[20].setAttribute("tabindex", "-1");
      tiles[20] && tiles[20].focus({ preventScroll: true });
    });
  }

  /* ---------- downloads: detect the system and use the latest release ---------- */
  const ua = navigator.userAgent;
  const plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  const mobile = /Android|iPhone|iPad|iPod/i.test(ua) || (navigator.maxTouchPoints > 1 && /Mac/.test(plat));
  const os = mobile ? null
    : /Win/i.test(plat) || /Windows/.test(ua) ? "windows"
    : /Mac/i.test(plat) ? "mac"
    : /Linux|X11|CrOS/i.test(plat + ua) ? "linux" : null;
  const LABEL = { windows: "Windows", mac: "Mac", linux: "Linux" };
  const heroBtn = $("#hero-download");
  const heroNote = $("#hero-note");

  function markYours() {
    if (!os) return;
    const row = $(`.dl[data-os="${os}"]`);
    if (!row) return;
    row.classList.add("yours");
    const h = $("h3", row);
    if (!$(".yours-badge", h)) h.insertAdjacentHTML("beforeend", '<span class="yours-badge">This computer</span>');
    heroBtn.textContent = `Download for ${LABEL[os]}`;
    heroBtn.href = $("[data-link]", row).href;
    const others = Object.keys(LABEL).filter(k => k !== os).map(k => k === "mac" ? "macOS" : LABEL[k]);
    heroNote.textContent = `Free and open source. Also for ${others.join(" and ")}.`;
  }
  if (mobile) {
    heroBtn.href = "#download";
    heroNote.textContent = "Free and open source. Emulsa is a desktop app for Windows, macOS and Linux.";
  }
  markYours();

  const PATTERN = { windows: /^EmulsaSetup-.*\.exe$/i, mac: /macOS.*\.dmg$/i, linux: /\.AppImage$/i };
  fetch("https://api.github.com/repos/ajr-alves/emulsa/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(rel => {
      const version = String(rel.tag_name || "").replace(/^v/, "");
      if (version) $$("[data-version]").forEach(el => { el.textContent = version; });
      for (const [key, re] of Object.entries(PATTERN)) {
        const asset = (rel.assets || []).find(a => re.test(a.name));
        const row = $(`.dl[data-os="${key}"]`);
        if (!asset || !row) continue;
        $("[data-name]", row).textContent = asset.name;
        $("[data-size]", row).textContent = Math.round(asset.size / 1e6) + " MB";
        $("[data-link]", row).href = asset.browser_download_url;
      }
      markYours();
    })
    .catch(() => { /* keep the links already in the page */ });
})();
