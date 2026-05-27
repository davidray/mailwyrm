const state = {
  mailbox: "inbox",
  limit: 25,
  auditLimit: 10,
};

const previewableWorkflows = new Set(["daily-preview", "labels", "archive", "trash"]);
const localActionWorkflows = new Set(["classify"]);

const els = {
  mailbox: document.querySelector("#mailbox"),
  refresh: document.querySelector("#refresh"),
  status: document.querySelector("#status-strip"),
  metrics: document.querySelector("#metrics"),
  cleanup: document.querySelector("#cleanup"),
  humanCount: document.querySelector("#human-count"),
  humanLane: document.querySelector("#human-lane"),
  reviewCount: document.querySelector("#review-count"),
  reviewLane: document.querySelector("#review-lane"),
  digestCount: document.querySelector("#digest-count"),
  digest: document.querySelector("#digest"),
  actions: document.querySelector("#actions"),
  trash: document.querySelector("#trash"),
  auditCount: document.querySelector("#audit-count"),
  audit: document.querySelector("#audit"),
  workflows: document.querySelector("#workflows"),
  previewPanel: document.querySelector("#preview-panel"),
  previewTitle: document.querySelector("#preview-title"),
  previewReport: document.querySelector("#preview-report"),
  previewClose: document.querySelector("#preview-close"),
  detailPanel: document.querySelector("#detail-panel"),
  detailTitle: document.querySelector("#detail-title"),
  detailContent: document.querySelector("#detail-content"),
  detailClose: document.querySelector("#detail-close"),
};

els.mailbox.addEventListener("change", () => {
  state.mailbox = els.mailbox.value;
  loadCockpit();
});
els.refresh.addEventListener("click", loadCockpit);
els.previewClose.addEventListener("click", () => {
  els.previewPanel.hidden = true;
});
els.detailClose.addEventListener("click", () => {
  els.detailPanel.hidden = true;
});

loadCockpit();

async function loadCockpit() {
  const params = new URLSearchParams({
    mailbox: state.mailbox,
    limit: String(state.limit),
    audit_limit: String(state.auditLimit),
  });
  try {
    const response = await fetch(`/api/daily-cockpit?${params}`);
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderError(payload.error || "Unable to load cockpit data.");
      return;
    }
    renderCockpit(payload);
  } catch (error) {
    renderError(error.message || "Unable to load cockpit data.");
  }
}

async function parseJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Mailwyrm returned a response the app could not read.");
  }
  return response.json();
}

function renderCockpit(payload) {
  document.title = `${payload.title} - ${payload.date}`;
  els.status.innerHTML = "";
  els.status.append(
    div("div", {}, [
      div("strong", {}, payload.account.email),
      div(
        "p",
        {},
        `${payload.account.indexed_messages} indexed, ${payload.account.classified_messages} classified`
      ),
    ]),
    div("p", {}, `Last sync: ${payload.account.last_sync_mailbox}`),
    div("p", { class: "read-only" }, "Local app view; Gmail mutations require CLI")
  );

  renderMetrics(payload);
  renderCleanup(payload.cleanup);
  renderLane(els.humanLane, els.humanCount, payload.lanes.human, {
    empty: "No human correspondence in this mailbox scope.",
    label: "people",
  });
  renderLane(els.reviewLane, els.reviewCount, payload.lanes.needs_review, {
    empty: "No protected or uncertain messages in this mailbox scope.",
    label: "review",
    badge: (item) => item.review_type || item.action || "review",
  });
  renderDigest(payload.digest);
  renderActions(payload.mailbox_actions);
  renderTrash(payload.trash_gate);
  renderAudit(payload.audit);
  renderWorkflows(payload.workflows);
}

