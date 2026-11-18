import React, { useCallback, useState, useEffect, useRef } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking, TextInput, Alert } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../context/AuthContext";
import { colors, isBeforeCurrentCycle, SA_BANKS, BANK_ACCOUNT_TYPES } from "../theme";
import NotificationBell from "../components/NotificationBell";
import GradientBackground from "../components/GradientBackground";
import Dropdown from "../components/Dropdown";
import {
  ApiError,
  fetchMyTutoringRequests,
  fetchNotificationsUnreadCount,
  tutoringCheckoutUrl,
  confirmTutoringSessionAsLearner,
  respondToTimeProposal,
  withdrawTutoringRequest,
  cancelTutoringSessionAsLearner,
  reallocateAfterTutorCancellation,
  requestRefundForCancelledSession,
  submitRefundBankDetails,
  checkInToSessionAsLearner,
  checkOutOfSessionAsLearner,
  reportNoShowAsLearner,
  TutoringRequest,
  Badge,
} from "../api/client";

const BADGE_COLORS: Record<string, string> = { bronze: "#cd7f32", silver: "#9aa0a6", gold: "#eda100" };

// Whichever timestamp actually closed this request, by status.
function closedAtFor(r: TutoringRequest): string | null {
  if (r.status === "completed") return r.completed_at;
  if (r.status === "cancelled") return r.cancelled_at;
  if (r.status === "lapsed") return r.lapsed_at;
  return null;
}

// Same automatic, calendar-based "clear session history each payment
// cycle" as TutorHomeScreen's own isHiddenHistory - an active (still
// open) request is never hidden, only a finished one from an
// already-closed cycle. Nothing is deleted: lifetimeStats above comes
// from the backend's own unfiltered count, so it's unaffected.
function isHiddenHistory(r: TutoringRequest): boolean {
  const group = groupForStatus(r.status);
  if (group !== "completed" && group !== "cancelled" && group !== "lapsed") return false;
  return isBeforeCurrentCycle(closedAtFor(r));
}

// Same hash-by-name palette as the tutor Jobs screen's subject avatars -
// requests can carry any subject string, so there's no fixed catalog to
// hand-map from.
const AVATAR_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];

// Mirrors backend/tutoring.py's LATE_CANCELLATION_PENALTY_PERCENT - used
// here purely to show the fee amount in the confirmation prompt before
// the API call; the backend enforces the real cutoff/percentage either way.
const LATE_CANCELLATION_PENALTY_PERCENT = 30;
function colorForSubject(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    // Always render in SAST (fixed UTC+2) regardless of the device's own
    // timezone, matching how the date/time was originally picked.
    return new Date(iso).toLocaleString("en-ZA", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      timeZone: "Africa/Johannesburg",
    });
  } catch {
    return iso;
  }
}

// Mirrors backend/tutoring.py's cancel_accepted_session, which now
// rejects a cancellation once a session's scheduled time has passed -
// hides the button rather than letting someone tap it just to see an
// error.
function hasSessionStarted(scheduledAt: string | null): boolean {
  if (!scheduledAt) return false;
  return new Date(scheduledAt).getTime() <= Date.now();
}

const STATUS_COLOR: Record<TutoringRequest["status"], string> = {
  requested: colors.textSecondary,
  time_proposed: "#eda100",
  admin_proposed: colors.textSecondary,
  awaiting_payment: "#eda100",
  confirmed: colors.primary,
  tutor_cancelled: colors.error,
  completed: colors.success,
  cancelled: colors.error,
  lapsed: colors.error,
};

type SessionGroup = "active" | "upcoming" | "completed" | "cancelled" | "lapsed";

// Keeps cancelled/lapsed sessions out of the same list as upcoming ones -
// previously everything rendered in one flat list regardless of status,
// which a tester flagged as confusing ("don't mix these two"). Paid
// sessions just waiting for their date ("confirmed") get their own
// "upcoming" group instead of sitting in the same "active" bucket as a
// request still awaiting payment or a tutor's acceptance - those two
// situations need genuinely different attention from the learner.
function groupForStatus(status: TutoringRequest["status"]): SessionGroup {
  if (status === "cancelled") return "cancelled";
  if (status === "lapsed") return "lapsed";
  if (status === "completed") return "completed";
  if (status === "confirmed") return "upcoming";
  return "active"; // requested, time_proposed, admin_proposed, awaiting_payment, tutor_cancelled
}

const GROUP_TABS: { key: SessionGroup; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "upcoming", label: "Upcoming" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "lapsed", label: "Lapsed" },
];

const GROUP_EMPTY_LABEL: Record<SessionGroup, string> = {
  active: "No requests awaiting payment or acceptance.",
  upcoming: "No upcoming paid sessions.",
  completed: "No completed sessions yet.",
  cancelled: "No cancelled sessions.",
  lapsed: "No lapsed sessions.",
};

