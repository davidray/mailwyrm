import unittest
from importlib import resources

from mailwyrm.app import (
    APP_MUTATION_HEADER,
    APP_MUTATION_HEADER_VALUE,
    _machine_bundle_clear_payload,
    _is_app_mutation_request,
    _query_bool,
    _query_int,
    _query_mailbox,
    _query_message_id,
    _query_workflow,
    _bundle_trash_plans,
    _request_bool,
    _request_mailbox,
    _request_string,
    _request_string_list,
    apply_archive_after_digest,
    apply_gmail_labels,
    apply_trash_after_digest,
    build_workflow_preview_payload,
    change_digest_category,
    classify_local_messages,
    create_app_server,
    mark_spam_messages,
    refresh_gmail_from_history,
    sync_gmail_messages,
)
from mailwyrm.actions import BundleTrashResult, SpamApplyResult
from mailwyrm.cli import build_parser
from mailwyrm.models import (
    AutomationPolicy,
    ClassificationRecord,
    DigestAuditEvent,
    MessageRecord,
)
from mailwyrm.gmail import GmailApiError, GmailLabel
from mailwyrm.store import MailwyrmState


def message(message_id: str, subject: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="Snippet",
        headers={"From": "Sender <sender@example.com>", "Subject": subject},
    )


def classification(message_id: str, *, suggested_actions=None) -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category="machine",
        machine_type="notification",
        importance="low",
        automation_safety="high",
        confidence=0.94,
        reason="Automated sender or subject pattern.",
        suggested_actions=suggested_actions or ["digest", "archive"],
        classifier_version="rules-v0",
    )


