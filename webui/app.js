(() => {
  "use strict";

  const state = {
    versions: {},
    selectedVersion: null,
    extra: {},
    appKind: "generic",
    product: "solver",
    dim: "3d",
    dp: true,
    proc: "4",
  };

  const $ = (id) => document.getElementById(id);

  function api() {
    return window.pywebview.api;
  }

  // ---------------- トースト ----------------
  let toastTimer = null;
  function showToast(message, kind = "info") {
    const el = $("toast");
    el.textContent = message;
    el.classList.toggle("error", kind === "error");
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2800);
  }

  // ---------------- 確認モーダル ----------------
  function showConfirm(message) {
    return new Promise((resolve) => {
      const overlay = $("confirmOverlay");
      $("confirmMessage").textContent = message;
      overlay.hidden = false;
      requestAnimationFrame(() => overlay.classList.add("show"));

      const cleanup = (result) => {
        overlay.classList.remove("show");
        setTimeout(() => { overlay.hidden = true; }, 200);
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        resolve(result);
      };
      const okBtn = $("confirmOkBtn");
      const cancelBtn = $("confirmCancelBtn");
      const onOk = () => cleanup(true);
      const onCancel = () => cleanup(false);
      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
    });
  }

  function openModal(overlay) {
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add("show"));
  }
  function closeModal(overlay) {
    overlay.classList.remove("show");
    setTimeout(() => { overlay.hidden = true; }, 200);
  }

  // ---------------- バージョン一覧(メイン画面) ----------------
  function renderVersionList() {
    const list = $("versionList");
    list.innerHTML = "";
    const entries = Object.entries(state.versions);
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "version-empty";
      empty.textContent = "登録済みのバージョンがありません。設定から追加してください。";
      list.appendChild(empty);
      return;
    }
    if (!state.selectedVersion || !(state.selectedVersion in state.versions)) {
      state.selectedVersion = entries[0][0];
    }
    for (const [name, path] of entries) {
      const row = document.createElement("div");
      row.className = "version-row" + (name === state.selectedVersion ? " selected" : "");
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", name === state.selectedVersion ? "true" : "false");
      row.dataset.name = name;

      const check = document.createElement("span");
      check.className = "v-check";
      check.textContent = "✓";

      const vname = document.createElement("span");
      vname.className = "v-name";
      vname.textContent = name;

      const vpath = document.createElement("span");
      vpath.className = "v-path";
      vpath.textContent = path;
      vpath.title = path;

      row.append(check, vname, vpath);
      row.addEventListener("click", () => {
        state.selectedVersion = name;
        renderVersionList();
      });
      list.appendChild(row);
    }
  }

  // ---------------- セグメントコントロール ----------------
  function wireSegmented(containerId, initialValue, onChange) {
    const container = $(containerId);
    if (!container) return;
    const apply = (value) => {
      container.querySelectorAll(".seg-btn").forEach((btn) => {
        btn.classList.toggle("selected", btn.dataset.value === value);
      });
    };
    apply(initialValue);
    container.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        apply(btn.dataset.value);
        onChange(btn.dataset.value);
      });
    });
  }

  function updateDimRowVisibility() {
    const dimRow = $("dimRow");
    if (dimRow) dimRow.hidden = state.product === "meshing";
  }

  // ---------------- 設定モーダル: バージョンテーブル ----------------
  function renderVersionTable() {
    const table = $("versionTable");
    table.innerHTML = "";
    const entries = Object.entries(state.versions);
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "version-empty";
      empty.textContent = "登録済みのバージョンはありません。";
      table.appendChild(empty);
      return;
    }
    entries.forEach(([name, path], idx) => {
      const row = document.createElement("div");
      row.className = "version-table-row";

      const vname = document.createElement("span");
      vname.className = "vt-name";
      vname.textContent = name;

      const vpath = document.createElement("span");
      vpath.className = "vt-path";
      vpath.textContent = path;
      vpath.title = path;

      const actions = document.createElement("span");
      actions.className = "vt-actions";

      const upBtn = mkIconBtn("↑", "上へ", () => moveVersion(name, -1));
      const downBtn = mkIconBtn("↓", "下へ", () => moveVersion(name, 1));
      const editBtn = mkIconBtn("✎", "編集", () => {
        $("newVerName").value = name;
        $("newVerPath").value = path;
      });
      const delBtn = mkIconBtn("🗑", "削除", () => deleteVersion(name));
      if (idx === 0) upBtn.disabled = true;
      if (idx === entries.length - 1) downBtn.disabled = true;

      actions.append(upBtn, downBtn, editBtn, delBtn);
      row.append(vname, vpath, actions);
      table.appendChild(row);
    });
  }

  function mkIconBtn(label, title, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "icon-btn";
    btn.textContent = label;
    btn.title = title;
    btn.addEventListener("click", onClick);
    return btn;
  }

  async function addOrUpdateVersion() {
    const name = $("newVerName").value.trim();
    const path = $("newVerPath").value.trim();
    if (!name || !path) {
      showToast("バージョン名とパスを入力してください。", "error");
      return;
    }
    const res = await api().add_or_update_version(name, path);
    if (!res.ok) {
      showToast(res.error || "登録に失敗しました。", "error");
      return;
    }
    state.versions = res.versions;
    $("newVerName").value = "";
    $("newVerPath").value = "";
    renderVersionTable();
    renderVersionList();
  }

  async function deleteVersion(name) {
    const ok = await showConfirm(`バージョン '${name}' を削除しますか？`);
    if (!ok) return;
    const res = await api().delete_version(name);
    state.versions = res.versions;
    renderVersionTable();
    renderVersionList();
  }

  async function moveVersion(name, direction) {
    const res = await api().move_version(name, direction);
    state.versions = res.versions;
    renderVersionTable();
    renderVersionList();
  }

  async function scanVersions() {
    const msg = state.extra.scanConfirmMessage ||
      "システムをスキャンして対応バージョンを検索しますか？\n既存のパスが上書きされる可能性があります。";
    const ok = await showConfirm(msg);
    if (!ok) return;
    const res = await api().scan_versions();
    state.versions = res.versions;
    renderVersionTable();
    renderVersionList();
    if (res.count > 0) {
      showToast((state.extra.scanDoneMessageTemplate || "{count} 個のバージョンを検出・更新しました。").replace("{count}", res.count));
    } else {
      showToast(state.extra.scanEmptyMessage || "インストールが見つかりませんでした。");
    }
  }

  // ---------------- 起動処理 ----------------
  async function launch(useLauncher) {
    if (!state.selectedVersion) {
      showToast("バージョンを選択してください。", "error");
      return;
    }
    const payload = {
      file: $("fileInput").value.trim(),
      version: state.selectedVersion,
      useLauncher: !!useLauncher,
      product: state.product,
      dim: state.dim,
      dp: state.dp,
      procs: state.proc,
    };
    const res = await api().launch(payload);
    if (res && res.ok) {
      await api().close();
    } else {
      showToast((res && res.error) || "起動に失敗しました。", "error");
    }
  }

  // ---------------- 初期化 ----------------
  async function boot() {
    const bootstrap = await api().get_bootstrap();
    document.title = bootstrap.title;
    $("appTitle").textContent = bootstrap.title;
    state.versions = bootstrap.versions || {};
    state.appKind = bootstrap.appKind;
    state.extra = bootstrap.extra || {};

    if (state.extra.fileGroupLabel) $("fileGroupLabel").textContent = state.extra.fileGroupLabel;
    if (state.extra.versionLabel) $("versionLabel").textContent = state.extra.versionLabel;
    if (bootstrap.initialFile) $("fileInput").value = bootstrap.initialFile;

    $("launchBtn").textContent = state.extra.primaryButtonLabel || "起動";

    if (state.extra.showLauncherButton) {
      $("launcherBtn").hidden = false;
      $("launcherBtn").textContent = state.extra.launcherButtonLabel || "Launcherを起動";
    }

    if (state.extra.helpText) {
      $("helpBtn").hidden = false;
      $("helpMessage").textContent = state.extra.helpText;
    }

    if (state.appKind === "fluent") {
      $("fluentControls").hidden = false;
      wireSegmented("productSeg", state.product, (v) => { state.product = v; updateDimRowVisibility(); });
      wireSegmented("dimSeg", state.dim, (v) => { state.dim = v; });
      wireSegmented("procSeg", state.proc, (v) => { state.proc = v; });
      $("dpCheck").checked = state.dp;
      $("dpCheck").addEventListener("change", (e) => { state.dp = e.target.checked; });
      updateDimRowVisibility();
    }

    renderVersionList();

    $("browseFileBtn").addEventListener("click", async () => {
      const path = await api().browse_input_file(state.extra.browseFileTypes || ["All files (*.*)"]);
      if (path) $("fileInput").value = path;
    });

    $("launchBtn").addEventListener("click", () => launch(false));
    $("launcherBtn").addEventListener("click", () => launch(true));

    $("settingsBtn").addEventListener("click", () => {
      renderVersionTable();
      openModal($("settingsOverlay"));
    });
    $("settingsCloseBtn").addEventListener("click", () => closeModal($("settingsOverlay")));
    $("settingsCancelBtn").addEventListener("click", () => closeModal($("settingsOverlay")));

    $("newVerBrowseBtn").addEventListener("click", async () => {
      const path = await api().browse_exe();
      if (path) $("newVerPath").value = path;
    });
    $("addVerBtn").addEventListener("click", addOrUpdateVersion);
    $("scanBtn").addEventListener("click", scanVersions);

    $("helpBtn").addEventListener("click", () => openModal($("helpOverlay")));
    $("helpCloseBtn").addEventListener("click", () => closeModal($("helpOverlay")));
  }

  window.addEventListener("pywebviewready", boot);
})();