// Built from plain Views (no SVG dependency, no emoji) - same icon
// language as the rest of this redesign pass.
function GroupTabIcon({ name, size = 20, color }: { name: SessionGroup; size?: number; color: string }) {
  const box = { width: size, height: size, alignItems: "center" as const, justifyContent: "center" as const, position: "relative" as const };
  switch (name) {
    case "active":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.82, borderRadius: 999, borderWidth: 1.6, borderColor: color }} />
          <View style={{ position: "absolute", width: 1.4, height: size * 0.26, backgroundColor: color, top: size * 0.16, borderRadius: 1 }} />
          <View style={{ position: "absolute", width: size * 0.2, height: 1.4, backgroundColor: color, borderRadius: 1 }} />
        </View>
      );
    case "upcoming":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.7, borderWidth: 1.6, borderColor: color, borderRadius: 3 }}>
            <View style={{ height: size * 0.2, borderBottomWidth: 1.6, borderBottomColor: color }} />
          </View>
        </View>
      );
    case "completed":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.82, borderRadius: 999, borderWidth: 1.6, borderColor: color }} />
          <View
            style={{
              position: "absolute",
              width: size * 0.16,
              height: 1.6,
              backgroundColor: color,
              borderRadius: 1,
              left: size * 0.28,
              top: size * 0.52,
              transform: [{ rotate: "45deg" }],
            }}
          />
          <View
            style={{
              position: "absolute",
              width: size * 0.3,
              height: 1.6,
              backgroundColor: color,
              borderRadius: 1,
              left: size * 0.36,
              top: size * 0.44,
              transform: [{ rotate: "-45deg" }],
            }}
          />
        </View>
      );
    case "cancelled":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.82, borderRadius: 999, borderWidth: 1.6, borderColor: color }} />
          <View style={{ position: "absolute", width: size * 0.42, height: 1.6, backgroundColor: color, borderRadius: 1, transform: [{ rotate: "45deg" }] }} />
          <View style={{ position: "absolute", width: size * 0.42, height: 1.6, backgroundColor: color, borderRadius: 1, transform: [{ rotate: "-45deg" }] }} />
        </View>
      );
    case "lapsed":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.82, borderRadius: 999, borderWidth: 1.6, borderColor: color }} />
          <View style={{ position: "absolute", width: size * 0.58, height: 1.6, backgroundColor: color, borderRadius: 1, transform: [{ rotate: "45deg" }] }} />
        </View>
      );
    default:
      return null;
  }
}