function renderCleanup(cleanup) {
  const archive = cleanup.archive;
  const trash = cleanup.trash;
  const statusText =
    cleanup.clearable_now > 0
      ? `${cleanup.clearable_now} ready to clear from ${cleanup.mailbox}`
      : `Nothing is ready to clear from ${cleanup.mailbox}`;

  els.cleanup.replaceChildren(
    div("div", { class: "cleanup-summary" }, [
      div("p", { class: "eyebrow" }, cleanupHeading(cleanup.mailbox)),
      div("h2", {}, statusText),
      div(
        "p",
        { class: "meta" },
        `${cleanup.kept_human} human kept, ${cleanup.protected_or_review} protected or review`
      ),
    ]),
    cleanupCard({
      title: "Archive",
      ready: archive.ready,
      detail: `${archive.candidates} candidates, ${archive.waiting_for_digest} need digest first`,
      previewWorkflow: "archive",
    }),
    cleanupCard({
      title: "Trash",
      ready: trash.ready,
      detail: trash.policy_enabled
        ? `${trash.candidates} candidates, ${trash.waiting_for_digest} need digest first`
        : `${trash.candidates} candidates, trash policy off`,
      previewWorkflow: "trash",
      danger: true,
    })
  );
}

function cleanupHeading(mailbox) {
  if (mailbox === "all-mail") {
    return "All mail cleanup";
  }
  if (mailbox === "trash") {
    return "Trash cleanup";
  }
  return "Inbox cleanup";
}

function cleanupCard({ title, ready, detail, previewWorkflow, danger = false }) {
  const preview = div("button", { type: "button", class: "preview-workflow" }, "Preview");
  preview.addEventListener("click", () => loadWorkflowPreview(previewWorkflow, preview));

  return div("article", { class: `cleanup-card ${danger ? "danger" : ""}` }, [
    div("div", { class: "cleanup-card-top" }, [
      div("strong", {}, String(ready)),
      div("span", {}, title),
    ]),
    div("p", { class: "meta" }, detail),
    div("div", { class: "cleanup-actions" }, [
      preview,
    ]),
  ]);
}

function renderMetrics(payload) {
  const actionCounts = payload.attention.actions;
  const metrics = [
    ["Human", payload.attention.human],
    ["Machine", payload.attention.machine],
    ["Needs review", payload.attention.needs_review],
    ["Protect", actionCounts.protect],
    ["Archive", actionCounts.archive_after_digest],
    ["Trash candidate", actionCounts.trash_after_digest],
    ["Trash policy", payload.policy.trash_after_digest ? "On" : "Off"],
    ["Archive policy", payload.policy.archive_after_digest ? "On" : "Off"],
  ];
  els.metrics.replaceChildren(
    ...metrics.map(([label, value]) =>
      div("article", { class: "metric" }, [
        div("strong", {}, String(value)),
        div("span", {}, label),
      ])
    )
  );
}

function renderLane(target, counter, lane, options) {
  counter.textContent = `${lane.showing_items} of ${lane.total_items}`;
  if (!lane.items.length) {
    renderEmpty(target, options.empty);
    return;
  }
  target.replaceChildren(
    ...lane.items.map((item) =>
      messageCard(item, {
        badge:
          typeof options.badge === "function"
            ? options.badge(item)
            : item.action || options.label,
        showSnippet: true,
        mailbox: state.mailbox,
      })
    )
  );
}

function renderDigest(digest) {
  els.digestCount.textContent = `${digest.showing_items} of ${digest.total_items}`;
  if (!digest.items.length) {
    renderEmpty(els.digest, "No digest items are shown.");
    return;
  }
  els.digest.replaceChildren(
    ...digest.items.map((item) =>
      messageCard(item, {
        badge: item.machine_type || item.category,
        showSnippet: true,
        mailbox: "all-mail",
      })
    )
  );
}

function renderActions(actions) {
  if (!actions.plans.length) {
    renderEmpty(els.actions, "No classified messages are ready for action preview.");
    return;
  }
  els.actions.replaceChildren(...actions.plans.map(actionItem));
}

