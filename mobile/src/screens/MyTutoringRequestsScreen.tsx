import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchMyTutoringRequests, tutoringCheckoutUrl, TutoringRequest } from "../api/client";

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

const STATUS_LABEL: Record<TutoringRequest["status"], string> = {
  requested: "Waiting to be matched with a tutor",
  matched: "Matched — awaiting price confirmation",
  awaiting_payment: "Matched! Pay to confirm your session",
  confirmed: "Confirmed ✅",
  completed: "Completed",
  cancelled: "Cancelled",
};

const STATUS_COLOR: Record<TutoringRequest["status"], string> = {
  requested: colors.textSecondary,
  matched: colors.primary,
  awaiting_payment: "#eda100",
  confirmed: colors.success,
  completed: colors.success,
  cancelled: colors.error,
};

export default function MyTutoringRequestsScreen({ navigation }: any) {
  const { token } = useAuth();
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
                {STATUS_LABEL[r.status]}
              </Text>
            </View>

            {r.preferred_times_note ? (
              <Text style={styles.cardMeta}>Preferred times: {r.preferred_times_note}</Text>
            ) : null}

            {r.tutor_name ? <Text style={styles.cardMeta}>Tutor: {r.tutor_name}</Text> : null}
            {r.price_zar != null ? (
              <Text style={styles.cardMeta}>
                R{r.price_zar}{r.duration_minutes ? ` · ${r.duration_minutes} min` : ""}
              </Text>
            ) : null}
            {r.scheduled_at ? <Text style={styles.cardMeta}>Scheduled: {formatDate(r.scheduled_at)}</Text> : null}

            {r.status === "awaiting_payment" && (
              <Pressable style={styles.payButton} onPress={() => handlePay(r.id)}>
                <Text style={styles.payButtonText}>Pay Now</Text>
              </Pressable>
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
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
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
