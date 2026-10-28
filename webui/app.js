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
    // Fluent 起動設定（キー名は Python 側の FACTORY_DEFAULTS と共通）
    japanese: false,
    solverType: "cpu",
    gpuRemap: true,
    gpuHybridPrecision: true,
    license: "",
    gpuRules: { gpuMinRelease: 231, gpuRemapMinRelease: 251, gpuHybridMinRelease: 261 },
    hasSavedDefaults: false,
  };

  // セグメントコントロールの表示を外部から切り替えるための setter
  const segSetters = {};

  const LICENSE_VALUES = new Set(["", "premium", "enterprise", "hpc_ultimate", "cfd_pro"]);

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
      const row = document.createElement("button");
      row.type = "button";
      row.className = "version-row" + (name === state.selectedVersion ? " selected" : "");
      row.setAttribute("role", "option");
      row.setAttribute("tabindex", "0");
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
      const selectVersion = () => {
        state.selectedVersion = name;
        renderVersionList();
      };
      row.addEventListener("click", selectVersion);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectVersion();
        }
      });
      list.appendChild(row);
    }
    if (state.appKind === "fluent") updateFluentControls();
  }

  // ---------------- セグメントコントロール ----------------
  function wireSegmented(containerId, initialValue, onChange) {
    const container = $(containerId);
    if (!container) return;
    const apply = (value) => {
      container.querySelectorAll(".seg-btn").forEach((btn) => {
        const selected = btn.dataset.value === value;
        btn.classList.toggle("selected", selected);
        btn.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    };
    apply(initialValue);
    container.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        apply(btn.dataset.value);
        onChange(btn.dataset.value);
      });
    });
    return apply;
  }

  function updateDimRowVisibility() {
    const dimRow = $("dimRow");
    if (dimRow) dimRow.hidden = state.product === "meshing";
  }

  // ---------------- Fluent 起動設定 ----------------
  // バージョン名 / fluent.exe パスから 3 桁のリリース番号 (例: 252) を推定（Python の detect_fluent_release と同じ規則）
  function detectRelease(name, path) {
    const parts = String(path || "").split(/[\\/]/).reverse();
    for (const part of parts) {
      const m = /^v(\d{3})$/i.exec(part.trim());
      if (m) return Number(m[1]);
    }
    const n = String(name || "").trim().toLowerCase();
    const m = /^v?(\d{3})$/.exec(n) || /(?:^|[^0-9a-z])v(\d{3})(?![0-9])/.exec(n);
    return m ? Number(m[1]) : null;
  }

  function formatRelease(rel) {
    return `${2000 + Math.floor(rel / 10)} R${rel % 10}`;
  }

  // 選択中バージョンでの GPU 機能の対応状況
  function gpuSupport() {
    const rules = state.gpuRules;
    const rel = state.selectedVersion
      ? detectRelease(state.selectedVersion, state.versions[state.selectedVersion])
      : null;
    const atLeast = (min) => rel === null || rel >= min;
    return {
      release: rel,
      gpu: atLeast(rules.gpuMinRelease),
      remap: atLeast(rules.gpuRemapMinRelease),
      hybrid: atLeast(rules.gpuHybridMinRelease),
    };
  }

  // 実際に起動へ渡す GPU 設定（未対応・無効な組み合わせは渡さない）
  function effectiveGpuOptions(useLauncher) {
    const sup = gpuSupport();
    const gpuOn = state.product !== "meshing" && state.solverType === "gpu";
    return {
      solverType: gpuOn ? "gpu" : "cpu",
      gpuRemap: gpuOn && state.gpuRemap && sup.remap,
      gpuHybridPrecision: gpuOn && state.gpuHybridPrecision && sup.hybrid && (state.dp || !!useLauncher),
    };
  }

  // 起動を止めるべき組み合わせ（直接起動時）。問題なければ null
  function gpuBlockingError(useLauncher) {
    if (state.product === "meshing" || state.solverType !== "gpu") return null;
    const sup = gpuSupport();
    if (!sup.gpu) {
      return `${state.selectedVersion} は Native GPU Solver に対応していません（${formatRelease(state.gpuRules.gpuMinRelease)} 以降が必要）。CPU Solver を選択してください。`;
    }
    if (!useLauncher && state.dim === "2d") {
      return "Native GPU Solver は 3D のみ対応しています。3D を選択するか CPU Solver で起動してください。";
    }
    return null;
  }

  // CFD Pro はコマンドラインから指定できないため、直接起動のときだけ止める
  function licenseBlockingError(useLauncher) {
    if (state.license === "cfd_pro" && !useLauncher) {
      return "CFD Pro はコマンドラインから指定できません。「Fluent Launcherを起動」から起動し、画面でライセンスを選択してください。";
    }
    return null;
  }

  function setCheckboxEnabled(checkId, labelId, enabled) {
    const input = $(checkId);
    input.disabled = !enabled;
    const label = labelId ? $(labelId) : input.closest(".checkbox-label");
    if (label) label.classList.toggle("is-disabled", !enabled);
  }

  function updateFluentControls() {
    if (state.appKind !== "fluent") return;
    updateDimRowVisibility();

    const meshing = state.product === "meshing";
    const gpu = state.solverType === "gpu";
    const sup = gpuSupport();

    // メッシング時は GPU 関連の操作を無効化
    const seg = $("solverTypeSeg");
    seg.classList.toggle("is-disabled", meshing);
    seg.setAttribute("aria-disabled", meshing ? "true" : "false");
    seg.querySelectorAll(".seg-btn").forEach((b) => { b.disabled = meshing; });

    // GPU 専用オプションは Native GPU Solver 選択時のみ表示
    $("gpuOptionsRow").hidden = !gpu;
    const remapOk = !meshing && sup.remap;
    const hybridOk = !meshing && sup.hybrid && state.dp;
    setCheckboxEnabled("gpuRemapCheck", "gpuRemapLabel", remapOk);
    setCheckboxEnabled("gpuHybridCheck", "gpuHybridLabel", hybridOk);
    // 表示は「実際に適用される値」に合わせる（ユーザーの選択は state に保持）
    $("gpuRemapCheck").checked = state.gpuRemap && remapOk;
    $("gpuHybridCheck").checked = state.gpuHybridPrecision && hybridOk;

    const notes = [];
    let warn = false;
    if (gpu && meshing) {
      notes.push("メッシングモードでは GPU 設定は使用されません（従来どおり起動します）。");
    } else if (gpu) {
      const blocking = gpuBlockingError(false);
      if (blocking) { notes.push(blocking); warn = true; }
      if (sup.gpu && !sup.remap) {
        notes.push(`GPU Remapping は ${formatRelease(state.gpuRules.gpuRemapMinRelease)} 以降で利用できます。`);
      }
      if (sup.gpu && !sup.hybrid) {
        notes.push(`GPU Hybrid Precision は ${formatRelease(state.gpuRules.gpuHybridMinRelease)} 以降で利用できます（β機能）。`);
      } else if (sup.gpu && !state.dp) {
        notes.push("GPU Hybrid Precision を使うには Double Precision を有効にしてください。");
      }
    }
    const hint = $("gpuHint");
    hint.textContent = notes.join("\n");
    hint.hidden = notes.length === 0;
    hint.classList.toggle("warn", warn);

    const licenseHint = $("licenseHint");
    if (state.license === "cfd_pro") {
      licenseHint.textContent = "CFD Pro はコマンドラインから指定できません。「Fluent Launcherを起動」から起動し、画面でライセンスを選択してください。";
      licenseHint.hidden = false;
      licenseHint.classList.add("warn");
    } else {
      licenseHint.textContent = "";
      licenseHint.hidden = true;
      licenseHint.classList.remove("warn");
    }
  }

  // UI の現在値（保存・起動に使う。キー名は Python と共通）
  function currentSettings() {
    return {
      version: state.selectedVersion || "",
      product: state.product,
      dim: state.dim,
      dp: state.dp,
      procs: state.proc,
      japanese: state.japanese,
      solverType: state.solverType,
      gpuRemap: state.gpuRemap,
      gpuHybridPrecision: state.gpuHybridPrecision,
      license: state.license,
    };
  }

  function hasSegValue(segId, value) {
    const seg = $(segId);
    return !!(seg && seg.querySelector(`.seg-btn[data-value="${CSS.escape(String(value))}"]`));
  }

  // 保存済み / 初期設定を state と UI に反映
  function applySettings(s) {
    if (!s) return;
    if (s.version && s.version in state.versions) state.selectedVersion = s.version;
    if (s.product === "solver" || s.product === "meshing") state.product = s.product;
    if (s.dim === "2d" || s.dim === "3d") state.dim = s.dim;
    if (typeof s.dp === "boolean") state.dp = s.dp;
    if (s.procs !== undefined && hasSegValue("procSeg", s.procs)) state.proc = String(s.procs);
    if (typeof s.japanese === "boolean") state.japanese = s.japanese;
    if (s.solverType === "cpu" || s.solverType === "gpu") state.solverType = s.solverType;
    if (typeof s.gpuRemap === "boolean") state.gpuRemap = s.gpuRemap;
    if (typeof s.gpuHybridPrecision === "boolean") state.gpuHybridPrecision = s.gpuHybridPrecision;
    if (typeof s.license === "string" && LICENSE_VALUES.has(s.license)) state.license = s.license;

    if (segSetters.product) segSetters.product(state.product);
    if (segSetters.dim) segSetters.dim(state.dim);
    if (segSetters.proc) segSetters.proc(state.proc);
    if (segSetters.solverType) segSetters.solverType(state.solverType);
    if (segSetters.license) segSetters.license(state.license);
    $("dpCheck").checked = state.dp;
    $("japaneseCheck").checked = state.japanese;
    renderVersionList();
  }

  function updateDefaultsButtons() {
    const btn = $("applyDefaultsBtn");
    btn.disabled = !state.hasSavedDefaults;
    btn.title = state.hasSavedDefaults ? "" : "保存されたデフォルト設定はまだありません";
  }

  async function saveDefaults() {
    const res = await api().save_defaults(currentSettings());
    if (res && res.ok) {
      state.hasSavedDefaults = true;
      updateDefaultsButtons();
      showToast("現在の設定をデフォルトとして保存しました。");
    } else {
      showToast((res && res.error) || "デフォルト設定の保存に失敗しました。", "error");
    }
  }

  // 保存したデフォルトを再適用（保存内容は変更しない）
  async function applySavedDefaults() {
    const res = await api().get_defaults();
    if (res && res.ok) {
      applySettings(res.defaults);
      if (res.missingVersion) {
        showToast(`保存したバージョン '${res.missingVersion}' が見つからないため '${res.defaults.version || "なし"}' を選択しました。`, "error");
      } else {
        showToast("保存したデフォルト設定を適用しました。");
      }
    } else {
      state.hasSavedDefaults = !!(res && res.hasSavedDefaults);
      updateDefaultsButtons();
      showToast((res && res.error) || "デフォルト設定の読み込みに失敗しました。", "error");
    }
  }

  // 保存内容を削除してアプリの初期値に戻す
  async function resetDefaults() {
    const ok = await showConfirm("保存したデフォルト設定を削除し、アプリの初期設定に戻しますか？\n（登録済みのバージョンは削除されません）");
    if (!ok) return;
    const res = await api().reset_defaults();
    if (res && res.ok) {
      applySettings(res.defaults);
      state.hasSavedDefaults = false;
      updateDefaultsButtons();
      showToast("初期設定にリセットしました。");
    } else {
      showToast((res && res.error) || "初期設定へのリセットに失敗しました。", "error");
    }
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
    if (state.appKind === "fluent") {
      const blocking = gpuBlockingError(!!useLauncher) || licenseBlockingError(!!useLauncher);
      if (blocking) {
        showToast(blocking, "error");
        return;
      }
      payload.japanese = state.japanese;
      payload.license = state.license;
      Object.assign(payload, effectiveGpuOptions(!!useLauncher));
    }
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
      if (bootstrap.fluentGpuRules) state.gpuRules = bootstrap.fluentGpuRules;
      // 保存済みのデフォルト設定（無ければ初期設定）を復元
      // （保存バージョンが削除済みの場合は renderVersionList が先頭のバージョンへフォールバック）
      applySettings(bootstrap.fluentDefaults || {});

      segSetters.product = wireSegmented("productSeg", state.product, (v) => { state.product = v; updateFluentControls(); });
      segSetters.dim = wireSegmented("dimSeg", state.dim, (v) => { state.dim = v; updateFluentControls(); });
      segSetters.proc = wireSegmented("procSeg", state.proc, (v) => { state.proc = v; });
      segSetters.solverType = wireSegmented("solverTypeSeg", state.solverType, (v) => { state.solverType = v; updateFluentControls(); });
      segSetters.license = wireSegmented("licenseSeg", state.license, (v) => { state.license = v; updateFluentControls(); });
      $("dpCheck").checked = state.dp;
      $("dpCheck").addEventListener("change", (e) => { state.dp = e.target.checked; updateFluentControls(); });
      $("japaneseCheck").checked = state.japanese;
      $("japaneseCheck").addEventListener("change", (e) => { state.japanese = e.target.checked; });
      $("gpuRemapCheck").addEventListener("change", (e) => { state.gpuRemap = e.target.checked; });
      $("gpuHybridCheck").addEventListener("change", (e) => { state.gpuHybridPrecision = e.target.checked; });
      state.hasSavedDefaults = !!bootstrap.hasSavedDefaults;
      updateDefaultsButtons();
      $("saveDefaultsBtn").addEventListener("click", saveDefaults);
      $("applyDefaultsBtn").addEventListener("click", applySavedDefaults);
      $("resetDefaultsBtn").addEventListener("click", resetDefaults);
      updateFluentControls();
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