function renderTrash(trash) {
  const summary = [
    div(
      "p",
      { class: "meta" },
      `Policy ${trash.policy_enabled ? "enabled" : "disabled"}`
    ),
  ];
  if (trash.skipped_not_digested) {
    summary.push(
      div("p", { class: "meta" }, `${trash.skipped_not_digested} skipped before digest`)
    );
  }
  if (!trash.plans.length) {
    els.trash.replaceChildren(
      ...summary,
      div("p", { class: "empty" }, "No messages are eligible for trash preview.")
    );
    return;
  }
  els.trash.replaceChildren(...summary, ...trash.plans.map(actionItem));
}

function actionItem(plan) {
  return messageCard(plan, {
    badge: plan.action,
    showSnippet: false,
    mailbox: state.mailbox,
  });
}

function messageCard(item, options) {
  return div("article", { class: "item" }, [
    div("div", { class: "item-header" }, [
      div("div", {}, [
        subjectButton(item, options.mailbox || state.mailbox),
        div("div", { class: "meta" }, item.sender),
      ]),
      pill(options.badge),
    ]),
    div("p", { class: "reason" }, item.reason),
    div("p", { class: "meta" }, metaLine(item)),
    options.showSnippet && item.snippet
      ? div("p", { class: "snippet" }, item.snippet)
      : "",
    div("div", { class: "item-actions" }, [
      detailButton(item, options.mailbox || state.mailbox),
      link(item.gmail_url, "Open in Gmail", "secondary-link"),
    ]),
  ]);
}

function subjectButton(item, mailbox) {
  const button = div("button", { type: "button", class: "message-link" }, item.subject);
  button.addEventListener("click", () => loadMessageDetail(item.message_id, mailbox));
  return button;
}

function detailButton(item, mailbox) {
  const button = div("button", { type: "button", class: "view-detail" }, "Details");
  button.addEventListener("click", () => loadMessageDetail(item.message_id, mailbox));
  return button;
}

async function loadMessageDetail(messageId, mailbox) {
  const params = new URLSearchParams({
    message_id: messageId,
    mailbox,
  });
  try {
    const response = await fetch(`/api/message-detail?${params}`);
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderDetailError(payload.error || "Unable to load message detail.");
      return;
    }
    renderMessageDetail(payload);
  } catch (error) {
    renderDetailError(error.message || "Unable to load message detail.");
  }
}

function renderMessageDetail(payload) {
  const message = payload.message;
  els.detailTitle.textContent = message.subject;
  els.detailContent.replaceChildren(
    div("div", { class: "detail-grid" }, [
      detailField("From", message.sender),
      detailField("To", message.to || "(not synced)"),
      detailField("Date", message.date || "(not synced)"),
      detailField("Thread", message.thread_id),
      detailField(
        "Gmail labels",
        message.label_ids.length ? message.label_ids.join(", ") : "None"
      ),
      detailField("Message-ID", message.message_id_header || "(not synced)"),
    ]),
    detailSection("Classification", classificationLines(payload)),
    detailSection("Suggested action", actionLines(payload)),
    detailSection(
      message.has_body_text ? "Stored body text" : "Snippet",
      [message.has_body_text ? message.body_text : message.snippet || "(no local text)"],
      { pre: true }
    ),
    auditSection(payload.audit),
    div("div", { class: "detail-actions" }, [
      link(message.gmail_url, "Open in Gmail", "secondary-link"),
    ])
  );
  els.detailPanel.hidden = false;
  els.detailPanel.scrollIntoView({ block: "start" });
}

function detailField(label, value) {
  return div("div", { class: "detail-field" }, [
    div("span", {}, label),
    div("strong", {}, value),
  ]);
}