class AppTest(unittest.TestCase):
    def test_app_static_assets_are_packaged_with_mailwyrm(self) -> None:
        static_root = resources.files("mailwyrm").joinpath("static")

        self.assertIn("<title>Bookwyrm Mail</title>", static_root.joinpath("index.html").read_text())
        self.assertIn(
            'aria-label="Bookwyrm Mail correspondence views"',
            static_root.joinpath("index.html").read_text(),
        )
        self.assertTrue(
            static_root.joinpath("icons", "bookwyrm-mail-icon.png").is_file()
        )
        self.assertIn("Real People", static_root.joinpath("index.html").read_text())
        self.assertIn("A quieter place", static_root.joinpath("index.html").read_text())
        self.assertIn("Daily digest", static_root.joinpath("index.html").read_text())
        self.assertIn('data-tab="review"', static_root.joinpath("index.html").read_text())
        self.assertIn('id="review-tab-count"', static_root.joinpath("index.html").read_text())
        self.assertIn('data-tab="tools"', static_root.joinpath("index.html").read_text())
        self.assertIn("secondary-tab", static_root.joinpath("index.html").read_text())
        self.assertIn("tab-panel", static_root.joinpath("index.html").read_text())
        self.assertIn("profile-avatar", static_root.joinpath("index.html").read_text())
        self.assertIn("profile-popover", static_root.joinpath("index.html").read_text())
        self.assertNotIn("status-strip", static_root.joinpath("index.html").read_text())
        self.assertIn('id="metrics" hidden', static_root.joinpath("index.html").read_text())
        self.assertIn("human-lane", static_root.joinpath("index.html").read_text())
        self.assertIn("review-lane", static_root.joinpath("index.html").read_text())
        self.assertNotIn("cleanup-band", static_root.joinpath("index.html").read_text())
        self.assertIn("workflows", static_root.joinpath("index.html").read_text())
        tools_markup = static_root.joinpath("index.html").read_text().split(
            '<section class="tab-panel" id="tab-tools" hidden>',
            maxsplit=1,
        )[1]
        self.assertLess(
            tools_markup.index("Preview-first tools"),
            tools_markup.index("Action proposals"),
        )
        self.assertIn("/api/daily-cockpit", static_root.joinpath("app.js").read_text())
        self.assertIn("refreshCockpit", static_root.joinpath("app.js").read_text())
        self.assertIn("setRefreshState", static_root.joinpath("app.js").read_text())
        self.assertIn("refresh-success", static_root.joinpath("app.css").read_text())
        self.assertIn("renderReviewTabCount", static_root.joinpath("app.js").read_text())
        self.assertIn(".tab-count", static_root.joinpath("app.css").read_text())
        self.assertIn("/api/gmail-sync", static_root.joinpath("app.js").read_text())
        self.assertIn('params.set("all", "true")', static_root.joinpath("app.js").read_text())
        self.assertIn("workflow.process_all", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/gmail-labels/apply", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/spam-messages", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/archive-after-digest", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/trash-after-digest", static_root.joinpath("app.js").read_text())
        self.assertIn("confirmGmailMutation", static_root.joinpath("app.js").read_text())
        self.assertIn("activateTab", static_root.joinpath("app.js").read_text())
        self.assertIn("renderProfile", static_root.joinpath("app.js").read_text())
        self.assertIn("profileInitial", static_root.joinpath("app.js").read_text())
        self.assertIn("refreshProfileLines", static_root.joinpath("app.js").read_text())
        self.assertIn("refreshModeLabel", static_root.joinpath("app.js").read_text())
        self.assertIn("Gmail modified", static_root.joinpath("app.js").read_text())
        self.assertIn("options.showReason && item.reason", static_root.joinpath("app.js").read_text())
        self.assertIn("Real People", static_root.joinpath("app.js").read_text())
        self.assertIn("show_metrics", static_root.joinpath("app.js").read_text())
        self.assertIn("personGroupCard", static_root.joinpath("app.js").read_text())
        self.assertIn("conversationBadge", static_root.joinpath("app.js").read_text())
        self.assertIn("digestReassignmentSelect", static_root.joinpath("app.js").read_text())
        self.assertIn("reassignRealPeopleItemToDigest", static_root.joinpath("app.js").read_text())
        self.assertIn("pillClassName", static_root.joinpath("app.js").read_text())
        self.assertIn("personInitials", static_root.joinpath("app.js").read_text())
        self.assertIn("prominentSender", static_root.joinpath("app.js").read_text())
        self.assertIn("showAllLaneItems", static_root.joinpath("app.js").read_text())
        self.assertIn("showAllItems", static_root.joinpath("app.js").read_text())
        self.assertIn("review-sender", static_root.joinpath("app.css").read_text())
        self.assertIn("item-sender", static_root.joinpath("app.js").read_text())
        self.assertIn("item-body", static_root.joinpath("app.css").read_text())
        self.assertIn("digest-sender", static_root.joinpath("app.css").read_text())
        self.assertIn("lane-more", static_root.joinpath("app.css").read_text())
        self.assertIn("person-name", static_root.joinpath("app.js").read_text())
        self.assertIn("person-identity", static_root.joinpath("app.css").read_text())
        self.assertIn("profile-popover", static_root.joinpath("app.css").read_text())
        self.assertIn("person-avatar", static_root.joinpath("app.css").read_text())
        self.assertIn("person-group", static_root.joinpath("app.css").read_text())
        self.assertIn("human-reassign-select", static_root.joinpath("app.css").read_text())
        self.assertIn(".person-group:first-child", static_root.joinpath("app.css").read_text())
        self.assertNotIn("renderCleanup", static_root.joinpath("app.js").read_text())
        self.assertNotIn("cleanupHeading", static_root.joinpath("app.js").read_text())
        self.assertIn(".tabs", static_root.joinpath("app.css").read_text())
        self.assertIn(".secondary-tab", static_root.joinpath("app.css").read_text())
        self.assertNotIn("cleanup-band", static_root.joinpath("app.css").read_text())
        self.assertNotIn("copy-command", static_root.joinpath("app.js").read_text())
        self.assertNotIn("command-text", static_root.joinpath("app.js").read_text())
        self.assertNotIn("commands-panel", static_root.joinpath("index.html").read_text())
        self.assertIn("workflow-status", static_root.joinpath("app.js").read_text())
        self.assertIn("appActionButton", static_root.joinpath("app.js").read_text())
        self.assertIn("appActionEndpoints", static_root.joinpath("app.js").read_text())
        self.assertIn("workflowAppAction", static_root.joinpath("app.js").read_text())
        self.assertIn("workflow-feedback", static_root.joinpath("app.js").read_text())
        self.assertIn("workflow-feedback", static_root.joinpath("app.css").read_text())
        self.assertIn("workflow-report", static_root.joinpath("app.js").read_text())
        self.assertIn("workflow-report", static_root.joinpath("app.css").read_text())
        self.assertIn("Preview only. Gmail was not modified.", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/workflow-preview", static_root.joinpath("app.js").read_text())
        self.assertIn("revealPreviewPanel", static_root.joinpath("app.js").read_text())
        self.assertIn('activateTab("tools")', static_root.joinpath("app.js").read_text())
        self.assertIn("/api/message-detail", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/local-classify", static_root.joinpath("app.js").read_text())
        self.assertIn('"X-Mailwyrm-App": "local-ui"', static_root.joinpath("app.js").read_text())
        self.assertIn("/api/conversation-complete", static_root.joinpath("app.js").read_text())
        self.assertIn("COMPLETE_UNDO_DELAY_MS = 5000", static_root.joinpath("app.js").read_text())
        self.assertIn("scheduleCompleteConversation", static_root.joinpath("app.js").read_text())
        self.assertIn("undoCompleteConversation", static_root.joinpath("app.js").read_text())
        self.assertIn("completeConversation", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/gmail-refresh", static_root.joinpath("app.js").read_text())
        self.assertIn("refreshSuccessLabel", static_root.joinpath("app.js").read_text())
        self.assertIn('mode !== "error"', static_root.joinpath("app.js").read_text())
        self.assertIn('els.refresh.removeAttribute("title")', static_root.joinpath("app.js").read_text())
        self.assertIn("complete-conversation", static_root.joinpath("app.css").read_text())
        self.assertIn("undo-complete", static_root.joinpath("app.css").read_text())
        self.assertIn("preview-panel", static_root.joinpath("index.html").read_text())
        self.assertIn("detail-panel", static_root.joinpath("index.html").read_text())
        self.assertIn("Reading", static_root.joinpath("index.html").read_text())
        self.assertNotIn("view-detail", static_root.joinpath("app.js").read_text())
        self.assertNotIn("Details", static_root.joinpath("app.js").read_text())
        self.assertIn("replyPlaceholderButton", static_root.joinpath("app.js").read_text())
        self.assertIn("Draft replies are not enabled yet.", static_root.joinpath("app.js").read_text())
        self.assertIn("conversationSection", static_root.joinpath("app.js").read_text())
        self.assertIn("conversationOpenButton", static_root.joinpath("app.js").read_text())
        self.assertIn("closeDetailPanel", static_root.joinpath("app.js").read_text())
        self.assertIn('event.target.closest("#detail-panel")', static_root.joinpath("app.js").read_text())
        self.assertNotIn("function detailField", static_root.joinpath("app.js").read_text())
        self.assertIn("markdownBlock", static_root.joinpath("app.js").read_text())
        self.assertIn("inlineMarkdownFragment", static_root.joinpath("app.js").read_text())
        self.assertIn("markdownLinkLabel", static_root.joinpath("app.js").read_text())
        self.assertIn("markdown-link", static_root.joinpath("app.css").read_text())
        self.assertIn("--sage:", static_root.joinpath("app.css").read_text())
        self.assertIn('document.body.classList.add("reader-open")', static_root.joinpath("app.js").read_text())
        self.assertNotIn('els.detailPanel.scrollIntoView({ block: "start" })', static_root.joinpath("app.js").read_text())
        self.assertIn("reading-body", static_root.joinpath("app.css").read_text())
        self.assertIn("position: fixed", static_root.joinpath("app.css").read_text())
        self.assertIn("conversation-message", static_root.joinpath("app.css").read_text())
        self.assertIn("Review type:", static_root.joinpath("app.js").read_text())
        self.assertIn("correctionLine", static_root.joinpath("app.js").read_text())
        self.assertIn("noopener noreferrer", static_root.joinpath("app.js").read_text())
        self.assertIn("overflow: auto", static_root.joinpath("app.css").read_text())
        self.assertIn("run-local-action", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/review-resolution", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/machine-bundle/got-it", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/followup", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/read-later", static_root.joinpath("app.js").read_text())
        self.assertIn("machineBundleCard", static_root.joinpath("app.js").read_text())
        self.assertIn("bundle-feedback", static_root.joinpath("app.js").read_text())
        self.assertIn("bundle-feedback", static_root.joinpath("app.css").read_text())
        self.assertIn("data-machine-type", static_root.joinpath("app.js").read_text())
        self.assertIn("/api/digest-category", static_root.joinpath("app.js").read_text())
        self.assertIn("digestCategorySelect", static_root.joinpath("app.js").read_text())
        self.assertIn("digestMessageControls", static_root.joinpath("app.js").read_text())
        self.assertIn("digest-row-controls", static_root.joinpath("app.css").read_text())
        self.assertIn("digest-message-list", static_root.joinpath("app.css").read_text())
        self.assertIn("digest-row", static_root.joinpath("app.js").read_text())
        self.assertIn('class: "item digest-row"', static_root.joinpath("app.js").read_text())
        self.assertIn("digest-group-title", static_root.joinpath("app.css").read_text())
        self.assertIn("followupButton", static_root.joinpath("app.js").read_text())
        self.assertIn("readLaterButton", static_root.joinpath("app.js").read_text())
        self.assertIn("read-later-toggle", static_root.joinpath("app.css").read_text())
        self.assertIn("icon-toggle.saving", static_root.joinpath("app.css").read_text())
        self.assertNotIn("read-later-identity", static_root.joinpath("app.css").read_text())
        self.assertNotIn('"Removing"', static_root.joinpath("app.js").read_text())
        self.assertIn("sender_groups", static_root.joinpath("app.js").read_text())
        self.assertNotIn("follow-up needed", static_root.joinpath("app.js").read_text())
        self.assertNotIn("followup-identity", static_root.joinpath("app.css").read_text())
        self.assertIn("followup-toggle", static_root.joinpath("app.css").read_text())
        self.assertIn("bundle-got-it", static_root.joinpath("app.css").read_text())
        self.assertIn("reviewResolutionSection", static_root.joinpath("app.js").read_text())
        self.assertIn("inlineReviewControls", static_root.joinpath("app.js").read_text())
        self.assertIn("renderContextFeedback", static_root.joinpath("app.js").read_text())
        self.assertIn("context-feedback", static_root.joinpath("app.css").read_text())
        self.assertIn("User resolved this from the Review card.", static_root.joinpath("app.js").read_text())
        self.assertIn("machineTypeLabel", static_root.joinpath("app.js").read_text())
        self.assertIn("Spam", static_root.joinpath("app.js").read_text())
        self.assertNotIn('["protect", "Protect"', static_root.joinpath("app.js").read_text())
        self.assertNotIn('["archive", "Archive"', static_root.joinpath("app.js").read_text())
        self.assertNotIn('["trash", "Trash"', static_root.joinpath("app.js").read_text())
        self.assertIn("Real People", static_root.joinpath("app.js").read_text())
        self.assertIn("resolution-controls", static_root.joinpath("app.css").read_text())
        self.assertIn("inline-review-controls", static_root.joinpath("app.css").read_text())
        self.assertIn("showReason", static_root.joinpath("app.js").read_text())
        self.assertIn("-webkit-line-clamp: 2", static_root.joinpath("app.css").read_text())
        self.assertIn(
            "Only explicit actions update Gmail",
            static_root.joinpath("app.js").read_text(),
        )

    def test_query_int_accepts_zero_and_positive_values(self) -> None:
        self.assertEqual(_query_int({"limit": ["0"]}, "limit", 25), 0)
        self.assertEqual(_query_int({"limit": ["10"]}, "limit", 25), 10)
        self.assertEqual(_query_int({}, "limit", 25), 25)

    def test_query_int_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            _query_int({"limit": ["-1"]}, "limit", 25)

        with self.assertRaises(ValueError):
            _query_int({"limit": ["many"]}, "limit", 25)

    def test_query_mailbox_accepts_supported_mailboxes(self) -> None:
        self.assertEqual(_query_mailbox({}, "inbox"), "inbox")
        self.assertEqual(
            _query_mailbox({"mailbox": ["all-mail"]}, "inbox"),
            "all-mail",
        )
        self.assertEqual(_query_mailbox({"mailbox": ["trash"]}, "inbox"), "trash")

    def test_query_mailbox_rejects_unknown_mailboxes(self) -> None:
        with self.assertRaisesRegex(ValueError, "inbox, all-mail, trash"):
            _query_mailbox({"mailbox": ["spam"]}, "inbox")

        with self.assertRaisesRegex(ValueError, "inbox, all-mail, trash"):
            create_app_server(mailbox="spam")

    def test_query_bool_accepts_browser_boolean_values(self) -> None:
        self.assertTrue(_query_bool({"all": ["true"]}, "all"))
        self.assertTrue(_query_bool({"all": ["1"]}, "all"))
        self.assertFalse(_query_bool({}, "all"))
        self.assertFalse(_query_bool({"all": ["false"]}, "all"))

        with self.assertRaises(ValueError):
            _query_bool({"all": ["maybe"]}, "all")

    def test_query_workflow_accepts_preview_workflows(self) -> None:
        self.assertEqual(
            _query_workflow({"workflow": ["daily-preview"]}),
            "daily-preview",
        )
        self.assertEqual(_query_workflow({"workflow": ["labels"]}), "labels")
        self.assertEqual(_query_workflow({"workflow": ["archive"]}), "archive")
        self.assertEqual(_query_workflow({"workflow": ["trash"]}), "trash")

    def test_query_workflow_rejects_non_preview_workflows(self) -> None:
        with self.assertRaises(ValueError):
            _query_workflow({"workflow": ["sync"]})

    def test_query_message_id_requires_value(self) -> None:
        self.assertEqual(_query_message_id({"message_id": ["msg-1"]}), "msg-1")

        with self.assertRaises(ValueError):
            _query_message_id({})

    def test_app_parser_accepts_client_secret_for_cockpit_payload(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "app",
                "--client-secret",
                "/Users/dave/code/client_secret.json",
                "--show-metrics",
            ]
        )

        self.assertEqual(str(args.client_secret), "/Users/dave/code/client_secret.json")
        self.assertTrue(args.show_metrics)

    def test_build_workflow_preview_payload_renders_daily_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )

        payload = build_workflow_preview_payload(
            state,
            workflow="daily-preview",
            mailbox="inbox",
            limit=10,
        )

        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["title"], "Daily Workflow Preview")
        self.assertIn("No Gmail labels", payload["report"])
        self.assertIn("Mailbox scope: inbox", payload["report"])

    def test_build_workflow_preview_payload_renders_label_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )

        payload = build_workflow_preview_payload(
            state,
            workflow="labels",
            mailbox="inbox",
        )

        self.assertEqual(payload["title"], "Gmail Label Preview")
        self.assertIn("Mailwyrm/Machine", payload["report"])

    def test_build_workflow_preview_payload_renders_archive_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )

        payload = build_workflow_preview_payload(
            state,
            workflow="archive",
            mailbox="inbox",
        )

        self.assertEqual(payload["title"], "Mailbox Action Preview")
        self.assertIn("archive_after_digest", payload["report"])

    def test_build_workflow_preview_payload_renders_trash_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Copilot")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    suggested_actions=["digest", "trash"],
                )
            },
            digest_audit_events=[
                DigestAuditEvent(
                    message_id="msg-1",
                    digest_title_date="2026-05-26",
                    reason="Low-risk notification.",
                    classifier_version="rules-v0",
                    created_at="2026-05-26T00:00:00+00:00",
                )
            ],
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        payload = build_workflow_preview_payload(
            state,
            workflow="trash",
            mailbox="inbox",
        )

        self.assertEqual(payload["title"], "Trash Policy Preview")
        self.assertIn("Trash policy: enabled", payload["report"])
        self.assertIn("trash_after_digest", payload["report"])

    def test_classify_local_messages_classifies_unclassified_mailbox_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Receipt"),
                "msg-2": message("msg-2", "Already done"),
            },
            classifications={"msg-2": classification("msg-2")},
        )

        result = classify_local_messages(state, mailbox="inbox", limit=25)

        self.assertEqual(result["classified_messages"], 1)
        self.assertEqual(result["skipped_already_classified"], 1)
        self.assertFalse(result["mutates_gmail"])
        self.assertIn("msg-1", state.classifications)

    def test_classify_local_messages_respects_mailbox_and_limit(self) -> None:
        inbox = message("msg-1", "Inbox")
        archived = MessageRecord(
            id="msg-2",
            thread_id="thread-msg-2",
            history_id="10",
            internal_date="1710000000001",
            label_ids=[],
            snippet="Snippet",
            headers={"From": "Sender <sender@example.com>", "Subject": "Archived"},
        )
        state = MailwyrmState(messages={"msg-1": inbox, "msg-2": archived})

        result = classify_local_messages(state, mailbox="all-mail", limit=1)

        self.assertEqual(result["matched_messages"], 1)
        self.assertEqual(result["classified_messages"], 1)
        self.assertIn("msg-2", state.classifications)
        self.assertNotIn("msg-1", state.classifications)

    def test_classify_local_messages_refreshes_missing_review_type(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Security alert for your account"),
            },
            classifications={
                "msg-1": ClassificationRecord(
                    message_id="msg-1",
                    category="needs_review",
                    machine_type=None,
                    importance="high",
                    automation_safety="low",
                    confidence=0.74,
                    reason="Legacy classification.",
                    suggested_actions=["review", "protect"],
                    classifier_version="rules-v0",
                ),
            },
        )

        result = classify_local_messages(state, mailbox="inbox", limit=25)

        self.assertEqual(result["classified_messages"], 1)
        self.assertEqual(result["skipped_already_classified"], 0)
        self.assertEqual(state.classifications["msg-1"].review_type, "security")

    def test_classify_local_messages_treats_zero_limit_as_noop(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1", "Receipt")})

        result = classify_local_messages(state, mailbox="inbox", limit=0)

        self.assertEqual(result["matched_messages"], 0)
        self.assertEqual(result["classified_messages"], 0)
        self.assertFalse(result["mutated_local_state"])
        self.assertEqual(state.classifications, {})

    def test_sync_gmail_messages_returns_app_action_report(self) -> None:
        state = MailwyrmState()
        client = FakeAppSyncClient()

        result = sync_gmail_messages(client, state, mailbox="inbox", limit=None)

        self.assertEqual(result["title"], "Gmail Sync")
        self.assertEqual(result["mailbox"], "inbox")
        self.assertEqual(result["matched_messages"], 1)
        self.assertFalse(result["mutates_gmail"])
        self.assertIn("Synced 1 selected inbox message", result["message"])
        self.assertIn("Fetched the full selected mailbox scope.", result["report_lines"])
        self.assertIn("Gmail was not modified.", result["report_lines"])
        self.assertIn(
            "Stored bounded body text and up to 3 message(s) per selected thread for classification and summaries.",
            result["report_lines"],
        )
        self.assertIn("Selected Gmail messages: 1", result["report_lines"])
        self.assertIn("Stored local message records: 1", result["report_lines"])
        self.assertEqual(client.thread_ids, ["thread-1"])
        self.assertEqual(client.full_message_ids, [])
        self.assertIsNone(client.list_kwargs["max_results"])
        self.assertEqual(state.messages["msg-1"].body_text, "Body text")

    def test_refresh_gmail_from_history_reconciles_and_classifies_new_messages(
        self,
    ) -> None:
        state = MailwyrmState(
            history_id="100",
            account_email="user@example.com",
        )
        client = FakeAppSyncClient(
            history_response={
                "historyId": "105",
                "history": [{"messagesAdded": [{"message": {"id": "msg-2"}}]}],
            }
        )

        result = refresh_gmail_from_history(client, state, mailbox="inbox")

        self.assertEqual(result["title"], "Gmail Refresh")
        self.assertEqual(result["refresh_mode"], "history")
        self.assertEqual(result["history_records"], 1)
        self.assertEqual(result["messages_fetched"], 1)
        self.assertEqual(result["classified_messages"], 1)
        self.assertFalse(result["mutates_gmail"])
        self.assertIn("Updated from Gmail", result["message"])
        self.assertIn("Gmail history is up to date.", result["report_lines"])
        self.assertEqual(client.history_start_ids, ["100"])
        self.assertEqual(client.full_message_ids, ["msg-2"])
        self.assertEqual(state.history_id, "105")
        self.assertEqual(state.last_refresh["mode"], "history")
        self.assertEqual(state.last_refresh["history_records"], 1)
        self.assertEqual(state.last_refresh["messages_fetched"], 1)
        self.assertFalse(state.last_refresh["gmail_modified"])
        self.assertIn("msg-2", state.messages)
        self.assertIn("msg-2", state.classifications)

    def test_refresh_gmail_from_history_runs_full_sync_without_cursor(self) -> None:
        state = MailwyrmState()
        client = FakeAppSyncClient()

        result = refresh_gmail_from_history(client, state, mailbox="inbox")

        self.assertEqual(result["refresh_mode"], "first-sync")
        self.assertEqual(result["matched_messages"], 1)
        self.assertEqual(result["stored_messages"], 1)
        self.assertEqual(result["classified_messages"], 1)
        self.assertIn("No Gmail history cursor was available.", result["report_lines"])
        self.assertEqual(client.history_start_ids, [])
        self.assertEqual(client.thread_ids, ["thread-1"])
        self.assertEqual(state.last_refresh["mode"], "first-sync")
        self.assertEqual(state.last_refresh["messages_fetched"], 1)
        self.assertIn("msg-1", state.classifications)

    def test_refresh_gmail_from_history_falls_back_when_cursor_expires(self) -> None:
        state = MailwyrmState(history_id="100", last_sync_mailbox="inbox")
        client = FakeAppSyncClient(history_error=GmailApiError("expired", status_code=404))

        result = refresh_gmail_from_history(client, state, mailbox="inbox")

        self.assertEqual(result["refresh_mode"], "history-expired")
        self.assertEqual(result["matched_messages"], 1)
        self.assertEqual(result["classified_messages"], 1)
        self.assertIn("The stored Gmail history cursor had expired.", result["report_lines"])
        self.assertEqual(client.history_start_ids, ["100"])
        self.assertEqual(client.thread_ids, ["thread-1"])
        self.assertEqual(state.last_refresh["mode"], "history-expired")

    def test_apply_gmail_labels_returns_preview_report_and_audits(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )
        client = FakeAppModifyClient()

        result = apply_gmail_labels(client, state, mailbox="inbox", limit=25)

        self.assertEqual(result["title"], "Gmail Labels Applied")
        self.assertEqual(result["applied"], 1)
        self.assertTrue(result["mutates_gmail"])
        self.assertIn("Mailwyrm/Machine", result["report"])
        self.assertEqual(client.added, [("msg-1", ["label-machine"])])
        self.assertEqual(state.label_audit_events[0].action, "add_labels")

    def test_apply_archive_after_digest_uses_existing_policy_gates(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Receipt"),
                "msg-2": message("msg-2", "Not digested"),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
            digest_audit_events=[
                DigestAuditEvent(
                    message_id="msg-1",
                    digest_title_date="2026-05-26",
                    reason="Low-risk machine mail.",
                    classifier_version="rules-v0",
                    created_at="2026-05-26T00:00:00+00:00",
                )
            ],
        )
        client = FakeAppModifyClient()

        result = apply_archive_after_digest(client, state, mailbox="inbox", limit=25)

        self.assertEqual(result["title"], "Archive Applied")
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["skipped_not_digested"], 1)
        self.assertIn("Gmail will be modified after this preview.", result["report"])
        self.assertEqual(client.removed, [("msg-1", ["INBOX"])])
        self.assertNotIn("INBOX", state.messages["msg-1"].label_ids)
        self.assertIn("INBOX", state.messages["msg-2"].label_ids)

    def test_apply_trash_after_digest_uses_policy_gate(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Copilot")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    suggested_actions=["digest", "trash"],
                )
            },
            digest_audit_events=[
                DigestAuditEvent(
                    message_id="msg-1",
                    digest_title_date="2026-05-26",
                    reason="Low-risk notification.",
                    classifier_version="rules-v0",
                    created_at="2026-05-26T00:00:00+00:00",
                )
            ],
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )
        client = FakeAppModifyClient()

        result = apply_trash_after_digest(client, state, mailbox="inbox", limit=25)

        self.assertEqual(result["title"], "Trash Applied")
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["skipped_policy_disabled"], 0)
        self.assertIn("Trash policy: enabled", result["report"])
        self.assertEqual(client.trashed, ["msg-1"])
        self.assertEqual(state.messages["msg-1"].label_ids, ["TRASH"])

    def test_change_digest_category_records_local_corrections(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Promo")},
            classifications={"msg-1": classification("msg-1")},
        )

        result = change_digest_category(
            state,
            message_ids=["msg-1"],
            machine_type="news",
            reason="User moved this digest row to another category.",
        )

        self.assertEqual(result["changed"], 1)
        self.assertEqual(state.corrections["msg-1"].category, "machine")
        self.assertEqual(state.corrections["msg-1"].machine_type, "news")
        self.assertEqual(
            state.corrections["msg-1"].reason,
            "User moved this digest row to another category.",
        )

    def test_change_digest_category_can_reassign_human_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Personal thread"),
                "msg-2": message("msg-2", "Personal thread"),
            },
            classifications={
                "msg-1": ClassificationRecord(
                    message_id="msg-1",
                    category="human",
                    machine_type=None,
                    importance="medium",
                    automation_safety="low",
                    confidence=0.82,
                    reason="Looks like personal correspondence.",
                    suggested_actions=[],
                    classifier_version="rules-v0",
                ),
                "msg-2": ClassificationRecord(
                    message_id="msg-2",
                    category="human",
                    machine_type=None,
                    importance="medium",
                    automation_safety="low",
                    confidence=0.78,
                    reason="Looks like personal correspondence.",
                    suggested_actions=[],
                    classifier_version="rules-v0",
                ),
            },
        )

        result = change_digest_category(
            state,
            message_ids=["msg-1", "msg-2"],
            machine_type="product_community",
            reason="User moved this correspondence conversation to a digest category.",
        )

        self.assertEqual(result["changed"], 2)
        self.assertEqual(state.corrections["msg-1"].category, "machine")
        self.assertEqual(state.corrections["msg-2"].machine_type, "product_community")

    def test_mark_spam_messages_records_correction_and_marks_gmail_spam(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-msg-1",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["INBOX"],
                    snippet="Snippet",
                    headers={
                        "From": "Sender <sender@example.com>",
                        "Subject": "Promo",
                        "List-Unsubscribe": "<mailto:unsubscribe@example.com>",
                    },
                )
            },
            classifications={"msg-1": classification("msg-1")},
        )
        client = FakeAppModifyClient()

        result = mark_spam_messages(
            client,
            state,
            message_ids=["msg-1"],
            reason="User resolved this Review card as Spam.",
        )

        self.assertEqual(result["title"], "Spam Marked")
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["unsubscribe_available"], 1)
        self.assertEqual(client.spammed, ["msg-1"])
        self.assertEqual(state.corrections["msg-1"].machine_type, "spam")
        self.assertEqual(state.messages["msg-1"].label_ids, ["SPAM"])

    def test_spam_bundle_payload_reports_spam_skip_separately_from_trash(self) -> None:
        payload = _machine_bundle_clear_payload(
            machine_type="spam",
            bundle_title="Spam",
            result=SpamApplyResult(
                applied=0,
                skipped_already_spam=2,
                unsubscribe_available=1,
            ),
        )

        self.assertEqual(payload["skipped_already_trashed"], 0)
        self.assertEqual(payload["skipped_already_spam"], 2)
        self.assertEqual(payload["unsubscribe_available"], 1)

    def test_trash_bundle_payload_keeps_trash_skip_field(self) -> None:
        payload = _machine_bundle_clear_payload(
            machine_type="news",
            bundle_title="News",
            result=BundleTrashResult(applied=0, skipped_already_trashed=2),
        )

        self.assertEqual(payload["skipped_already_trashed"], 2)
        self.assertEqual(payload["skipped_already_spam"], 0)

    def test_app_mutation_request_requires_expected_header(self) -> None:
        self.assertFalse(_is_app_mutation_request({}))
        self.assertFalse(_is_app_mutation_request({APP_MUTATION_HEADER: "other"}))
        self.assertTrue(
            _is_app_mutation_request({APP_MUTATION_HEADER: APP_MUTATION_HEADER_VALUE})
        )

    def test_request_string_helpers_validate_review_resolution_inputs(self) -> None:
        self.assertEqual(_request_string({"message_id": "msg-1"}, "message_id"), "msg-1")
        self.assertEqual(_request_mailbox({"mailbox": "all-mail"}, "inbox"), "all-mail")
        self.assertEqual(_request_mailbox({}, "inbox"), "inbox")
        self.assertEqual(
            _request_string_list({"message_ids": ["msg-1"]}, "message_ids"),
            ["msg-1"],
        )
        self.assertTrue(_request_bool({"followup": True}, "followup"))

        with self.assertRaises(ValueError):
            _request_string({}, "message_id")

        with self.assertRaises(ValueError):
            _request_mailbox({"mailbox": "spam"}, "inbox")

        with self.assertRaises(ValueError):
            _request_string_list({"message_ids": []}, "message_ids")

        with self.assertRaises(ValueError):
            _request_bool({"followup": "true"}, "followup")

    def test_bundle_trash_plans_select_machine_bundle_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Top story"),
                "msg-2": message("msg-2", "Receipt"),
            },
            classifications={
                "msg-1": ClassificationRecord(
                    message_id="msg-1",
                    category="machine",
                    machine_type="news",
                    importance="low",
                    automation_safety="high",
                    confidence=0.95,
                    reason="News digest.",
                    suggested_actions=["digest"],
                    classifier_version="rules-v0",
                ),
                "msg-2": ClassificationRecord(
                    message_id="msg-2",
                    category="machine",
                    machine_type="transactional",
                    importance="medium",
                    automation_safety="medium",
                    confidence=0.82,
                    reason="Receipt.",
                    suggested_actions=["digest"],
                    classifier_version="rules-v0",
                ),
            },
        )

        plans = _bundle_trash_plans(state, "news", mailbox="inbox")

        self.assertEqual([plan.message.id for plan in plans], ["msg-1"])
        self.assertEqual(plans[0].action, "trash_after_digest")

    def test_classify_local_messages_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            classify_local_messages(MailwyrmState(), mailbox="spam")

        with self.assertRaises(ValueError):
            classify_local_messages(MailwyrmState(), limit=-1)


