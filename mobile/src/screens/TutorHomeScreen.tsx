import React, { useCallback, useEffect, useState } from "react";
import { Alert, View, Text, Pressable, TextInput, StyleSheet, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import {
  ApiError,
  TutorProfile,
  TutorPayout,
  TutoringRequest,
  fetchTutorMyProfile,
  fetchTutorMyPayouts,
  fetchTutorOpenRequests,
  acceptTutoringRequest,
  proposeNewTime,
  confirmTutoringSessionAsTutor,
  respondToAdminMatch,
  cancelTutoringSessionAsTutor,
  submitSessionRecording,
} from "../api/client";
import SessionDateTimePicker, {
  SessionDateTimeValue,
  sessionDateTimeToIso,
} from "../components/SessionDateTimePicker";

type Section = "open" | "sessions" | "payouts";

function formatScheduled(iso: string): string {
  // Always render in SAST (fixed UTC+2, no daylight saving), regardless of
  // the device's own timezone - otherwise the same stored instant displays
  // as a different wall-clock time depending on where the phone's clock is
  // set, which looked like scheduling itself being "hours off".
  return new Date(iso).toLocaleString("en-ZA", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Africa/Johannesburg",
  });
}

function payoutPreview(priceZar: number, cutPercent: number): string {
  return `R${(priceZar * (1 - cutPercent / 100)).toFixed(2)}`;
}

const STATUS_COLOR: Record<string, string> = {
  pending_review: colors.textSecondary,
  approved: colors.success,
  rejected: colors.error,
  suspended: colors.error,
};

type SessionGroup = "active" | "completed" | "cancelled" | "lapsed";

// Keeps cancelled/lapsed sessions out of the same list as upcoming ones -
// previously everything rendered in one flat list regardless of status.
function groupForStatus(status: string): SessionGroup {
  if (status === "cancelled") return "cancelled";
  if (status === "lapsed") return "lapsed";
  if (status === "completed") return "completed";
  return "active";
}

const SESSION_GROUP_TABS: { key: SessionGroup; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "lapsed", label: "Lapsed" },
];