function detailSection(title, lines, options = {}) {
  const content = options.pre
    ? div("pre", { class: "detail-body" }, lines.join("\n"))
    : div(
        "div",
        { class: "detail-lines" },
        lines.map((line) => div("p", {}, line))
      );
  return div("section", { class: "detail-section" }, [
    div("h3", {}, title),
    content,
  ]);
}

function classificationLines(payload) {
  const classification = payload.classification;
  if (!classification) {
    const lines = ["This message has not been classified locally."];
    if (payload.correction) {
      lines.push(correctionLine(payload.correction));
    }
    return lines;
  }
  const lines = [
    `Category: ${classification.category}`,
    `Machine type: ${classification.machine_type || "none"}`,
    `Review type: ${classification.review_type || "none"}`,
    `Importance: ${classification.importance}`,
    `Automation safety: ${classification.automation_safety}`,
    `Confidence: ${formatConfidence(classification.confidence)}`,
    `Reason: ${classification.reason}`,
    `Suggested actions: ${classification.suggested_actions.join(", ") || "none"}`,
    `Classifier: ${classification.classifier_version}`,
  ];
  if (payload.correction) {
    lines.push(correctionLine(payload.correction));
  }
  return lines;
}

function correctionLine(correction) {
  const machineType = correction.machine_type ? `, ${correction.machine_type}` : "";
  return `Correction: ${correction.category}${machineType} (${correction.reason || "no reason"})`;
}

function actionLines(payload) {
  if (!payload.suggested_action) {
    return ["No action is available until the message is classified."];
  }
  return [
    `Action: ${payload.suggested_action.action}`,
    `Gmail mutation: ${payload.suggested_action.mutates_gmail ? "yes" : "no"}`,
    `Reason: ${payload.suggested_action.reason}`,
  ];
}

function auditSection(events) {
  if (!events.length) {
    return detailSection("Audit", ["No Gmail mutation audit events for this message."]);
  }
  return detailSection(
    "Audit",
    events.map((event) => `${event.created_at}: ${event.action} (${event.reason})`)
  );
}

function renderDetailError(message) {
  els.detailTitle.textContent = "Message detail error";
  els.detailContent.replaceChildren(div("p", { class: "empty" }, message));
  els.detailPanel.hidden = false;
  els.detailPanel.scrollIntoView({ block: "start" });
}

function metaLine(item) {
  const parts = [
    item.category,
    item.review_type ? `${item.review_type.replaceAll("_", " ")} review` : "",
    item.importance ? `${item.importance} importance` : "",
    item.automation_safety ? `${item.automation_safety} safety` : "",
    `${formatConfidence(item.confidence)} confidence`,
  ];
  return parts.filter(Boolean).join(", ");
}

function renderAudit(audit) {
  els.auditCount.textContent = `${audit.showing_events} of ${audit.total_events}`;
  if (!audit.events.length) {
    renderEmpty(els.audit, "No Gmail mutation audit events yet.");
    return;
  }
  const table = div("table", {}, [
    div("thead", {}, [
      div("tr", {}, [
        div("th", {}, "Time"),
        div("th", {}, "Action"),
        div("th", {}, "Subject"),
        div("th", {}, "Reason"),
      ]),
    ]),
    div(
      "tbody",
      {},
      audit.events.map((event) =>
        div("tr", {}, [
          div("td", {}, event.created_at),
          div("td", {}, event.action),
          div("td", {}, link(event.gmail_url, event.subject)),
          div("td", {}, event.reason),
        ])
      )
    ),
  ]);
  els.audit.replaceChildren(table);
}

function renderWorkflows(workflows) {
  if (!workflows.length) {
    renderEmpty(els.workflows, "No workflow controls are available.");
    return;
  }
  els.workflows.replaceChildren(...workflows.map(workflowCard));
}