class FakeAppSyncClient:
    def __init__(self, *, history_response=None, history_error=None) -> None:
        self.full_message_ids: list[str] = []
        self.thread_ids: list[str] = []
        self.history_start_ids: list[str] = []
        self.list_kwargs = {}
        self.history_response = history_response
        self.history_error = history_error

    def profile(self):
        return {"emailAddress": "user@example.com", "historyId": "42"}

    def list_messages(self, **kwargs):
        self.list_kwargs = kwargs
        return [{"id": "msg-1", "threadId": "thread-1"}]

    def list_history(self, *, start_history_id, page_token=None):
        self.history_start_ids.append(start_history_id)
        if self.history_error is not None:
            raise self.history_error
        if self.history_response is not None:
            return self.history_response
        return {"historyId": "42", "history": []}

    def get_message_full(self, message_id):
        self.full_message_ids.append(message_id)
        return self._message(message_id)

    def get_thread_full(self, thread_id):
        self.thread_ids.append(thread_id)
        return {"id": thread_id, "messages": [self._message("msg-1")]}

    def _message(self, message_id):
        return {
            "id": message_id,
            "threadId": "thread-1",
            "historyId": "10",
            "internalDate": "1710000000000",
            "labelIds": ["INBOX"],
            "snippet": "Snippet",
            "payload": {
                "headers": [{"name": "Subject", "value": "Hello"}],
                "mimeType": "text/plain",
                "body": {"data": "Qm9keSB0ZXh0"},
            },
        }


