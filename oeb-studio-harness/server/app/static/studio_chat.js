(function () {
  const STANDARD_REVIEW_VIEWS = ["top", "bottom", "left", "right", "front", "rear", "action"];

  const state = {
    models: [],
    presets: [],
    messages: [],
    raw: {
      request: null,
      response: null,
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
    streamToggle: document.getElementById("stream-toggle"),
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

  function renderTranscript() {
    els.transcript.innerHTML = "";
    if (!state.messages.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No messages yet.";
      els.transcript.appendChild(empty);
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
      content.textContent = message.content;
      row.append(role, content);
      els.transcript.appendChild(row);
    }
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }

  function currentSettings() {
    return {
      model: els.model.value,
      preset_id: els.preset.value,
      temperature: Number(els.temperature.value),
      max_tokens: Number(els.maxTokens.value),
      review_views: selectedReviewViews(),
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
    if (state.presets.length) applyPreset(state.presets[0].id);

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
  els.streamToggle.addEventListener("change", renderDebug);
  els.temperature.addEventListener("input", renderDebug);
  els.maxTokens.addEventListener("input", renderDebug);
  els.reviewViews.addEventListener("change", renderDebug);
  els.model.addEventListener("change", renderDebug);
  els.systemPrompt.addEventListener("input", renderDebug);
  els.clear.addEventListener("click", () => {
    state.messages = [];
    state.raw.request = null;
    state.raw.response = null;
    clearError();
    renderTranscript();
    renderDebug();
    els.input.focus();
  });
  els.exportJson.addEventListener("click", exportJson);
  els.exportMd.addEventListener("click", exportMarkdown);

  loadControls().catch((err) => {
    showError("Could not initialize studio chat", err.message);
    setStatus("Ollama unavailable");
    renderTranscript();
  });
})();
