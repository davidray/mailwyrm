const state = {
  mailbox: "inbox",
  limit: 25,
  auditLimit: 10,
  activeTab: "people",
  refreshTimer: null,
  completeTimers: new Map(),
};

const COMPLETE_UNDO_DELAY_MS = 5000;
const previewableWorkflows = new Set(["daily-preview", "labels", "archive", "trash"]);
const appActionEndpoints = {
  refresh: "/api/gmail-refresh",
  sync: "/api/gmail-sync",
  classify: "/api/local-classify",
  labels: "/api/gmail-labels/apply",
  archive: "/api/archive-after-digest",
  trash: "/api/trash-after-digest",
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
  reviewTabCount: document.querySelector("#review-tab-count"),
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
  const clickedProfile = event.target.closest(".profile-menu");
  if (!clickedProfile) {
    els.profilePopover.hidden = true;
    els.profileAvatar.setAttribute("aria-expanded", "false");
  }
  if (
    !els.detailPanel.hidden &&
    !event.target.closest("#detail-panel") &&
    !event.target.closest(".message-link")
  ) {
    closeDetailPanel();
  }
});
els.previewClose.addEventListener("click", () => {
  els.previewPanel.hidden = true;
});
els.detailClose.addEventListener("click", closeDetailPanel);

function closeDetailPanel() {
  els.detailPanel.hidden = true;
  document.body.classList.remove("reader-open");
}

loadCockpit();

async function refreshCockpit() {
  setRefreshState("loading");
  const startedAt = Date.now();
  let refreshMessage = "Updated";
  try {
    const params = new URLSearchParams({
      mailbox: state.mailbox,
    });
    const response = await fetch(`${appActionEndpoints.refresh}?${params}`, {
      method: "POST",
      headers: {
        "X-Mailwyrm-App": "local-ui",
      },
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(payload.error || "Unable to update from Gmail.");
    }
    refreshMessage = refreshSuccessLabel(payload);
    await loadCockpit();
  } catch (error) {
    setRefreshState("error", error.message || "Refresh failed");
    return;
  }
  const remaining = Math.max(0, 900 - (Date.now() - startedAt));
  window.setTimeout(() => {
    setRefreshState("success", refreshMessage);
    state.refreshTimer = window.setTimeout(() => {
      setRefreshState("idle");
    }, 1300);
  }, remaining);
}

function refreshSuccessLabel(payload) {
  if (payload.refresh_mode === "history") {
    return payload.history_records ? "Updated" : "Current";
  }
  return "Synced";
}

function setRefreshState(mode, message = "") {
  if (state.refreshTimer) {
    window.clearTimeout(state.refreshTimer);
    state.refreshTimer = null;
  }
  els.refresh.classList.remove("refreshing", "refresh-success");
  els.refresh.disabled = mode === "loading";
  els.refresh.setAttribute("aria-busy", mode === "loading" ? "true" : "false");
  if (mode !== "error") {
    els.refresh.removeAttribute("title");
  }
  if (mode === "loading") {
    els.refresh.classList.add("refreshing");
    els.refresh.textContent = "Refreshing";
    return;
  }
  if (mode === "success") {
    els.refresh.classList.add("refresh-success");
    els.refresh.textContent = message || "Updated";
    return;
  }
  if (mode === "error") {
    els.refresh.textContent = "Refresh failed";
    els.refresh.title = message;
    state.refreshTimer = window.setTimeout(() => {
      setRefreshState("idle");
    }, 2600);
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
    return payload;
  } catch (error) {
    renderError(error.message || "Unable to load cockpit data.");
  }
  return null;
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
    empty: "No current conversations in this mailbox scope.",
    label: "people",
    groupPeople: true,
  });
  renderLane(els.reviewLane, els.reviewCount, payload.lanes.needs_review, {
    empty: "Nothing needs extra context in this mailbox scope.",
    label: "review",
    badge: (item) => item.review_type || item.action || "review",
    showReason: true,
    prominentSender: true,
    reviewControls: true,
  });
  renderReviewTabCount(payload.lanes.needs_review);
  renderDigest(payload.digest);
  renderActions(payload.mailbox_actions);
  renderTrash(payload.trash_gate);
  renderAudit(payload.audit);
  renderWorkflows(payload.workflows);
}

