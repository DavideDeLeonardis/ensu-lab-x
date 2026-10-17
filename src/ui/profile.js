/*
  The team's lab profile, shared by the plan page (/plan) and the booking page (/bookings).

    {team, lab_id, lab_name, equipment: [ids], updated}

  Stored ONLY in this browser (localStorage), under one key for both pages, so a change made in one page shows up
  in the other, even in another open tab. The team name is never sent to the server and never stored there.
  Every storage access is guarded: in a private window or with storage blocked, the pages still work
  (no profile = all equipment).

    LabProfile.get()                    → profile or null
    LabProfile.set(p)                   → saves and notifies both pages; false if storage is unavailable
    LabProfile.uses(id)                 → true if the team uses this equipment (true when there is no profile)
    LabProfile.summary(labs)            → "Team & lab: … · n of m devices" (same text on both pages)
    LabProfile.onChange(cb)             → cb(profile) after any change, from this tab or another
    LabProfile.mountEditor(el, labs)    → team + lab + equipment editor inside `el`
    LabProfile.label(id, fallback)      → plain-language name (both pages use the same names)
*/
(function () {
  const KEY = "labx.profile";
  const EVENT = "labprofile";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  // Plain-language names for people outside the lab (both pages); the technical name stays in tooltips.
  const PLAIN = {
    "TIP-10-F-RACK": ["Pipette tips, plastic, new box each time", "Throw-away plastic tips for a pipette (the tool that measures tiny drops of liquid). Each pack comes in a new plastic box."],
    "TIP-10-F-BIO-RELOAD": ["Pipette tips, plant-based plastic, refills", "The same tips, made from plant-based plastic and sold as refills for a box you keep."],
    "TUBE-50-SU": ["Plastic tubes 50 mL, used once", "Screw-cap tubes for holding and spinning liquids with cells. Thrown away after one use."],
    "TUBE-50-GLASS-REUSE": ["Glass tubes 50 mL, washed and reused", "Glass tubes the lab washes and sterilises with steam, then uses again."],
    "TUBE-50-PP-REUSE": ["Sturdy plastic tubes 50 mL, washed and reused", "Heat-resistant plastic tubes the lab washes and sterilises, then uses again."],
    "PETRI-6-SU": ["Small plastic dishes, used once", "Shallow round dishes (6 cm) that hold cells or tissue samples. Thrown away after use."],
    "PETRI-6-GLASS-REUSE": ["Small glass dishes, washed and reused", "Glass dishes the lab washes and sterilises, then uses again."],
    "PASTEUR-SU": ["Plastic droppers, used once", "Simple droppers (Pasteur pipettes) to move small amounts of liquid. Thrown away after use."],
    "PASTEUR-GLASS-REUSE": ["Glass droppers, washed and reused", "Glass droppers the lab washes and sterilises, then uses again."],
    "FLASK-1L-SU": ["Plastic culture flasks 1 L, used once", "Large cone-shaped flasks for growing cultures or mixing media. Thrown away after one use."],
    "FLASK-1L-GLASS-REUSE": ["Glass culture flasks 1 L, washed and reused", "Glass flasks the lab washes and sterilises, then uses again."],
    "FLASK-1L-PC-REUSE": ["Sturdy plastic flasks 1 L, washed and reused", "The same plastic flask, washed and sterilised by the lab, used again."],
    "GLOVE-NITRILE": ["Disposable gloves", "Single-use lab gloves (nitrile, a synthetic rubber)."],
    "ULT-1": ["Deep freezer −80 °C (newer)", "Keeps samples frozen at −80 °C. Always on."],
    "ULT-2": ["Deep freezer −80 °C (older)", "Keeps samples frozen at −80 °C. Older, uses more power."],
    "INC-1": ["Cell incubator 1 (warm box)", "Keeps cells at body temperature (37 °C) while they grow. Counted per shelf-hour."],
    "INC-2": ["Cell incubator 2 (warm box)", "Keeps cells at body temperature (37 °C) while they grow. Counted per shelf-hour."],
    "INC-3": ["Cell incubator 3 (warm box)", "Keeps cells at body temperature (37 °C) while they grow. Counted per shelf-hour."],
    "SHK-1": ["Shaking incubator", "A warm box that also shakes the samples, e.g. to grow bacteria."],
    "BSC-1": ["Clean workbench, large", "Enclosed bench with filtered air (biosafety cabinet): you work with cells inside it so nothing gets contaminated."],
    "BSC-2": ["Clean workbench, small", "A smaller enclosed bench with filtered air (biosafety cabinet)."],
    "CEN-1": ["Centrifuge (fast spinner)", "Spins tubes very fast to separate cells from liquid."],
    "HB-1": ["Heat block", "Metal block that keeps small tubes at a set temperature. Always on."],
    "WB-1": ["Warm water bath", "Tank of 37 °C water to warm up liquids. Always on."],
    "CONF-1": ["Laser microscope", "Confocal microscope: uses lasers for sharp 3D pictures of cells."],
    "FLU-1": ["Fluorescence microscope", "Microscope that photographs cells stained with glowing dyes."],
    "BIO-1": ["Bioreactor (tissue 'gym')", "Machine that stretches and trains the growing heart-valve tissue for days."],
    "FH-1": ["Fume hood", "Ventilated cabinet that sucks away chemical fumes."],
    "AUT-1": ["Autoclave (steam steriliser)", "Sterilises equipment and waste with hot steam; counted per cycle, so bookings only."],
  };
  const label = (id, fallback) => (PLAIN[id] || [fallback || id])[0];
  const what = id => (PLAIN[id] || [, ""])[1];

  function get() {
    try { const p = JSON.parse(localStorage.getItem(KEY) || "null"); return p && p.lab_id ? p : null; }
    catch (e) { return null; }
  }
  function set(p) {
    const next = {...p, updated: new Date().toISOString().slice(0, 16).replace("T", " ")};
    let ok = true;
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch (e) { ok = false; }
    window.dispatchEvent(new CustomEvent(EVENT, {detail: next}));   // same tab ("storage" only fires in other tabs)
    return ok;
  }
  function uses(id) { const p = get(); return !p || p.equipment.includes(id); }
  /* the same "Team & lab: …" text on both pages */
  function summary(labs) {
    const p = get(), lab = (labs || []).find(l => l.lab_id === p?.lab_id) || (labs || [])[0];
    if (!lab) return "Team & lab";
    const n = p ? p.equipment.length : lab.equipment.length;
    return `Team & lab: ${p?.team ? p.team + " · " : ""}${lab.name.split(":")[0]} · ${n} of ${lab.equipment.length} devices`;
  }
  function onChange(cb) {
    window.addEventListener("storage", e => { if (e.key === KEY) cb(get()); });
    window.addEventListener(EVENT, () => cb(get()));
  }
  function defaultFor(lab) {
    return {team: "", lab_id: lab.lab_id, lab_name: lab.name, equipment: lab.equipment.map(e => e.item_id)};
  }

  const CSS = `
  .lp{display:flex;flex-direction:column;gap:10px}
  .lp-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .lp input[type=text],.lp select{font:inherit;padding:6px 8px;border-radius:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink);min-height:34px}
  .lp-room h4{margin:8px 0 4px;font-size:12px;color:var(--muted);font-family:var(--mono,monospace);text-transform:uppercase;letter-spacing:.06em;font-weight:500}
  .lp-eq{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px}
  .lp-eq label{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:7px 9px;cursor:pointer;font-size:13px}
  .lp-eq label:has(input:checked){border-color:var(--ink)}
  .lp-muted{color:var(--muted);font-size:12px}
  .lp-btn{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;padding:4px 10px;cursor:pointer}`;
  function injectCss() {
    if (document.getElementById("lp-css")) return;
    const s = document.createElement("style"); s.id = "lp-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  function mountEditor(el, labs, opts = {}) {
    if (!labs || !labs.length) { el.innerHTML = ""; return; }
    injectCss();
    const lab_ = opts.label || label, what_ = opts.what || what;
    const lab = () => { const p = get(); return labs.find(l => l.lab_id === p?.lab_id) || labs[0]; };
    const profile = () => get() || defaultFor(lab());

    function render() {
      const p = profile(), L = lab(), byRoom = {};
      L.equipment.forEach(e => (byRoom[e.room] = byRoom[e.room] || []).push(e));
      el.innerHTML = `<div class="lp">
        <div class="lp-row">
          <label>Team <input type="text" data-lp="team" maxlength="40" placeholder="e.g. Valve team" value="${esc(p.team)}"></label>
          <label>Lab <select data-lp="lab">${labs.map(l => `<option value="${esc(l.lab_id)}" ${l.lab_id === L.lab_id ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select></label>
        </div>
        <div class="lp-row lp-muted">Equipment your team uses: ${p.equipment.length} of ${L.equipment.length}
          <button class="lp-btn" data-lp="all">Select all</button><button class="lp-btn" data-lp="none">Select none</button></div>
        ${Object.entries(byRoom).map(([room, list]) => `<div class="lp-room"><h4>${esc((L.rooms || {})[room] || room)}</h4><div class="lp-eq">
          ${list.map(e => `<label title="${esc(e.name)}"><input type="checkbox" data-eq="${esc(e.item_id)}" ${p.equipment.includes(e.item_id) ? "checked" : ""}>
            <span><b>${esc(lab_(e.item_id, e.name))}</b>${what_(e.item_id) ? `<br><span class="lp-muted">${esc(what_(e.item_id))}</span>` : ""}
            ${e.plan_line === false ? `<br><span class="lp-muted">bookings only</span>` : ""}</span></label>`).join("")}
        </div></div>`).join("")}
        <div class="lp-muted">Saved only in this browser and shared by the plan and booking pages. The team name is never sent.</div>
      </div>`;
    }
    el.addEventListener("change", e => {
      const t = e.target, p = profile(), L = lab();
      if (t.dataset.lp === "team") set({...p, team: t.value.trim()});
      else if (t.dataset.lp === "lab") { const nl = labs.find(l => l.lab_id === t.value); set({...defaultFor(nl), team: p.team}); }
      else if (t.dataset.eq) {
        const s = new Set(p.equipment); t.checked ? s.add(t.dataset.eq) : s.delete(t.dataset.eq);
        set({...p, equipment: L.equipment.map(x => x.item_id).filter(x => s.has(x))});
      }
    });
    el.addEventListener("click", e => {
      const a = e.target.dataset.lp, p = profile(), L = lab();
      if (a === "all") set({...p, equipment: L.equipment.map(x => x.item_id)});
      if (a === "none") set({...p, equipment: []});
    });
    onChange(() => { if (!el.contains(document.activeElement) || document.activeElement.type !== "text") render(); });
    render();
  }

  window.LabProfile = {get, set, uses, onChange, mountEditor, PLAIN, label, what, summary};
})();
