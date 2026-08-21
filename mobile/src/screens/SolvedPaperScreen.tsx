import React, { useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, solvePastPaper, SolvedPaperQuestion } from "../api/client";
import { StepView } from "./AITutorScreen";

// Runs every question in a past paper through the LLM fallback and shows
// the worked solutions right here, one question at a time - the mobile
// twin of app.py's "Solve all questions with AI" button.
export default function SolvedPaperScreen({ route, navigation }: any) {
  const { paperId, title } = route.params ?? {};
  const { token } = useAuth();
  const [questions, setQuestions] = useState<SolvedPaperQuestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!token || !paperId) return;
    solvePastPaper(token, paperId)
      .then((res) => setQuestions(res.questions))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't solve this paper. Please try again."))
      .finally(() => setLoading(false));
  }, [token, paperId]);

  function toggle(number: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(number)) next.delete(number);
      else next.add(number);
      return next;
    });
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.goBack()}>
        <Text style={styles.backLinkText}>‹ Back</Text>
      </Pressable>
      <Text style={styles.title}>🧠 AI-Solved: {title ?? "Past Paper"}</Text>

      {loading ? (
        <View style={styles.centerBox}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={styles.loadingText}>
            Reading the paper and solving every question with AI — this can take a minute for a full paper…
          </Text>
        </View>
      ) : error ? (
        <Text style={styles.error}>{error}</Text>
      ) : questions && questions.length > 0 ? (
        questions.map((q) => {
          const isOpen = expanded.has(q.number);
          return (
            <View key={q.number} style={styles.card}>
              <Pressable style={styles.cardHeader} onPress={() => toggle(q.number)}>
                <Text style={styles.cardHeaderText}>Question {q.number}</Text>
                <Text style={styles.chevron}>{isOpen ? "▲" : "▼"}</Text>
              </Pressable>
              {isOpen && (
                <View style={styles.cardBody}>
                  <Text style={styles.originalLabel}>Original question (as extracted from the PDF):</Text>
                  <Text style={styles.originalText}>{q.text}</Text>
                  {q.steps.map((step, i) => (
                    <StepView key={i} step={step} />
                  ))}
                </View>
              )}
            </View>
          );
        })
      ) : (
        <Text style={styles.emptyText}>Couldn't detect individual questions in this document.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 20, fontWeight: "700", color: colors.text, marginBottom: 16 },
  centerBox: { alignItems: "center", marginTop: 40 },
  loadingText: { color: colors.textSecondary, textAlign: "center", marginTop: 16, paddingHorizontal: 16 },
  error: { color: colors.error, marginTop: 12 },
  emptyText: { color: colors.textSecondary, marginTop: 12 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    marginBottom: 12,
    overflow: "hidden",
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 14,
    paddingHorizontal: 16,
  },
  cardHeaderText: { fontSize: 15, fontWeight: "700", color: colors.text },
  chevron: { fontSize: 12, color: colors.textSecondary },
  cardBody: { paddingHorizontal: 16, paddingBottom: 16 },
  originalLabel: { fontSize: 12, color: colors.textSecondary, marginBottom: 6 },
  originalText: {
    fontSize: 13,
    color: colors.text,
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
});