function renderReviewTabCount(lane) {
  const count = lane.total_items || 0;
  els.reviewTabCount.hidden = false;
  els.reviewTabCount.textContent = String(count);
  els.reviewTabCount.setAttribute(
    "aria-label",
    `${count} review message${count === 1 ? "" : "s"}`
  );
}

function renderProfile(account) {
  const lines = [
    profileLine("Account", account.email),
    profileLine(
      "Local index",
      `${account.indexed_messages} indexed, ${account.classified_messages} classified`
    ),
    profileLine("Last sync", account.last_sync_mailbox),
    ...refreshProfileLines(account.last_refresh),
    profileLine("Gmail boundary", "Only explicit actions update Gmail", {
      strong: true,
    }),
  ];
  els.profileAvatar.replaceChildren(profileAvatarContent(account));
  els.profilePopover.replaceChildren(...lines);
}

function refreshProfileLines(lastRefresh) {
  if (!lastRefresh) {
    return [profileLine("Last refresh", "Not yet refreshed from Gmail")];
  }
  return [
    profileLine("Last refresh", formatRefreshTime(lastRefresh.refreshed_at)),
    profileLine("Refresh mode", refreshModeLabel(lastRefresh.mode)),
    profileLine(
      "Refresh changes",
      [
        `${lastRefresh.messages_fetched || 0} fetched`,
        `${lastRefresh.label_changes || 0} label changes`,
        `${lastRefresh.messages_deleted || 0} deleted locally`,
        `${lastRefresh.classified_messages || 0} classified`,
      ].join(", ")
    ),
    profileLine(
      "Gmail modified",
      lastRefresh.gmail_modified ? "Yes" : "No",
      { strong: !lastRefresh.gmail_modified }
    ),
  ];
}

function formatRefreshTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function refreshModeLabel(mode) {
  if (mode === "history") {
    return "Gmail history";
  }
  if (mode === "first-sync") {
    return "First full sync";
  }
  if (mode === "history-expired") {
    return "Full sync fallback";
  }
  return mode || "Unknown";
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
    ["Conversations", payload.attention.human],
    ["Digest material", payload.attention.machine],
    ["Needs context", payload.attention.needs_review],
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
          reassignToDigest: true,
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

  return div("article", { class: "machine-bundle", "data-machine-type": bundle.machine_type }, [
    div("div", { class: "bundle-header" }, [
      div("div", {}, [
        div("h3", {}, bundle.title),
        div("p", { class: "meta" }, `${bundle.count} message(s)`),
      ]),
      gotIt,
    ]),
    div(
      "div",
      { class: "headline-list" },
      bundle.sender_groups.map((group) => digestRowCard(group, bundle))
    ),
  ]);
}

function digestRowCard(group, bundle) {
  return div("article", { class: "item digest-row" }, [
    div("div", { class: "item-sender digest-sender" }, [
      div("div", { class: "review-sender-name" }, group.sender_name || group.sender),
      group.sender_email
        ? div("div", { class: "review-sender-email" }, group.sender_email)
        : "",
      pill(`${group.count} message${group.count === 1 ? "" : "s"}`),
    ]),
    div("div", { class: "item-body" }, [
      div("div", { class: "item-header" }, [
        div("div", {}, [digestRowTitle(group)]),
        div("div", { class: "digest-row-actions" }, [
          followupButton(group),
          readLaterButton(group),
        ]),
      ]),
      group.summary ? inlineMarkdownElement("p", { class: "snippet" }, group.summary) : "",
      digestRowControls(group, bundle),
    ]),
  ]);
}

function digestRowTitle(group) {
  if (group.count === 1 && group.messages && group.messages.length === 1) {
    return subjectButton(
      {
        message_id: group.messages[0].message_id,
        subject: group.subject || group.messages[0].subject || group.sender_name,
      },
      state.mailbox
    );
  }
  return div("div", { class: "message-link digest-group-title" }, group.sender_name || group.sender);
}

