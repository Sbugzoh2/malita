import React, { useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors, topicColors, SUBJECTS, Subject } from "../theme";
import { fetchLearnerProfile, LearnerProfile } from "../api/client";
import LatexView from "../latex/LatexView";

const DEFAULT_TOPIC_COLOR = colors.primary;

function formatDate(iso: string | null): string {
  if (!iso) return "Unknown date";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "Unknown date";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

// Practice-source questions are already proper LaTeX; AI Tutor questions
// are whatever the learner typed, ranging from a clean expression to a
// full English word problem - only genuine LaTeX or a short, word-free
// expression is worth rendering as math, same rule app.py's Recent
// Activity uses, so a word problem doesn't get mangled by math mode.
const CLEAN_EXPR_RE = /^[0-9a-zA-Z\s^+\-*/=<>().,;:]+$/;
const LONG_WORD_RE = /[a-zA-Z]{4,}/;

function isLikelyLatex(text: string): boolean {
  if (text.includes("\\")) return true;
  return CLEAN_EXPR_RE.test(text) && !LONG_WORD_RE.test(text);
}

export default function LearnerProfileScreen({ navigation }: any) {
  const { token } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setProfile(null);
    setError(null);
    fetchLearnerProfile(token, subject)
      .then(setProfile)
      .catch(() => setError("Could not load your progress. Please try again."));
  }, [token, subject]);

  const maxTopicCount = profile
    ? Math.max(1, ...Object.values(profile.topic_counts))
    : 1;

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>🎯 Learner Profile</Text>
      <Text style={styles.subtitle}>Track your progress across the AI Tutor and Practice Questions.</Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.label}>Subject</Text>
      <View style={styles.row}>
        {SUBJECTS.map((s) => (
          <Pressable
            key={s}
            style={[styles.chip, subject === s && styles.chipActive]}
            onPress={() => setSubject(s)}
          >
            <Text style={[styles.chipText, subject === s && styles.chipTextActive]}>{s}</Text>
          </Pressable>
        ))}
      </View>

      {!profile ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 32 }} />
      ) : (
        <>
          <View style={styles.statsRow}>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{profile.solved}</Text>
              <Text style={styles.statLabel}>Questions Solved</Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{profile.marks}</Text>
              <Text style={styles.statLabel}>Marks Earned</Text>
            </View>
          </View>

          <View style={styles.badgeCard}>
            <Text style={styles.badgeLabel}>Badge: {profile.badge.label}</Text>
            {profile.badge.next_milestone != null && (
              <>
                <View style={styles.progressTrack}>
                  <View
                    style={[
                      styles.progressFill,
                      { width: `${Math.min(100, (profile.solved / profile.badge.next_milestone) * 100)}%` },
                    ]}
                  />
                </View>
                <Text style={styles.progressCaption}>
                  {profile.badge.remaining_to_next} more solved question
                  {profile.badge.remaining_to_next === 1 ? "" : "s"} to your next badge.
                </Text>
              </>
            )}
          </View>

          <Text style={styles.sectionTitle}>📊 Questions solved per topic</Text>
          {Object.keys(profile.topic_counts).length === 0 ? (
            <Text style={styles.emptyNote}>Solve some practice questions to see your progress here!</Text>
          ) : (
            <View style={styles.chartCard}>
              {Object.entries(profile.topic_counts).map(([topic, count]) => (
                <View key={topic} style={styles.barRow}>
                  <Text style={styles.barLabel} numberOfLines={1}>{topic}</Text>
                  <View style={styles.barTrack}>
                    <View
                      style={[
                        styles.barFill,
                        {
                          width: `${(count / maxTopicCount) * 100}%`,
                          backgroundColor: topicColors[topic] ?? DEFAULT_TOPIC_COLOR,
                        },
                      ]}
                    />
                  </View>
                  <Text style={styles.barCount}>{count}</Text>
                </View>
              ))}
            </View>
          )}

          <Text style={styles.sectionTitle}>🕒 Recent Activity</Text>
          {profile.recent.length === 0 ? (
            <Text style={styles.emptyNote}>Nothing solved yet for this subject.</Text>
          ) : (
            profile.recent.map((r, i) => (
              <View key={i} style={styles.activityCard}>
                <View style={styles.activityHeader}>
                  <Text style={styles.activityType}>
                    {r.source === "ai_tutor" ? "AI Tutor" : "Practice Question"}
                  </Text>
                  <Text style={styles.activityDate}>{formatDate(r.solved_at)}</Text>
                </View>
                <Text style={styles.activityMeta}>
                  {r.paper || "No paper specified"} · {r.topic || "No topic specified"}
                </Text>
                {r.question ? (
                  isLikelyLatex(r.question) ? (
                    <View style={styles.activityLatexBox}>
                      <LatexView latex={r.question} />
                    </View>
                  ) : (
                    <Text style={styles.activityQuestion}>{r.question}</Text>
                  )
                ) : null}
              </View>
            ))
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  error: { color: colors.error, marginBottom: 12 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 14, marginBottom: 6 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipText: { color: colors.text, fontSize: 13 },
  chipTextActive: { color: "#fff", fontWeight: "700" },
  statsRow: { flexDirection: "row", gap: 12, marginTop: 18 },
  statCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    alignItems: "center",
  },
  statValue: { fontSize: 28, fontWeight: "800", color: colors.primary },
  statLabel: { fontSize: 12, color: colors.textSecondary, marginTop: 4, textAlign: "center" },
  badgeCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 12 },
  badgeLabel: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 10 },
  progressTrack: { height: 8, backgroundColor: colors.border, borderRadius: 999, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: colors.primary, borderRadius: 999 },
  progressCaption: { fontSize: 12, color: colors.textSecondary, marginTop: 6 },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginTop: 22, marginBottom: 10 },
  emptyNote: { fontSize: 13, color: colors.textSecondary, fontStyle: "italic" },
  chartCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 16 },
  barRow: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  barLabel: { width: 110, fontSize: 12, color: colors.text },
  barTrack: { flex: 1, height: 14, backgroundColor: colors.border, borderRadius: 999, overflow: "hidden", marginHorizontal: 8 },
  barFill: { height: "100%", borderRadius: 999 },
  barCount: { fontSize: 12, fontWeight: "700", color: colors.text, width: 20, textAlign: "right" },
  activityCard: { backgroundColor: colors.surface, borderRadius: 14, padding: 14, marginBottom: 10 },
  activityHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 4 },
  activityType: { fontSize: 13, fontWeight: "700", color: colors.primaryDark },
  activityDate: { fontSize: 12, color: colors.textSecondary },
  activityMeta: { fontSize: 12, color: colors.textSecondary, marginBottom: 6 },
  activityLatexBox: { backgroundColor: "#f3f6fb", borderRadius: 10, padding: 10 },
  activityQuestion: { fontSize: 13, color: colors.text },
});
