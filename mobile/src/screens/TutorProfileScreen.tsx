import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import {
  ApiError,
  TutorProfile,
  fetchTutorMyProfile,
  fetchTutorMyPayouts,
} from "../api/client";

const STATUS_COLOR: Record<string, string> = {
  pending_review: colors.textSecondary,
  approved: colors.success,
  rejected: colors.error,
  suspended: colors.error,
};

const BADGE_COLORS: Record<string, string> = { bronze: "#cd7f32", silver: "#9aa0a6", gold: "#eda100" };

function formatDateJoined(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

export default function TutorProfileScreen({ navigation }: any) {
  const { token } = useTutorAuth();
  const [profile, setProfile] = useState<TutorProfile | null>(null);
  const [totalEarned, setTotalEarned] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorMyProfile(token)
      .then(setProfile)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your profile."));
    fetchTutorMyPayouts(token)
      .then((res) => setTotalEarned(res.payouts.reduce((sum, p) => sum + p.amount_zar, 0)))
      .catch(() => {});
  }, [token]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  if (!profile) {
    return (
      <View style={styles.loadingContainer}>
        {error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator color={colors.primary} />}
      </View>
    );
  }

  const firstLetter = profile.name.charAt(0).toUpperCase() || "?";

  return (
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      <View style={styles.profileRow}>
        <View style={styles.avatarBadge}>
          <Text style={styles.avatarBadgeText}>{firstLetter}</Text>
        </View>
        <View style={styles.profileTextCol}>
          <Text style={styles.name}>{profile.name}</Text>
          <Text style={styles.email}>{profile.email}</Text>
          {profile.phone ? <Text style={styles.email}>{profile.phone}</Text> : null}
        </View>
      </View>

      <View style={styles.pillRow}>
        <View style={[styles.pill, { backgroundColor: STATUS_COLOR[profile.status] ?? colors.primary }]}>
          <Text style={styles.pillTextLight}>{profile.status_label}</Text>
        </View>
        {profile.badge ? (
          <View style={[styles.pill, { backgroundColor: BADGE_COLORS[profile.badge] }]}>
            <Text style={styles.pillTextLight}>{profile.badge.toUpperCase()}</Text>
          </View>
        ) : null}
      </View>

      {profile.bio ? (
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>Bio</Text>
          <Text style={styles.bioText}>{profile.bio}</Text>
        </View>
      ) : null}

      <View style={styles.card}>
        <Text style={styles.sectionLabel}>Lifetime</Text>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Sessions completed</Text>
          <Text style={styles.detailValue}>{profile.sessions_completed}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Total earned</Text>
          <Text style={styles.detailValue}>{totalEarned != null ? `R${totalEarned.toFixed(0)}` : "—"}</Text>
        </View>
        {profile.average_rating != null ? (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Average rating</Text>
            <Text style={styles.detailValue}>{profile.average_rating.toFixed(1)}★</Text>
          </View>
        ) : null}
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Date joined</Text>
          <Text style={styles.detailValue}>{formatDateJoined(profile.created_at)}</Text>
        </View>
      </View>

      <Pressable style={styles.supportCard} onPress={() => navigation.navigate("TutorSupport")}>
        <Text style={styles.supportCardText}>Contact Support</Text>
        <Text style={styles.supportCardChevron}>›</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  container: { backgroundColor: colors.background, flexGrow: 1, padding: 20, paddingBottom: 40 },
  error: { color: colors.error },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  avatarBadge: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: "#0b0b0b",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadgeText: { fontSize: 20, fontWeight: "800", color: "#fff" },
  profileTextCol: { flex: 1, minWidth: 0 },
  name: { fontSize: 19, fontWeight: "800", color: colors.text },
  email: { fontSize: 13, color: colors.textSecondary, marginTop: 2 },
  pillRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  pill: { borderRadius: 999, paddingVertical: 6, paddingHorizontal: 14 },
  pillTextLight: { fontSize: 12, fontWeight: "700", color: "#fff" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  sectionLabel: { fontSize: 12, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 10 },
  bioText: { fontSize: 14, color: colors.text, lineHeight: 20 },
  detailRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 7 },
  detailLabel: { fontSize: 13, color: colors.textSecondary },
  detailValue: { fontSize: 13, fontWeight: "700", color: colors.text },
  supportCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  supportCardText: { fontSize: 14, fontWeight: "700", color: colors.text },
  supportCardChevron: { fontSize: 16, color: colors.textSecondary },
});
