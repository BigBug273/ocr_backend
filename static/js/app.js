/* ═══════════════════════════════════════════════
   RECEIPT OCR SCANNER — APPLICATION LOGIC
   ═══════════════════════════════════════════════
   Backend: FastAPI (receipts/scan, save-receipts, receipts, etc.)
   Key fix: FormData with "files" field for multipart upload
   ═══════════════════════════════════════════════ */

(function () {
  "use strict";

  // ─── CONFIG ───────────────────────────────────
  // The frontend server (port 3001) acts as a reverse proxy.
  // It forwards all API requests to the FastAPI backend.
  // No backend URL needed — just use relative paths.
  // The backend port can be changed via the sidebar input.

  function apiUrl(path) {
    // All API calls are relative — the Bun server proxies them
    return path;
  }

  // ─── STATE ────────────────────────────────────
  let selectedFiles = [];       // Files pending scan
  let lastScanResults = [];     // Parsed results from last scan
  let allReceipts = [];         // All saved receipts from backend

  // ─── DOM REFERENCES ───────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dropZone         = $("#dropZone");
  const fileInput        = $("#fileInput");
  const filePreviewList  = $("#filePreviewList");
  const fileItems        = $("#fileItems");
  const clearFilesBtn    = $("#clearFilesBtn");
  const scanBtn          = $("#scanBtn");
  const scanProgress     = $("#scanProgress");
  const scanResults      = $("#scanResults");
  const resultsList      = $("#resultsList");
  const saveAllBtn       = $("#saveAllBtn");
  const exportCsvBtn     = $("#exportCsvBtn");
  const refreshBtn       = $("#refreshBtn");
  const receiptModal     = $("#receiptModal");
  const modalCloseBtn    = $("#modalCloseBtn");
  const modalTitle       = $("#modalTitle");
  const modalBody        = $("#modalBody");
  const menuToggle       = $("#menuToggle");
  const sidebar          = $("#sidebar");
  const connectionStatus = $("#connectionStatus");
  const mobileStatus     = $("#mobileStatus");

  // ─── INITIALIZATION ───────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initDropZone();
    initButtons();
    initBackendPort();
    checkHealth();
    loadDashboard();
  });

  // ─── BACKEND PORT CONFIG ─────────────────────
  function initBackendPort() {
    const input = $("#backendPortInput");
    if (!input) return;

    // Restore saved port
    const savedPort = localStorage.getItem("receipt_backend_port");
    if (savedPort) input.value = savedPort;

    // Save and recheck on change
    input.addEventListener("change", () => {
      const port = input.value.trim() || "8000";
      localStorage.setItem("receipt_backend_port", port);
      // Update the proxy by calling the config endpoint
      fetch(`/__config?backend_port=${port}`)
        .then(r => r.json())
        .then(data => {
          showToast("Backend port set to " + port, "info");
          checkHealth();
          loadDashboard();
        })
        .catch(() => {
          showToast("Port saved to " + port + " (requires server restart)", "info");
        });
    });
  }

  // ─── NAVIGATION ───────────────────────────────
  function initNavigation() {
    // Sidebar nav buttons
    $$(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        switchView(view);
        // Close mobile sidebar
        sidebar.classList.remove("open");
        removeOverlay();
      });
    });

    // Mobile menu toggle
    menuToggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      if (sidebar.classList.contains("open")) {
        showOverlay();
      } else {
        removeOverlay();
      }
    });

    // Close modal
    modalCloseBtn.addEventListener("click", closeModal);
    receiptModal.addEventListener("click", (e) => {
      if (e.target === receiptModal) closeModal();
    });

    // Escape key closes modal/mobile menu
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeModal();
        sidebar.classList.remove("open");
        removeOverlay();
      }
    });
  }

  // Make switchView globally available for inline onclick
  window.switchView = function (viewName) {
    // Update nav buttons
    $$(".nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewName);
    });

    // Update views
    $$(".view").forEach((view) => {
      view.classList.remove("active");
    });
    const target = $(`#view-${viewName}`);
    if (target) target.classList.add("active");

    // Load data when switching views
    if (viewName === "dashboard") loadDashboard();
    if (viewName === "history") loadHistory();
  };

  // ─── OVERLAY (mobile sidebar backdrop) ────────
  function showOverlay() {
    let overlay = $(".sidebar-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "sidebar-overlay";
      document.body.appendChild(overlay);
      overlay.addEventListener("click", () => {
        sidebar.classList.remove("open");
        removeOverlay();
      });
    }
    // Force reflow then add class
    overlay.offsetHeight;
    overlay.classList.add("active");
  }

  function removeOverlay() {
    const overlay = $(".sidebar-overlay");
    if (overlay) overlay.classList.remove("active");
  }

  // ─── HEALTH CHECK ─────────────────────────────
  async function checkHealth() {
    setStatus("checking");
    try {
      const res = await fetch(apiUrl("/health"));
      if (!res.ok) throw new Error("not ok");
      setStatus("online");
    } catch {
      setStatus("offline");
    }
  }

  function setStatus(state) {
    const dots = $$(".status-dot");
    const texts = $$(".status-text");
    dots.forEach((d) => {
      d.className = "status-dot";
      if (state !== "checking") d.classList.add(state);
      else d.classList.add("checking");
    });
    const labels = { online: "Connected", offline: "Disconnected", checking: "Checking..." };
    texts.forEach((t) => { t.textContent = labels[state] || state; });
  }

  // ─── DROP ZONE & FILE SELECTION ───────────────
  function initDropZone() {
    // Click to browse
    dropZone.addEventListener("click", () => fileInput.click());

    // File input change
    fileInput.addEventListener("change", () => {
      addFiles(Array.from(fileInput.files));
      fileInput.value = "";
    });

    // Drag & drop
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        addFiles(Array.from(e.dataTransfer.files));
      }
    });
  }

  function addFiles(files) {
    // Filter to allowed types
    const allowed = [".jpg", ".jpeg", ".png", ".pdf", ".txt"];
    const valid = files.filter((f) => {
      const ext = "." + f.name.split(".").pop().toLowerCase();
      return allowed.includes(ext);
    });

    if (valid.length === 0) {
      showToast("No valid files selected. Allowed: JPG, PNG, PDF, TXT", "error");
      return;
    }

    selectedFiles = [...selectedFiles, ...valid];
    renderFileList();
  }

  function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
  }

  function renderFileList() {
    if (selectedFiles.length === 0) {
      filePreviewList.style.display = "none";
      dropZone.style.display = "";
      return;
    }

    dropZone.style.display = "none";
    filePreviewList.style.display = "";

    fileItems.innerHTML = selectedFiles
      .map((f, i) => {
        const ext = f.name.split(".").pop().toUpperCase();
        const size = formatBytes(f.size);
        return `
          <div class="file-item">
            <span class="file-item-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </span>
            <span class="file-item-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
            <span class="file-item-size">${size}</span>
            <button class="file-item-remove" data-index="${i}" title="Remove">&times;</button>
          </div>`;
      })
      .join("");

    // Bind remove buttons
    fileItems.querySelectorAll(".file-item-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeFile(parseInt(btn.dataset.index, 10));
      });
    });
  }

  // ─── BUTTONS ──────────────────────────────────
  function initButtons() {
    clearFilesBtn.addEventListener("click", () => {
      selectedFiles = [];
      lastScanResults = [];
      renderFileList();
      scanResults.style.display = "none";
      scanProgress.style.display = "none";
    });

    scanBtn.addEventListener("click", doScan);
    saveAllBtn.addEventListener("click", doSaveAll);
    exportCsvBtn.addEventListener("click", doExportCsv);
    refreshBtn.addEventListener("click", () => loadHistory());
  }

  // ─── SCAN (THE CRITICAL FIX) ─────────────────
  async function doScan() {
    if (selectedFiles.length === 0) {
      showToast("Please select at least one file to scan.", "error");
      return;
    }

    // Show progress, hide previous results
    scanProgress.style.display = "";
    scanResults.style.display = "none";
    scanBtn.disabled = true;

    try {
      // ═══════════════════════════════════════════════════
      // THE KEY FIX: Build FormData correctly.
      // The FastAPI endpoint expects:
      //   POST /receipts/scan
      //   Content-Type: multipart/form-data
      //   Field name: "files" (repeated for each file)
      //
      // DO NOT set Content-Type header manually!
      // The browser sets it automatically with the correct boundary
      // when using FormData.
      // ═══════════════════════════════════════════════════
      const formData = new FormData();
      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      console.log(`Scanning ${selectedFiles.length} file(s)...`);
      console.log("FormData entries:");
      for (const [key, value] of formData.entries()) {
        console.log(`  ${key}: ${value instanceof File ? value.name + " (" + formatBytes(value.size) + ")" : value}`);
      }

      const response = await fetch(apiUrl("/receipts/scan"), {
        method: "POST",
        body: formData,
        // DO NOT add: headers: { "Content-Type": "multipart/form-data" }
        // The browser will set the correct Content-Type with boundary automatically.
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server returned ${response.status}: ${errorText}`);
      }

      const data = await response.json();
      console.log("Scan response:", data);

      lastScanResults = data.results || [];
      renderScanResults(lastScanResults);

    } catch (err) {
      console.error("Scan failed:", err);
      showToast("Scan failed: " + err.message, "error");
    } finally {
      scanProgress.style.display = "none";
      scanBtn.disabled = false;
    }
  }

  // ─── RENDER SCAN RESULTS ──────────────────────
  function renderScanResults(results) {
    if (!results.length) {
      scanResults.style.display = "none";
      showToast("No results returned.", "info");
      return;
    }

    scanResults.style.display = "";

    resultsList.innerHTML = results
      .map((r, idx) => {
        const success = r.success;
        const badgeClass = success ? "badge-green" : "badge-red";
        const badgeText = success ? "Parsed" : "Failed";

        if (!success) {
          return `
            <div class="result-card">
              <div class="result-card-header">
                <h3>${escapeHtml(r.filename || "Unknown")} <span class="badge ${badgeClass}">${badgeText}</span></h3>
              </div>
              <div class="result-card-body">
                <div class="result-error">Error: ${escapeHtml(r.error || "Unknown error")}</div>
              </div>
            </div>`;
        }

        const items = r.items || [];
        let itemsHtml = "";
        if (items.length > 0) {
          itemsHtml = `
            <table class="result-items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                ${items
                  .map(
                    (it) => `
                  <tr>
                    <td>${escapeHtml(it.item_name || "-")}</td>
                    <td>${it.qty != null ? it.qty : "-"}</td>
                    <td>${it.unit_price != null ? it.unit_price.toFixed(2) : "-"}</td>
                    <td>${it.line_total != null ? it.line_total.toFixed(2) : "-"}</td>
                  </tr>`
                  )
                  .join("")}
              </tbody>
            </table>`;
        }

        return `
          <div class="result-card">
            <div class="result-card-header">
              <h3>
                ${escapeHtml(r.filename || "Unknown")}
                <span class="badge ${badgeClass}">${badgeText}</span>
                ${r.doc_type ? `<span class="badge badge-blue">${escapeHtml(r.doc_type)}</span>` : ""}
                ${r.needs_review ? `<span class="badge badge-amber">Needs Review</span>` : ""}
              </h3>
            </div>
            <div class="result-card-body">
              <div class="result-field">
                <span class="result-field-label">Company</span>
                <span class="result-field-value">${escapeHtml(r.company_name || "-")}</span>
              </div>
              <div class="result-field">
                <span class="result-field-label">Tax ID</span>
                <span class="result-field-value">${escapeHtml(r.tax_id || "-")}</span>
              </div>
              <div class="result-field">
                <span class="result-field-label">Grand Total</span>
                <span class="result-field-value">${r.grand_total != null ? "฿" + r.grand_total.toFixed(2) : "-"}</span>
              </div>
              ${itemsHtml}
              ${r.error ? `<div class="result-error" style="margin-top:12px;">Note: ${escapeHtml(r.error)}</div>` : ""}
            </div>
          </div>`;
      })
      .join("");
  }

  // ─── SAVE ALL RESULTS ─────────────────────────
  async function doSaveAll() {
    const validResults = lastScanResults.filter((r) => r.success && r.raw_text);
    if (validResults.length === 0) {
      showToast("No valid results to save.", "error");
      return;
    }

    saveAllBtn.disabled = true;

    try {
      const response = await fetch(apiUrl("/save-receipts"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: validResults }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server returned ${response.status}: ${errorText}`);
      }

      const saved = await response.json();
      showToast(`Saved ${saved.length} receipt(s) successfully!`, "success");

      // Clear scan state
      selectedFiles = [];
      lastScanResults = [];
      renderFileList();
      scanResults.style.display = "none";

      // Refresh dashboard
      loadDashboard();

    } catch (err) {
      console.error("Save failed:", err);
      showToast("Save failed: " + err.message, "error");
    } finally {
      saveAllBtn.disabled = false;
    }
  }

  // ─── LOAD DASHBOARD ───────────────────────────
  async function loadDashboard() {
    try {
      const res = await fetch(apiUrl("/receipts"));
      if (!res.ok) throw new Error("Failed to load receipts");
      allReceipts = await res.json();
    } catch {
      allReceipts = [];
    }

    // Stats
    const total = allReceipts.length;
    const reviewed = allReceipts.filter((r) => !r.needs_review).length;
    const needsReview = total - reviewed;
    const totalAmount = allReceipts.reduce((sum, r) => sum + (r.grand_total || 0), 0);

    $("#statTotal").textContent = total;
    $("#statReviewed").textContent = reviewed;
    $("#statNeedsReview").textContent = needsReview;
    $("#statTotalAmount").textContent = "฿" + totalAmount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    // Recent receipts (last 5)
    const recent = allReceipts.slice(0, 5);
    const container = $("#recentReceipts");

    if (recent.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <p>No receipts yet. Scan your first slip!</p>
        </div>`;
      return;
    }

    container.innerHTML = recent.map((r) => buildReceiptRow(r)).join("");

    // Bind click events
    container.querySelectorAll(".receipt-row").forEach((row) => {
      row.addEventListener("click", () => {
        const id = parseInt(row.dataset.id, 10);
        openReceiptDetail(id);
      });
    });
  }

  // ─── LOAD HISTORY ─────────────────────────────
  async function loadHistory() {
    const container = $("#historyList");

    // Show loading state
    container.innerHTML = `
      <div class="empty-state">
        <div class="progress-spinner" style="width:28px;height:28px;"></div>
        <p>Loading receipts...</p>
      </div>`;

    try {
      const res = await fetch(apiUrl("/receipts"));
      if (!res.ok) throw new Error("Failed to load");
      allReceipts = await res.json();
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <p style="color:var(--accent-red);">Failed to load receipts: ${escapeHtml(err.message)}</p>
        </div>`;
      return;
    }

    if (allReceipts.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <p>No receipts saved yet.</p>
        </div>`;
      return;
    }

    container.innerHTML = allReceipts.map((r) => buildReceiptRow(r)).join("");

    container.querySelectorAll(".receipt-row").forEach((row) => {
      row.addEventListener("click", () => {
        const id = parseInt(row.dataset.id, 10);
        openReceiptDetail(id);
      });
    });
  }

  // ─── BUILD RECEIPT ROW HTML ───────────────────
  function buildReceiptRow(r) {
    const name = r.company_name || r.filename || "Unknown";
    const date = r.created_at ? formatDate(r.created_at) : "";
    const amount = r.grand_total != null ? "฿" + r.grand_total.toFixed(2) : "-";
    const reviewClass = r.needs_review ? "review" : "";

    return `
      <div class="receipt-row" data-id="${r.id}">
        <div class="receipt-row-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div class="receipt-row-info">
          <div class="receipt-row-name">${escapeHtml(name)}</div>
          <div class="receipt-row-meta">
            <span>${date}</span>
            ${r.needs_review ? '<span class="badge badge-amber">Review</span>' : '<span class="badge badge-green">OK</span>'}
          </div>
        </div>
        <div class="receipt-row-amount ${reviewClass}">${amount}</div>
      </div>`;
  }

  // ─── RECEIPT DETAIL MODAL ─────────────────────
  async function openReceiptDetail(id) {
    modalTitle.textContent = "Loading...";
    modalBody.innerHTML = `<div class="progress-container"><div class="progress-spinner"></div></div>`;
    receiptModal.style.display = "";

    try {
      const res = await fetch(apiUrl(`/receipts/${id}`));
      if (!res.ok) throw new Error("Receipt not found");
      const r = await res.json();

      modalTitle.textContent = r.company_name || r.filename || `Receipt #${r.id}`;

      const items = r.items || [];
      let itemsHtml = "";
      if (items.length > 0) {
        itemsHtml = `
          <h4 style="margin:16px 0 8px;font-size:0.85rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Line Items</h4>
          <table class="result-items-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
            <tbody>
              ${items
                .map(
                  (it) => `
                <tr>
                  <td>${escapeHtml(it.item_name || "-")}</td>
                  <td>${it.qty != null ? it.qty : "-"}</td>
                  <td>${it.unit_price != null ? it.unit_price.toFixed(2) : "-"}</td>
                  <td>${it.line_total != null ? it.line_total.toFixed(2) : "-"}</td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>`;
      }

      modalBody.innerHTML = `
        <div class="result-field">
          <span class="result-field-label">ID</span>
          <span class="result-field-value">#${r.id}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Filename</span>
          <span class="result-field-value">${escapeHtml(r.filename || "-")}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Company</span>
          <span class="result-field-value">${escapeHtml(r.company_name || "-")}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Tax ID</span>
          <span class="result-field-value">${escapeHtml(r.tax_id || "-")}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Grand Total</span>
          <span class="result-field-value">${r.grand_total != null ? "฿" + r.grand_total.toFixed(2) : "-"}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Status</span>
          <span class="result-field-value">${r.needs_review ? '<span class="badge badge-amber">Needs Review</span>' : '<span class="badge badge-green">Reviewed</span>'}</span>
        </div>
        <div class="result-field">
          <span class="result-field-label">Created</span>
          <span class="result-field-value">${r.created_at ? formatDate(r.created_at) : "-"}</span>
        </div>
        ${itemsHtml}
        ${r.raw_text ? `
          <h4 style="margin:16px 0 8px;font-size:0.85rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Raw OCR Text</h4>
          <pre style="background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;font-size:0.78rem;max-height:200px;overflow-y:auto;white-space:pre-wrap;word-break:break-word;color:var(--text-secondary);line-height:1.5;">${escapeHtml(r.raw_text)}</pre>
        ` : ""}`;

    } catch (err) {
      modalTitle.textContent = "Error";
      modalBody.innerHTML = `<div class="result-error">Failed to load receipt: ${escapeHtml(err.message)}</div>`;
    }
  }

  function closeModal() {
    receiptModal.style.display = "none";
  }

  // ─── EXPORT CSV ───────────────────────────────
  async function doExportCsv() {
    try {
      const res = await fetch(apiUrl("/receipts/export/csv"));
      if (!res.ok) throw new Error("Export failed");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "receipts_export.csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      showToast("CSV exported successfully!", "success");
    } catch (err) {
      showToast("Export failed: " + err.message, "error");
    }
  }

  // ─── TOAST NOTIFICATIONS ──────────────────────
  function showToast(message, type = "info") {
    const container = $("#toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    const icons = {
      success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
      error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
      info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };

    toast.innerHTML = (icons[type] || "") + " " + escapeHtml(message);
    container.appendChild(toast);

    // Auto-remove after 4 seconds
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ─── UTILITY FUNCTIONS ────────────────────────
  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function formatDate(dateStr) {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  }
})();
