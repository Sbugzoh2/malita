import React, { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
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
} from "../api/client";
import SessionDateTimePicker, {
  SessionDateTimeValue,
  sessionDateTimeToIso,
} from "../components/SessionDateTimePicker";

type Section = "open" | "sessions" | "payouts";

function formatScheduled(iso: string): string {
  return new Date(iso).toLocaleString("en-ZA", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
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
                    You'll receive {r.price_zar != null ? payoutPreview(r.price_zar, openCutPercent) : "—"} after
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
              profile.sessions.map((sess) => (
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
                        You'll receive {payoutPreview(sess.price_zar, sess.platform_cut_percent ?? openCutPercent)} after
                        Malita's {sess.platform_cut_percent ?? openCutPercent}% cut.
                      </Text>
                    </>
                  ) : null}
                  {sess.status === "time_proposed" ? (
                    <Text style={styles.cardMeta}>
                      Your proposed time: {sess.proposed_scheduled_at ? formatScheduled(sess.proposed_scheduled_at) : "—"} -
                      awaiting the learner's approval.
                    </Text>
                  ) : sess.scheduled_at ? (
                    <Text style={styles.cardMeta}>Scheduled: {formatScheduled(sess.scheduled_at)}</Text>
                  ) : null}
                  {sess.meet_link ? (
                    <Text style={styles.cardMeta}>🎥 Google Meet link sent by email</Text>
                  ) : null}

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
                </View>
              ))
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
  proposeLinkButton: { marginTop: 10, alignItems: "center" },
  proposeLinkText: { color: colors.primary, fontWeight: "600", fontSize: 13 },
  confirmBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
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
