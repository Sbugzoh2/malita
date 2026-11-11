import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking, TextInput, Alert } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  fetchMyTutoringRequests,
  tutoringCheckoutUrl,
  confirmTutoringSessionAsLearner,
  respondToTimeProposal,
  withdrawTutoringRequest,
  cancelTutoringSessionAsLearner,
  TutoringRequest,
} from "../api/client";

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

const STATUS_COLOR: Record<TutoringRequest["status"], string> = {
  requested: colors.textSecondary,
  time_proposed: "#eda100",
  admin_proposed: colors.textSecondary,
  awaiting_payment: "#eda100",
  confirmed: colors.primary,
  completed: colors.success,
  cancelled: colors.error,
  lapsed: colors.error,
};

type SessionGroup = "active" | "completed" | "cancelled" | "lapsed";

// Keeps cancelled/lapsed sessions out of the same list as upcoming ones -
// previously everything rendered in one flat list regardless of status,
// which a tester flagged as confusing ("don't mix these two").
function groupForStatus(status: TutoringRequest["status"]): SessionGroup {
  if (status === "cancelled") return "cancelled";
  if (status === "lapsed") return "lapsed";
  if (status === "completed") return "completed";
  return "active"; // requested, time_proposed, admin_proposed, awaiting_payment, confirmed
}

const GROUP_TABS: { key: SessionGroup; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "lapsed", label: "Lapsed" },
];

const GROUP_EMPTY_LABEL: Record<SessionGroup, string> = {
  active: "No active requests or upcoming sessions.",
  completed: "No completed sessions yet.",
  cancelled: "No cancelled sessions.",
  lapsed: "No lapsed sessions.",
};

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

