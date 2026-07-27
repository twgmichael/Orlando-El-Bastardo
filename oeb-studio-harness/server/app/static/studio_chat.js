(function () {
  const STANDARD_REVIEW_VIEWS = ["top", "bottom", "left", "right", "front", "rear", "action"];

  const state = {
    models: [],
    presets: [],
    threads: [],
    activeThreadId: null,
    assets: [],
    activeAssetId: null,
    assetRevisions: [],
    activeRevisionNumber: null,
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
      asset_edit: null,
      asset_revert: null,
      milestone: null,
      error: null,
      settings: {},
    },
  };

  const els = {
    threadList: document.getElementById("thread-list"),
    newThread: document.getElementById("new-thread"),
    activeAsset: document.getElementById("active-asset-select"),
    activeAssetMeta: document.getElementById("active-asset-meta"),
    activeRevision: document.getElementById("active-revision-select"),
    activeRevisionMeta: document.getElementById("active-revision-meta"),
    revertRevision: document.getElementById("revert-revision"),
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
    const originalContent = message.role === "assistant"
      && message.raw
      && typeof message.raw.original_content === "string"
      ? message.raw.original_content
      : null;
    return {
      role: message.role,
      content: originalContent || message.content,
    };
  }

  function ollamaMessages() {
    const messages = state.messages
      .filter((message) => ["user", "assistant", "system"].includes(message.role))
      .map(messagePayload);
    const deduped = [];
    for (const message of messages) {
      const previous = deduped[deduped.length - 1];
      if (previous && previous.role === message.role && previous.content === message.content) continue;
      deduped.push(message);
    }
    return deduped.slice(-12);
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

  function stripJsonComments(source) {
    let result = "";
    let inString = false;
    let escaped = false;
    let lineComment = false;
    let blockComment = false;
    for (let index = 0; index < source.length; index += 1) {
      const char = source[index];
      const next = source[index + 1];
      if (lineComment) {
        if (char === "\n") {
          lineComment = false;
          result += char;
        }
        continue;
      }
      if (blockComment) {
        if (char === "*" && next === "/") {
          blockComment = false;
          index += 1;
        }
        continue;
      }
      if (inString) {
        result += char;
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === "\"") {
          inString = false;
        }
        continue;
      }
      if (char === "\"") {
        inString = true;
        result += char;
      } else if (char === "/" && next === "/") {
        lineComment = true;
        index += 1;
      } else if (char === "/" && next === "*") {
        blockComment = true;
        index += 1;
      } else {
        result += char;
      }
    }
    return result;
  }

  function parseJsonCandidate(source) {
    const candidate = source.trim();
    if (!candidate) return null;
    try {
      const parsed = JSON.parse(candidate);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
    } catch (_err) {
      try {
        const normalized = stripJsonComments(candidate).replace(/,\s*([}\]])/g, "$1");
        const parsed = JSON.parse(normalized);
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
      } catch (_innerErr) {
        return null;
      }
    }
  }

  function balancedJsonSpan(source, start) {
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < source.length; index += 1) {
      const char = source[index];
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === "\"") {
          inString = false;
        }
        continue;
      }
      if (char === "\"") {
        inString = true;
      } else if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) return { start, end: index + 1 };
      }
    }
    return null;
  }

  function cleanAssistantProse(text) {
    return text
      .replace(
        /\s*(?:Here(?:'s| is)|Below is)[^.!?\n]*(?:JSON|structured request|structured command)[^.!?\n]*:\s*(?=\n|$)/gim,
        "",
      )
      .replace(/^\s*```(?:json)?\s*$/gim, "")
      .replace(/\n[ \t]+\n/g, "\n\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function parseAssistantResponse(text) {
    if (!text || typeof text !== "string") return { parsed: null, prose: "" };
    const source = text.trim();
    const fencedPattern = /```(?:json)?\s*([\s\S]*?)```/gi;
    let fencedMatch = fencedPattern.exec(source);
    while (fencedMatch) {
      const parsed = parseJsonCandidate(fencedMatch[1]);
      if (parsed) {
        const prose = cleanAssistantProse(
          `${source.slice(0, fencedMatch.index)}\n${source.slice(fencedPattern.lastIndex)}`,
        );
        return { parsed, prose };
      }
      fencedMatch = fencedPattern.exec(source);
    }

    const whole = parseJsonCandidate(source);
    if (whole) return { parsed: whole, prose: "" };

    for (let start = source.indexOf("{"); start >= 0; start = source.indexOf("{", start + 1)) {
      const span = balancedJsonSpan(source, start);
      if (!span) continue;
      const parsed = parseJsonCandidate(source.slice(span.start, span.end));
      if (parsed) {
        const prose = cleanAssistantProse(
          `${source.slice(0, span.start)}\n${source.slice(span.end)}`,
        );
        return { parsed, prose };
      }
    }
    return { parsed: null, prose: cleanAssistantProse(source) };
  }

  function parseAssistantJson(text) {
    return parseAssistantResponse(text).parsed;
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

  function assistantVisibleText(message, control) {
    if (control.clarification || control.escalation) {
      return control.clarification || control.escalation;
    }
    const raw = message && message.raw ? message.raw : {};
    if (typeof raw.assistant_prose === "string" && raw.assistant_prose.trim()) {
      return raw.assistant_prose.trim();
    }
    const original = typeof raw.original_content === "string"
      ? raw.original_content
      : message && message.content;
    const extracted = parseAssistantResponse(original).prose;
    if (extracted) return extracted;
    return original !== (message && message.content) ? message.content.trim() : "";
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
    if (status.review_job && status.review_job.status === "completed") return false;
    return true;
  }

  function milestoneCommand(content) {
    const text = (content || "").trim();
    const match = text.match(/^(?:save(?:\s+this)?\s+milestone|snapshot\s+progress)(?:\s+as\s+(.+))?\.?$/i);
    if (!match) return null;
    const label = match[1] ? match[1].trim().replace(/\.$/, "") : "";
    return { label: label || null };
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
      missing.textContent = `Missing registered views: ${status.missing_views.join(", ")}`;
      card.appendChild(missing);
    }

    if (status && status.missing_uploaded_views && status.missing_uploaded_views.length) {
      const uploaded = document.createElement("div");
      uploaded.className = "build-job-meta";
      uploaded.textContent = `Missing uploaded views: ${status.missing_uploaded_views.join(", ")}`;
      card.appendChild(uploaded);
    }

    if (status && status.diagnostics && status.diagnostics.length) {
      const details = document.createElement("details");
      details.className = "assistant-json-details build-resolver-details";
      const summary = document.createElement("summary");
      summary.textContent = "Review diagnostics";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(status.diagnostics, null, 2);
      details.append(summary, pre);
      card.appendChild(details);
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

  function renderMilestoneCard(milestone) {
    const card = document.createElement("div");
    card.className = "chat-build-card chat-milestone-card";

    const eyebrow = document.createElement("div");
    eyebrow.className = "chat-build-eyebrow";
    eyebrow.textContent = "Milestone saved";
    card.appendChild(eyebrow);

    const title = document.createElement("strong");
    const label = milestone.label || milestone.asset_id || "Studio Chat milestone";
    title.textContent = label;
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "build-job-meta";
    const savedViews = (milestone.renders || []).map((render) => render.view);
    const missingViews = milestone.missing_views || [];
    meta.textContent = [
      milestone.asset_id ? `Asset ${milestone.asset_id}` : "Thread snapshot",
      savedViews.length ? `saved ${savedViews.join(", ")}` : "no renders copied",
      missingViews.length ? `missing ${missingViews.join(", ")}` : "",
    ].filter(Boolean).join("; ");
    card.appendChild(meta);

    const links = document.createElement("div");
    links.className = "build-job-links";
    const manifest = (milestone.files || []).find((file) => file.filename === "milestone.json");
    const readme = (milestone.files || []).find((file) => file.filename === "README.md");
    const detailLink = document.createElement("a");
    detailLink.href = `/api/v1/studio-chat/milestones/${milestone.id}`;
    detailLink.textContent = "Milestone JSON";
    links.appendChild(detailLink);
    if (manifest && manifest.url) {
      const manifestLink = document.createElement("a");
      manifestLink.href = manifest.url;
      manifestLink.textContent = "Manifest file";
      links.appendChild(manifestLink);
    }
    if (readme && readme.url) {
      const readmeLink = document.createElement("a");
      readmeLink.href = readme.url;
      readmeLink.textContent = "README";
      links.appendChild(readmeLink);
    }
    card.appendChild(links);

    if (milestone.renders && milestone.renders.length) {
      const grid = document.createElement("div");
      grid.className = "chat-render-grid";
      for (const [index, render] of milestone.renders.entries()) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "chat-render-thumb";
        button.setAttribute("aria-label", `Open saved ${render.view} render`);
        button.addEventListener("click", () => openLightbox(milestone.renders, index, button));
        const image = document.createElement("img");
        image.src = render.url;
        image.alt = `${render.view} milestone render`;
        const span = document.createElement("span");
        span.textContent = render.view;
        button.append(image, span);
        grid.appendChild(button);
      }
      card.appendChild(grid);
    }

    return card;
  }

  function artifactsForRevision(assetId, revisionNumber) {
    for (const message of state.messages) {
      const events = message.revisionEvents || [];
      const hasRevision = events.some((event) => {
        const payload = event.payload || {};
        const eventAsset = payload.asset || {};
        const revision = payload.revision || {};
        return eventAsset.asset_id === assetId && revision.revision === revisionNumber;
      });
      const artifacts = message.build && message.build.status && message.build.status.artifacts;
      if (hasRevision && artifacts && artifacts.length) return artifacts;
    }
    return [];
  }

  function renderRevisionArtifactStrip(label, artifacts) {
    const section = document.createElement("div");
    section.className = "revision-artifact-strip";
    const heading = document.createElement("div");
    heading.className = "build-job-meta";
    heading.textContent = label;
    section.appendChild(heading);
    const grid = document.createElement("div");
    grid.className = "revision-artifact-grid";
    for (const [index, artifact] of artifacts.slice(0, 4).entries()) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-render-thumb revision-render-thumb";
      button.setAttribute("aria-label", `Open ${label} ${artifact.view} render`);
      button.addEventListener("click", () => openLightbox(artifacts, index, button));
      const image = document.createElement("img");
      image.src = artifact.url;
      image.alt = `${label} ${artifact.view} render`;
      const span = document.createElement("span");
      span.textContent = artifact.view;
      button.append(image, span);
      grid.appendChild(button);
    }
    section.appendChild(grid);
    return section;
  }

  function renderRevisionCard(event) {
    const card = document.createElement("div");
    card.className = "chat-build-card chat-revision-card";
    const payload = event.payload || {};
    const asset = payload.asset || null;
    const revision = payload.revision || null;
    const eyebrow = document.createElement("div");
    eyebrow.className = "chat-build-eyebrow";
    eyebrow.textContent = event.event_type === "asset_reverted" ? "Revision reverted" : "Asset edit";
    card.appendChild(eyebrow);
    const title = document.createElement("strong");
    title.textContent = asset
      ? `${asset.asset_id} revision ${asset.current_revision}`
      : "Asset revision";
    card.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "build-job-meta";
    meta.textContent = revision
      ? `Before r${revision.parent_revision || "none"}; after r${revision.revision}; status ${revision.status}`
      : "Revision state recorded";
    card.appendChild(meta);
    if (payload.job && payload.review_url) {
      const links = document.createElement("div");
      links.className = "build-job-links";
      const jobLink = document.createElement("a");
      jobLink.href = payload.review_url;
      jobLink.textContent = "Edit job";
      links.appendChild(jobLink);
      if (payload.asset_review_url) {
        const assetLink = document.createElement("a");
        assetLink.href = payload.asset_review_url;
        assetLink.textContent = "Asset review gallery";
        links.appendChild(assetLink);
      }
      card.appendChild(links);
    }
    if (payload.diagnostics && payload.diagnostics.length) {
      const details = document.createElement("details");
      details.className = "assistant-json-details build-resolver-details";
      const summary = document.createElement("summary");
      summary.textContent = "Edit diagnostics";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(payload.diagnostics, null, 2);
      details.append(summary, pre);
      card.appendChild(details);
    }
    if (asset && revision) {
      const beforeArtifacts = revision.parent_revision
        ? artifactsForRevision(asset.asset_id, revision.parent_revision)
        : [];
      const afterArtifacts = artifactsForRevision(asset.asset_id, revision.revision);
      if (beforeArtifacts.length || afterArtifacts.length) {
        const pair = document.createElement("div");
        pair.className = "revision-render-pair";
        if (beforeArtifacts.length) {
          pair.appendChild(renderRevisionArtifactStrip(`Before r${revision.parent_revision}`, beforeArtifacts));
        }
        if (afterArtifacts.length) {
          pair.appendChild(renderRevisionArtifactStrip(`After r${revision.revision}`, afterArtifacts));
        }
        card.appendChild(pair);
      }
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
        const visibleText = assistantVisibleText(message, control);
        if (visibleText) {
          const visible = document.createElement("p");
          visible.textContent = visibleText;
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
      if (message.milestone) {
        const spacer = document.createElement("div");
        spacer.className = "chat-message-build-spacer";
        row.append(spacer, renderMilestoneCard(message.milestone));
      }
      for (const event of message.revisionEvents || []) {
        const spacer = document.createElement("div");
        spacer.className = "chat-message-build-spacer";
        row.append(spacer, renderRevisionCard(event));
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

  function systemPromptWithActiveAsset() {
    const asset = activeAsset();
    if (!asset) return els.systemPrompt.value;
    const stateJson = asset.state_json && typeof asset.state_json === "object"
      ? asset.state_json
      : {};
    const intent = stateJson.asset_intent && typeof stateJson.asset_intent === "object"
      ? stateJson.asset_intent
      : {};
    const graph = stateJson.semantic_graph && typeof stateJson.semantic_graph === "object"
      ? stateJson.semantic_graph
      : null;
    const graphParts = graph && Array.isArray(graph.parts) ? graph.parts : [];
    const compactState = {
      canonical_id: stateJson.canonical_id || asset.asset_id,
      name: stateJson.name || intent.name || asset.asset_id,
      kind: stateJson.kind || intent.kind || null,
      description: stateJson.description || intent.description || null,
      parts: graphParts.length
        ? graphParts.map((part) => ({
          id: part.id || null,
          type: part.geometry && part.geometry.type ? part.geometry.type : null,
          material: part.material || null,
          role: part.role || null,
          transform: part.transform || {},
        }))
        : Array.isArray(intent.objects)
        ? intent.objects.map((part) => ({
          id: part.id || part.label || null,
          type: part.type || null,
          material: part.material || null,
          placement: part.placement || null,
          description: part.description || null,
        }))
        : [],
      relationships: graph && Array.isArray(graph.relationships)
        ? graph.relationships
        : (Array.isArray(intent.relationships) ? intent.relationships : []),
      attachments: graph && Array.isArray(graph.attachments) ? graph.attachments : [],
      constraints: graph && Array.isArray(graph.constraints) ? graph.constraints : [],
      primitives: Array.isArray(stateJson.primitives)
        ? stateJson.primitives.map((primitive) => ({
          id: primitive.id || primitive.label || null,
          type: primitive.type || null,
          material: primitive.material || null,
          transform: primitive.transform || {},
          params: primitive.params || {},
        }))
        : [],
    };
    const context = {
      active_asset: {
        asset_id: asset.asset_id,
        current_revision: asset.current_revision,
        base_builder: asset.base_builder,
        state_json: compactState,
      },
      edit_contract: {
        return_field: "asset_edit_request",
        required: ["operation", "base_revision"],
        optional: ["target", "view", "semantic_direction", "amount", "preserve", "edit_delta"],
        operations: ["add", "remove", "replace", "move", "rotate", "attach", "detach", "recolor", "resize", "group", "ungroup", "undo"],
        note: "For follow-up edits to the active asset, return asset_edit_request instead of a fresh build.",
        examples: {
          replace_part_type: {
            operation: "replace",
            target: "<part_id>",
            preserve: ["material", "attachments"],
            edit_delta: { type: "<new_type>" },
          },
          remove_part: {
            operation: "remove",
            target: "<part_id>",
          },
          center_objects: {
            operation: "move",
            target: "whole_asset",
            edit_delta: { mode: "align_centers_xy" },
            preserve: ["vertical_heights", "materials", "relationships"],
          },
          move_part_on_top_of_another: {
            operation: "move",
            target: "<moving_part_id>",
            edit_delta: {
              relation: "on_top_of",
              reference_id: "<stationary_part_id>",
            },
          },
          resize_part_to_match_width: {
            operation: "resize",
            target: "<resized_part_id>",
            edit_delta: {
              mode: "match_reference_width",
              reference_id: "<stationary_reference_id>",
              proportional: true,
            },
          },
          cut_half_sphere: {
            operation: "replace",
            target: "<sphere_id>",
            edit_delta: {
              mode: "geometry_modifier",
              shape_modifiers: ["half", "flat"],
              hemisphere_direction: "up",
            },
          },
        },
      },
    };
    return [
      els.systemPrompt.value,
      "",
      "Active OEB asset context:",
      JSON.stringify(context, null, 2),
    ].join("\n");
  }

  function selectedReviewViews() {
    return els.reviewViews.value === "standard" ? STANDARD_REVIEW_VIEWS : [];
  }

  function activeAsset() {
    return state.assets.find((asset) => asset.asset_id === state.activeAssetId) || null;
  }

  function renderActiveAsset() {
    if (!els.activeAsset) return;
    els.activeAsset.innerHTML = "";
    els.activeAsset.appendChild(option("", "No asset selected"));
    for (const asset of state.assets) {
      const label = `${asset.asset_id} r${asset.current_revision}`;
      els.activeAsset.appendChild(option(asset.asset_id, label));
    }
    if (state.activeAssetId && state.assets.some((asset) => asset.asset_id === state.activeAssetId)) {
      els.activeAsset.value = state.activeAssetId;
    } else if (state.assets.length) {
      state.activeAssetId = state.assets[0].asset_id;
      els.activeAsset.value = state.activeAssetId;
    } else {
      state.activeAssetId = null;
      els.activeAsset.value = "";
    }
    const asset = activeAsset();
    els.activeAssetMeta.textContent = asset
      ? `Revision ${asset.current_revision}; builder ${asset.base_builder || "unknown"}`
      : "No asset state yet.";
  }

  function activeRevision() {
    return state.assetRevisions.find((revision) => revision.revision === state.activeRevisionNumber) || null;
  }

  function renderActiveRevision() {
    if (!els.activeRevision) return;
    const asset = activeAsset();
    els.activeRevision.innerHTML = "";
    if (!asset || !state.assetRevisions.length) {
      els.activeRevision.appendChild(option("", "No revisions"));
      els.activeRevision.disabled = true;
      els.revertRevision.disabled = true;
      els.activeRevisionMeta.textContent = "No revision selected.";
      return;
    }
    const revisions = [...state.assetRevisions].sort((a, b) => b.revision - a.revision);
    for (const revision of revisions) {
      const label = `r${revision.revision} ${revision.status}`;
      els.activeRevision.appendChild(option(String(revision.revision), label));
    }
    if (!state.activeRevisionNumber || !state.assetRevisions.some((item) => item.revision === state.activeRevisionNumber)) {
      state.activeRevisionNumber = asset.current_revision;
    }
    els.activeRevision.value = String(state.activeRevisionNumber);
    els.activeRevision.disabled = false;
    const revision = activeRevision();
    const canRevert = Boolean(revision && revision.revision !== asset.current_revision);
    els.revertRevision.disabled = !canRevert;
    els.activeRevisionMeta.textContent = revision
      ? `r${revision.revision}; parent ${revision.parent_revision || "none"}; ${revision.status}`
      : "No revision selected.";
  }

  function renderDebug() {
    els.debugPanel.hidden = !els.debugToggle.checked;
    state.raw.settings = {
      ...currentSettings(),
      active_asset: activeAsset(),
      active_revision: activeRevision(),
    };
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
        if (!response.ok) {
          throw new Error(`HTTP ${response.status} ${response.statusText}: ${text.slice(0, 240)}`);
        }
        throw new Error(`Invalid JSON from ${url}: ${text.slice(0, 240)}`);
      }
    }
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : response.statusText;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = response.status;
      error.detail = detail;
      throw error;
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
      if (event.event_type === "review_ready" || event.event_type === "failure" || event.event_type === "review_attention") {
        message.build = message.build || {};
        message.build.status = event.payload && event.payload.build_status;
        if (event.event_type === "failure") {
          message.build.error = "Render pipeline needs attention";
        }
      }
      if (event.event_type === "milestone_created") {
        message.milestone = event.payload && event.payload.milestone;
      }
      if (["asset_revision_created", "asset_edit_recorded", "asset_edit_compiled", "asset_reverted"].includes(event.event_type)) {
        message.revisionEvents = message.revisionEvents || [];
        message.revisionEvents.push(event);
      }
    }
  }

  function resumeThreadPolling() {
    stopPolling();
    for (const message of state.messages) {
      const jobId = message.build && message.build.result && message.build.result.job && message.build.result.job.id;
      const status = message.build && message.build.status;
      if (!jobId) continue;
      if (status && (
        status.gallery_ready
        || status.build_job.status === "failed"
        || (status.review_job && ["completed", "failed"].includes(status.review_job.status))
      )) {
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
    state.assets = [];
    state.activeAssetId = null;
    state.assetRevisions = [];
    state.activeRevisionNumber = null;
    renderActiveAsset();
    renderActiveRevision();
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
      milestone: message.raw && message.raw.milestone ? message.raw.milestone : null,
    }));
    attachThreadEvents(detail.events || []);
    await loadThreadAssets(detail.thread.id);
    renderThreadOptions();
    renderTranscript();
    renderDebug();
    resumeThreadPolling();
  }

  async function loadThreadAssets(threadId) {
    const payload = await fetchJson(`/api/v1/studio-chat/threads/${threadId}/assets`);
    state.assets = payload.assets || [];
    if (!state.assets.some((asset) => asset.asset_id === state.activeAssetId)) {
      state.activeAssetId = state.assets.length ? state.assets[0].asset_id : null;
    }
    renderActiveAsset();
    await loadActiveAssetRevisions();
  }

  async function loadActiveAssetRevisions() {
    const asset = activeAsset();
    if (!asset) {
      state.assetRevisions = [];
      state.activeRevisionNumber = null;
      renderActiveRevision();
      return;
    }
    const payload = await fetchJson(
      `/api/v1/studio-chat/assets/${asset.asset_id}/revisions?thread_id=${state.activeThreadId}`,
    );
    state.assetRevisions = payload.revisions || [];
    if (!state.assetRevisions.some((revision) => revision.revision === state.activeRevisionNumber)) {
      state.activeRevisionNumber = asset.current_revision;
    }
    renderActiveRevision();
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
    state.raw.asset_edit = null;
    state.raw.asset_revert = null;
    state.raw.milestone = null;
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

    const milestoneIntent = milestoneCommand(content);
    if (milestoneIntent) {
      await createMilestone(userMessage, milestoneIntent.label);
      return;
    }

    const payload = {
      model: els.model.value,
      thread_id: state.activeThreadId,
      message_id: userMessage.id || null,
      preset_id: els.preset.value,
      system_prompt: systemPromptWithActiveAsset(),
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
      const assistantResponse = parseAssistantResponse(response.message.content);
      const assistantJson = assistantResponse.parsed;
      const control = assistantControl({
        role: "assistant",
        content: response.message.content,
        raw: { assistant_json: assistantJson },
      });
      const visibleContent = control.clarification
        || control.escalation
        || assistantResponse.prose
        || "I’ve prepared that asset change.";
      const savedAssistant = await saveThreadMessage(
        "assistant",
        visibleContent,
        {
          ollama: response.raw,
          original_content: response.message.content,
          assistant_prose: assistantResponse.prose,
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
        const edited = await createAssetEdit(assistantMessage, assistantJson);
        if (!edited) {
          if (activeAsset()) {
            await repairActiveAssetEdit(assistantMessage, assistantJson);
          } else {
            await createBuildJob({ auto: true });
          }
        }
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
      } else if (status.review_job && status.review_job.status === "completed") {
        stopPolling(jobId);
        setStatus(status.missing_views && status.missing_views.length
          ? "Review renders need attention"
          : "Review renders available");
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

  function latestBuildJobId() {
    for (let idx = state.messages.length - 1; idx >= 0; idx -= 1) {
      const build = state.messages[idx].build;
      const jobId = build && build.result && build.result.job && build.result.job.id;
      if (jobId) return jobId;
    }
    return null;
  }

  function editRequestFromAssistant(assistantJson) {
    if (!assistantJson || typeof assistantJson !== "object") return null;
    const source = assistantJson.asset_edit_request || assistantJson.edit_delta || null;
    if (!source || typeof source !== "object") return null;
    const asset = activeAsset();
    if (!asset) return null;
    return {
      thread_id: state.activeThreadId,
      message_id: null,
      base_revision: Number(asset.current_revision),
      target: source.target || null,
      operation: source.operation || "record_intent",
      view: source.view || null,
      semantic_direction: source.semantic_direction || source.direction || null,
      amount: typeof source.amount === "number" ? source.amount : null,
      preserve: Array.isArray(source.preserve) ? source.preserve : [],
      edit_delta: source.edit_delta && typeof source.edit_delta === "object" ? source.edit_delta : source,
    };
  }

  function latestUserIntentText(assistant) {
    return (latestUserBefore(assistant)?.content || "").trim().toLowerCase();
  }

  function editConflictsWithUserIntent(request, assistant) {
    const prompt = latestUserIntentText(assistant);
    const operation = (request.operation || "").toLowerCase();
    if (/\b(add|create|append|attach|put)\b/.test(prompt) && ["replace_with", "replace", "remove", "delete"].includes(operation)) {
      return "add";
    }
    if (/\b(remove|delete)\b/.test(prompt) && ["add", "add_part", "create_part", "append_part", "replace_with", "replace"].includes(operation)) {
      return "remove";
    }
    if (/\b(replace|swap|change)\b/.test(prompt) && ["add", "add_part", "create_part", "append_part", "remove", "delete"].includes(operation)) {
      return "replace";
    }
    return null;
  }

  async function createAssetEdit(assistant, assistantJson) {
    const asset = activeAsset();
    const request = editRequestFromAssistant(assistantJson);
    if (!asset || !request) return false;
    request.edit_delta = {
      ...(request.edit_delta || {}),
      requested_intent: latestUserIntentText(assistant),
    };
    const conflict = editConflictsWithUserIntent(request, assistant);
    if (conflict && !assistant.additiveIntentRepairAttempted) {
      assistant.additiveIntentRepairAttempted = true;
      return repairActiveAssetEdit(assistant, assistantJson, conflict);
    }
    request.message_id = assistant.id || null;
    setStatus("Compiling asset edit...");
    try {
      const result = await fetchJson(`/api/v1/studio-chat/assets/${asset.asset_id}/edits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      state.raw.asset_edit = result;
      const idx = state.assets.findIndex((item) => item.asset_id === result.asset.asset_id);
      if (idx >= 0) {
        state.assets[idx] = result.asset;
      } else {
        state.assets.unshift(result.asset);
      }
      state.activeAssetId = result.asset.asset_id;
      renderActiveAsset();
      await loadActiveAssetRevisions();
      assistant.revisionEvents = assistant.revisionEvents || [];
      assistant.revisionEvents.push({
        event_type: result.job_created ? "asset_edit_compiled" : "asset_edit_recorded",
        payload: {
          asset: result.asset,
          revision: result.revision,
          job: result.job,
          review_url: result.review_url,
          asset_review_url: result.asset_review_url,
          diagnostics: result.diagnostics,
        },
      });
      if (result.job && result.job.id) {
        assistant.build = assistant.build || {};
        assistant.build.result = {
          job: result.job,
          review_url: result.review_url,
          asset_review_url: result.asset_review_url,
          spec: result.asset.state_json,
        };
        assistant.build.status = null;
        assistant.build.error = null;
        startBuildPolling(result.job.id, assistant);
      }
      setStatus(result.job_created ? `Edit job queued: ${result.job.id}` : "Edit recorded");
      return true;
    } catch (err) {
      if (err.status === 422 && !assistant.compilerRepairAttempted) {
        assistant.compilerRepairAttempted = true;
        return repairActiveAssetEdit(assistant, assistantJson, "compiler_rejected");
      }
      showError("Could not create asset edit", err.message);
      setStatus("Asset edit failed");
      return true;
    } finally {
      renderTranscript();
      renderDebug();
    }
  }

  async function repairActiveAssetEdit(assistant, assistantJson, repairIntent) {
    const asset = activeAsset();
    if (!asset) return false;
    setStatus("Repairing active asset edit...");
    const repairPayload = {
      model: els.model.value,
      thread_id: state.activeThreadId,
      message_id: assistant.id || null,
      preset_id: "asset_edit_translator",
      system_prompt: [
        systemPromptWithActiveAsset(),
        "EDIT REPAIR OVERRIDE:",
        "The active asset already exists. Do not return build_asset or asset_intent.",
        "Return asset_edit_request only. Use only add, remove, replace, move, rotate, attach, detach, recolor, resize, group, ungroup, undo.",
        "Never emit align_centers, center_group, set_geometry_modifier, replace_with, add_part, or proportional_scale.",
        "For 'center/middle the objects', use operation move, target whole_asset, edit_delta {\"mode\":\"align_centers_xy\"}.",
        "For 'move X to the top of Y', use operation move, target X, edit_delta {\"relation\":\"on_top_of\",\"reference_id\":\"Y\"}.",
        "The target is the moving part and reference_id is stationary. Use exact ids from the active semantic graph.",
        "For 'resize/reduce X proportionally to match Y width', use operation resize, target X, edit_delta {\"mode\":\"match_reference_width\",\"reference_id\":\"Y\",\"proportional\":true}.",
        "Do not guess a numeric factor for match requests; the compiler measures both parts.",
        "For 'replace X with Y', use operation replace, target X, edit_delta {\"type\": Y}.",
        "For 'remove/delete X', use operation remove, target X.",
        "For 'add/create X below/above/near Y', use operation add, target Y, semantic_direction below/above/near, edit_delta {\"type\": X}.",
        repairIntent ? `The latest user prompt intent is ${repairIntent}; preserve that intent exactly.` : "",
        "This is one repair attempt; do not explain or write Blender code.",
      ].join("\n"),
      messages: [
        { role: "user", content: latestUserBefore(assistant)?.content || "" },
        {
          role: "assistant",
          content: JSON.stringify(assistantJson || {}),
        },
        {
          role: "user",
          content: "Repair the previous response as an edit to the active asset. Return asset_edit_request only.",
        },
      ],
      temperature: Math.min(Number(els.temperature.value), 0.1),
      max_tokens: Number(els.maxTokens.value),
      review_views: selectedReviewViews(),
      stream: false,
    };
    state.raw.repair_request = repairPayload;
    try {
      const response = await fetchJson("/api/v1/studio-chat/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(repairPayload),
      });
      const repairedResponse = parseAssistantResponse(response.message.content);
      const repairedJson = repairedResponse.parsed;
      state.raw.repair_response = response.raw;
      assistant.raw = assistant.raw || {};
      assistant.raw.edit_repair = {
        response: response.raw,
        prose: repairedResponse.prose,
        original_json: assistantJson,
        repaired_json: repairedJson,
      };
      renderDebug();
      const edited = await createAssetEdit(assistant, repairedJson);
      if (!edited) {
        showError("Active asset edit was not compiler-ready; no new build was submitted.");
        setStatus("Edit needs clarification");
      }
      return true;
    } catch (err) {
      showError("Active asset edit could not be repaired; no new build was submitted.", err.message);
      setStatus("Edit repair failed");
      return true;
    }
  }

  async function revertActiveAssetToRevision() {
    const asset = activeAsset();
    const revision = activeRevision();
    if (!asset || !revision || revision.revision === asset.current_revision) return;
    clearError();
    const content = `Revert ${asset.asset_id} to revision ${revision.revision}.`;
    let userMessage = { role: "user", content };
    try {
      const savedUser = await saveThreadMessage("user", content, {
        settings: currentSettings(),
        active_asset: asset,
        target_revision: revision.revision,
      });
      userMessage = {
        id: savedUser.id,
        role: savedUser.role,
        content: savedUser.content,
        raw: savedUser.raw || {},
      };
      state.messages.push(userMessage);
      renderTranscript();
      setStatus("Reverting asset revision...");
      const result = await fetchJson(`/api/v1/studio-chat/assets/${asset.asset_id}/revert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: state.activeThreadId,
          message_id: userMessage.id || null,
          target_revision: revision.revision,
          base_revision: asset.current_revision,
        }),
      });
      state.raw.asset_revert = result;
      const idx = state.assets.findIndex((item) => item.asset_id === result.asset.asset_id);
      if (idx >= 0) {
        state.assets[idx] = result.asset;
      } else {
        state.assets.unshift(result.asset);
      }
      state.activeAssetId = result.asset.asset_id;
      state.activeRevisionNumber = result.asset.current_revision;
      userMessage.revisionEvents = userMessage.revisionEvents || [];
      userMessage.revisionEvents.push({
        event_type: "asset_reverted",
        payload: {
          asset: result.asset,
          revision: result.revision,
          reverted_to_revision: result.reverted_to_revision,
        },
      });
      renderActiveAsset();
      await loadActiveAssetRevisions();
      setStatus(`Reverted to revision ${result.reverted_to_revision}`);
    } catch (err) {
      showError("Could not revert asset revision", err.message);
      setStatus("Revert failed");
    } finally {
      renderTranscript();
      renderDebug();
      els.input.focus();
    }
  }

  async function createMilestone(userMessage, label) {
    els.send.disabled = true;
    setStatus("Saving milestone...");
    try {
      const threadId = await ensureThread();
      const milestone = await fetchJson(`/api/v1/studio-chat/threads/${threadId}/milestones`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          message_id: userMessage.id || null,
          build_job_id: latestBuildJobId(),
          label,
        }),
      });
      state.raw.milestone = milestone;
      userMessage.milestone = milestone;
      setStatus("Milestone saved");
    } catch (err) {
      showError("Could not save milestone", err.message);
      setStatus("Milestone failed");
    } finally {
      els.send.disabled = false;
      state.awaitingAssistant = false;
      renderTranscript();
      renderDebug();
      els.input.focus();
    }
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
      if (result.asset) {
        const idx = state.assets.findIndex((asset) => asset.asset_id === result.asset.asset_id);
        if (idx >= 0) {
          state.assets[idx] = result.asset;
        } else {
          state.assets.unshift(result.asset);
        }
        state.activeAssetId = result.asset.asset_id;
        renderActiveAsset();
        await loadActiveAssetRevisions();
        assistant.revisionEvents = assistant.revisionEvents || [];
        assistant.revisionEvents.push({
          event_type: "asset_revision_created",
          payload: {
            asset: result.asset,
            revision: result.revision,
          },
        });
      }
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
  els.activeAsset.addEventListener("change", () => {
    state.activeAssetId = els.activeAsset.value || null;
    state.activeRevisionNumber = null;
    renderActiveAsset();
    renderDebug();
    loadActiveAssetRevisions().catch((err) => {
      showError("Could not load asset revisions", err.message);
    });
  });
  els.activeRevision.addEventListener("change", () => {
    state.activeRevisionNumber = els.activeRevision.value ? Number(els.activeRevision.value) : null;
    renderActiveRevision();
    renderDebug();
  });
  els.revertRevision.addEventListener("click", revertActiveAssetToRevision);
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
