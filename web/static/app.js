document.addEventListener("DOMContentLoaded", () => {
  const shownToasts = new Set();
  const knownRunStates = new Map();
  const knownTaskStates = new Map();
  const toastStack = document.querySelector("#app-toast-stack");
  const keywordInput = document.querySelector("[data-keyword-input]");

  const showToast = (message, type = "info", dedupeKey = "") => {
    const text = String(message || "").trim();
    if (!text || !toastStack) {
      return;
    }
    const key = dedupeKey || `${type}:${text}`;
    if (shownToasts.has(key)) {
      return;
    }
    shownToasts.add(key);

    const item = document.createElement("div");
    item.className = `app-toast app-toast-${type}`;
    item.innerHTML = `
      <div class="app-toast-copy">${text}</div>
      <button type="button" class="app-toast-close" aria-label="关闭提示">关闭</button>
    `;
    item.querySelector(".app-toast-close").addEventListener("click", () => {
      item.remove();
    });
    toastStack.appendChild(item);
    window.setTimeout(() => {
      item.remove();
    }, type === "error" ? 12000 : 8000);
  };

  const parseResponseText = (event) => {
    const xhr = event.detail?.xhr;
    if (!xhr) {
      return "请求失败，请稍后重试。";
    }
    const raw = String(xhr.responseText || xhr.statusText || "").trim();
    if (!raw) {
      return `请求失败（HTTP ${xhr.status || "unknown"}）`;
    }
    const doc = new DOMParser().parseFromString(raw, "text/html");
    const text = (doc.body?.textContent || raw).trim().replace(/\s+/g, " ");
    return text || `请求失败（HTTP ${xhr.status || "unknown"}）`;
  };

  const inspectKeywordRuns = (root, { suppressExisting = false } = {}) => {
    root.querySelectorAll("[data-run-id]").forEach((row) => {
      const runId = row.dataset.runId;
      const keyword = row.dataset.runKeyword || runId;
      const status = row.dataset.runStatus || "";
      const summary = row.dataset.runSummary || "";
      const updatedAt = row.dataset.runUpdatedAt || "";
      const snapshot = `${status}|${summary}|${updatedAt}`;
      const previous = knownRunStates.get(runId);
      knownRunStates.set(runId, snapshot);
      if (suppressExisting && !previous) {
        return;
      }
      if (previous === snapshot) {
        return;
      }
      if (status === "verification_required") {
        showToast(summary || `关键词任务 ${keyword} 需要人工验证`, "warning", `run:${runId}:verification_required`);
        return;
      }
      if (status === "failed") {
        showToast(summary || `关键词任务 ${keyword} 执行失败`, "error", `run:${runId}:failed`);
        return;
      }
      if (!["queued", "running"].includes(status) || !updatedAt) {
        return;
      }
      const ageMs = Date.now() - Date.parse(updatedAt);
      if (Number.isFinite(ageMs) && ageMs > 60_000) {
        showToast(`关键词任务 ${keyword} 长时间没有进展，可能卡住了`, "warning", `run:${runId}:stuck`);
      }
    });
  };

  const inspectTaskRows = (root, { suppressExisting = false } = {}) => {
    root.querySelectorAll("[data-task-id]").forEach((row) => {
      const taskId = row.dataset.taskId;
      const taskType = row.dataset.taskType || taskId;
      const status = row.dataset.taskStatus || "";
      const errorText = row.dataset.taskError || row.dataset.taskSummary || "";
      const snapshot = `${status}|${errorText}`;
      const previous = knownTaskStates.get(taskId);
      knownTaskStates.set(taskId, snapshot);
      if (suppressExisting && !previous) {
        return;
      }
      if (previous === snapshot) {
        return;
      }
      if (status === "failed") {
        showToast(errorText || `后台任务 ${taskType} 失败`, "error", `task:${taskId}:failed`);
      }
    });
  };

  const inspectActionMessages = (root) => {
    root.querySelectorAll(".keyword-result-message, .app-result-message").forEach((node, index) => {
      const text = node.textContent?.trim();
      if (text) {
        showToast(text, "info", `action:${index}:${text}`);
      }
    });
  };

  const taskFeed = document.querySelector("[data-task-feed]");
  const serializeLeadPoolFilters = () => {
    const form = document.querySelector("#lead-pool-filter-form");
    const params = new URLSearchParams();
    if (!form) {
      return params;
    }
    const formData = new FormData(form);
    for (const [key, value] of formData.entries()) {
      const text = String(value || "").trim();
      if (text) {
        params.set(key, text);
      }
    }
    return params;
  };

  const refreshLeadPoolContent = () => {
    const content = document.querySelector("#lead-pool-content");
    if (!content) {
      return;
    }
    const params = serializeLeadPoolFilters();
    params.set("partial", "content");
    htmx.ajax("GET", `/lead-pool?${params.toString()}`, {
      target: "#lead-pool-content",
      swap: "innerHTML",
    });
  };

  const taskSource = new EventSource("/streams/tasks");
  taskSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.status === "failed") {
        showToast(payload.error_summary || `后台任务 ${payload.task_type || payload.task_id} 失败`, "error", `task-event:${payload.task_id}:failed`);
      }
    } catch {
      showToast("后台任务状态更新失败，请刷新页面检查。", "warning", "task-stream-parse");
    }
    if (taskFeed) {
      htmx.ajax("GET", "/tasks?partial=rows", {
        target: "[data-task-feed]",
        swap: "innerHTML",
      });
    }
  };

  const eventFeed = document.querySelector("#event-feed");
  if (eventFeed) {
    const eventSource = new EventSource("/streams/events");
    eventSource.onmessage = (event) => {
      const line = document.createElement("pre");
      line.textContent = event.data;
      eventFeed.prepend(line);
    };
  }

  document.body.addEventListener("htmx:responseError", (event) => {
    showToast(parseResponseText(event), "error");
  });

  document.body.addEventListener("htmx:sendError", () => {
    showToast("请求发送失败，请检查本地服务和网络状态。", "error", "htmx:sendError");
  });

  document.body.addEventListener("htmx:timeout", () => {
    showToast("请求超时，任务可能卡住了。", "warning", "htmx:timeout");
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail?.target;
    if (!target) {
      return;
    }
    if (target.id === "keyword-run-feed") {
      inspectKeywordRuns(target);
    }
    if (target.matches("[data-task-feed]")) {
      inspectTaskRows(target);
    }
    if (target.id === "keyword-funnel-result" || target.id === "lead-pool-result") {
      inspectActionMessages(target);
    }
    inspectActionMessages(target);
  });

  const keywordRunFeed = document.querySelector("#keyword-run-feed");
  if (keywordRunFeed) {
    inspectKeywordRuns(keywordRunFeed, { suppressExisting: true });
  }
  if (taskFeed) {
    inspectTaskRows(taskFeed, { suppressExisting: true });
  }
  const keywordResult = document.querySelector("#keyword-funnel-result");
  if (keywordResult) {
    inspectActionMessages(keywordResult);
  }
  const leadPoolResult = document.querySelector("#lead-pool-result");
  if (leadPoolResult) {
    inspectActionMessages(leadPoolResult);
  }

  document.body.addEventListener("lead-pool-refresh", refreshLeadPoolContent);

  document.body.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-keyword-chip]");
    if (!trigger || !keywordInput) {
      return;
    }
    keywordInput.value = trigger.dataset.keywordChip || "";
    keywordInput.focus();
  });
});
