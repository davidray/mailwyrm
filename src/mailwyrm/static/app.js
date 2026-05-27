const state = {
  mailbox: "inbox",
  limit: 25,
  auditLimit: 10,
  activeTab: "people",
  refreshTimer: null,
};

const previewableWorkflows = new Set(["daily-preview", "labels", "archive", "trash"]);
const appActionEndpoints = {
  sync: "/api/gmail-sync",
  classify: "/api/local-classify",
};
const reviewMachineTypes = [
  ["marketing", "Marketing"],
  ["transactional", "Transactional"],
  ["news", "News"],
  ["product_community", "Community"],
  ["spam", "Spam"],
];

const els = {
  tabs: Array.from(document.querySelectorAll(".tab")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  mailbox: document.querySelector("#mailbox"),
  refresh: document.querySelector("#refresh"),
  profileAvatar: document.querySelector("#profile-avatar"),
  profilePopover: document.querySelector("#profile-popover"),
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
  previewPanel: document.querySelector("#preview-panel"),
  previewTitle: document.querySelector("#preview-title"),
  previewReport: document.querySelector("#preview-report"),
  previewClose: document.querySelector("#preview-close"),
  detailPanel: document.querySelector("#detail-panel"),
  detailTitle: document.querySelector("#detail-title"),
  detailContent: document.querySelector("#detail-content"),
  detailClose: document.querySelector("#detail-close"),
};

for (const tab of els.tabs) {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
}

els.mailbox.addEventListener("change", () => {
  state.mailbox = els.mailbox.value;
  loadCockpit();
});
els.refresh.addEventListener("click", () => refreshCockpit());
els.profileAvatar.addEventListener("click", () => {
  const isOpen = !els.profilePopover.hidden;
  els.profilePopover.hidden = isOpen;
  els.profileAvatar.setAttribute("aria-expanded", isOpen ? "false" : "true");
});
document.addEventListener("click", (event) => {
  if (event.target.closest(".profile-menu")) {
    return;
  }
  els.profilePopover.hidden = true;
  els.profileAvatar.setAttribute("aria-expanded", "false");
});
els.previewClose.addEventListener("click", () => {
  els.previewPanel.hidden = true;
});
els.detailClose.addEventListener("click", () => {
  els.detailPanel.hidden = true;
});

loadCockpit();

async function refreshCockpit() {
  setRefreshState("loading");
  const startedAt = Date.now();
  await loadCockpit();
  const remaining = Math.max(0, 900 - (Date.now() - startedAt));
  window.setTimeout(() => {
    setRefreshState("success");
    state.refreshTimer = window.setTimeout(() => {
      setRefreshState("idle");
    }, 1300);
  }, remaining);
}

function setRefreshState(mode) {
  if (state.refreshTimer) {
    window.clearTimeout(state.refreshTimer);
    state.refreshTimer = null;
  }
  els.refresh.classList.remove("refreshing", "refresh-success");
  els.refresh.disabled = mode === "loading";
  els.refresh.setAttribute("aria-busy", mode === "loading" ? "true" : "false");
  if (mode === "loading") {
    els.refresh.classList.add("refreshing");
    els.refresh.textContent = "Refreshing";
    return;
  }
  if (mode === "success") {
    els.refresh.classList.add("refresh-success");
    els.refresh.textContent = "Refreshed";
    return;
  }
  els.refresh.textContent = "Refresh";
}

function activateTab(tabName) {
  state.activeTab = tabName;
  for (const tab of els.tabs) {
    const isActive = tab.dataset.tab === tabName;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
  }
  for (const panel of els.tabPanels) {
    const isActive = panel.id === `tab-${tabName}`;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  }
}

async function loadCockpit(options = {}) {
  const scrollTop = options.preserveScroll ? window.scrollY : null;
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
    if (scrollTop !== null) {
      requestAnimationFrame(() => {
        window.scrollTo({
          top: Math.min(
            scrollTop,
            Math.max(0, document.body.scrollHeight - window.innerHeight)
          ),
        });
      });
    }
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
  renderProfile(payload.account);

  renderMetrics(payload);
  renderLane(els.humanLane, els.humanCount, payload.lanes.human, {
    empty: "No human correspondence in this mailbox scope.",
    label: "people",
    groupPeople: true,
  });
  renderLane(els.reviewLane, els.reviewCount, payload.lanes.needs_review, {
    empty: "No protected or uncertain messages in this mailbox scope.",
    label: "review",
    badge: (item) => item.review_type || item.action || "review",
    showReason: true,
    prominentSender: true,
    reviewControls: true,
  });
  renderDigest(payload.digest);
  renderActions(payload.mailbox_actions);
  renderTrash(payload.trash_gate);
  renderAudit(payload.audit);
  renderWorkflows(payload.workflows);
}

function renderProfile(account) {
  els.profileAvatar.replaceChildren(profileAvatarContent(account));
  els.profilePopover.replaceChildren(
    profileLine("Account", account.email),
    profileLine(
      "Local index",
      `${account.indexed_messages} indexed, ${account.classified_messages} classified`
    ),
    profileLine("Last sync", account.last_sync_mailbox),
    profileLine("Gmail updates", "Explicit app actions can update Gmail", {
      strong: true,
    })
  );
}

function profileAvatarContent(account) {
  if (account.avatar_url) {
    const image = document.createElement("img");
    image.src = account.avatar_url;
    image.alt = "";
    return image;
  }
  return div("span", {}, profileInitial(account.email));
}

function profileInitial(email) {
  const value = email && email !== "unknown" ? email : "M";
  return value.trim()[0].toUpperCase();
}

function profileLine(label, value, options = {}) {
  return div("div", { class: "profile-line" }, [
    div("span", {}, label),
    div(options.strong ? "strong" : "p", {}, value),
  ]);
}

function renderMetrics(payload) {
  if (!payload.features || !payload.features.show_metrics) {
    els.metrics.hidden = true;
    els.metrics.replaceChildren();
    return;
  }
  els.metrics.hidden = false;
  const actionCounts = payload.attention.actions;
  const metrics = [
    ["Real People", payload.attention.human],
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
  const people = options.groupPeople ? lane.people || [] : [];
  if (options.groupPeople && people.length) {
    const groups = people.map((person) => personGroupCard(person, options));
    if (lane.showing_items < lane.total_items) {
      groups.push(showAllLaneItems(lane, options.label));
    }
    target.replaceChildren(...groups);
    return;
  }
  if (!lane.items.length) {
    renderEmpty(target, options.empty);
    return;
  }
  const cards = lane.items.map((item) =>
    messageCard(item, {
      badge:
        typeof options.badge === "function"
          ? options.badge(item)
          : item.action || options.label,
      showSnippet: true,
      showReason: options.showReason || false,
      prominentSender: options.prominentSender || false,
      reviewControls: options.reviewControls || false,
      mailbox: state.mailbox,
    })
  );
  if (lane.showing_items < lane.total_items) {
    cards.push(showAllLaneItems(lane, options.label));
  }
  target.replaceChildren(...cards);
}

function showAllLaneItems(lane, label) {
  return showAllItems(
    `Showing ${lane.showing_items} of ${lane.total_items} ${label} messages.`,
    lane.total_items
  );
}

function showAllItems(message, totalItems) {
  const button = div("button", { type: "button" }, "Show all");
  button.addEventListener("click", async () => {
    state.limit = Math.max(state.limit, totalItems);
    await loadCockpit({ preserveScroll: true });
  });
  return div("div", { class: "lane-more" }, [div("p", {}, message), button]);
}

function personGroupCard(person, options) {
  return div("article", { class: "person-group" }, [
    div("div", { class: "person-header" }, [
      div("div", { class: "person-identity" }, [
        div("div", { class: "person-avatar" }, personInitials(person)),
        div("div", {}, [
          div("h3", { class: "person-name" }, person.name || person.email),
          person.email && person.email !== person.name
            ? div("p", { class: "person-email" }, person.email)
            : "",
        ]),
      ]),
      pill(`${person.count} message${person.count === 1 ? "" : "s"}`),
    ]),
    div(
      "div",
      { class: "person-messages" },
      person.items.map((item) =>
        messageCard(item, {
          badge: conversationBadge(item, options),
          showSnippet: true,
          showReason: options.showReason || false,
          completeConversation: true,
          compact: true,
          showSender: false,
          mailbox: state.mailbox,
        })
      )
    ),
  ]);
}

function conversationBadge(item, options) {
  if (item.message_count > 1) {
    return `${item.message_count} messages`;
  }
  if (typeof options.badge === "function") {
    return options.badge(item);
  }
  return item.action || options.label;
}

function personInitials(person) {
  const source = person.name || person.email || "?";
  const parts = source
    .replace(/<.*>/, "")
    .split(/[\s@._-]+/)
    .filter(Boolean);
  return (parts[0]?.[0] || "?").toUpperCase();
}

function renderDigest(digest) {
  const bundles = digest.bundles || [];
  els.digestCount.textContent = `${digest.showing_items} of ${digest.total_items}`;
  if (!bundles.length) {
    renderEmpty(els.digest, "No machine summaries are shown.");
    return;
  }
  els.digest.replaceChildren(...bundles.map(machineBundleCard));
}

function machineBundleCard(bundle) {
  const gotIt = div("button", { type: "button", class: "bundle-got-it" }, "Got it");
  gotIt.addEventListener("click", () => clearMachineBundle(bundle, gotIt));

  return div("article", { class: "machine-bundle" }, [
    div("div", { class: "bundle-header" }, [
      div("div", {}, [
        div("h3", {}, bundle.title),
        div("p", { class: "meta" }, `${bundle.count} message(s)`),
      ]),
      gotIt,
    ]),
    div(
      "ul",
      { class: "headline-list" },
      bundle.sender_groups.map((group) =>
        div("li", {}, [
          div("div", { class: "digest-row-heading" }, [
            div("div", {}, [
              div("strong", {}, group.sender_name || group.sender),
              group.followup_count
                ? div(
                    "div",
                    { class: "followup-identity" },
                    `${group.followup_count} follow-up needed`
                  )
                : "",
            ]),
            div("div", { class: "digest-row-actions" }, [
              pill(`${group.count} message${group.count === 1 ? "" : "s"}`),
              followupButton(group),
            ]),
          ]),
          group.subject ? div("p", { class: "digest-subject" }, group.subject) : "",
          group.sender_email ? div("p", { class: "meta" }, group.sender_email) : "",
          group.summary ? div("p", { class: "meta" }, group.summary) : "",
        ])
      )
    ),
  ]);
}

function followupButton(group) {
  const isFollowup = group.followup_count === group.count;
  const button = div(
    "button",
    {
      type: "button",
      class: `followup-toggle${group.followup_count ? " active" : ""}`,
      title: isFollowup
        ? "Remove follow-up from these digest messages."
        : "Keep these digest messages out of Got it cleanup.",
    },
    isFollowup ? "Remove follow-up" : "Follow up"
  );
  button.addEventListener("click", () =>
    setDigestFollowup(group.message_ids, !isFollowup, button)
  );
  return button;
}

async function setDigestFollowup(messageIds, followup, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = followup ? "Marking" : "Removing";
  try {
    const response = await fetch("/api/followup", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_ids: messageIds,
        followup,
        reason: "User marked this digest row for follow-up.",
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to update follow-up.");
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderPreviewError(error.message || "Unable to update follow-up.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

async function clearMachineBundle(bundle, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Clearing";
  try {
    const response = await fetch("/api/machine-bundle/got-it", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        machine_type: bundle.machine_type,
        mailbox: state.mailbox,
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to clear machine bundle.");
      return;
    }
    renderLocalMutationResult(payload);
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderPreviewError(error.message || "Unable to clear machine bundle.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function renderActions(actions) {
  if (!actions.plans.length) {
    renderEmpty(els.actions, "No classified messages are ready for action preview.");
    return;
  }
  const cards = actions.plans.map(actionItem);
  if (actions.showing_plans < actions.total_plans) {
    cards.push(
      showAllItems(
        `Showing ${actions.showing_plans} of ${actions.total_plans} action preview messages.`,
        actions.total_plans
      )
    );
  }
  els.actions.replaceChildren(...cards);
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
    showReason: true,
    showSnippet: false,
    prominentSender: true,
    mailbox: state.mailbox,
  });
}

function messageCard(item, options) {
  const explanation = [item.reason, metaLine(item)].filter(Boolean).join(" ");
  const sender = personIdentity(item.sender);
  return div("article", { class: "item" }, [
    div("div", { class: "item-header" }, [
      div("div", {}, [
        options.prominentSender ? prominentSender(sender) : "",
        subjectButton(item, options.mailbox || state.mailbox),
        options.showSender === false || options.prominentSender
          ? ""
          : div("div", { class: "meta" }, item.sender),
      ]),
      pill(options.badge, explanation),
    ]),
    options.showReason ? div("p", { class: "reason" }, item.reason) : "",
    options.showSnippet && item.snippet
      ? div("p", { class: "snippet" }, item.snippet)
      : "",
    options.reviewControls ? inlineReviewControls(item) : "",
    div("div", { class: "item-actions" }, [
      options.completeConversation ? completeConversationButton(item) : "",
      detailButton(item, options.mailbox || state.mailbox),
      link(item.gmail_url, "Open in Gmail", "secondary-link"),
    ]),
  ]);
}

function personIdentity(sender) {
  const nameMatch = sender.match(/^"?([^"<]+?)"?\s*</);
  const emailMatch = sender.match(/<([^>]+)>/) || sender.match(/([^\s<>]+@[^\s<>]+)/);
  const email = emailMatch ? emailMatch[1] : "";
  const name = (nameMatch ? nameMatch[1] : "").trim() || email || sender;
  return { name, email };
}

function prominentSender(sender) {
  return div("div", { class: "review-sender" }, [
    div("div", { class: "review-sender-name" }, sender.name),
    sender.email && sender.email !== sender.name
      ? div("div", { class: "review-sender-email" }, sender.email)
      : "",
  ]);
}

function completeConversationButton(item) {
  const button = div(
    "button",
    {
      type: "button",
      class: "complete-conversation",
      title: "Archive this Gmail conversation and remove it from Real People.",
    },
    "Complete"
  );
  button.addEventListener("click", () => completeConversation(item, button));
  return button;
}

async function completeConversation(item, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Completing";
  try {
    const response = await fetch("/api/conversation-complete", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        thread_id: item.thread_id,
        mailbox: state.mailbox,
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to complete conversation.");
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderPreviewError(error.message || "Unable to complete conversation.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function inlineReviewControls(item) {
  return div("div", { class: "inline-review-controls" }, [
    inlineReviewButton(
      item,
      "human",
      "Real People",
      null,
      "Move to the Real People tab."
    ),
    ...reviewMachineTypes.map(([type, label]) =>
      inlineReviewButton(
        item,
        "machine",
        label,
        type,
        `Move to the ${label} digest.`
      )
    ),
  ]);
}

function inlineReviewButton(item, resolution, label, machineType, title) {
  const button = div(
    "button",
    {
      type: "button",
      class: `inline-review-action ${machineType || resolution}`,
      title,
    },
    label
  );
  button.addEventListener("click", () =>
    saveReviewResolution({
      messageId: item.message_id,
      resolution,
      machineType,
      reason: "User resolved this from the Review card.",
      button,
      renderDetail: false,
      showResult: false,
    })
  );
  return button;
}

function machineTypeLabel(type) {
  return type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
    reviewResolutionSection(payload),
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

function reviewResolutionSection(payload) {
  const resolution = payload.review_resolution;
  if (!resolution || !resolution.available) {
    return "";
  }

  const reason = div("input", {
    type: "text",
    class: "resolution-reason",
    "aria-label": "Review resolution reason",
    placeholder: "Optional reason",
  });

  return div("section", { class: "detail-section review-resolution" }, [
    div("h3", {}, "Resolve review"),
    div("div", { class: "resolution-controls" }, [
      reason,
      ...resolution.resolutions.map((option) =>
        reviewResolutionButton(payload.message.message_id, option, null, reason)
      ),
      ...resolution.machine_types.map((type) =>
        reviewResolutionButton(
          payload.message.message_id,
          {
            id: "machine",
            label: machineTypeLabel(type),
            description: `Move to the ${machineTypeLabel(type)} digest.`,
            requires_machine_type: true,
          },
          type,
          reason
        )
      ),
    ]),
  ]);
}

function reviewResolutionButton(messageId, option, machineType, reason) {
  const button = div("button", { type: "button", class: "resolve-review" }, option.label);
  button.title = option.description;
  button.addEventListener("click", () =>
    saveReviewResolution({
      messageId,
      resolution: option.id,
      machineType: option.requires_machine_type ? machineType : null,
      reason: reason.value,
      button,
    })
  );
  return button;
}

async function saveReviewResolution({
  messageId,
  resolution,
  machineType,
  reason,
  button,
  renderDetail = true,
  showResult = true,
}) {
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Saving";
  try {
    const response = await fetch("/api/review-resolution", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_id: messageId,
        mailbox: state.mailbox,
        resolution,
        machine_type: machineType,
        reason,
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderPreviewError(payload.error || "Unable to save review resolution.");
      return;
    }
    if (renderDetail) {
      renderMessageDetail(payload.detail);
    }
    if (showResult) {
      renderLocalMutationResult(payload);
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderPreviewError(error.message || "Unable to save review resolution.");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
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
  const appAction = workflowAppAction(workflow);
  const controls = [];
  if (appAction) {
    controls.push(appActionButton(workflow));
  }
  if (previewableWorkflows.has(workflow.id)) {
    controls.push(previewButton(workflow));
  }

  return div("article", { class: `workflow ${workflow.id}`, "data-workflow-id": workflow.id }, [
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

function workflowAppAction(workflow) {
  const action = workflow.app_action || workflow.id;
  return appActionEndpoints[action] ? action : "";
}

function appActionButton(workflow) {
  const button = div(
    "button",
    { type: "button", class: "run-local-action" },
    workflow.action_label || "Run"
  );
  button.addEventListener("click", () => runAppAction(workflow, button));
  return button;
}

async function runAppAction(workflow, button) {
  const params = new URLSearchParams({
    mailbox: state.mailbox,
    limit: String(state.limit),
  });
  const endpoint = appActionEndpoints[workflowAppAction(workflow)];
  const previousText = button.textContent;
  clearWorkflowFeedback(button);
  button.disabled = true;
  button.textContent = "Running";
  try {
    const response = await fetch(`${endpoint}?${params}`, {
      method: "POST",
      headers: {
        "X-Mailwyrm-App": "local-ui",
      },
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderWorkflowFeedback(button, {
        title: "Action failed",
        lines: [payload.error || "Unable to run action."],
        tone: "error",
      });
      return;
    }
    await loadCockpit();
    renderWorkflowFeedbackForId(workflow.id, {
      title: payload.title,
      lines: actionReportLines(payload),
      tone: "success",
    });
  } catch (error) {
    renderWorkflowFeedback(button, {
      title: "Action failed",
      lines: [error.message || "Unable to run action."],
      tone: "error",
    });
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
  revealPreviewPanel();
}

function actionReportLines(payload) {
  if (payload.report_lines && payload.report_lines.length) {
    return [payload.message, "", ...payload.report_lines];
  }
  return [
    payload.message,
    "",
    `Mailbox: ${payload.mailbox}`,
    `Matched messages: ${payload.matched_messages}`,
    `Classified locally: ${payload.classified_messages}`,
    `Already classified: ${payload.skipped_already_classified}`,
    "Gmail was not modified.",
  ];
}

function clearWorkflowFeedback(button) {
  const card = button.closest(".workflow");
  card?.querySelector(".workflow-feedback")?.remove();
}

function renderWorkflowFeedbackForId(workflowId, options) {
  const card = els.workflows.querySelector(`[data-workflow-id="${workflowId}"]`);
  if (!card) {
    return;
  }
  renderWorkflowFeedback(card, options);
}

function renderWorkflowFeedback(target, { title, lines, tone }) {
  const card = target.closest ? target.closest(".workflow") : target;
  if (!card) {
    return;
  }
  card.querySelector(".workflow-feedback")?.remove();
  const feedback = div("div", { class: `workflow-feedback ${tone}` }, [
    div("strong", {}, title),
    ...lines.map((line) => div("p", {}, line)),
  ]);
  const actions = card.querySelector(".workflow-actions");
  if (actions) {
    actions.insertAdjacentElement("afterend", feedback);
    return;
  }
  card.append(feedback);
}

function renderLocalMutationResult(payload) {
  const gmailLine = payload.mutates_gmail
    ? payload.gmail_refresh_hint || "Gmail was modified."
    : "Gmail was not modified.";
  els.previewTitle.textContent = payload.title;
  els.previewReport.textContent = [
    payload.message,
    "",
    gmailLine,
  ].join("\n");
  revealPreviewPanel();
}

function renderPreviewError(message) {
  els.previewTitle.textContent = "Preview error";
  els.previewReport.textContent = message;
  revealPreviewPanel();
}

function revealPreviewPanel() {
  activateTab("tools");
  els.previewPanel.hidden = false;
  els.previewPanel.scrollIntoView({ block: "start" });
}

function renderError(message) {
  els.profilePopover.hidden = false;
  els.profileAvatar.setAttribute("aria-expanded", "true");
  els.profilePopover.replaceChildren(profileLine("Status", message));
}

function renderEmpty(target, message) {
  target.replaceChildren(div("p", { class: "empty" }, message));
}

function pill(text, title = "") {
  const attrs = { class: `pill ${pillClassName(text)}` };
  if (title) {
    attrs.title = title;
  }
  return div("span", attrs, text.replaceAll("_", " "));
}

function pillClassName(text) {
  const slug = String(text)
    .toLowerCase()
    .replaceAll("_", "-")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug ? `pill-${slug}` : "pill-default";
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