function StarPicker({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <View style={styles.starRow}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable key={n} onPress={() => onChange(n)}>
          <Text style={styles.star}>{n <= value ? "⭐" : "☆"}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export default function MyTutoringRequestsScreen({ navigation, route }: any) {
  const { token } = useAuth();
  const insets = useSafeAreaInsets();
  const [unreadCount, setUnreadCount] = useState(0);
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  // Lifetime standing - unaffected by this screen's own cycle-based
  // history filtering below (see theme.ts's isBeforeCurrentCycle).
  const [lifetimeStats, setLifetimeStats] = useState<{
    completed_count: number; average_rating: number | null; badge: Badge;
  } | null>(null);
  // Screen-wide (load failures only, nothing session-specific to attach
  // it to) - shown at the top. Per-session action errors (confirm,
  // withdraw, cancel, reallocate, refund) use actionErrors below instead:
  // those used to all funnel into this SAME error, rendered only once at
  // the top of the whole scroll - so a "can't cancel within 24 hours"
  // triggered by a session near the bottom of a long list was invisible
  // unless the learner scrolled all the way back up, and looked like the
  // button just wasn't responding.
  const [error, setError] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  function setActionError(requestId: number, message: string | null) {
    setActionErrors((prev) => {
      const next = { ...prev };
      if (message) next[requestId] = message;
      else delete next[requestId];
      return next;
    });
  }
  const [ratingDraft, setRatingDraft] = useState<Record<number, number>>({});
  const [commentDraft, setCommentDraft] = useState<Record<number, string>>({});
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [respondingId, setRespondingId] = useState<number | null>(null);
  const [withdrawingId, setWithdrawingId] = useState<number | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [cancelReasonId, setCancelReasonId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [reallocatingId, setReallocatingId] = useState<number | null>(null);
  const [refundingId, setRefundingId] = useState<number | null>(null);
  const [checkingInId, setCheckingInId] = useState<number | null>(null);
  const [reportingNoShowId, setReportingNoShowId] = useState<number | null>(null);
  // Draft state for the "where should we send your refund" form that
  // appears once refund_requested_at is set but refund_bank_details_
  // submitted_at isn't yet - keyed per request id the same way
  // ratingDraft/commentDraft are, since a learner could in principle
  // have more than one pending refund at once.
  const [bankDraft, setBankDraft] = useState<Record<number, {
    bankName: string; bankNameOther: string; branchCode: string; accountNumber: string;
    accountType: string; accountTypeOther: string; accountHolder: string; confirmed: boolean;
  }>>({});
  function setBankDraftField(requestId: number, field: string, value: string | boolean) {
    setBankDraft((prev) => ({
      ...prev,
      [requestId]: {
        bankName: "", bankNameOther: "", branchCode: "", accountNumber: "",
        accountType: "", accountTypeOther: "", accountHolder: "", confirmed: false,
        ...prev[requestId],
        [field]: value,
      },
    }));
  }
  const [submittingBankDetailsId, setSubmittingBankDetailsId] = useState<number | null>(null);
  const [group, setGroup] = useState<SessionGroup>("active");
  // Set when PayFast's checkout redirects back via the malita://tutoring
  // deep link (see api_server.py's /billing/return?target=tutoring) -
  // the learner is shown a "confirming your payment" state for just this
  // one request instead of the normal "Pay Now" button, since PayFast's
  // own server-to-server webhook (the thing that actually flips the
  // request to "confirmed") can easily arrive a few seconds AFTER this
  // redirect, so a plain refresh-on-focus often still read
  // "awaiting_payment" and looked like the payment hadn't gone through.
  const [processingPaymentId, setProcessingPaymentId] = useState<number | null>(null);
  const pollAttemptsRef = useRef(0);

  const load = useCallback(() => {
    if (!token) return;
    fetchMyTutoringRequests(token)
      .then((res) => {
        setRequests(res.requests);
        setLifetimeStats({
          completed_count: res.completed_count, average_rating: res.average_rating, badge: res.badge,
        });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your requests."));
  }, [token]);

  // Refreshes every time this screen regains focus - in particular, when
  // PayFast's checkout redirects back into the app via the malita://
  // tutoring deep link (see RootNavigator's linking config and
  // api_server.py's /billing/return?target=tutoring), this is what picks
  // up the newly-confirmed status without needing to restart the app.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      fetchNotificationsUnreadCount(token).then((res) => setUnreadCount(res.count)).catch(() => {});
    }, [token])
  );

  // Captures the deep link's own params (upgraded=1&request_id=...) the
  // moment they arrive, and clears them off the route immediately -
  // otherwise re-focusing this screen later (e.g. navigating away and
  // back) would see the same params still sitting there and incorrectly
  // re-enter "confirming your payment" for a request that's long since
  // settled one way or the other.
  useEffect(() => {
    const incomingRequestId = route?.params?.request_id;
    if (route?.params?.upgraded === "1" && incomingRequestId != null) {
      const id = Number(incomingRequestId);
      if (!Number.isNaN(id)) {
        setProcessingPaymentId(id);
        pollAttemptsRef.current = 0;
      }
    }
    if (route?.params?.upgraded != null || route?.params?.cancelled != null || incomingRequestId != null) {
      navigation.setParams({ upgraded: undefined, cancelled: undefined, request_id: undefined });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route?.params?.upgraded, route?.params?.request_id]);

  // Polls every 2s (up to 30s) while waiting for PayFast's webhook to
  // actually land and flip the request to "confirmed" - the effect
  // below watching `requests` is what normally ends this early, the
  // moment the status changes; this cap is just so a learner is never
  // stuck on "confirming" forever if the webhook is unusually slow or
  // never arrives (they can still see/retry normally once it clears).
  useEffect(() => {
    if (processingPaymentId == null) return;
    const interval = setInterval(() => {
      pollAttemptsRef.current += 1;
      load();
      if (pollAttemptsRef.current >= 15) {
        setProcessingPaymentId(null);
      }
    }, 2000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [processingPaymentId]);

  useEffect(() => {
    if (processingPaymentId == null || !requests) return;
    const match = requests.find((r) => r.id === processingPaymentId);
    if (match && match.status !== "awaiting_payment") {
      setProcessingPaymentId(null);
    }
  }, [requests, processingPaymentId]);

  function handlePay(requestId: number) {
    if (!token) return;
    Linking.openURL(tutoringCheckoutUrl(token, requestId));
  }

  async function handleConfirm(requestId: number) {
    if (!token) return;
    const rating = ratingDraft[requestId];
    if (!rating) {
      setActionError(requestId, "Please pick a rating (tap a star) before confirming.");
      return;
    }
    setConfirmingId(requestId);
    setActionError(requestId, null);
    try {
      await confirmTutoringSessionAsLearner(token, requestId, rating, commentDraft[requestId] || "");
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not confirm this session.");
    } finally {
      setConfirmingId(null);
    }
  }

  async function handleRespond(requestId: number, accept: boolean) {
    if (!token) return;
    setRespondingId(requestId);
    setActionError(requestId, null);
    try {
      await respondToTimeProposal(token, requestId, accept);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not record your response.");
    } finally {
      setRespondingId(null);
    }
  }

  function confirmWithdraw(requestId: number) {
    Alert.alert(
      "Withdraw this request?",
      "This can't be undone - you'd need to submit a new request if you change your mind.",
      [
        { text: "Never mind", style: "cancel" },
        { text: "Withdraw", style: "destructive", onPress: () => handleWithdraw(requestId) },
      ]
    );
  }

  async function handleWithdraw(requestId: number) {
    if (!token) return;
    setWithdrawingId(requestId);
    setActionError(requestId, null);
    try {
      await withdrawTutoringRequest(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not withdraw this request.");
    } finally {
      setWithdrawingId(null);
    }
  }

  async function handleCancel(requestId: number, confirmLateCancellation: boolean = false) {
    if (!token) return;
    setCancelingId(requestId);
    setActionError(requestId, null);
    try {
      await cancelTutoringSessionAsLearner(token, requestId, cancelReason.trim(), confirmLateCancellation);
      setCancelReasonId(null);
      setCancelReason("");
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not cancel this session.");
    } finally {
      setCancelingId(null);
    }
  }

  // Cancelling a PAID session within 24 hours of its start costs a late-
  // cancellation fee (see backend/tutoring.py's cancel_accepted_session/
  // LATE_CANCELLATION_PENALTY_PERCENT) - warn and get explicit agreement
  // BEFORE calling the API with confirmLateCancellation, rather than
  // letting the fee apply silently. Computed client-side purely to show
  // the number early; the backend enforces the same cutoff/fee either way.
  function confirmCancelWithLateFeeCheck(r: TutoringRequest) {
    const isPaid = r.status === "confirmed";
    const isLate = !!r.scheduled_at && new Date(r.scheduled_at).getTime() - Date.now() < 24 * 60 * 60 * 1000;
    if (isPaid && isLate && r.price_zar != null) {
      const fee = Math.round(r.price_zar * LATE_CANCELLATION_PENALTY_PERCENT) / 100;
      const refund = Math.round((r.price_zar - fee) * 100) / 100;
      Alert.alert(
        "Cancel within 24 hours?",
        `This session is less than 24 hours away. Cancelling now applies Malita's ${LATE_CANCELLATION_PENALTY_PERCENT}% ` +
          `late-cancellation fee - you'll be refunded R${refund.toFixed(2)} instead of the full R${r.price_zar.toFixed(2)}.`,
        [
          { text: "Never mind", style: "cancel" },
          { text: "Cancel anyway", style: "destructive", onPress: () => handleCancel(r.id, true) },
        ]
      );
    } else {
      handleCancel(r.id);
    }
  }

  async function handleReallocate(requestId: number) {
    if (!token) return;
    setReallocatingId(requestId);
    setActionError(requestId, null);
    try {
      await reallocateAfterTutorCancellation(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not reopen this request.");
    } finally {
      setReallocatingId(null);
    }
  }

  function confirmRequestRefund(requestId: number) {
    Alert.alert(
      "Request a refund?",
      "We'll stop looking for another tutor and arrange your refund instead.",
      [
        { text: "Never mind", style: "cancel" },
        { text: "Request Refund", style: "destructive", onPress: () => handleRequestRefund(requestId) },
      ]
    );
  }

  async function handleRequestRefund(requestId: number) {
    if (!token) return;
    setRefundingId(requestId);
    setActionError(requestId, null);
    try {
      await requestRefundForCancelledSession(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not request a refund for this session.");
    } finally {
      setRefundingId(null);
    }
  }

  async function handleCheckIn(requestId: number) {
    if (!token) return;
    setCheckingInId(requestId);
    setActionError(requestId, null);
    try {
      await checkInToSessionAsLearner(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not check you in.");
    } finally {
      setCheckingInId(null);
    }
  }

  async function handleCheckOut(requestId: number) {
    if (!token) return;
    setCheckingInId(requestId);
    setActionError(requestId, null);
    try {
      await checkOutOfSessionAsLearner(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not check you out.");
    } finally {
      setCheckingInId(null);
    }
  }

  function confirmReportNoShow(requestId: number) {
    Alert.alert(
      "Report that your tutor didn't show up?",
      "If you checked in and waited at least 15 minutes with no sign of your tutor, this can refund you in full right away. " +
        "Otherwise Malita will review it.",
      [
        { text: "Never mind", style: "cancel" },
        { text: "Report No-Show", style: "destructive", onPress: () => handleReportNoShow(requestId) },
      ]
    );
  }

  async function handleReportNoShow(requestId: number) {
    if (!token) return;
    setReportingNoShowId(requestId);
    setActionError(requestId, null);
    try {
      await reportNoShowAsLearner(token, requestId);
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not report this.");
    } finally {
      setReportingNoShowId(null);
    }
  }

  async function handleSubmitBankDetails(requestId: number) {
    if (!token) return;
    const d = bankDraft[requestId];
    if (!d || !d.confirmed) {
      setActionError(requestId, "Please confirm the bank details are correct before submitting.");
      return;
    }
    const bankName = d.bankName === "Other" ? d.bankNameOther.trim() : d.bankName;
    const accountType = d.accountType === "Other" ? d.accountTypeOther.trim() : d.accountType;
    if (!bankName || !d.branchCode.trim() || !d.accountNumber.trim() || !accountType || !d.accountHolder.trim()) {
      setActionError(requestId, "Please fill in every banking detail field.");
      return;
    }
    setSubmittingBankDetailsId(requestId);
    setActionError(requestId, null);
    try {
      await submitRefundBankDetails(token, requestId, {
        bank_name: bankName,
        branch_code: d.branchCode.trim(),
        account_number: d.accountNumber.trim(),
        account_type: accountType,
        account_holder: d.accountHolder.trim(),
      });
      load();
    } catch (e) {
      setActionError(requestId, e instanceof ApiError ? e.message : "Could not submit your bank details.");
    } finally {
      setSubmittingBankDetailsId(null);
    }
  }

  // Everything still open, plus only this cycle's finished requests -
  // last cycle's completed/cancelled/lapsed ones are still in
  // `requests` (lifetimeStats needs them), just not shown here any more.
  const visibleRequests = (requests ?? []).filter((r) => !isHiddenHistory(r));
  const activeCount = visibleRequests.filter((r) => groupForStatus(r.status) === "active").length;
  const paymentDueCount = visibleRequests.filter((r) => r.status === "awaiting_payment").length;

  return (
    <GradientBackground style={styles.screen}>
    <ScrollView style={styles.scrollView} contentContainerStyle={[styles.container, { paddingTop: insets.top + 20 }]}>
      <View style={styles.headerRow}>
        <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
          <Text style={styles.backLinkText}>‹ Back to Home</Text>
        </Pressable>
        <NotificationBell
          count={unreadCount}
          onPress={() => navigation.navigate("Notifications")}
          color={colors.text}
          size={22}
        />
      </View>
      <Text style={styles.title}>My Requests</Text>

      {lifetimeStats && lifetimeStats.completed_count > 0 && (
        <View style={styles.standingCard}>
          <View style={styles.standingRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.standingLabel}>Lifetime</Text>
              <Text style={styles.standingValue}>
                {lifetimeStats.completed_count} session{lifetimeStats.completed_count === 1 ? "" : "s"} completed
                {lifetimeStats.average_rating != null ? ` · ${lifetimeStats.average_rating.toFixed(1)}★ avg` : ""}
              </Text>
            </View>
            {lifetimeStats.badge ? (
              <View style={[styles.badgePill, { backgroundColor: BADGE_COLORS[lifetimeStats.badge] }]}>
                <Text style={styles.badgePillText}>{lifetimeStats.badge.toUpperCase()}</Text>
              </View>
            ) : null}
          </View>
        </View>
      )}

      {requests && requests.length > 0 && (
        <View style={styles.statCard}>
          <View style={styles.statCardRow}>
            <View>
              <Text style={styles.statLabel}>Active requests</Text>
              <Text style={styles.statValue}>{activeCount}</Text>
            </View>
            {paymentDueCount > 0 ? (
              <View style={styles.paymentDuePill}>
                <View style={styles.paymentDueDot} />
                <Text style={styles.paymentDueText}>
                  {paymentDueCount} payment{paymentDueCount === 1 ? "" : "s"} due
                </Text>
              </View>
            ) : null}
          </View>
        </View>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!requests ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : requests.length === 0 ? (
        <Text style={styles.empty}>You haven't requested a tutor yet.</Text>
      ) : visibleRequests.filter((r) => groupForStatus(r.status) === group).length === 0 ? (
        <Text style={styles.empty}>{GROUP_EMPTY_LABEL[group]}</Text>
      ) : (
        visibleRequests.filter((r) => groupForStatus(r.status) === group).map((r) => (
          <View key={r.id} style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <View style={[styles.cardAvatar, { backgroundColor: colorForSubject(r.subject) }]}>
                <Text style={styles.cardAvatarText}>{r.subject.charAt(0).toUpperCase()}</Text>
              </View>
              <View style={styles.cardHeaderTextCol}>
                <View style={styles.cardHeaderTitleRow}>
                  <Text style={styles.cardSubject}>
                    {r.grade ? `Grade ${r.grade} · ` : ""}{r.subject}{r.topic ? ` · ${r.topic}` : ""}
                  </Text>
                  <View style={styles.cardStatusRow}>
                    <View style={[styles.cardStatusDot, { backgroundColor: STATUS_COLOR[r.status] }]} />
                    <Text style={[styles.cardStatus, { color: STATUS_COLOR[r.status] }]}>{r.status_label}</Text>
                  </View>
                </View>
              </View>
            </View>

            {r.preferred_times_note ? (
              <Text style={styles.cardMeta}>Notes: {r.preferred_times_note}</Text>
            ) : null}

            {r.tutor_name ? <Text style={styles.cardMeta}>Tutor: {r.tutor_name}</Text> : null}
            {r.price_zar != null ? (
              <Text style={styles.cardMeta}>
                R{r.price_zar}{r.duration_minutes ? ` · ${r.duration_minutes} min` : ""}
              </Text>
            ) : null}
            {r.scheduled_at ? <Text style={styles.cardMeta}>Scheduled: {formatDate(r.scheduled_at)}</Text> : null}
            {r.meet_link ? (
              <Pressable onPress={() => Linking.openURL(r.meet_link!)}>
                <Text style={styles.meetLink}>🎥 Join via Google Meet</Text>
              </Pressable>
            ) : r.status === "awaiting_payment" ? (
              <Text style={styles.cardMeta}>
                The Google Meet link will be created once your payment is confirmed.
              </Text>
            ) : null}

            {r.status === "time_proposed" && (
              <View style={styles.proposalBox}>
                <Text style={styles.confirmLabel}>
                  Your tutor proposed a different time: {formatDate(r.proposed_scheduled_at)}
                </Text>
                <View style={styles.proposalButtonRow}>
                  <Pressable
                    style={[styles.confirmButton, styles.proposalApproveButton]}
                    onPress={() => handleRespond(r.id, true)}
                    disabled={respondingId === r.id}
                  >
                    {respondingId === r.id ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.confirmButtonText}>Approve</Text>
                    )}
                  </Pressable>
                  <Pressable
                    style={[styles.confirmButton, styles.proposalDeclineButton]}
                    onPress={() => handleRespond(r.id, false)}
                    disabled={respondingId === r.id}
                  >
                    {respondingId === r.id ? (
                      <ActivityIndicator color={colors.primary} />
                    ) : (
                      <Text style={styles.proposalDeclineButtonText}>Decline</Text>
                    )}
                  </Pressable>
                </View>
              </View>
            )}

            {(r.status === "requested" || r.status === "time_proposed") && (
              <View style={styles.actionButtonRow}>
                {r.status === "requested" && (
                  <Pressable
                    style={[styles.secondaryButton, styles.actionButtonFlex]}
                    onPress={() => navigation.navigate("RequestTutor", { editRequest: r })}
                  >
                    <Text style={styles.secondaryButtonText}>Edit</Text>
                  </Pressable>
                )}
                <Pressable
                  style={[styles.dangerButton, styles.actionButtonFlex]}
                  onPress={() => confirmWithdraw(r.id)}
                  disabled={withdrawingId === r.id}
                >
                  {withdrawingId === r.id ? (
                    <ActivityIndicator color={colors.error} />
                  ) : (
                    <Text style={styles.dangerButtonText}>Withdraw</Text>
                  )}
                </Pressable>
              </View>
            )}

            {r.status === "tutor_cancelled" && (
              <View style={styles.tutorCancelledBox}>
                <Text style={styles.confirmLabel}>
                  Your tutor cancelled this session - you've already paid for it. What would you like to do?
                </Text>
                <Pressable
                  style={styles.confirmButton}
                  onPress={() => handleReallocate(r.id)}
                  disabled={reallocatingId === r.id || refundingId === r.id}
                >
                  {reallocatingId === r.id ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.confirmButtonText}>Find Another Tutor</Text>
                  )}
                </Pressable>
                <Pressable
                  style={styles.dangerLinkButton}
                  onPress={() => confirmRequestRefund(r.id)}
                  disabled={reallocatingId === r.id || refundingId === r.id}
                >
                  {refundingId === r.id ? (
                    <ActivityIndicator color={colors.error} />
                  ) : (
                    <Text style={styles.dangerButtonText}>Request a Refund Instead</Text>
                  )}
                </Pressable>
              </View>
            )}

            {r.status === "awaiting_payment" && processingPaymentId === r.id ? (
              <View style={styles.processingBox}>
                <ActivityIndicator color={colors.primary} style={styles.processingSpinner} />
                <Text style={styles.processingText}>
                  We're confirming your payment - this can take a few seconds. Please don't pay again or close the app.
                </Text>
              </View>
            ) : r.status === "awaiting_payment" ? (
              <>
                <Pressable style={styles.payButton} onPress={() => handlePay(r.id)}>
                  <Text style={styles.payButtonText}>Pay Now</Text>
                </Pressable>
                <Text style={styles.helperText}>
                  Pay within 24 hours of being matched, or this request lapses and you'll need to submit a new one.
                </Text>
              </>
            ) : null}

            {(r.status === "awaiting_payment" || r.status === "confirmed") && processingPaymentId !== r.id &&
              !hasSessionStarted(r.scheduled_at) && (
              <View style={styles.cancelSection}>
                {cancelReasonId === r.id ? (
                  <View style={styles.cancelBox}>
                    <TextInput
                      style={styles.commentInput}
                      placeholder="Reason (optional)"
                      placeholderTextColor={colors.inputPlaceholder}
                      value={cancelReason}
                      onChangeText={setCancelReason}
                    />
                    <View style={styles.proposalButtonRow}>
                      <Pressable
                        style={[styles.dangerButton, styles.actionButtonFlex]}
                        onPress={() => confirmCancelWithLateFeeCheck(r)}
                        disabled={cancelingId === r.id}
                      >
                        {cancelingId === r.id ? (
                          <ActivityIndicator color={colors.error} />
                        ) : (
                          <Text style={styles.dangerButtonText}>Confirm Cancel</Text>
                        )}
                      </Pressable>
                      <Pressable
                        style={[styles.secondaryButton, styles.actionButtonFlex]}
                        onPress={() => { setCancelReasonId(null); setCancelReason(""); }}
                      >
                        <Text style={styles.secondaryButtonText}>Never mind</Text>
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <Pressable style={styles.dangerLinkButton} onPress={() => setCancelReasonId(r.id)}>
                    <Text style={styles.dangerButtonText}>Cancel this session</Text>
                  </Pressable>
                )}
                <Text style={styles.helperText}>
                  Cancelling a paid session within 24 hours still works, but applies Malita's{" "}
                  {LATE_CANCELLATION_PENALTY_PERCENT}% late-cancellation fee to your refund.
                </Text>
              </View>
            )}

            {r.status === "cancelled" && (
              <Text style={styles.cardMeta}>
                Cancelled by {r.cancelled_by ?? "—"}{r.cancellation_reason ? `: ${r.cancellation_reason}` : "."}
              </Text>
            )}
            {r.status === "cancelled" && r.refund_requested_at && (
              <Text style={styles.cardMeta}>
                {(() => {
                  const amountStr = r.refund_amount_zar != null ? `R${r.refund_amount_zar.toFixed(2)}` : "your refund";
                  const feeNote =
                    r.price_zar != null && r.refund_amount_zar != null && r.refund_amount_zar < r.price_zar
                      ? ` (R${r.price_zar.toFixed(2)} minus Malita's late-cancellation fee)`
                      : "";
                  if (r.refund_processed_at) return `✓ Your refund (${amountStr}) has been processed.`;
                  if (r.refund_processing_at) {
                    return `Your refund (${amountStr}${feeNote}) is being processed - expect it in your bank account within 5-7 working days.`;
                  }
                  if (!r.refund_bank_details_submitted_at) {
                    return `Refund requested (${amountStr}${feeNote}) - please provide your banking details below so Malita can send it.`;
                  }
                  return `Refund requested (${amountStr}${feeNote}) - Malita is arranging it.`;
                })()}
              </Text>
            )}

            {r.status === "cancelled" && r.refund_requested_at && !r.refund_processed_at && (
              r.refund_bank_details_submitted_at ? (
                <Text style={styles.cardMeta}>
                  Refund will be sent to {r.refund_account_holder}'s {r.refund_bank_name} account ending{" "}
                  {r.refund_account_number?.slice(-4)}.
                </Text>
              ) : (
                <View style={styles.cancelBox}>
                  <Text style={styles.confirmLabel}>Where should we send your refund?</Text>
                  <Text style={styles.label}>Account holder name</Text>
                  <TextInput
                    style={styles.commentInput}
                    placeholder="As it appears on the bank statement"
                    placeholderTextColor={colors.inputPlaceholder}
                    value={bankDraft[r.id]?.accountHolder ?? ""}
                    onChangeText={(v) => setBankDraftField(r.id, "accountHolder", v)}
                  />
                  <Dropdown
                    label="Bank"
                    options={SA_BANKS.map((b) => ({ label: b, value: b }))}
                    value={bankDraft[r.id]?.bankName ?? null}
                    onChange={(v) => setBankDraftField(r.id, "bankName", v)}
                  />
                  {bankDraft[r.id]?.bankName === "Other" && (
                    <TextInput
                      style={styles.commentInput}
                      placeholder="Bank name"
                      placeholderTextColor={colors.inputPlaceholder}
                      value={bankDraft[r.id]?.bankNameOther ?? ""}
                      onChangeText={(v) => setBankDraftField(r.id, "bankNameOther", v)}
                    />
                  )}
                  <Text style={styles.label}>Branch code</Text>
                  <TextInput
                    style={styles.commentInput}
                    keyboardType="number-pad"
                    value={bankDraft[r.id]?.branchCode ?? ""}
                    onChangeText={(v) => setBankDraftField(r.id, "branchCode", v)}
                  />
                  <Text style={styles.label}>Account number</Text>
                  <TextInput
                    style={styles.commentInput}
                    keyboardType="number-pad"
                    value={bankDraft[r.id]?.accountNumber ?? ""}
                    onChangeText={(v) => setBankDraftField(r.id, "accountNumber", v)}
                  />
                  <Dropdown
                    label="Account type"
                    options={BANK_ACCOUNT_TYPES.map((t) => ({ label: t, value: t }))}
                    value={bankDraft[r.id]?.accountType ?? null}
                    onChange={(v) => setBankDraftField(r.id, "accountType", v)}
                  />
                  {bankDraft[r.id]?.accountType === "Other" && (
                    <TextInput
                      style={styles.commentInput}
                      placeholder="Account type"
                      placeholderTextColor={colors.inputPlaceholder}
                      value={bankDraft[r.id]?.accountTypeOther ?? ""}
                      onChangeText={(v) => setBankDraftField(r.id, "accountTypeOther", v)}
                    />
                  )}
                  <Pressable
                    style={styles.checkboxRow}
                    onPress={() => setBankDraftField(r.id, "confirmed", !(bankDraft[r.id]?.confirmed ?? false))}
                  >
                    <View style={[styles.checkbox, bankDraft[r.id]?.confirmed && styles.checkboxChecked]}>
                      {bankDraft[r.id]?.confirmed ? <Text style={styles.checkboxMark}>✓</Text> : null}
                    </View>
                    <Text style={styles.checkboxLabel}>I confirm the above bank details are correct.</Text>
                  </Pressable>
                  <Pressable
                    style={styles.confirmButton}
                    onPress={() => handleSubmitBankDetails(r.id)}
                    disabled={submittingBankDetailsId === r.id}
                  >
                    {submittingBankDetailsId === r.id ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.confirmButtonText}>Submit Bank Details</Text>
                    )}
                  </Pressable>
                </View>
              )
            )}
            {r.status === "lapsed" && (
              <Text style={styles.cardMeta}>
                {r.lapse_reason === "no_tutor_accepted"
                  ? "No tutor accepted this request before the requested time passed - submit a new request with a later time if you still need a tutor."
                  : "This match lapsed because payment wasn't completed in time - submit a new request if you still need a tutor."}
              </Text>
            )}

            {r.status === "confirmed" && !r.no_show_reported_at && !r.learner_checked_out_at && (
              <Pressable
                style={styles.secondaryButton}
                onPress={() => (r.learner_checked_in_at ? handleCheckOut(r.id) : handleCheckIn(r.id))}
                disabled={checkingInId === r.id}
              >
                {checkingInId === r.id ? (
                  <ActivityIndicator color={colors.primary} />
                ) : (
                  <Text style={styles.secondaryButtonText}>
                    {r.learner_checked_in_at ? "Check Out" : "I'm on the call"}
                  </Text>
                )}
              </Pressable>
            )}
            {r.learner_checked_out_at && (
              <Text style={styles.cardMeta}>✓ Checked out at {formatDate(r.learner_checked_out_at)}</Text>
            )}
            {r.status === "confirmed" && !r.no_show_reported_at && (
              <Pressable style={styles.dangerLinkButton} onPress={() => confirmReportNoShow(r.id)}>
                <Text style={styles.dangerButtonText}>This didn't happen</Text>
              </Pressable>
            )}
            {r.no_show_reported_at && !r.no_show_resolved_at && (
              <Text style={styles.cardMeta}>
                {r.no_show_reported_by === "learner"
                  ? "You reported this session didn't happen - Malita is reviewing it."
                  : "Your tutor reported this session didn't happen - Malita is reviewing it."}
              </Text>
            )}
            {r.no_show_resolution === "dismissed" && (
              <Text style={styles.cardMeta}>
                Malita reviewed the no-show report on this session and found no action was needed.
              </Text>
            )}

            {r.status === "confirmed" && !r.learner_confirmed && !r.no_show_reported_at && !r.learner_checked_out_at && (
              <Text style={styles.cardMeta}>Check out once your session is done to rate your tutor.</Text>
            )}
            {r.status === "confirmed" && !r.learner_confirmed && !r.no_show_reported_at && r.learner_checked_out_at && (
              <View style={styles.confirmBox}>
                <Text style={styles.confirmLabel}>Did this session happen? Rate your tutor:</Text>
                <StarPicker
                  value={ratingDraft[r.id] || 0}
                  onChange={(v) => setRatingDraft((prev) => ({ ...prev, [r.id]: v }))}
                />
                <TextInput
                  style={styles.commentInput}
                  placeholder="Comment (optional)"
                  placeholderTextColor={colors.inputPlaceholder}
                  value={commentDraft[r.id] || ""}
                  onChangeText={(v) => setCommentDraft((prev) => ({ ...prev, [r.id]: v }))}
                />
                <Pressable
                  style={styles.confirmButton}
                  onPress={() => handleConfirm(r.id)}
                  disabled={confirmingId === r.id}
                >
                  {confirmingId === r.id ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.confirmButtonText}>Confirm & Rate</Text>
                  )}
                </Pressable>
              </View>
            )}
            {r.status === "confirmed" && r.learner_confirmed && (
              <Text style={styles.cardMeta}>✓ You confirmed this session - waiting on your tutor to confirm too.</Text>
            )}
            {r.status === "completed" && r.learner_rating != null && (
              <Text style={styles.cardMeta}>You rated this session {r.learner_rating}/5 ⭐</Text>
            )}

            {actionErrors[r.id] ? <Text style={styles.cardError}>{actionErrors[r.id]}</Text> : null}
          </View>
        ))
      )}

      <Pressable style={styles.newRequestButton} onPress={() => navigation.navigate("RequestTutor")}>
        <Text style={styles.newRequestButtonText}>Request Another Tutor</Text>
      </Pressable>
    </ScrollView>

    {requests && requests.length > 0 && (
      <View style={[styles.bottomBar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        {GROUP_TABS.map((tab) => {
          const count = visibleRequests.filter((r) => groupForStatus(r.status) === tab.key).length;
          const active = group === tab.key;
          const tint = active ? colors.primary : colors.textMuted;
          return (
            <Pressable
              key={tab.key}
              style={styles.bottomBarItem}
              onPress={() => setGroup(tab.key)}
              accessibilityRole="button"
              accessibilityLabel={tab.label}
            >
              <GroupTabIcon name={tab.key} color={tint} />
              <Text style={[styles.bottomBarLabel, { color: tint, fontWeight: active ? "700" : "500" }]}>
                {tab.label}{count ? ` (${count})` : ""}
              </Text>
            </Pressable>
          );
        })}
      </View>
    )}
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  scrollView: { flex: 1 },
  container: { padding: 20, paddingBottom: 40, flexGrow: 1 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backLink: { alignSelf: "flex-start" },
  backLinkText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  title: { fontSize: 22, fontWeight: "800", color: colors.text, marginTop: 4, marginBottom: 16 },
  statCard: { backgroundColor: colors.primaryDark, borderRadius: 20, padding: 18, marginBottom: 16 },
  standingCard: {
    backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginBottom: 16,
    borderWidth: 1, borderColor: colors.border,
  },
  standingRow: { flexDirection: "row", alignItems: "center" },
  standingLabel: { fontSize: 11, color: colors.textSecondary, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.4 },
  standingValue: { fontSize: 14, color: colors.text, fontWeight: "700", marginTop: 4 },
  badgePill: { borderRadius: 999, paddingVertical: 6, paddingHorizontal: 12, marginLeft: 10 },
  badgePillText: { fontSize: 11, fontWeight: "800", color: "#fff", letterSpacing: 0.4 },
  statCardRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  statLabel: { fontSize: 11, color: "rgba(255,255,255,0.7)", fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.4 },
  statValue: { fontSize: 26, color: colors.success, fontWeight: "800", marginTop: 4 },
  paymentDuePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(237,161,0,0.18)",
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  paymentDueDot: { width: 7, height: 7, borderRadius: 999, backgroundColor: "#eda100" },
  paymentDueText: { fontSize: 12, fontWeight: "700", color: "#eda100" },
  error: { color: colors.error, marginBottom: 12 },
  cardError: { color: colors.error, fontSize: 13, marginTop: 12, fontWeight: "600" },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 24 },
  screen: { flex: 1 },
  bottomBar: {
    flexDirection: "row",
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 10,
  },
  bottomBarItem: { flex: 1, alignItems: "center", gap: 4 },
  bottomBarLabel: { fontSize: 11 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 14,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  cardHeaderRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  cardAvatar: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  cardAvatarText: { fontSize: 15, fontWeight: "800", color: "#fff" },
  cardHeaderTextCol: { flex: 1, minWidth: 0 },
  cardHeaderTitleRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 6 },
  cardSubject: { fontSize: 15, fontWeight: "700", color: colors.text },
  cardStatusRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  cardStatusDot: { width: 6, height: 6, borderRadius: 999 },
  cardStatus: { fontSize: 11, fontWeight: "700" },
  cardMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  payButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 12,
  },
  payButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  processingBox: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.primaryDark,
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
    gap: 10,
  },
  processingSpinner: { marginRight: 2 },
  processingText: { flex: 1, color: "#fff", fontSize: 13, lineHeight: 18, fontWeight: "600" },
  meetLink: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 10 },
  confirmBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  confirmLabel: { fontSize: 13, color: colors.text, fontWeight: "600", marginBottom: 8 },
  starRow: { flexDirection: "row", gap: 6 },
  star: { fontSize: 26 },
  commentInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.inputText,
    backgroundColor: colors.inputBackground,
    marginTop: 10,
  },
  confirmButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 10,
  },
  confirmButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  checkboxRow: { flexDirection: "row", alignItems: "center", marginTop: 12 },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },
  checkboxChecked: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkboxMark: { color: "#fff", fontWeight: "700", fontSize: 13 },
  checkboxLabel: { fontSize: 14, color: colors.text, flexShrink: 1 },
  proposalBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  proposalButtonRow: { flexDirection: "row", gap: 10 },
  proposalApproveButton: { flex: 1, marginTop: 0 },
  proposalDeclineButton: {
    flex: 1,
    marginTop: 0,
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: colors.primary,
  },
  proposalDeclineButtonText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  actionButtonRow: { flexDirection: "row", gap: 10, marginTop: 12 },
  actionButtonFlex: { flex: 1, marginTop: 0 },
  secondaryButton: {
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  secondaryButtonText: { color: colors.text, fontWeight: "700", fontSize: 14 },
  dangerButton: {
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.error,
    backgroundColor: colors.surface,
  },
  dangerButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  dangerLinkButton: { marginTop: 12, alignItems: "center" },
  tutorCancelledBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  cancelSection: { marginTop: 4 },
  cancelBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  helperText: { fontSize: 11, color: colors.textSecondary, marginTop: 6, fontStyle: "italic" },
  newRequestButton: {
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.primary,
    marginTop: 8,
  },
  newRequestButtonText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
});
