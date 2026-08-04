# Handoff: Port NHL's gear-icon Connection UI to the NFL optimizer

**Context:** During NHL Session 6.2 (full parity rebuild), the person running
both projects reviewed NHL's new gear-icon settings modal against NFL's
existing inline collapsible "Connection" panel and preferred the gear-icon
pattern. This doc is everything needed to bring NFL's frontend in line,
written by the Claude instance that built NHL's version — hand this to
whichever session is working on `drgregmscott-tech/DFS_Optimizer`.

**File to change:** `dfs_optimizer_frontend/index.html` in the NFL repo.

**Scope:** Purely a UI/UX change — swaps *where* the Worker URL/Token fields
live and how they're revealed, changes nothing about what they connect to,
how `testConnection()` works, or any dispatch/poll/slate/preset logic. Every
existing function that reads `document.getElementById("settingsWorkerUrl")`
/ `"settingsWorkerToken")` keeps working unchanged if you keep those exact
two element IDs (recommended — see below).

---

## 1. What NHL built (for reference)

- A small gear button (⚙) in the header, next to the site toggle
- Clicking it opens a centered modal (dark backdrop, click-outside-to-close)
  with two fields (Worker URL, Worker Auth Token — `type="password"`), a
  **Test Connection** button, and a **Save** button
- Modal is closed by default and only ever open when explicitly clicked —
  this is what replaces NFL's current "readonly-by-default, click Locked to
  unlock" protection (Session 7.3, item #4): a closed modal can't be
  stray-clicked into the way an always-visible inline panel can.
- Values persist to `localStorage` on Save; the modal re-reads current
  values from `localStorage` every time it's opened.

## 2. What to remove from NFL's `index.html`

**Markup** — the whole `.conn-panel` block (search for `id="connPanel"`),
roughly:
```html
<div class="conn-panel" id="connPanel">
  <div class="conn-header" id="connHeader">...</div>
  <div class="conn-body">
    <div class="settings-row" id="workerSettingsRow">...</div>
    <div class="hint">Locked by default...</div>
    <div class="solve-status" id="connectionTestStatus"></div>
  </div>
</div>
```

**CSS** — the `.conn-panel`, `.conn-header`, `.conn-body` rule block (search
`/* ---------------- Connection panel ---------------- */`).

**JS** — these become dead code once the panel markup is gone, remove them:
- `setWorkerFieldsLocked(locked)` and its `btnToggleWorkerLock` click handler
- `document.getElementById("connHeader").addEventListener("click", ...)`
  (the collapsible-panel toggle)
- The `setWorkerFieldsLocked(true)` call in the init section at the bottom

**Keep as-is** (still needed, now called from the modal instead):
- `testConnection()` — entirely unchanged, just gets wired to the modal's
  Test Connection button instead of `btnTestConnection` in the old panel
  (reuse the same button ID if you keep the same markup structure, or
  rewire the `addEventListener` target)
- `loadSettings()` / `saveSettings()` — unchanged, still read/write
  `localStorage["dfs_worker_url"]` / `localStorage["dfs_worker_token"]`
- Every other function reading `settingsWorkerUrl` / `settingsWorkerToken`
  by ID — unchanged, as long as you keep those two IDs (see below)

## 3. What to add

**Header button** (add next to the existing site-toggle in the header):
```html
<button class="gear-btn" id="settingsBtn" title="Solver connection settings">&#9881;</button>
```

**Modal** (add once, right after `</header>`, before `<div class="wrap">`):
```html
<div class="modal-backdrop hidden" id="settingsModal">
<div class="modal">
<h3>Real Solver Connection</h3>
<p class="hint">"Build Lineups" calls your deployed <code>dfs-optimizer-api</code>
Cloudflare Worker, which dispatches to GitHub Actions and runs the real
optimizer.py. Also used for cloud-synced slates and presets. Stored only
in this browser's localStorage.</p>
<label for="settingsWorkerUrl">Worker URL</label>
<input type="text" id="settingsWorkerUrl" placeholder="https://dfs-optimizer-api.&lt;subdomain&gt;.workers.dev">
<label for="settingsWorkerToken">Worker Auth Token</label>
<input type="password" id="settingsWorkerToken" placeholder="WORKER_AUTH_TOKEN">
<div class="modal-actions">
<button class="secondary-btn" id="btnTestConnection">Test Connection</button>
<button class="primary-btn" id="btnSaveSettings">Save</button>
</div>
<div class="solve-status" id="connectionTestStatus"></div>
</div>
</div>
```

