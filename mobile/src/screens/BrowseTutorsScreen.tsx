import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../context/AuthContext";
import { colors, HIGH_SCHOOL_TUTORING_SUBJECTS, HighSchoolTutoringSubject } from "../theme";
import { ApiError, DirectoryTutor, fetchNotificationsUnreadCount, fetchTutorsDirectory } from "../api/client";
import Dropdown from "../components/Dropdown";
import NotificationBell from "../components/NotificationBell";

// Same hash-by-name palette as the other redesigned screens' subject/
// tutor avatars - a tutor's name has no fixed catalog to hand-map a
// color from.
const AVATAR_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

export default function BrowseTutorsScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const insets = useSafeAreaInsets();
  const [unreadCount, setUnreadCount] = useState(0);
  const isHigherEd = me?.user.account_type === "higher_ed";
  // Rare admin override (see backend/set_cross_segment_access.py) - shows
  // BOTH high-school subject tutors and higher-ed module tutors together,
  // instead of the usual either/or.
  const hasCrossAccess = !!me?.user.cross_segment_access;
  const showSubjects = hasCrossAccess || !isHigherEd;
  const showModules = hasCrossAccess || isHigherEd;

  const [subjectFilter, setSubjectFilter] = useState<HighSchoolTutoringSubject | null>(null);
  const [tutors, setTutors] = useState<DirectoryTutor[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    // With cross access the subject filter is applied client-side below
    // instead (the API's subject param would otherwise hide a tutor who
    // only offers higher-ed modules, since it's an AND-filter server-side).
    const serverSubjectFilter = !hasCrossAccess && !isHigherEd ? subjectFilter ?? undefined : undefined;
    fetchTutorsDirectory(token, { subject: serverSubjectFilter })
      .then((res) => setTutors(res.tutors))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the tutor directory."));
  }, [token, isHigherEd, hasCrossAccess, subjectFilter]);

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

  function requestSubject(tutor: DirectoryTutor, subject: string) {
    navigation.navigate("RequestTutor", {
      preferredTutorId: tutor.id,
      directoryPrefill: { subject, tutorName: tutor.name },
    });
  }

  function requestModule(
    tutor: DirectoryTutor,
    mod: DirectoryTutor["higher_ed_modules"][number]
  ) {
    navigation.navigate("RequestTutor", {
      preferredTutorId: tutor.id,
      directoryPrefill: {
        institutionId: mod.institution_id,
        qualificationId: mod.qualification_id,
        moduleId: mod.id,
        tutorName: tutor.name,
      },
    });
  }

  const visibleTutors = (tutors ?? []).filter((t) => {
    const matchingSubjects = showSubjects
      ? t.subjects.filter((s) => !subjectFilter || s.subject === subjectFilter)
      : [];
    const hasQualifyingSubject = matchingSubjects.length > 0;
    const hasQualifyingModule = showModules && t.higher_ed_modules.length > 0;
    return hasQualifyingSubject || hasQualifyingModule;
  });

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + 20 }]}>
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
      <Text style={styles.title}>Browse Tutors</Text>
      <Text style={styles.subtitle}>
        Pick a specific tutor instead of broadcasting a request. Once they accept, it's the exact same
        flow — a Google Meet link is created and you'll be asked to pay before the session is confirmed.
      </Text>

      {showSubjects && (
        <Dropdown
          label="Filter by subject (optional)"
          options={[{ label: "All subjects", value: "" }, ...HIGH_SCHOOL_TUTORING_SUBJECTS.map((s) => ({ label: s, value: s }))]}
          value={subjectFilter ?? ""}
          onChange={(v) => setSubjectFilter((v || null) as HighSchoolTutoringSubject | null)}
        />
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!tutors ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : visibleTutors.length === 0 ? (
        <Text style={styles.empty}>No approved tutors match that filter right now.</Text>
      ) : (
        visibleTutors.map((tutor) => (
          <View key={tutor.id} style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <View style={[styles.cardAvatar, { backgroundColor: colorForName(tutor.name) }]}>
                <Text style={styles.cardAvatarText}>{tutor.name.charAt(0).toUpperCase()}</Text>
              </View>
              <View style={styles.cardHeaderTextCol}>
                <Text style={styles.cardTitle}>{tutor.name}</Text>
                <Text style={styles.cardMeta}>{tutor.sessions_completed} session(s) completed on Malita</Text>
              </View>
            </View>
            {tutor.bio ? <Text style={styles.bio}>{tutor.bio}</Text> : null}
            {tutor.availability_note ? (
              <Text style={styles.cardMeta}>Availability: {tutor.availability_note}</Text>
            ) : null}

            {showSubjects &&
              tutor.subjects
                .filter((s) => !subjectFilter || s.subject === subjectFilter)
                .map((s) => (
                <View key={s.subject} style={styles.offerRow}>
                  <View style={[styles.offerDot, { backgroundColor: colorForName(s.subject) }]} />
                  <View style={styles.offerTextCol}>
                    <Text style={styles.offerTitle}>{s.subject}</Text>
                    <Text style={styles.offerMeta}>
                      {s.matric_percentage}% matric
                      {s.hourly_rate_zar != null ? ` · R${s.hourly_rate_zar}/hr` : ""}
                      {s.topics ? ` · ${s.topics}` : ""}
                    </Text>
                  </View>
                  <Pressable style={styles.requestButton} onPress={() => requestSubject(tutor, s.subject)}>
                    <Text style={styles.requestButtonText}>Request</Text>
                  </Pressable>
                </View>
              ))}

            {showModules &&
              tutor.higher_ed_modules.map((m) => (
                <View key={m.id} style={styles.offerRow}>
                  <View style={[styles.offerDot, { backgroundColor: colorForName(m.name) }]} />
                  <View style={styles.offerTextCol}>
                    <Text style={styles.offerTitle}>{m.name} ({m.year_level_label})</Text>
                    <Text style={styles.offerMeta}>
                      {m.qualification ?? "—"}{m.institution ? ` · ${m.institution}` : ""}
                    </Text>
                  </View>
                  <Pressable style={styles.requestButton} onPress={() => requestModule(tutor, m)}>
                    <Text style={styles.requestButtonText}>Request</Text>
                  </Pressable>
                </View>
              ))}
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  // Generous bottom padding so the last card sits well clear of the
  // device's own bottom nav bar/gesture area.
  container: { padding: 20, paddingBottom: 56, backgroundColor: colors.background, flexGrow: 1 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backLink: { alignSelf: "flex-start" },
  backLinkText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  title: { fontSize: 22, fontWeight: "800", color: colors.text, marginTop: 4 },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4, marginBottom: 14 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 16 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    marginTop: 12,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  cardHeaderRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  cardAvatar: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  cardAvatarText: { fontSize: 17, fontWeight: "800", color: "#fff" },
  cardHeaderTextCol: { flex: 1, minWidth: 0 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.text },
  cardMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  bio: { fontSize: 13, color: colors.text, marginTop: 8, lineHeight: 18 },
  offerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 12,
    gap: 10,
  },
  offerDot: { width: 8, height: 8, borderRadius: 999, flexShrink: 0 },
  offerTextCol: { flex: 1, paddingRight: 10 },
  offerTitle: { fontSize: 14, fontWeight: "700", color: colors.text },
  offerMeta: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  requestButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  requestButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
});
