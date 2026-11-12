import React, { useEffect, useState, useCallback } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import NotificationBell from "../components/NotificationBell";
import {
  fetchNotificationsUnreadCount,
  fetchInstitutions,
  fetchQualifications,
  Institution,
  Qualification,
  YEAR_LEVEL_LABELS,
} from "../api/client";

const ACCOUNT_TYPE_LABEL: Record<string, string> = {
  high_school: "High School",
  higher_ed: "Higher Ed",
};

export default function AccountScreen({ navigation }: any) {
  const { token, me, logout } = useAuth();
  const insets = useSafeAreaInsets();
  const [unreadCount, setUnreadCount] = useState(0);
  const [institutions, setInstitutions] = useState<Institution[] | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[] | null>(null);

  const isHigherEd = me?.user.account_type === "higher_ed";
  const firstName = me?.user.name.split(" ")[0] ?? "";

  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      fetchNotificationsUnreadCount(token).then((res) => setUnreadCount(res.count)).catch(() => {});
    }, [token])
  );

  // Only the IDs are on `me` - resolve them to display names from the same
  // catalog endpoints RequestTutorScreen already uses for its pickers.
  useEffect(() => {
    if (!isHigherEd) return;
    fetchInstitutions().then((res) => setInstitutions(res.institutions)).catch(() => {});
  }, [isHigherEd]);

  useEffect(() => {
    if (!me?.user.higher_ed_institution_id) return;
    fetchQualifications(me.user.higher_ed_institution_id)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => {});
  }, [me?.user.higher_ed_institution_id]);

  const institutionName = institutions?.find((i) => i.id === me?.user.higher_ed_institution_id)?.name;
  const qualificationName = qualifications?.find((q) => q.id === me?.user.higher_ed_qualification_id)?.name;

  if (!me) return null;

  return (
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      <View style={[styles.headerRow, { paddingTop: insets.top + 12 }]}>
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

      <View style={styles.profileRow}>
        <View style={styles.avatarBadge}>
          <Text style={styles.avatarBadgeText}>{firstName.charAt(0).toUpperCase() || "?"}</Text>
        </View>
        <View style={styles.profileTextCol}>
          <Text style={styles.name}>{me.user.name}</Text>
          <Text style={styles.email}>{me.user.email}</Text>
        </View>
      </View>

      <View style={styles.pillRow}>
        <View style={styles.pill}>
          <Text style={styles.pillText}>{ACCOUNT_TYPE_LABEL[me.user.account_type] ?? me.user.account_type}</Text>
        </View>
        {me.is_admin ? (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Admin</Text>
          </View>
        ) : null}
      </View>

      {isHigherEd ? (
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>Study details</Text>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Institution</Text>
            <Text style={styles.detailValue}>{institutionName ?? "—"}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Qualification</Text>
            <Text style={styles.detailValue}>{qualificationName ?? "—"}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Year of study</Text>
            <Text style={styles.detailValue}>
              {me.user.higher_ed_year_of_study != null ? YEAR_LEVEL_LABELS[me.user.higher_ed_year_of_study] ?? "—" : "—"}
            </Text>
          </View>
          {me.user.student_number ? (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Student number</Text>
              <Text style={styles.detailValue}>{me.user.student_number}</Text>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>Plan</Text>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Current plan</Text>
            <Text style={styles.detailValue}>{me.tier_label}</Text>
          </View>
          {me.daily_limit != null ? (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Solves today</Text>
              <Text style={styles.detailValue}>
                {me.used_today} / {me.daily_limit}
              </Text>
            </View>
          ) : null}
          <Pressable style={styles.managePlanLink} onPress={() => navigation.navigate("Subscription")}>
            <Text style={styles.managePlanLinkText}>Manage plan ›</Text>
          </Pressable>
        </View>
      )}

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flexGrow: 1, padding: 20, paddingBottom: 40 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backLink: { alignSelf: "flex-start" },
  backLinkText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 14, marginTop: 20 },
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
  pill: { backgroundColor: colors.surface, borderRadius: 999, paddingVertical: 6, paddingHorizontal: 14 },
  pillText: { fontSize: 12, fontWeight: "700", color: colors.primaryDark },
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
  detailRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 7 },
  detailLabel: { fontSize: 13, color: colors.textSecondary },
  detailValue: { fontSize: 13, fontWeight: "700", color: colors.text },
  managePlanLink: { marginTop: 6 },
  managePlanLinkText: { fontSize: 13, fontWeight: "700", color: colors.primary },
  logoutButton: {
    marginTop: 28,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
