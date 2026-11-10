import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking, TextInput } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  fetchMyTutoringRequests,
  tutoringCheckoutUrl,
  confirmTutoringSessionAsLearner,
  respondToTimeProposal,
  TutoringRequest,
} from "../api/client";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-ZA", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const STATUS_COLOR: Record<TutoringRequest["status"], string> = {
  requested: colors.textSecondary,
  time_proposed: "#eda100",
  awaiting_payment: "#eda100",
  confirmed: colors.primary,
  completed: colors.success,
  cancelled: colors.error,
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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📋 My Tutoring Requests</Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!requests ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : requests.length === 0 ? (
        <Text style={styles.empty}>You haven't requested a tutor yet.</Text>
      ) : (
        requests.map((r) => (
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

            {r.status === "awaiting_payment" && (
              <Pressable style={styles.payButton} onPress={() => handlePay(r.id)}>
                <Text style={styles.payButtonText}>Pay Now</Text>
              </Pressable>
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
