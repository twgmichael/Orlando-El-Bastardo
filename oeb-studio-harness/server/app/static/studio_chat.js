(function () {
  const STANDARD_REVIEW_VIEWS = ["top", "bottom", "left", "right", "front", "rear", "action"];

  const state = {
    models: [],
    presets: [],
    messages: [],
    pollTimers: {},
    raw: {
      request: null,
      response: null,
      build_job: null,
      build_status: null,
      error: null,
      settings: {},
    },
  };

  const els = {
    model: document.getElementById("model-select"),
    preset: document.getElementById("preset-select"),
    temperature: document.getElementById("temperature-input"),
    maxTokens: document.getElementById("max-tokens-input"),
    reviewViews: document.getElementById("review-views-select"),
    systemPrompt: document.getElementById("system-prompt"),
    debugToggle: document.getElementById("debug-toggle"),
    autoBuild: document.getElementById("auto-build-toggle"),
    streamToggle: document.getElementById("stream-toggle"),
    createBuildJob: document.getElementById("create-build-job"),
    clear: document.getElementById("clear-chat"),
    exportJson: document.getElementById("export-json"),
    exportMd: document.getElementById("export-md"),
    status: document.getElementById("chat-status"),
    error: document.getElementById("chat-error"),
    transcript: document.getElementById("transcript"),
    composer: document.getElementById("composer"),
    input: document.getElementById("message-input"),
    send: document.getElementById("send-message"),
    debugPanel: document.getElementById("debug-panel"),
    debugOutput: document.getElementById("debug-output"),
  };

  function option(value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    return node;
  }

  function setStatus(text) {
    els.status.textContent = text;
  }

  function showError(message, detail) {
    state.raw.error = { message, detail: detail || null };
    els.error.hidden = false;
    els.error.textContent = detail ? `${message}: ${detail}` : message;
    renderDebug();
  }

  function clearError() {
    state.raw.error = null;
    els.error.hidden = true;
    els.error.textContent = "";
  }

  function stopPolling(jobId) {
    if (jobId) {
      if (state.pollTimers[jobId]) {
        clearInterval(state.pollTimers[jobId]);
        delete state.pollTimers[jobId];
      }
      return;
    }
    for (const timer of Object.values(state.pollTimers)) {
      clearInterval(timer);
    }
    state.pollTimers = {};
  }

  function buildCardStatusText(build) {
    if (!build) return "";
    if (build.status) {
      const reviewStatus = build.status.review_job ? `, review ${build.status.review_job.status}` : "";
      return `Build ${build.status.build_job.status}${reviewStatus}; phase ${build.status.phase}`;
    }
    if (build.result) {
      return `Build ${build.result.job.status}; phase queued`;
    }
    return "Build job pending";
  }

  function renderBuildCard(build) {
    const card = document.createElement("div");
    card.className = "chat-build-card";

    const result = build.result || null;
    const status = build.status || null;
    const spec = result && result.spec ? result.spec : null;
    const buildJob = status ? status.build_job : result && result.job;
    const buildReviewUrl = status ? status.build_review_url : result && result.review_url;
    const assetReviewUrl = status ? status.asset_review_url : result && result.asset_review_url;

    const eyebrow = document.createElement("div");
    eyebrow.className = "chat-build-eyebrow";
    eyebrow.textContent = status ? `Rendering pipeline: ${status.phase}` : "Rendering pipeline: queued";
    card.appendChild(eyebrow);

    const title = document.createElement("strong");
    title.textContent = spec
      ? `Building ${spec.canonical_id}`
      : buildJob
        ? `Building ${buildJob.title}`
        : "Creating build job";
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "build-job-meta";
    meta.textContent = build.error || buildCardStatusText(build);
    card.appendChild(meta);

    if (buildReviewUrl && assetReviewUrl) {
      const links = document.createElement("div");
      links.className = "build-job-links";
      const jobLink = document.createElement("a");
      jobLink.href = buildReviewUrl;
      jobLink.textContent = "Build job";
      const assetLink = document.createElement("a");
      assetLink.href = assetReviewUrl;
      assetLink.textContent = "Asset review gallery";
      links.append(jobLink, assetLink);
      card.appendChild(links);
    }

    if (status && status.missing_views && status.missing_views.length) {
      const missing = document.createElement("div");
      missing.className = "build-job-meta";
      missing.textContent = `Waiting for ${status.missing_views.join(", ")}`;
      card.appendChild(missing);
    }

    if (status && status.artifacts && status.artifacts.length) {
      const grid = document.createElement("div");
      grid.className = "chat-render-grid";
      for (const artifact of status.artifacts) {
        const link = document.createElement("a");
        link.href = artifact.url;
        link.className = "chat-render-thumb";
        const image = document.createElement("img");
        image.src = artifact.url;
        image.alt = `${artifact.view} render`;
        const label = document.createElement("span");
        label.textContent = artifact.view;
        link.append(image, label);
        grid.appendChild(link);
      }
      card.appendChild(grid);
    }

    const resolver = (result && result.resolver) || build.resolver || null;
    if (resolver) {
      const details = document.createElement("details");
      details.className = "assistant-json-details build-resolver-details";
      const summary = document.createElement("summary");
      summary.textContent = "Primitive Resolver JSON";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(resolver, null, 2);
      details.append(summary, pre);
      card.appendChild(details);
    }

    return card;
  }

  function renderTranscript() {
    els.transcript.innerHTML = "";
    if (!state.messages.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No messages yet.";
      els.transcript.appendChild(empty);
      els.createBuildJob.disabled = true;
      return;
    }
    for (const message of state.messages) {
      const row = document.createElement("article");
      row.className = `chat-message chat-message-${message.role}`;
      const role = document.createElement("div");
      role.className = "chat-message-role";
      role.textContent = message.role;
      const content = document.createElement("div");
      content.className = "chat-message-content";
      if (message.role === "assistant") {
        const details = document.createElement("details");
        details.className = "assistant-json-details";
        const summary = document.createElement("summary");
        summary.textContent = "Assistant JSON";
        const pre = document.createElement("pre");
        pre.textContent = message.content;
        details.append(summary, pre);
        content.appendChild(details);
      } else {
        content.textContent = message.content;
      }
      row.append(role, content);
      if (message.build) {
        const spacer = document.createElement("div");
        spacer.className = "chat-message-build-spacer";
        row.append(spacer, renderBuildCard(message.build));
      }
      els.transcript.appendChild(row);
    }
    els.transcript.scrollTop = els.transcript.scrollHeight;
    els.createBuildJob.disabled = !latestAssistantMessage();
  }

  function latestAssistantMessage() {
    for (let idx = state.messages.length - 1; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "assistant") return state.messages[idx];
    }
    return null;
  }

  function latestUserBefore(message) {
    const messageIndex = state.messages.indexOf(message);
    const startIndex = messageIndex >= 0 ? messageIndex - 1 : state.messages.length - 1;
    for (let idx = startIndex; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "user") return state.messages[idx];
    }
    return null;
  }

  function currentSettings() {
    return {
      model: els.model.value,
      preset_id: els.preset.value,
      temperature: Number(els.temperature.value),
      max_tokens: Number(els.maxTokens.value),
      review_views: selectedReviewViews(),
      auto_build: els.autoBuild.checked,
      stream: els.streamToggle.checked,
      system_prompt: els.systemPrompt.value,
    };
  }

  function selectedReviewViews() {
    return els.reviewViews.value === "standard" ? STANDARD_REVIEW_VIEWS : [];
  }

  function renderDebug() {
    els.debugPanel.hidden = !els.debugToggle.checked;
    state.raw.settings = currentSettings();
    els.debugOutput.textContent = JSON.stringify(state.raw, null, 2);
  }

  function applyPreset(presetId) {
    const preset = state.presets.find((item) => item.id === presetId);
    if (!preset) return;
    els.systemPrompt.value = preset.system_prompt;
    els.temperature.value = preset.temperature;
    els.maxTokens.value = preset.max_tokens;
    renderDebug();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (err) {
        throw new Error(`Invalid JSON from ${url}: ${text.slice(0, 240)}`);
      }
    }
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return payload;
  }

  async function loadControls() {
    clearError();
    const [modelPayload, presetPayload] = await Promise.all([
      fetchJson("/api/v1/studio-chat/models"),
      fetchJson("/api/v1/studio-chat/presets"),
    ]);

    state.models = modelPayload.models || [];
    state.presets = presetPayload.presets || [];

    els.model.innerHTML = "";
    const defaultModel = modelPayload.default_model || "";
    const modelNames = state.models.length ? state.models : [defaultModel].filter(Boolean);
    for (const model of modelNames) {
      els.model.appendChild(option(model, model));
    }
    if (defaultModel) els.model.value = defaultModel;

    els.preset.innerHTML = "";
    for (const preset of state.presets) {
      els.preset.appendChild(option(preset.id, preset.label));
    }
    const defaultPreset = state.presets.find((preset) => preset.id === "asset_builder_translator") || state.presets[0];
    if (defaultPreset) {
      els.preset.value = defaultPreset.id;
      applyPreset(defaultPreset.id);
    }

    setStatus(`Ollama: ${modelPayload.ollama_base_url}`);
    renderTranscript();
    renderDebug();
  }

  async function sendMessage(event) {
    event.preventDefault();
    const content = els.input.value.trim();
    if (!content) return;
    clearError();
    els.input.value = "";
    state.raw.build_job = null;
    state.raw.build_status = null;
    state.messages.push({ role: "user", content });
    renderTranscript();

    const payload = {
      model: els.model.value,
      preset_id: els.preset.value,
      system_prompt: els.systemPrompt.value,
      messages: state.messages,
      temperature: Number(els.temperature.value),
      max_tokens: Number(els.maxTokens.value),
      review_views: selectedReviewViews(),
      stream: els.streamToggle.checked,
    };
    state.raw.request = payload;
    state.raw.response = null;
    renderDebug();

    els.send.disabled = true;
    setStatus("Waiting for local model...");
    try {
      const response = await fetchJson("/api/v1/studio-chat/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.raw.response = response.raw;
      state.messages.push(response.message);
      setStatus(`Done: ${response.model}`);
      renderTranscript();
      renderDebug();
      if (els.autoBuild.checked) {
        await createBuildJob({ auto: true });
      }
    } catch (err) {
      showError("Local chat failed", err.message);
      setStatus("Error");
    } finally {
      els.send.disabled = false;
      renderTranscript();
      renderDebug();
      els.input.focus();
    }
  }

  function transcriptJson() {
    return {
      timestamp: new Date().toISOString(),
      settings: currentSettings(),
      messages: state.messages,
      raw: state.raw,
    };
  }

  async function pollBuildJobStatus(jobId, message) {
    try {
      const status = await fetchJson(`/api/v1/studio-chat/build-jobs/${jobId}/status`);
      if (message && message.build) {
        message.build.status = status;
      }
      state.raw.build_status = status;
      renderTranscript();
      renderDebug();
      if (status.gallery_ready) {
        stopPolling(jobId);
        setStatus("Review renders ready");
      } else if (status.build_job.status === "failed" || (status.review_job && status.review_job.status === "failed")) {
        stopPolling(jobId);
        setStatus("Render pipeline needs attention");
      } else {
        setStatus(`Rendering pipeline: ${status.phase}`);
      }
    } catch (err) {
      stopPolling(jobId);
      showError("Could not refresh build status", err.message);
    }
  }

  function startBuildPolling(jobId, message) {
    stopPolling(jobId);
    pollBuildJobStatus(jobId, message);
    state.pollTimers[jobId] = setInterval(() => pollBuildJobStatus(jobId, message), 3000);
  }

  async function createBuildJob(options) {
    const auto = options && options.auto;
    const assistant = latestAssistantMessage();
    const user = assistant ? latestUserBefore(assistant) : null;
    if (!assistant || !user) {
      showError("Build job needs a user request and assistant JSON");
      return;
    }
    clearError();
    els.createBuildJob.disabled = true;
    setStatus(auto ? "Auto-creating deterministic build job..." : "Creating deterministic build job...");
    try {
      assistant.build = {
        result: null,
        status: null,
        error: null,
      };
      renderTranscript();
      const result = await fetchJson("/api/v1/studio-chat/build-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: els.model.value,
          creative_request: user.content,
          assistant_response: assistant.content,
          messages: state.messages.slice(-12),
          review_views: selectedReviewViews(),
          priority: 0,
          policy: "run_anywhere",
        }),
      });
      state.raw.build_job = result;
      assistant.build.result = result;
      assistant.build.error = null;
      renderTranscript();
      setStatus(`Build job queued: ${result.job.id}`);
      startBuildPolling(result.job.id, assistant);
    } catch (err) {
      assistant.build = {
        result: null,
        status: null,
        error: err.message,
      };
      renderTranscript();
      showError("Could not create build job", err.message);
      setStatus("Build job failed");
    } finally {
      renderDebug();
      els.createBuildJob.disabled = !latestAssistantMessage();
    }
  }

  function download(filename, mimeType, content) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    download(
      `oeb-studio-chat-${Date.now()}.json`,
      "application/json",
      JSON.stringify(transcriptJson(), null, 2),
    );
  }

  function exportMarkdown() {
    const data = transcriptJson();
    const lines = [
      "# OEB Studio Chat Transcript",
      "",
      `Timestamp: ${data.timestamp}`,
      `Model: ${data.settings.model}`,
      `Preset: ${data.settings.preset_id}`,
      `Temperature: ${data.settings.temperature}`,
      `Max tokens: ${data.settings.max_tokens}`,
      "",
    ];
    for (const message of data.messages) {
      lines.push(`## ${message.role}`, "", message.content, "");
    }
    download(`oeb-studio-chat-${Date.now()}.md`, "text/markdown", lines.join("\n"));
  }

  els.composer.addEventListener("submit", sendMessage);
  els.preset.addEventListener("change", () => applyPreset(els.preset.value));
  els.debugToggle.addEventListener("change", renderDebug);
  els.autoBuild.addEventListener("change", renderDebug);
  els.streamToggle.addEventListener("change", renderDebug);
  els.temperature.addEventListener("input", renderDebug);
  els.maxTokens.addEventListener("input", renderDebug);
  els.reviewViews.addEventListener("change", renderDebug);
  els.model.addEventListener("change", renderDebug);
  els.systemPrompt.addEventListener("input", renderDebug);
  els.clear.addEventListener("click", () => {
    stopPolling();
    state.messages = [];
    state.raw.request = null;
    state.raw.response = null;
    state.raw.build_job = null;
    state.raw.build_status = null;
    clearError();
    renderTranscript();
    renderDebug();
    els.input.focus();
  });
  els.createBuildJob.addEventListener("click", createBuildJob);
  els.exportJson.addEventListener("click", exportJson);
  els.exportMd.addEventListener("click", exportMarkdown);

  loadControls().catch((err) => {
    showError("Could not initialize studio chat", err.message);
    setStatus("Ollama unavailable");
    renderTranscript();
  });
})();