function workflowCard(workflow) {
  const countText = workflow.count === null ? "" : `${workflow.count} candidates`;
  const controls = [];
  if (localActionWorkflows.has(workflow.id)) {
    controls.push(localActionButton(workflow));
  }
  if (previewableWorkflows.has(workflow.id)) {
    controls.push(previewButton(workflow));
  }

  return div("article", { class: `workflow ${workflow.id}` }, [
    div("div", { class: "workflow-topline" }, [
      pill(workflow.phase),
      div("div", { class: "workflow-state" }, [
        div("span", { class: "workflow-status" }, workflow.status),
        countText ? div("span", { class: "workflow-count" }, countText) : "",
      ]),
    ]),
    div("h3", {}, workflow.title),
    div("p", { class: "meta" }, workflow.description),
    controls.length ? div("div", { class: "workflow-actions" }, controls) : "",
  ]);
}

function localActionButton(workflow) {
  const button = div("button", { type: "button", class: "run-local-action" }, "Run classify");
  button.addEventListener("click", () => runLocalAction(workflow.id, button));
  return button;
}

async function runLocalAction(workflowId, button) {
  const params = new URLSearchParams({
    mailbox: state.mailbox,
    limit: String(state.limit),
  });
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Running";
  try {
    const response = await fetch(`/api/local-classify?${params}`, {
      method: "POST",
      headers: {
        "X-Mailwyrm-App": "local-ui",
      },
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to run local action.");
      return;
    }
    renderLocalActionResult(payload);
    await loadCockpit();
  } catch (error) {
    renderPreviewError(error.message || "Unable to run local action.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function previewButton(workflow) {
  const button = div("button", { type: "button", class: "preview-workflow" }, "View preview");
  button.addEventListener("click", () => loadWorkflowPreview(workflow.id, button));
  return button;
}

async function loadWorkflowPreview(workflowId, button) {
  const params = new URLSearchParams({
    workflow: workflowId,
    mailbox: state.mailbox,
    limit: String(state.limit),
  });
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Loading";
  try {
    const response = await fetch(`/api/workflow-preview?${params}`);
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to render preview.");
      return;
    }
    renderWorkflowPreview(payload);
  } catch (error) {
    renderPreviewError(error.message || "Unable to render preview.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function renderWorkflowPreview(payload) {
  els.previewTitle.textContent = payload.title;
  els.previewReport.textContent = payload.report;
  els.previewPanel.hidden = false;
  els.previewPanel.scrollIntoView({ block: "start" });
}

function renderLocalActionResult(payload) {
  els.previewTitle.textContent = payload.title;
  els.previewReport.textContent = [
    payload.message,
    "",
    `Mailbox: ${payload.mailbox}`,
    `Matched messages: ${payload.matched_messages}`,
    `Classified locally: ${payload.classified_messages}`,
    `Already classified: ${payload.skipped_already_classified}`,
    "Gmail was not modified.",
  ].join("\n");
  els.previewPanel.hidden = false;
  els.previewPanel.scrollIntoView({ block: "start" });
}

function renderPreviewError(message) {
  els.previewTitle.textContent = "Preview error";
  els.previewReport.textContent = message;
  els.previewPanel.hidden = false;
  els.previewPanel.scrollIntoView({ block: "start" });
}

function renderError(message) {
  els.status.replaceChildren(div("p", { class: "empty" }, message));
}

function renderEmpty(target, message) {
  target.replaceChildren(div("p", { class: "empty" }, message));
}

function pill(text) {
  return div("span", { class: `pill ${text}` }, text.replaceAll("_", " "));
}

function link(href, text, className = "") {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  if (className) {
    a.className = className;
  }
  a.textContent = text;
  return a;
}

function div(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    el.setAttribute(name, value);
  }
  if (children instanceof Node) {
    el.append(children);
    return el;
  }
  if (!Array.isArray(children)) {
    el.textContent = children;
    return el;
  }
  for (const child of children) {
    if (child === "") continue;
    el.append(child);
  }
  return el;
}

function formatConfidence(confidence) {
  return `${Math.round(confidence * 100)}%`;
}