class FakeAppModifyClient:
    def __init__(self) -> None:
        self.added: list[tuple[str, list[str]]] = []
        self.removed: list[tuple[str, list[str]]] = []
        self.trashed: list[str] = []
        self.spammed: list[str] = []

    def ensure_mailwyrm_labels(self, label_names=None):
        labels = {
            "Mailwyrm/Human": GmailLabel(id="label-human", name="Mailwyrm/Human"),
            "Mailwyrm/Machine": GmailLabel(id="label-machine", name="Mailwyrm/Machine"),
            "Mailwyrm/Needs Review": GmailLabel(
                id="label-review",
                name="Mailwyrm/Needs Review",
            ),
            "Mailwyrm/Protected": GmailLabel(
                id="label-protected",
                name="Mailwyrm/Protected",
            ),
        }
        if label_names is None:
            return labels
        return {label_name: labels[label_name] for label_name in label_names}

    def add_labels_to_message(self, message_id: str, label_ids: list[str]) -> None:
        self.added.append((message_id, label_ids))

    def remove_labels_from_message(self, message_id: str, label_ids: list[str]) -> None:
        self.removed.append((message_id, label_ids))

    def trash_message(self, message_id: str) -> None:
        self.trashed.append(message_id)

    def mark_message_spam(self, message_id: str) -> None:
        self.spammed.append(message_id)
