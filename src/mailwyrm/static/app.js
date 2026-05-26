const state = {
  mailbox: "inbox",
  limit: 25,
  auditLimit: 10,
};

const els = {
  mailbox: document.querySelector("#mailbox"),
  refresh: document.querySelector("#refresh"),
  status: document.querySelector("#status-strip"),
  metrics: document.querySelector("#metrics"),
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
  commands: document.querySelector("#commands"),
};

els.mailbox.addEventListener("change", () => {
  state.mailbox = els.mailbox.value;
  loadCockpit();
});
els.refresh.addEventListener("click", loadCockpit);

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
    div("p", { class: "read-only" }, "Read-only local view")
  );

  renderMetrics(payload);
  renderLane(els.humanLane, els.humanCount, payload.lanes.human, {
    empty: "No human correspondence in this mailbox scope.",
    label: "people",
  });
  renderLane(els.reviewLane, els.reviewCount, payload.lanes.needs_review, {
    empty: "No protected or uncertain messages in this mailbox scope.",
    label: "review",
  });
  renderDigest(payload.digest);
  renderActions(payload.mailbox_actions);
  renderTrash(payload.trash_gate);
  renderAudit(payload.audit);
  renderWorkflows(payload.workflows);
  renderCommands(payload.commands);
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
        badge: item.action || options.label,
        showSnippet: true,
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
  });
}

function messageCard(item, options) {
  return div("article", { class: "item" }, [
    div("div", { class: "item-header" }, [
      div("div", {}, [
        link(item.gmail_url, item.subject),
        div("div", { class: "meta" }, item.sender),
      ]),
      pill(options.badge),
    ]),
    div("p", { class: "reason" }, item.reason),
    div("p", { class: "meta" }, metaLine(item)),
    options.showSnippet && item.snippet
      ? div("p", { class: "snippet" }, item.snippet)
      : "",
  ]);
}

function metaLine(item) {
  const parts = [
    item.category,
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
  const command = workflow.primary_command;
  const previewCommand = workflow.preview_command;
  const countText = workflow.count === null ? "" : `${workflow.count} candidates`;
  const commands = [];
  if (previewCommand) {
    commands.push(commandRow("Preview", previewCommand));
  }
  commands.push(commandRow(primaryLabel(workflow), command));

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
    div("div", { class: "workflow-commands" }, commands),
  ]);
}

function commandRow(label, command) {
  const copyButton = div("button", { type: "button", class: "copy-command" }, "Copy");
  copyButton.addEventListener("click", async () => {
    const copied = await copyText(command);
    copyButton.textContent = copied ? "Copied" : "Copy failed";
    setTimeout(() => {
      copyButton.textContent = "Copy";
    }, 1200);
  });

  return div("div", { class: "command-row" }, [
    div("span", { class: "command-label" }, label),
    div("code", {}, command),
    copyButton,
  ]);
}

async function copyText(text) {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_error) {
      return legacyCopyText(text);
    }
  }
  return legacyCopyText(text);
}

function legacyCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } finally {
    textarea.remove();
  }
}

function primaryLabel(workflow) {
  if (workflow.mutates_gmail) {
    return "Apply";
  }
  if (workflow.id === "sync") {
    return "Sync";
  }
  return "Run";
}

function renderCommands(commands) {
  els.commands.replaceChildren(...commands.map((command) => div("code", {}, command)));
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

function link(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noreferrer";
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
