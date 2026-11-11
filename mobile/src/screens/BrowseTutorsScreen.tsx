import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors, SUBJECTS, Subject } from "../theme";
import { ApiError, DirectoryTutor, fetchTutorsDirectory } from "../api/client";
import Dropdown from "../components/Dropdown";

export default function BrowseTutorsScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const isHigherEd = me?.user.account_type === "higher_ed";

  const [subjectFilter, setSubjectFilter] = useState<Subject | null>(null);
  const [tutors, setTutors] = useState<DirectoryTutor[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorsDirectory(token, { subject: !isHigherEd && subjectFilter ? subjectFilter : undefined })
      .then((res) => setTutors(res.tutors))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the tutor directory."));
  }, [token, isHigherEd, subjectFilter]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
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

  const visibleTutors = (tutors ?? []).filter((t) =>
    isHigherEd ? t.higher_ed_modules.length > 0 : t.subjects.length > 0
  );

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>🔎 Browse Tutors</Text>
      <Text style={styles.subtitle}>
        Pick a specific tutor instead of broadcasting a request. Once they accept, it's the exact same
        flow — a Google Meet link is created and you'll be asked to pay before the session is confirmed.
      </Text>

      {!isHigherEd && (
        <Dropdown
          label="Filter by subject (optional)"
          options={[{ label: "All subjects", value: "" }, ...SUBJECTS.map((s) => ({ label: s, value: s }))]}
          value={subjectFilter ?? ""}
          onChange={(v) => setSubjectFilter((v || null) as Subject | null)}
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
            <Text style={styles.cardTitle}>{tutor.name}</Text>
            <Text style={styles.cardMeta}>{tutor.sessions_completed} session(s) completed on Malita</Text>
            {tutor.bio ? <Text style={styles.bio}>{tutor.bio}</Text> : null}
            {tutor.availability_note ? (
              <Text style={styles.cardMeta}>Availability: {tutor.availability_note}</Text>
            ) : null}

            {!isHigherEd &&
              tutor.subjects.map((s) => (
                <View key={s.subject} style={styles.offerRow}>
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

            {isHigherEd &&
              tutor.higher_ed_modules.map((m) => (
                <View key={m.id} style={styles.offerRow}>
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
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4, marginBottom: 14 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 16 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    marginTop: 12,
  },
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
  },
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