const SESSION_GROUP_EMPTY_LABEL: Record<SessionGroup, string> = {
  active: "No active or upcoming sessions.",
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

export default function TutorHomeScreen() {
  const { token, me, logout } = useTutorAuth();
  const [profile, setProfile] = useState<TutorProfile | null>(null);
  const [payouts, setPayouts] = useState<TutorPayout[] | null>(null);
  const [openRequests, setOpenRequests] = useState<TutoringRequest[] | null>(null);
  const [openCutPercent, setOpenCutPercent] = useState<number>(30);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("open");
  const [proposingId, setProposingId] = useState<number | null>(null);
  const [proposeDateTime, setProposeDateTime] = useState<Record<number, SessionDateTimeValue>>({});
  const [acceptingId, setAcceptingId] = useState<number | null>(null);
  const [sendingProposalId, setSendingProposalId] = useState<number | null>(null);
  const [ratingDraft, setRatingDraft] = useState<Record<number, number>>({});
  const [commentDraft, setCommentDraft] = useState<Record<number, string>>({});
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [respondingAdminMatchId, setRespondingAdminMatchId] = useState<number | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [cancelReasonId, setCancelReasonId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [recordingDraft, setRecordingDraft] = useState<Record<number, string>>({});
  const [submittingRecordingId, setSubmittingRecordingId] = useState<number | null>(null);
  const [sessionGroup, setSessionGroup] = useState<SessionGroup>("active");

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorMyProfile(token)
      .then(setProfile)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your profile."));
    fetchTutorMyPayouts(token)
      .then((res) => setPayouts(res.payouts))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your payouts."));
    fetchTutorOpenRequests(token)
      .then((res) => {
        setOpenRequests(res.requests);
        setOpenCutPercent(res.platform_cut_percent);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load open requests."));
  }, [token]);

  async function handleAccept(requestId: number) {
    if (!token) return;
    setAcceptingId(requestId);
    setError(null);
    try {
      await acceptTutoringRequest(token, requestId);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not accept this request.");
    } finally {
      setAcceptingId(null);
    }
  }

  async function handleSendProposal(requestId: number) {
    if (!token) return;
    const dt = proposeDateTime[requestId];
    if (!dt) {
      setError("Please pick a date and time to propose.");
      return;
    }
    setSendingProposalId(requestId);
    setError(null);
    try {
      await proposeNewTime(token, requestId, sessionDateTimeToIso(dt));
      setProposingId(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send that proposal.");
    } finally {
      setSendingProposalId(null);
    }
  }

  async function handleAdminMatchResponse(requestId: number, accept: boolean) {
    if (!token) return;
    setRespondingAdminMatchId(requestId);
    setError(null);
    try {
      await respondToAdminMatch(token, requestId, accept);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record your response.");
    } finally {
      setRespondingAdminMatchId(null);
    }
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
      await confirmTutoringSessionAsTutor(token, requestId, rating, commentDraft[requestId] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not confirm this session.");
    } finally {
      setConfirmingId(null);
    }
  }

  async function handleCancel(requestId: number) {
    if (!token) return;
    setCancelingId(requestId);
    setError(null);
    try {
      await cancelTutoringSessionAsTutor(token, requestId, cancelReason.trim());
      setCancelReasonId(null);
      setCancelReason("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel this session.");
    } finally {
      setCancelingId(null);
    }
  }

  async function handleSubmitRecording(requestId: number) {
    if (!token) return;
    const link = (recordingDraft[requestId] || "").trim();
    if (!link) {
      setError("Please paste in the recording link.");
      return;
    }
    setSubmittingRecordingId(requestId);
    setError(null);
    try {
      await submitSessionRecording(token, requestId, link);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit the recording link.");
    } finally {
      setSubmittingRecordingId(null);
    }
  }

  function confirmCancel(requestId: number) {
    Alert.alert(
      "Cancel this session?",
      "The learner will be notified. This can't be undone.",
      [
        { text: "Never mind", style: "cancel" },
        { text: "Cancel Session", style: "destructive", onPress: () => handleCancel(requestId) },
      ]
    );
  }

  // Refreshes every time this screen regains focus, so a new match or a
  // payout being marked paid shows up without needing to log out/in.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  if (!me) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>🙋 Welcome, {me.name.split(" ")[0]}!</Text>
      <Text style={[styles.statusBadge, { color: STATUS_COLOR[me.status] ?? colors.text }]}>
        {me.status_label}
      </Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {me.status !== "approved" ? (
        <View style={styles.card}>
          <Text style={styles.cardText}>
            {me.status === "pending_review"
              ? "Your application is still being reviewed - we'll email you once a decision is made."
              : me.status === "rejected"
              ? "Your application was not approved. Check your email for details."
              : "Your tutor account is currently suspended."}
          </Text>
        </View>
      ) : (
        <>
          <View style={styles.sectionRow}>
            {([
              { key: "open", label: "Open Requests" },
              { key: "sessions", label: "My Sessions" },
              { key: "payouts", label: "My Payouts" },
            ] as { key: Section; label: string }[]).map((s) => (
              <Pressable
                key={s.key}
                style={[styles.sectionChip, section === s.key && styles.sectionChipActive]}
                onPress={() => setSection(s.key)}
              >
                <Text style={[styles.sectionChipText, section === s.key && styles.sectionChipTextActive]}>
                  {s.label}
                </Text>
              </Pressable>
            ))}
          </View>

          {section === "open" ? (
            !openRequests ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
            ) : openRequests.length === 0 ? (
              <Text style={styles.empty}>No open requests for your subjects right now.</Text>
            ) : (
              openRequests.map((r) => (
                <View key={r.id} style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {r.subject}
                    {r.topic ? ` · ${r.topic}` : ""}
                  </Text>
                  <Text style={styles.cardMeta}>
                    R{r.price_zar}{r.duration_minutes ? ` · ${r.duration_minutes} min` : ""}
                  </Text>
                  <Text style={styles.payoutNote}>
                    Estimated payout: ~{r.price_zar != null ? payoutPreview(r.price_zar, openCutPercent) : "—"} after
                    Malita's {openCutPercent}% cut — the amount above is not your final payout.
                  </Text>
                  {r.scheduled_at ? (
                    <Text style={styles.cardMeta}>Requested time: {formatScheduled(r.scheduled_at)}</Text>
                  ) : null}
                  {r.preferred_times_note ? (
                    <Text style={styles.cardMeta}>Notes: {r.preferred_times_note}</Text>
                  ) : null}

                  <Pressable
                    style={styles.acceptButton}
                    onPress={() => handleAccept(r.id)}
                    disabled={acceptingId === r.id}
                  >
                    {acceptingId === r.id ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.acceptButtonText}>
                        Accept{r.scheduled_at ? ` at ${formatScheduled(r.scheduled_at)}` : ""}
                      </Text>
                    )}
                  </Pressable>

                  <Pressable
                    style={styles.proposeLinkButton}
                    onPress={() => setProposingId(proposingId === r.id ? null : r.id)}
                  >
                    <Text style={styles.proposeLinkText}>
                      {proposingId === r.id ? "Cancel" : "Can't make that time? Propose a different one"}
                    </Text>
                  </Pressable>

                  {proposingId === r.id && (
                    <View style={styles.confirmBox}>
                      <SessionDateTimePicker
                        label="Propose a new date & time"
                        value={proposeDateTime[r.id] || null}
                        onChange={(v) => setProposeDateTime((prev) => ({ ...prev, [r.id]: v }))}
                      />
                      <Pressable
                        style={styles.acceptButton}
                        onPress={() => handleSendProposal(r.id)}
                        disabled={sendingProposalId === r.id}
                      >
                        {sendingProposalId === r.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.acceptButtonText}>Send Proposal</Text>
                        )}
                      </Pressable>
                    </View>
                  )}
                </View>
              ))
            )
          ) : section === "sessions" ? (
            !profile ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
            ) : profile.sessions.length === 0 ? (
              <Text style={styles.empty}>No sessions yet - accept an open request to get started.</Text>
            ) : (
              <>
                <View style={styles.sectionRow}>
                  {SESSION_GROUP_TABS.map((tab) => {
                    const count = profile.sessions.filter((s) => groupForStatus(s.status) === tab.key).length;
                    return (
                      <Pressable
                        key={tab.key}
                        style={[styles.sectionChip, sessionGroup === tab.key && styles.sectionChipActive]}
                        onPress={() => setSessionGroup(tab.key)}
                      >
                        <Text style={[styles.sectionChipText, sessionGroup === tab.key && styles.sectionChipTextActive]}>
                          {tab.label}{count ? ` (${count})` : ""}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
                {profile.sessions.filter((s) => groupForStatus(s.status) === sessionGroup).length === 0 ? (
                  <Text style={styles.empty}>{SESSION_GROUP_EMPTY_LABEL[sessionGroup]}</Text>
                ) : (
                  profile.sessions
                    .filter((s) => groupForStatus(s.status) === sessionGroup)
                    .map((sess) => (
                <View key={sess.id} style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {sess.subject}
                    {sess.topic ? ` · ${sess.topic}` : ""}
                  </Text>
                  <Text style={styles.cardStatus}>{sess.status_label}</Text>
                  {sess.price_zar != null ? (
                    <>
                      <Text style={styles.cardMeta}>
                        R{sess.price_zar}{sess.duration_minutes ? ` · ${sess.duration_minutes} min` : ""}
                      </Text>
                      <Text style={styles.payoutNote}>
                        Estimated payout: ~{payoutPreview(sess.price_zar, sess.platform_cut_percent ?? openCutPercent)} after
                        Malita's {sess.platform_cut_percent ?? openCutPercent}% cut — not your final payout.
                      </Text>
                    </>
                  ) : null}
                  {sess.status === "time_proposed" ? (
                    <Text style={styles.cardMeta}>
                      Your proposed time: {sess.proposed_scheduled_at ? formatScheduled(sess.proposed_scheduled_at) : "—"} -
                      awaiting the learner's approval.
                    </Text>
                  ) : sess.status === "admin_proposed" ? (
                    <Text style={styles.cardMeta}>
                      {sess.proposed_scheduled_at
                        ? `An admin proposed: ${formatScheduled(sess.proposed_scheduled_at)}`
                        : `Learner's requested time: ${sess.scheduled_at ? formatScheduled(sess.scheduled_at) : "—"}`}
                    </Text>
                  ) : sess.scheduled_at ? (
                    <Text style={styles.cardMeta}>Scheduled: {formatScheduled(sess.scheduled_at)}</Text>
                  ) : null}
                  {sess.meet_link ? (
                    <Pressable onPress={() => Linking.openURL(sess.meet_link!)}>
                      <Text style={styles.meetLink}>🎥 Join via Google Meet</Text>
                    </Pressable>
                  ) : null}

                  {(sess.status === "confirmed" || sess.status === "completed") && (
                    sess.recording_link ? (
                      <Text style={styles.cardMeta}>✓ Recording shared with Malita.</Text>
                    ) : (
                      <View style={styles.cancelBox}>
                        <Text style={styles.confirmLabel}>
                          Please record this session (Meet's own "Record meeting" button) and share the link:
                        </Text>
                        <TextInput
                          style={styles.input}
                          placeholder="Paste the recording link (e.g. Google Drive)"
                          value={recordingDraft[sess.id] || ""}
                          onChangeText={(v) => setRecordingDraft((prev) => ({ ...prev, [sess.id]: v }))}
                        />
                        <Pressable
                          style={styles.acceptButton}
                          onPress={() => handleSubmitRecording(sess.id)}
                          disabled={submittingRecordingId === sess.id}
                        >
                          {submittingRecordingId === sess.id ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.acceptButtonText}>Submit Recording Link</Text>
                          )}
                        </Pressable>
                      </View>
                    )
                  )}

                  {sess.status === "admin_proposed" && (
                    <View style={styles.proposalButtonRow}>
                      <Pressable
                        style={[styles.acceptButton, styles.proposalApproveButton]}
                        onPress={() => handleAdminMatchResponse(sess.id, true)}
                        disabled={respondingAdminMatchId === sess.id}
                      >
                        {respondingAdminMatchId === sess.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.acceptButtonText}>Confirm</Text>
                        )}
                      </Pressable>
                      <Pressable
                        style={[styles.acceptButton, styles.proposalDeclineButton]}
                        onPress={() => handleAdminMatchResponse(sess.id, false)}
                        disabled={respondingAdminMatchId === sess.id}
                      >
                        {respondingAdminMatchId === sess.id ? (
                          <ActivityIndicator color={colors.primary} />
                        ) : (
                          <Text style={styles.proposalDeclineButtonText}>Decline</Text>
                        )}
                      </Pressable>
                    </View>
                  )}

                  {sess.status === "confirmed" && !sess.tutor_confirmed && (
                    <View style={styles.confirmBox}>
                      <Text style={styles.confirmLabel}>Did this session happen? Rate the learner:</Text>
                      <StarPicker
                        value={ratingDraft[sess.id] || 0}
                        onChange={(v) => setRatingDraft((prev) => ({ ...prev, [sess.id]: v }))}
                      />
                      <TextInput
                        style={styles.input}
                        placeholder="Comment (optional)"
                        value={commentDraft[sess.id] || ""}
                        onChangeText={(v) => setCommentDraft((prev) => ({ ...prev, [sess.id]: v }))}
                      />
                      <Pressable
                        style={styles.acceptButton}
                        onPress={() => handleConfirm(sess.id)}
                        disabled={confirmingId === sess.id}
                      >
                        {confirmingId === sess.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.acceptButtonText}>Confirm & Rate</Text>
                        )}
                      </Pressable>
                    </View>
                  )}
                  {sess.status === "confirmed" && sess.tutor_confirmed && (
                    <Text style={styles.cardMeta}>✓ You confirmed this session - waiting on the learner too.</Text>
                  )}
                  {sess.status === "completed" && sess.tutor_rating != null && (
                    <Text style={styles.cardMeta}>You rated this session {sess.tutor_rating}/5 ⭐</Text>
                  )}

                  {(sess.status === "awaiting_payment" || sess.status === "confirmed") && (
                    cancelReasonId === sess.id ? (
                      <View style={styles.cancelBox}>
                        <Text style={styles.label}>Reason (optional)</Text>
                        <TextInput
                          style={styles.input}
                          placeholder="e.g. I'm no longer available at this time"
                          value={cancelReason}
                          onChangeText={setCancelReason}
                        />
                        <View style={styles.proposalButtonRow}>
                          <Pressable
                            style={[styles.acceptButton, styles.proposalDeclineButton]}
                            onPress={() => { setCancelReasonId(null); setCancelReason(""); }}
                          >
                            <Text style={styles.proposalDeclineButtonText}>Never mind</Text>
                          </Pressable>
                          <Pressable
                            style={[styles.acceptButton, styles.proposalApproveButton, styles.dangerButton]}
                            onPress={() => confirmCancel(sess.id)}
                            disabled={cancelingId === sess.id}
                          >
                            {cancelingId === sess.id ? (
                              <ActivityIndicator color="#fff" />
                            ) : (
                              <Text style={styles.acceptButtonText}>Confirm Cancel</Text>
                            )}
                          </Pressable>
                        </View>
                        <Text style={styles.payoutNote}>
                          Not available within 24 hours of the session - contact support for anything that close.
                        </Text>
                      </View>
                    ) : (
                      <Pressable style={styles.proposeLinkButton} onPress={() => setCancelReasonId(sess.id)}>
                        <Text style={styles.dangerLinkText}>Cancel this session</Text>
                      </Pressable>
                    )
                  )}
                  {sess.status === "cancelled" && (
                    <Text style={styles.cardMeta}>
                      Cancelled by {sess.cancelled_by ?? "—"}
                      {sess.cancellation_reason ? `: ${sess.cancellation_reason}` : "."}
                    </Text>
                  )}
                  {sess.status === "lapsed" && (
                    <Text style={styles.cardMeta}>
                      Lapsed - the learner didn't pay within 24 hours of being matched. They'll need to submit a new request.
                    </Text>
                  )}
                </View>
                    ))
                )}
              </>
            )
          ) : !payouts ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
          ) : payouts.length === 0 ? (
            <Text style={styles.empty}>No payouts yet.</Text>
          ) : (
            payouts.map((p) => (
              <View key={p.id} style={styles.card}>
                <Text style={styles.cardTitle}>Session #{p.session_id}</Text>
                <Text
                  style={[
                    styles.cardStatus,
                    { color: p.status === "paid" ? colors.success : colors.textSecondary },
                  ]}
                >
                  {p.status === "paid" ? "Paid" : "Pending"}
                </Text>
                <Text style={styles.cardMeta}>R{p.amount_zar.toFixed(2)}</Text>
                {p.payment_reference ? (
                  <Text style={styles.cardMeta}>Reference: {p.payment_reference}</Text>
                ) : null}
              </View>
            ))
          )}
        </>
      )}

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  container: { padding: 20, paddingBottom: 40, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  statusBadge: { fontSize: 14, fontWeight: "700", marginTop: 6, marginBottom: 16 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 16 },
  sectionRow: { flexDirection: "row", gap: 8, marginBottom: 16 },
  sectionChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 16,
    backgroundColor: "#fff",
  },
  sectionChipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  sectionChipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  sectionChipTextActive: { color: "#fff" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardText: { fontSize: 14, color: colors.text, lineHeight: 20 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.text },
  cardStatus: { fontSize: 13, fontWeight: "700", color: colors.primary, marginTop: 4 },
  cardMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 10, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    color: colors.text,
    backgroundColor: "#fff",
  },
  acceptButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 10,
  },
  acceptButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  payoutNote: { fontSize: 12, color: colors.textSecondary, marginTop: 4, fontStyle: "italic" },
  meetLink: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 10 },
  proposalButtonRow: { flexDirection: "row", gap: 10, marginTop: 10 },
  proposalApproveButton: { flex: 1, marginTop: 0 },
  proposalDeclineButton: {
    flex: 1,
    marginTop: 0,
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: colors.primary,
  },
  proposalDeclineButtonText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  proposeLinkButton: { marginTop: 10, alignItems: "center" },
  proposeLinkText: { color: colors.primary, fontWeight: "600", fontSize: 13 },
  confirmBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  cancelBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  dangerButton: { backgroundColor: colors.error },
  dangerLinkText: { color: colors.error, fontWeight: "600", fontSize: 13 },
  confirmLabel: { fontSize: 13, color: colors.text, fontWeight: "600", marginBottom: 8 },
  starRow: { flexDirection: "row", gap: 6 },
  star: { fontSize: 26 },
  logoutButton: {
    marginTop: 24,
    marginBottom: 24,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