function digestRowControls(group, bundle) {
  return div("div", { class: "item-actions digest-row-controls" }, [
    digestCategorySelect(group, bundle.machine_type),
    ...digestMessageControls(group),
  ]);
}

function digestCategorySelect(group, currentMachineType) {
  const select = div(
    "select",
    {
      class: "digest-category-select",
      "aria-label": "Move digest row to category",
      title: "Move this digest row to another category.",
      "data-current-value": currentMachineType,
    },
    reviewMachineTypes.map(([type, label]) =>
      div("option", { value: type }, label)
    )
  );
  select.value = currentMachineType;
  select.addEventListener("change", () =>
    updateDigestCategory(group.message_ids, select.value, select)
  );
  return select;
}

function digestMessageControls(group) {
  const messages = group.messages || [];
  if (messages.length === 1) {
    const message = messages[0];
    return [
      link(message.gmail_url, "Open in Gmail", "secondary-link"),
    ];
  }
  if (messages.length > 1) {
    return [
      div("details", { class: "digest-message-list" }, [
        div("summary", {}, `Read ${messages.length} emails`),
        div(
          "div",
          { class: "digest-message-items" },
          messages.map((message) =>
            div("div", { class: "digest-message-item" }, [
              div("span", {}, message.subject),
              div("div", { class: "digest-message-actions" }, [
                link(message.gmail_url, "Open in Gmail", "secondary-link"),
              ]),
            ])
          )
        ),
      ]),
    ];
  }
  return [];
}

