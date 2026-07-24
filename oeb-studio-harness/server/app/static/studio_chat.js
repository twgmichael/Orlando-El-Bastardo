(function () {
  const STANDARD_REVIEW_VIEWS = ["top", "bottom", "left", "right", "front", "rear", "action"];

  const state = {
    models: [],
    presets: [],
    threads: [],
    activeThreadId: null,
    messages: [],
    awaitingAssistant: false,
    pollTimers: {},
    lightbox: {
      artifacts: [],
      index: 0,
      lastFocus: null,
    },
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
    threadList: document.getElementById("thread-list"),
    newThread: document.getElementById("new-thread"),
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
    copyDebug: document.getElementById("copy-debug"),
    lightbox: document.getElementById("chat-lightbox"),
    lightboxImage: document.getElementById("chat-lightbox-image"),
    lightboxTitle: document.getElementById("chat-lightbox-title"),
    lightboxPrev: document.getElementById("chat-lightbox-prev"),
    lightboxNext: document.getElementById("chat-lightbox-next"),
    lightboxClose: document.getElementById("chat-lightbox-close"),
  };

  function option(value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    return node;
  }

  function setStatus(text) {
    state.raw.ui_status = text;
    if (els.status) {
      els.status.textContent = text;
    }
  }

  function messagePayload(message) {
    return {
      role: message.role,
      content: message.content,
    };
  }

  function ollamaMessages() {
    return state.messages
      .filter((message) => ["user", "assistant", "system"].includes(message.role))
      .map(messagePayload);
  }

  function threadSettingsPayload(title) {
    return {
      title: title || null,
      environment: "local",
      default_model: els.model.value || null,
      default_preset_id: els.preset.value || null,
      system_prompt: els.systemPrompt.value || null,
      review_views: selectedReviewViews(),
    };
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

  function parseAssistantJson(text) {
    if (!text || typeof text !== "string") return null;
    let source = text.trim();
    if (source.startsWith("```")) {
      source = source.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
    }
    try {
      return JSON.parse(source);
    } catch (_err) {
      const start = source.indexOf("{");
      const end = source.lastIndexOf("}");
      if (start < 0 || end <= start) return null;
      try {
        return JSON.parse(source.slice(start, end + 1));
      } catch (_innerErr) {
        return null;
      }
    }
  }

  function assistantControl(message) {
    const raw = message && message.raw ? message.raw : {};
    const parsed = raw.assistant_json || parseAssistantJson(message && message.content);
    if (!parsed || typeof parsed !== "object") return { parsed: null };
    const clarification = typeof parsed.clarification_question === "string"
      ? parsed.clarification_question.trim()
      : "";
    const escalation = typeof parsed.escalation_reason === "string"
      ? parsed.escalation_reason.trim()
      : "";
    return {
      parsed,
      clarification,
      escalation,
      blocksBuild: Boolean(clarification || escalation),
    };
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

  function buildIsActive(build) {
    if (!build || build.error) return false;
    const status = build.status || null;
    if (!status) return true;
    if (status.gallery_ready) return false;
    if (status.build_job && status.build_job.status === "failed") return false;
    if (status.review_job && status.review_job.status === "failed") return false;
    return true;
  }

  function lightboxArtifactLabel(artifact, index, total) {
    const view = artifact && artifact.view ? artifact.view.toUpperCase() : "RENDER";
    return `${view} ${index + 1}/${total}`;
  }

  function renderLightbox() {
    const artifact = state.lightbox.artifacts[state.lightbox.index];
    if (!artifact) return;
    els.lightboxImage.src = artifact.url;
    els.lightboxImage.alt = `${artifact.view || "review"} render`;
    els.lightboxTitle.textContent = lightboxArtifactLabel(
      artifact,
      state.lightbox.index,
      state.lightbox.artifacts.length,
    );
    const single = state.lightbox.artifacts.length < 2;
    els.lightboxPrev.disabled = single;
    els.lightboxNext.disabled = single;
  }

  function openLightbox(artifacts, index, sourceElement) {
    if (!artifacts || !artifacts.length) return;
    state.lightbox.artifacts = artifacts;
    state.lightbox.index = Math.max(0, Math.min(index, artifacts.length - 1));
    state.lightbox.lastFocus = sourceElement || document.activeElement;
    renderLightbox();
    els.lightbox.setAttribute("aria-hidden", "false");
    els.lightboxClose.focus();
  }

  function closeLightbox() {
    els.lightbox.setAttribute("aria-hidden", "true");
    els.lightboxImage.removeAttribute("src");
    const focusTarget = state.lightbox.lastFocus;
    state.lightbox.artifacts = [];
    state.lightbox.index = 0;
    state.lightbox.lastFocus = null;
    if (focusTarget && typeof focusTarget.focus === "function") {
      focusTarget.focus();
    }
  }

  function moveLightbox(delta) {
    const total = state.lightbox.artifacts.length;
    if (total < 2) return;
    state.lightbox.index = (state.lightbox.index + delta + total) % total;
    renderLightbox();
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
      for (const [index, artifact] of status.artifacts.entries()) {
        const link = document.createElement("button");
        link.type = "button";
        link.className = "chat-render-thumb";
        link.setAttribute("aria-label", `Open ${artifact.view} render`);
        link.addEventListener("click", () => openLightbox(status.artifacts, index, link));
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

  function renderAssistantActivityContent(content, labelText, indicatorClass, indicatorLabel) {
    content.classList.add("assistant-waiting-content");
    const label = document.createElement("span");
    label.className = "assistant-waiting-label";
    label.textContent = labelText;
    const indicator = document.createElement("div");
    indicator.className = indicatorClass;
    indicator.setAttribute("aria-label", indicatorLabel);
    indicator.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    content.append(label, indicator);
  }

  function renderAssistantWaitingRow() {
    const row = document.createElement("article");
    row.className = "chat-message chat-message-assistant chat-message-waiting";
    const role = document.createElement("div");
    role.className = "chat-message-role";
    role.textContent = "assistant";
    const content = document.createElement("div");
    content.className = "chat-message-content";
    renderAssistantActivityContent(content, "Waiting for local model", "assistant-thinking-bubbles", "Thinking");
    row.append(role, content);
    return row;
  }

  function renderTranscript() {
    els.transcript.innerHTML = "";
    if (!state.messages.length && !state.awaitingAssistant) {
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
        const control = assistantControl(message);
        const buildActive = message.build && buildIsActive(message.build);
        if (control.clarification || control.escalation) {
          const visible = document.createElement("p");
          visible.textContent = control.clarification || control.escalation;
          content.appendChild(visible);
        } else if (buildActive) {
          renderAssistantActivityContent(content, "Rendering pipeline", "build-stacked-blocks", "Building");
        } else if (control.parsed) {
          content.textContent = "";
        } else {
          content.textContent = message.content;
        }
      } else {
        content.textContent = message.content;
      }
      row.append(role, content);
      if (message.build && (message.build.result || message.build.status || message.build.error)) {
        const spacer = document.createElement("div");
        spacer.className = "chat-message-build-spacer";
        row.append(spacer, renderBuildCard(message.build));
      }
      els.transcript.appendChild(row);
    }
    if (state.awaitingAssistant) {
      els.transcript.appendChild(renderAssistantWaitingRow());
    }
    els.transcript.scrollTop = els.transcript.scrollHeight;
    els.createBuildJob.disabled = !latestBuildableAssistantMessage();
  }

  function latestAssistantMessage() {
    for (let idx = state.messages.length - 1; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "assistant") return state.messages[idx];
    }
    return null;
  }

  function latestBuildableAssistantMessage() {
    const assistant = latestAssistantMessage();
    if (!assistant) return null;
    return assistantControl(assistant).blocksBuild ? null : assistant;
  }

  function latestUserBefore(message) {
    const messageIndex = state.messages.indexOf(message);
    const startIndex = messageIndex >= 0 ? messageIndex - 1 : state.messages.length - 1;
    for (let idx = startIndex; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "user") return state.messages[idx];
    }
    return null;
  }

  function previousAssistantBefore(message) {
    const messageIndex = state.messages.indexOf(message);
    const startIndex = messageIndex >= 0 ? messageIndex - 1 : state.messages.length - 1;
    for (let idx = startIndex; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "assistant") return state.messages[idx];
    }
    return null;
  }

  function clarificationContextForUserAnswer(userMessage) {
    const priorAssistant = previousAssistantBefore(userMessage);
    if (!priorAssistant || !assistantControl(priorAssistant).blocksBuild) return null;
    const originalUser = latestUserBefore(priorAssistant);
    if (!originalUser) return null;
    return {
      assistant: priorAssistant,
      originalUser,
      effectiveCreativeRequest: [
        originalUser.content,
        `Clarification answer: ${userMessage.content}`,
      ].join("\n"),
    };
  }

  function creativeRequestForBuild(assistant, user) {
    if (user && user.raw && user.raw.effective_creative_request) {
      return user.raw.effective_creative_request;
    }
    const clarification = user ? clarificationContextForUserAnswer(user) : null;
    if (clarification) {
      return clarification.effectiveCreativeRequest;
    }
    return user ? user.content : "";
  }

  function currentSettings() {
    return {
      thread_id: state.activeThreadId,
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

  function selectRawDebugText() {
    const selection = window.getSelection();
    if (!selection) return;
    const range = document.createRange();
    range.selectNodeContents(els.debugOutput);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  async function copyRawDebug() {
    const text = els.debugOutput.textContent || "";
    if (!text) {
      setStatus("Raw debug is empty");
      return;
    }
    selectRawDebugText();
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        document.execCommand("copy");
      }
      els.copyDebug.classList.add("is-copied");
      setStatus("Raw debug copied");
      window.setTimeout(() => {
        els.copyDebug.classList.remove("is-copied");
      }, 1200);
    } catch (err) {
      showError("Could not copy raw debug", err.message);
    }
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

  function renderThreadOptions() {
    els.threadList.innerHTML = "";
    for (const thread of state.threads) {
      const label = thread.title || "Studio Chat Thread";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "thread-button";
      if (thread.id === state.activeThreadId) {
        button.classList.add("is-active");
        button.setAttribute("aria-current", "page");
      }
      button.dataset.threadId = thread.id;
      button.textContent = label;
      button.title = label;
      button.addEventListener("click", () => {
        if (thread.id === state.activeThreadId) return;
        loadThread(thread.id).catch((err) => {
          showError("Could not load thread", err.message);
        });
      });
      els.threadList.appendChild(button);
    }
  }

  function applyThreadSettings(thread) {
    if (!thread) return;
    if (thread.default_model && state.models.includes(thread.default_model)) {
      els.model.value = thread.default_model;
    }
    if (thread.default_preset_id && state.presets.some((preset) => preset.id === thread.default_preset_id)) {
      els.preset.value = thread.default_preset_id;
      if (thread.system_prompt) {
        els.systemPrompt.value = thread.system_prompt;
      } else {
        applyPreset(thread.default_preset_id);
      }
    } else if (thread.system_prompt) {
      els.systemPrompt.value = thread.system_prompt;
    }
  }

  function attachThreadEvents(events) {
    const byMessageId = new Map();
    for (const message of state.messages) {
      if (message.id) byMessageId.set(String(message.id), message);
    }
    for (const event of events || []) {
      const message = byMessageId.get(String(event.message_id || ""));
      if (!message) continue;
      if (event.event_type === "resolver") {
        message.resolver = event.payload && event.payload.resolver_output;
      }
      if (event.event_type === "build_created") {
        message.build = message.build || {};
        message.build.result = event.payload && event.payload.build_result;
        message.build.resolver = event.payload && event.payload.resolver_output;
        message.build.error = null;
      }
      if (event.event_type === "review_ready" || event.event_type === "failure") {
        message.build = message.build || {};
        message.build.status = event.payload && event.payload.build_status;
        if (event.event_type === "failure") {
          message.build.error = "Render pipeline needs attention";
        }
      }
    }
  }

  function resumeThreadPolling() {
    stopPolling();
    for (const message of state.messages) {
      const jobId = message.build && message.build.result && message.build.result.job && message.build.result.job.id;
      const status = message.build && message.build.status;
      if (!jobId) continue;
      if (status && (status.gallery_ready || status.build_job.status === "failed" || (status.review_job && status.review_job.status === "failed"))) {
        continue;
      }
      startBuildPolling(jobId, message);
    }
  }

  async function createThread(title) {
    const thread = await fetchJson("/api/v1/studio-chat/threads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(threadSettingsPayload(title)),
    });
    state.threads.unshift(thread);
    state.activeThreadId = thread.id;
    renderThreadOptions();
    return thread;
  }

  async function loadThread(threadId) {
    const detail = await fetchJson(`/api/v1/studio-chat/threads/${threadId}`);
    state.activeThreadId = detail.thread.id;
    applyThreadSettings(detail.thread);
    state.messages = (detail.messages || []).map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      raw: message.raw || {},
    }));
    attachThreadEvents(detail.events || []);
    renderThreadOptions();
    renderTranscript();
    renderDebug();
    resumeThreadPolling();
  }

  async function loadThreads() {
    const payload = await fetchJson("/api/v1/studio-chat/threads");
    state.threads = payload.threads || [];
    if (!state.threads.length) {
      await createThread();
    }
    renderThreadOptions();
    await loadThread(state.activeThreadId || state.threads[0].id);
  }

  async function ensureThread() {
    if (state.activeThreadId) return state.activeThreadId;
    const thread = await createThread();
    return thread.id;
  }

  async function saveThreadMessage(role, content, raw) {
    const threadId = await ensureThread();
    return fetchJson(`/api/v1/studio-chat/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content, raw: raw || {} }),
    });
  }

  async function patchActiveThreadSettings(extra) {
    if (!state.activeThreadId) return null;
    return fetchJson(`/api/v1/studio-chat/threads/${state.activeThreadId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        default_model: els.model.value || null,
        default_preset_id: els.preset.value || null,
        system_prompt: els.systemPrompt.value || null,
        review_views: selectedReviewViews(),
        ...(extra || {}),
      }),
    });
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
    await loadThreads();
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
    let userMessage = { role: "user", content };
    const pendingClarification = latestAssistantMessage();
    const pendingControl = assistantControl(pendingClarification);
    const originalRequest = pendingControl.blocksBuild ? latestUserBefore(pendingClarification) : null;
    const effectiveCreativeRequest = originalRequest
      ? [originalRequest.content, `Clarification answer: ${content}`].join("\n")
      : null;
    try {
      const savedUser = await saveThreadMessage("user", content, {
        settings: currentSettings(),
        clarification_response_to_message_id: pendingControl.blocksBuild && pendingClarification
          ? pendingClarification.id || null
          : null,
        original_request_message_id: originalRequest ? originalRequest.id || null : null,
        effective_creative_request: effectiveCreativeRequest,
      });
      userMessage = {
        id: savedUser.id,
        role: savedUser.role,
        content: savedUser.content,
        raw: savedUser.raw || {},
      };
      const updated = await patchActiveThreadSettings();
      if (updated) {
        const idx = state.threads.findIndex((thread) => thread.id === updated.id);
        if (idx >= 0) state.threads[idx] = updated;
        renderThreadOptions();
      }
    } catch (err) {
      showError("Could not save user message", err.message);
      setStatus("Thread save failed");
      return;
    }
    state.messages.push(userMessage);
    renderTranscript();

    const payload = {
      model: els.model.value,
      thread_id: state.activeThreadId,
      message_id: userMessage.id || null,
      preset_id: els.preset.value,
      system_prompt: els.systemPrompt.value,
      messages: ollamaMessages(),
      temperature: Number(els.temperature.value),
      max_tokens: Number(els.maxTokens.value),
      review_views: selectedReviewViews(),
      stream: els.streamToggle.checked,
    };
    state.raw.request = payload;
    state.raw.response = null;
    renderDebug();

    els.send.disabled = true;
    state.awaitingAssistant = true;
    setStatus("Waiting for local model...");
    renderTranscript();
    try {
      const response = await fetchJson("/api/v1/studio-chat/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.raw.response = response.raw;
      state.awaitingAssistant = false;
      const assistantJson = parseAssistantJson(response.message.content);
      const control = assistantControl({
        role: "assistant",
        content: response.message.content,
        raw: { assistant_json: assistantJson },
      });
      const savedAssistant = await saveThreadMessage(
        "assistant",
        control.clarification || control.escalation || response.message.content,
        {
          ollama: response.raw,
          original_content: response.message.content,
          assistant_json: assistantJson,
        },
      );
      const assistantMessage = {
        id: savedAssistant.id,
        role: savedAssistant.role,
        content: savedAssistant.content,
        raw: savedAssistant.raw || {},
      };
      state.messages.push(assistantMessage);
      setStatus(`Done: ${response.model}`);
      renderTranscript();
      renderDebug();
      if (control.blocksBuild) {
        setStatus(control.clarification ? "Clarification needed" : "Escalation needed");
      } else if (els.autoBuild.checked) {
        await createBuildJob({ auto: true });
      }
    } catch (err) {
      state.awaitingAssistant = false;
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
    const assistant = latestBuildableAssistantMessage();
    const user = assistant ? latestUserBefore(assistant) : null;
    if (!assistant || !user) {
      showError("Build job needs a user request and buildable assistant JSON");
      return;
    }
    clearError();
    els.createBuildJob.disabled = true;
    setStatus(auto ? "Auto-creating deterministic build job..." : "Creating deterministic build job...");
    try {
      const threadId = await ensureThread();
      const result = await fetchJson(`/api/v1/studio-chat/threads/${threadId}/build-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: els.model.value,
          thread_id: threadId,
          message_id: assistant.id || null,
          creative_request: creativeRequestForBuild(assistant, user),
          assistant_response: assistant.raw && assistant.raw.original_content
            ? assistant.raw.original_content
            : assistant.content,
          messages: ollamaMessages().slice(-12),
          review_views: selectedReviewViews(),
          priority: 0,
          policy: "run_anywhere",
        }),
      });
      state.raw.build_job = result;
      assistant.build = assistant.build || {};
      assistant.build.result = result;
      assistant.build.status = null;
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
      els.createBuildJob.disabled = !latestBuildableAssistantMessage();
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
  els.input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    els.composer.requestSubmit();
  });
  els.newThread.addEventListener("click", async () => {
    try {
      clearError();
      stopPolling();
      closeLightbox();
      const thread = await createThread();
      await loadThread(thread.id);
      setStatus("New thread ready");
      els.input.focus();
    } catch (err) {
      showError("Could not create thread", err.message);
    }
  });
  els.preset.addEventListener("change", () => applyPreset(els.preset.value));
  els.debugToggle.addEventListener("change", renderDebug);
  els.autoBuild.addEventListener("change", renderDebug);
  els.streamToggle.addEventListener("change", renderDebug);
  els.temperature.addEventListener("input", renderDebug);
  els.maxTokens.addEventListener("input", renderDebug);
  els.reviewViews.addEventListener("change", renderDebug);
  els.model.addEventListener("change", renderDebug);
  els.systemPrompt.addEventListener("input", renderDebug);
  els.clear.addEventListener("click", async () => {
    stopPolling();
    closeLightbox();
    try {
      const thread = await createThread();
      await loadThread(thread.id);
      state.raw.request = null;
      state.raw.response = null;
      state.raw.build_job = null;
      state.raw.build_status = null;
      clearError();
      renderTranscript();
      renderDebug();
      els.input.focus();
    } catch (err) {
      showError("Could not start a clear thread", err.message);
    }
  });
  els.createBuildJob.addEventListener("click", createBuildJob);
  els.exportJson.addEventListener("click", exportJson);
  els.exportMd.addEventListener("click", exportMarkdown);
  els.copyDebug.addEventListener("click", copyRawDebug);
  els.lightboxClose.addEventListener("click", closeLightbox);
  els.lightboxPrev.addEventListener("click", () => moveLightbox(-1));
  els.lightboxNext.addEventListener("click", () => moveLightbox(1));
  els.lightbox.addEventListener("click", (event) => {
    if (event.target && event.target.hasAttribute("data-lightbox-close")) {
      closeLightbox();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (els.lightbox.getAttribute("aria-hidden") === "true") return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeLightbox();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      moveLightbox(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      moveLightbox(1);
    }
  });

  loadControls().catch((err) => {
    showError("Could not initialize studio chat", err.message);
    setStatus("Ollama unavailable");
    renderTranscript();
  });
})();