export default function MyTutoringRequestsScreen({ navigation }: any) {
  const { token } = useAuth();
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ratingDraft, setRatingDraft] = useState<Record<number, number>>({});
  const [commentDraft, setCommentDraft] = useState<Record<number, string>>({});
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [respondingId, setRespondingId] = useState<number | null>(null);
  const [withdrawingId, setWithdrawingId] = useState<number | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [cancelReasonId, setCancelReasonId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [group, setGroup] = useState<SessionGroup>("active");

  const load = useCallback(() => {
    if (!token) return;
    fetchMyTutoringRequests(token)
      .then((res) => setRequests(res.requests))
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

  function handlePay(requestId: number) {
    if (!token) return;
    Linking.openURL(tutoringCheckoutUrl(token, requestId));
  }

  async function handleConfirm(requestId: number) {
    if (!token) return;
    const rating = ratingDraft[requestId];
    if (!rating) {
      setError("Please pick a rating (tap a star) before confirming.");
      return;
    }
    setConfirmingId(requestId);
    setError(null);
    try {
      await confirmTutoringSessionAsLearner(token, requestId, rating, commentDraft[requestId] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not confirm this session.");
    } finally {
      setConfirmingId(null);
    }
  }

  async function handleRespond(requestId: number, accept: boolean) {
    if (!token) return;
    setRespondingId(requestId);
    setError(null);
    try {
      await respondToTimeProposal(token, requestId, accept);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record your response.");
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
    setError(null);
    try {
      await withdrawTutoringRequest(token, requestId);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not withdraw this request.");
    } finally {
      setWithdrawingId(null);
    }
  }

  async function handleCancel(requestId: number) {
    if (!token) return;
    setCancelingId(requestId);
    setError(null);
    try {
      await cancelTutoringSessionAsLearner(token, requestId, cancelReason.trim());
      setCancelReasonId(null);
      setCancelReason("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel this session.");
    } finally {
      setCancelingId(null);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📋 My Tutoring Requests</Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {requests && requests.length > 0 && (
        <View style={styles.groupTabRow}>
          {GROUP_TABS.map((tab) => {
            const count = requests.filter((r) => groupForStatus(r.status) === tab.key).length;
            return (
              <Pressable
                key={tab.key}
                style={[styles.groupTab, group === tab.key && styles.groupTabActive]}
                onPress={() => setGroup(tab.key)}
              >
                <Text style={[styles.groupTabText, group === tab.key && styles.groupTabTextActive]}>
                  {tab.label}{count ? ` (${count})` : ""}
                </Text>
              </Pressable>
            );
          })}
        </View>
      )}

      {!requests ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : requests.length === 0 ? (
        <Text style={styles.empty}>You haven't requested a tutor yet.</Text>
      ) : requests.filter((r) => groupForStatus(r.status) === group).length === 0 ? (
        <Text style={styles.empty}>{GROUP_EMPTY_LABEL[group]}</Text>
      ) : (
        requests.filter((r) => groupForStatus(r.status) === group).map((r) => (
          <View key={r.id} style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardSubject}>{r.subject}{r.topic ? ` · ${r.topic}` : ""}</Text>
              <Text style={[styles.cardStatus, { color: STATUS_COLOR[r.status] }]}>
                {r.status_label}
              </Text>
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

            {r.status === "awaiting_payment" && (
              <>
                <Pressable style={styles.payButton} onPress={() => handlePay(r.id)}>
                  <Text style={styles.payButtonText}>Pay Now</Text>
                </Pressable>
                <Text style={styles.helperText}>
                  Pay within 24 hours of being matched, or this request lapses and you'll need to submit a new one.
                </Text>
              </>
            )}

            {(r.status === "awaiting_payment" || r.status === "confirmed") && (
              <View style={styles.cancelSection}>
                {cancelReasonId === r.id ? (
                  <View style={styles.cancelBox}>
                    <TextInput
                      style={styles.commentInput}
                      placeholder="Reason (optional)"
                      value={cancelReason}
                      onChangeText={setCancelReason}
                    />
                    <View style={styles.proposalButtonRow}>
                      <Pressable
                        style={[styles.dangerButton, styles.actionButtonFlex]}
                        onPress={() => handleCancel(r.id)}
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
                  Cancelling isn't available within 24 hours of the session.
                </Text>
              </View>
            )}

            {r.status === "cancelled" && (
              <Text style={styles.cardMeta}>
                Cancelled by {r.cancelled_by ?? "—"}{r.cancellation_reason ? `: ${r.cancellation_reason}` : "."}
              </Text>
            )}
            {r.status === "lapsed" && (
              <Text style={styles.cardMeta}>
                This match lapsed because payment wasn't completed in time - submit a new request if you still need a tutor.
              </Text>
            )}

            {r.status === "confirmed" && !r.learner_confirmed && (
              <View style={styles.confirmBox}>
                <Text style={styles.confirmLabel}>Did this session happen? Rate your tutor:</Text>
                <StarPicker
                  value={ratingDraft[r.id] || 0}
                  onChange={(v) => setRatingDraft((prev) => ({ ...prev, [r.id]: v }))}
                />
                <TextInput
                  style={styles.commentInput}
                  placeholder="Comment (optional)"
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
          </View>
        ))
      )}

      <Pressable style={styles.newRequestButton} onPress={() => navigation.navigate("RequestTutor")}>
        <Text style={styles.newRequestButtonText}>Request Another Tutor</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingBottom: 40, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text, marginBottom: 16 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 24 },
  groupTabRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 16 },
  groupTab: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  groupTabActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  groupTabText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  groupTabTextActive: { color: "#fff" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 14,
  },
  cardHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 6 },
  cardSubject: { fontSize: 16, fontWeight: "700", color: colors.text },
  cardStatus: { fontSize: 13, fontWeight: "700" },
  cardMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  payButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 12,
  },
  payButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
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
    color: colors.text,
    backgroundColor: "#fff",
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
    backgroundColor: "#fff",
  },
  secondaryButtonText: { color: colors.text, fontWeight: "700", fontSize: 14 },
  dangerButton: {
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.error,
    backgroundColor: "#fff",
  },
  dangerButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  dangerLinkButton: { marginTop: 12, alignItems: "center" },
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