**IMPORTANT — kept the same element IDs on purpose** (`settingsWorkerUrl`,
`settingsWorkerToken`, `connectionTestStatus`, `btnTestConnection`): every
other function in NFL's file (`cloudConfigured()`, `workerUrl()`,
`confirmWithRealSolver()`, `cloudSaveSlate()`, preset save/load, etc.)
already reads these by ID. Keeping the IDs identical means **zero changes**
to any of that logic — only the surrounding markup moves. Do not rename
these IDs unless you're also updating every `getElementById` call site.

**CSS** — reuse NHL's gear-btn/modal-backdrop/modal block verbatim, just
swap the accent color: NHL used `var(--ice)`/`var(--ice-dim)` throughout;
NFL's own accent variable is `var(--amber)`/`var(--amber-dim)` (confirmed
in NFL's own `:root` — search `--amber:` near the top of the file). Every
other CSS variable name (`--panel`, `--line`, `--bone`, `--dim`, `--dimmer`,
`--ink-raised`, `--radius`) is identical between the two projects, so a
straight copy-paste of NHL's gear/modal CSS block works as long as you do
that one find/replace (`--ice` → `--amber`, `--ice-dim` → `--amber-dim`).
NFL doesn't currently have `.primary-btn`/`.secondary-btn` classes (NHL
added those for its modal) — include them in the copy-paste, they're new,
harmless additions.

**JS wiring** (add near where `loadSettings()`/`saveSettings()` are
already called):
```javascript
document.getElementById("settingsBtn").addEventListener("click", function () {
  document.getElementById("settingsModal").classList.remove("hidden");
});
document.getElementById("settingsModal").addEventListener("click", function (e) {
  if (e.target === this) this.classList.add("hidden");
});
document.getElementById("btnSaveSettings").addEventListener("click", function () {
  saveSettings();
  document.getElementById("settingsModal").classList.add("hidden");
  refreshPresetDropdown();
  refreshForActiveSlate();
});
```
`testConnection()` itself needs no changes — just make sure its existing
`addEventListener("click", testConnection)` still targets whichever
element ID you used for the Test Connection button (`btnTestConnection`
above, matching the old panel's button ID, so no rewire needed if kept
identical).

## 4. One behavioral difference to decide on

NHL's modal calls `loadSettings()`-equivalent (populates the fields from
`localStorage`) **every time the gear icon is clicked**, not just once on
page load — so if the person edits the fields, clicks away without saving
(closing via backdrop click), then reopens the gear icon, they see the
last *saved* values, not their abandoned edit. NFL's current panel has no
equivalent "revert unsaved edits on reopen" behavior since it's always
visible. Recommend adding this line to the gear button's click handler
(before showing the modal):
```javascript
document.getElementById("settingsWorkerUrl").value = localStorage.getItem("dfs_worker_url") || "";
document.getElementById("settingsWorkerToken").value = localStorage.getItem("dfs_worker_token") || "";
```

## 5. Testing checklist before calling it done

- Gear icon opens the modal; backdrop click and re-clicking gear both work
- Existing saved Worker URL/Token (if any, from before this change) still
  populate correctly — confirms the localStorage keys weren't renamed
- Test Connection button still calls the real Worker and reports
  correctly (ping action, no GitHub call — should be instant)
- Save closes the modal and immediately enables slate/preset cloud sync
  (matches NHL's post-save `refreshPresetDropdown()` / `refreshForActiveSlate()`
  calls)
- No leftover references to `connPanel` / `connHeader` / `workerSettingsRow`
  / `btnToggleWorkerLock` anywhere in the file (`grep -n` for each before
  considering this done)