async function updateDigestCategory(messageIds, machineType, select) {
  const previousValue = select.dataset.currentValue || select.value;
  if (machineType === previousValue) {
    return;
  }
  if (machineType === "spam") {
    await markMessagesSpam(
      messageIds,
      select,
      "User moved this digest row to Spam."
    );
    return;
  }
  select.disabled = true;
  try {
    const response = await fetch("/api/digest-category", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_ids: messageIds,
        machine_type: machineType,
        reason: "User moved this digest row to another category.",
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      select.value = previousValue;
      renderBundleFeedback(select, {
        title: "Category failed",
        message: payload.error || "Unable to update digest category.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    select.value = previousValue;
    renderBundleFeedback(select, {
      title: "Category failed",
      message: error.message || "Unable to update digest category.",
      tone: "error",
    });
  } finally {
    select.disabled = false;
  }
}

function digestReassignmentSelect(item) {
  const select = div(
    "select",
    {
      class: "digest-category-select human-reassign-select",
      "aria-label": "Move conversation to digest category",
      title: "Move this conversation out of correspondence and into a digest category.",
      "data-current-value": "",
    },
    [
      div("option", { value: "" }, "Move to digest..."),
      ...reviewMachineTypes.map(([type, label]) =>
        div("option", { value: type }, label)
      ),
    ]
  );
  select.value = "";
  select.addEventListener("change", () =>
    reassignRealPeopleItemToDigest(item, select.value, select)
  );
  return select;
}

async function reassignRealPeopleItemToDigest(item, machineType, select) {
  if (!machineType) {
    return;
  }
  const messageIds =
    item.message_ids && item.message_ids.length ? item.message_ids : [item.message_id];
  if (machineType === "spam") {
    await markMessagesSpam(
      messageIds,
      select,
      "User moved this correspondence conversation to Spam."
    );
    return;
  }
  select.disabled = true;
  try {
    const response = await fetch("/api/digest-category", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_ids: messageIds,
        machine_type: machineType,
        reason: "User moved this correspondence conversation to a digest category.",
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      select.value = "";
      renderContextFeedback(select, {
        title: "Category failed",
        message: payload.error || "Unable to move this conversation.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    select.value = "";
    renderContextFeedback(select, {
      title: "Category failed",
      message: error.message || "Unable to move this conversation.",
      tone: "error",
    });
  } finally {
    select.disabled = false;
  }
}

function followupButton(group) {
  const isFollowup = group.followup_count === group.count;
  const button = div(
    "button",
    {
      type: "button",
      class: `icon-toggle followup-toggle${group.followup_count ? " active" : ""}`,
      "aria-label": isFollowup ? "Remove follow-up" : "Mark for follow-up",
      title: isFollowup
        ? "Remove follow-up from these digest messages."
        : "Keep these digest messages out of Got it cleanup.",
    },
    isFollowup ? "☑" : "☐"
  );
  button.addEventListener("click", () =>
    setDigestFollowup(group.message_ids, !isFollowup, button)
  );
  return button;
}

function readLaterButton(group) {
  const isReadLater = group.read_later_count === group.count;
  const button = div(
    "button",
    {
      type: "button",
      class: `icon-toggle read-later-toggle${group.read_later_count ? " active" : ""}`,
      "aria-label": isReadLater ? "Remove read marker" : "Mark to read",
      title: isReadLater
        ? "Remove read marker from these digest messages."
        : "Keep these digest messages around to read later.",
    },
    isReadLater ? "♥" : "♡"
  );
  button.addEventListener("click", () =>
    setDigestReadLater(group.message_ids, !isReadLater, button)
  );
  return button;
}

async function setDigestFollowup(messageIds, followup, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.classList.add("saving");
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
      renderBundleFeedback(button, {
        title: "Follow-up failed",
        message: payload.error || "Unable to update follow-up.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderBundleFeedback(button, {
      title: "Follow-up failed",
      message: error.message || "Unable to update follow-up.",
      tone: "error",
    });
  } finally {
    button.disabled = false;
    button.classList.remove("saving");
    button.textContent = previousText;
  }
}

async function setDigestReadLater(messageIds, readLater, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.classList.add("saving");
  try {
    const response = await fetch("/api/read-later", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_ids: messageIds,
        read_later: readLater,
        reason: "User marked this digest row to read.",
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderBundleFeedback(button, {
        title: "Read marker failed",
        message: payload.error || "Unable to update read marker.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderBundleFeedback(button, {
      title: "Read marker failed",
      message: error.message || "Unable to update read marker.",
      tone: "error",
    });
  } finally {
    button.disabled = false;
    button.classList.remove("saving");
    button.textContent = previousText;
  }
}

async function clearMachineBundle(bundle, button) {
  const previousText = button.textContent;
  clearBundleFeedback(button);
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
      renderBundleFeedback(button, {
        title: "Got it failed",
        message: payload.error || "Unable to clear machine bundle.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
    if (payload.applied === 0) {
      renderBundleFeedbackForType(payload.machine_type, {
        title: payload.title,
        message: payload.message,
        tone: "success",
      });
    }
  } catch (error) {
    renderBundleFeedback(button, {
      title: "Got it failed",
      message: error.message || "Unable to clear machine bundle.",
      tone: "error",
    });
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function clearBundleFeedback(button) {
  button.closest(".machine-bundle")?.querySelector(".bundle-feedback")?.remove();
}

function renderBundleFeedbackForType(machineType, options) {
  const bundleCard = els.digest.querySelector(
    `[data-machine-type="${CSS.escape(machineType)}"]`
  );
  if (bundleCard) {
    renderBundleFeedback(bundleCard, options);
  }
}

function renderBundleFeedback(target, { title, message, tone }) {
  const bundleCard = target.closest ? target.closest(".machine-bundle") : target;
  if (!bundleCard) {
    return;
  }
  bundleCard.querySelector(".bundle-feedback")?.remove();
  const feedback = div("div", { class: `bundle-feedback ${tone}` }, [
    div("strong", {}, title),
    div("p", {}, message),
  ]);
  const header = bundleCard.querySelector(".bundle-header");
  if (header) {
    header.insertAdjacentElement("afterend", feedback);
    return;
  }
  bundleCard.prepend(feedback);
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
    options.showSender === false
      ? ""
      : div("div", { class: "item-sender" }, [
          options.prominentSender
            ? prominentSender(sender)
            : compactSenderIdentity(sender),
        ]),
    div("div", { class: "item-body" }, [
      div("div", { class: "item-header" }, [
        div("div", {}, [subjectButton(item, options.mailbox || state.mailbox)]),
        pill(options.badge, explanation),
      ]),
      options.showReason && item.reason ? div("p", { class: "reason" }, item.reason) : "",
      options.showSnippet && item.snippet
        ? div("p", { class: "snippet" }, item.snippet)
        : "",
      options.reviewControls ? inlineReviewControls(item) : "",
      div("div", { class: "item-actions" }, [
        options.reassignToDigest ? digestReassignmentSelect(item) : "",
        options.completeConversation ? completeConversationButton(item) : "",
        link(item.gmail_url, "Open in Gmail", "secondary-link"),
      ]),
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

function compactSenderIdentity(sender) {
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
      title: "Archive this Gmail conversation and remove it from correspondence.",
    },
    "Complete"
  );
  button.addEventListener("click", () => scheduleCompleteConversation(item, button));
  return button;
}

function scheduleCompleteConversation(item, button) {
  const pendingKey = item.thread_id || item.message_id;
  if (state.completeTimers.has(pendingKey)) {
    return;
  }
  button.disabled = true;
  button.textContent = "Completing in 5s";
  const undo = div(
    "button",
    {
      type: "button",
      class: "undo-complete",
      title: "Cancel completing this conversation.",
    },
    "Undo"
  );
  button.insertAdjacentElement("afterend", undo);

  const timer = window.setTimeout(() => {
    state.completeTimers.delete(pendingKey);
    undo.remove();
    completeConversation(item, button);
  }, COMPLETE_UNDO_DELAY_MS);

  state.completeTimers.set(pendingKey, { timer, button, undo });
  undo.addEventListener("click", () => undoCompleteConversation(pendingKey));
}

function undoCompleteConversation(pendingKey) {
  const pending = state.completeTimers.get(pendingKey);
  if (!pending) {
    return;
  }
  window.clearTimeout(pending.timer);
  state.completeTimers.delete(pendingKey);
  pending.undo.remove();
  pending.button.disabled = false;
  pending.button.textContent = "Complete";
}

async function completeConversation(item, button) {
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "Archiving";
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
      renderContextFeedback(button, {
        title: "Complete failed",
        message: payload.error || "Unable to complete conversation.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderContextFeedback(button, {
      title: "Complete failed",
      message: error.message || "Unable to complete conversation.",
      tone: "error",
    });
  } finally {
    button.disabled = false;
    button.textContent = previousText === "Completing in 5s" ? "Complete" : previousText;
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
  button.addEventListener("click", () => {
    if (machineType === "spam") {
      markMessagesSpam(
        [item.message_id],
        button,
        "User resolved this Review card as Spam."
      );
      return;
    }
    saveReviewResolution({
      messageId: item.message_id,
      resolution,
      machineType,
      reason: "User resolved this from the Review card.",
      button,
      renderDetail: false,
      showResult: false,
    });
  });
  return button;
}

async function markMessagesSpam(messageIds, control, reason) {
  const previousText = control.textContent;
  control.disabled = true;
  if (control.tagName !== "SELECT") {
    control.textContent = "Spam";
  }
  try {
    const response = await fetch("/api/spam-messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mailwyrm-App": "local-ui",
      },
      body: JSON.stringify({
        message_ids: messageIds,
        mailbox: state.mailbox,
        reason,
      }),
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderContextFeedback(control, {
        title: "Spam failed",
        message: payload.error || "Unable to mark as spam.",
        tone: "error",
      });
      return;
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderContextFeedback(control, {
      title: "Spam failed",
      message: error.message || "Unable to mark as spam.",
      tone: "error",
    });
  } finally {
    control.disabled = false;
    if (control.tagName !== "SELECT") {
      control.textContent = previousText;
    }
    if (control.tagName === "SELECT") {
      control.value = control.dataset.currentValue || "";
    }
  }
}

function machineTypeLabel(type) {
  return type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function subjectButton(item, mailbox) {
  const button = div("button", { type: "button", class: "message-link" }, item.subject);
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
    div("article", { class: "reading-message" }, [
      div("div", { class: "reading-header" }, [
        div("div", {}, [
          div("p", { class: "reading-from" }, message.sender),
          message.to ? div("p", { class: "reading-meta" }, `To ${message.to}`) : "",
          message.date ? div("p", { class: "reading-meta" }, message.date) : "",
        ]),
        div("div", { class: "reading-actions" }, [
          replyPlaceholderButton(payload),
          link(message.gmail_url, "Open in Gmail", "secondary-link"),
        ]),
      ]),
      markdownBlock(
        message.has_body_text ? message.body_text : message.snippet || "(no local text)",
        `reading-body${message.has_body_text ? "" : " muted"}`
      ),
    ]),
    conversationSection(payload),
    div("div", { class: "detail-support-grid" }, [
      detailSection("Context", contextLines(payload)),
      detailSection("Classification", classificationLines(payload)),
      detailSection("Suggested action", actionLines(payload)),
    ]),
    reviewResolutionSection(payload),
    auditSection(payload.audit)
  );
  els.detailPanel.hidden = false;
  document.body.classList.add("reader-open");
}

function replyPlaceholderButton(payload) {
  const button = div(
    "button",
    {
      type: "button",
      class: "reply-placeholder",
      title: payload.reply_status || "Draft replies are not enabled yet.",
      disabled: true,
    },
    "Reply"
  );
  return button;
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

function contextLines(payload) {
  const message = payload.message;
  return [
    `Thread: ${message.thread_id}`,
    `Gmail labels: ${message.label_ids.length ? message.label_ids.join(", ") : "None"}`,
    `Message-ID: ${message.message_id_header || "(not synced)"}`,
  ];
}

function conversationSection(payload) {
  const conversation = payload.conversation || [];
  if (conversation.length <= 1) {
    return "";
  }
  return div("section", { class: "conversation-section" }, [
    div("div", { class: "conversation-heading" }, [
      div("h3", {}, "Conversation"),
      pill(`${conversation.length} messages`),
    ]),
    div(
      "div",
      { class: "conversation-list" },
      conversation.map((message) => conversationMessage(message))
    ),
  ]);
}

function conversationMessage(message) {
  return div(
    "article",
    { class: `conversation-message${message.selected ? " selected" : ""}` },
    [
      div("div", { class: "conversation-message-header" }, [
        div("div", {}, [
          div("strong", {}, message.sender),
          message.date ? div("span", {}, message.date) : "",
        ]),
        message.selected ? pill("open") : conversationOpenButton(message),
      ]),
      div(
        "p",
        { class: "conversation-message-preview" },
        inlineMarkdownFragment(
          message.has_body_text ? message.body_text : message.snippet || "(no local text)"
        )
      ),
    ]
  );
}

function conversationOpenButton(message) {
  const button = div("button", { type: "button", class: "message-link" }, "Open");
  button.addEventListener("click", () => loadMessageDetail(message.message_id, state.mailbox));
  return button;
}

function markdownBlock(text, className) {
  const container = div("div", { class: className });
  let list = null;
  const closeList = () => {
    if (list) {
      container.append(list);
      list = null;
    }
  };

  for (const rawLine of String(text || "").split(/\n+/)) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 5);
      container.append(
        inlineMarkdownElement(`h${level}`, { class: "markdown-heading" }, heading[2])
      );
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!list) {
        list = div("ul", { class: "markdown-list" });
      }
      list.append(inlineMarkdownElement("li", {}, bullet[1]));
      continue;
    }

    closeList();
    container.append(inlineMarkdownElement("p", {}, line));
  }
  closeList();
  return container;
}

function inlineMarkdownElement(tag, attrs, text) {
  const element = div(tag, attrs);
  element.append(inlineMarkdownFragment(text));
  return element;
}

function inlineMarkdownFragment(text) {
  const fragment = document.createDocumentFragment();
  const pattern =
    /(\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|(https?:\/\/[^\s<>()]+))/gi;
  let lastIndex = 0;
  const value = String(text || "");
  for (const match of value.matchAll(pattern)) {
    if (match.index > lastIndex) {
      fragment.append(value.slice(lastIndex, match.index));
    }
    if (match[2] && match[3]) {
      fragment.append(markdownLink(match[3], match[2]));
    } else if (match[4]) {
      fragment.append(div("code", { class: "inline-code" }, match[4]));
    } else if (match[5]) {
      fragment.append(div("strong", {}, match[5]));
    } else if (match[6]) {
      fragment.append(div("em", {}, match[6]));
    } else if (match[7]) {
      fragment.append(markdownLink(match[7], markdownLinkLabel(match[7])));
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < value.length) {
    fragment.append(value.slice(lastIndex));
  }
  return fragment;
}

function markdownLink(href, text) {
  const cleanedHref = href.replace(/[.,;!?]+$/, "");
  const anchor = link(cleanedHref, text, "markdown-link");
  return anchor;
}

function markdownLinkLabel(href) {
  try {
    return new URL(href).hostname || href;
  } catch {
    return href;
  }
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
    payload.suggested_action.reason
      ? `Reason: ${payload.suggested_action.reason}`
      : "",
  ].filter(Boolean);
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
      renderContextFeedback(button, {
        title: "Resolution failed",
        message: payload.error || "Unable to save review resolution.",
        tone: "error",
      });
      return;
    }
    if (renderDetail) {
      renderMessageDetail(payload.detail);
    }
    if (showResult) {
      renderContextFeedback(button, {
        title: payload.title,
        message: payload.message,
        tone: "success",
      });
    }
    await loadCockpit({ preserveScroll: true });
  } catch (error) {
    renderContextFeedback(button, {
      title: "Resolution failed",
      message: error.message || "Unable to save review resolution.",
      tone: "error",
    });
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function renderContextFeedback(target, { title, message, tone }) {
  const container =
    target.closest(".review-resolution") ||
    target.closest(".item") ||
    target.closest(".machine-bundle");
  if (!container) {
    return;
  }
  container.querySelector(".context-feedback")?.remove();
  const feedback = div("div", { class: `context-feedback ${tone}` }, [
    div("strong", {}, title),
    div("p", {}, message),
  ]);
  const controls =
    target.closest(".resolution-controls") ||
    target.closest(".inline-review-controls") ||
    target.closest(".item-actions");
  if (controls) {
    controls.insertAdjacentElement("afterend", feedback);
    return;
  }
  container.append(feedback);
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
  document.body.classList.add("reader-open");
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
  if (workflow.mutates_gmail && !confirmGmailMutation(workflow)) {
    return;
  }
  const params = new URLSearchParams({
    mailbox: state.mailbox,
  });
  if (workflow.sync_all || workflow.process_all) {
    params.set("all", "true");
  } else {
    params.set("limit", String(state.limit));
  }
  const endpoint = appActionEndpoints[workflowAppAction(workflow)];
  const previousText = button.textContent;
  clearWorkflowFeedback(button);
  els.previewPanel.hidden = true;
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

function confirmGmailMutation(workflow) {
  return window.confirm(
    `${workflow.title} will update Gmail for the selected mailbox scope.\n\n` +
      "Review the preview first if you are not sure. Continue?"
  );
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
  clearWorkflowFeedback(button);
  button.disabled = true;
  button.textContent = "Loading";
  try {
    const response = await fetch(`/api/workflow-preview?${params}`);
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      renderWorkflowFeedback(button, {
        title: "Preview failed",
        lines: [payload.error || "Unable to render preview."],
        tone: "error",
      });
      return;
    }
    renderWorkflowFeedback(button, {
      title: payload.title,
      lines: ["Preview only. Gmail was not modified."],
      report: payload.report,
      tone: "preview",
    });
  } catch (error) {
    renderWorkflowFeedback(button, {
      title: "Preview failed",
      lines: [error.message || "Unable to render preview."],
      tone: "error",
    });
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
  if (payload.report) {
    return [
      payload.message,
      "",
      ...payload.report.split("\n"),
      "",
      payload.mutates_gmail
        ? payload.gmail_refresh_hint || "Gmail was modified."
        : "Gmail was not modified.",
    ];
  }
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

function renderWorkflowFeedback(target, { title, lines, report, tone }) {
  const card = target.closest ? target.closest(".workflow") : target;
  if (!card) {
    return;
  }
  const content = [
    div("strong", {}, title),
    ...lines.map((line) => div("p", {}, line)),
  ];
  if (report) {
    content.push(div("pre", { class: "workflow-report" }, report));
  }
  card.querySelector(".workflow-feedback")?.remove();
  const feedback = div("div", { class: `workflow-feedback ${tone}` }, content);
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
