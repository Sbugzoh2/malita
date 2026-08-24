import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors, topicColors, SUBJECTS, Subject } from "../theme";
import {
  ApiError,
  fetchPracticeTopics,
  fetchPracticeQuestions,
  checkPracticeAnswer,
  recordPracticeSolved,
  PracticeQuestion,
} from "../api/client";
import LatexView from "../latex/LatexView";

export default function PracticeScreen({ navigation }: any) {
  const { token } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [topicsByPaper, setTopicsByPaper] = useState<Record<string, string[]> | null>(null);
  const [paper, setPaper] = useState<string | null>(null);
  const [topic, setTopic] = useState<string | null>(null);
  const [questions, setQuestions] = useState<PracticeQuestion[] | null>(null);
  const [qIndex, setQIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [showHint, setShowHint] = useState(false);
  const [attempt, setAttempt] = useState("");
  const [verdict, setVerdict] = useState<boolean | null | "unchecked">("unchecked");
  const [checking, setChecking] = useState(false);
  const [showSolution, setShowSolution] = useState(false);
  const [recorded, setRecorded] = useState(false);

  useEffect(() => {
    if (!token) return;
    setTopicsByPaper(null);
    fetchPracticeTopics(token, subject)
      .then((res) => {
        setTopicsByPaper(res);
        const firstPaper = Object.keys(res)[0];
        setPaper(firstPaper);
        setTopic(res[firstPaper]?.[0] ?? null);
      })
      .catch(() => setError("Could not load practice topics. Please try again."));
  }, [token, subject]);

  useEffect(() => {
    if (!token || !paper || !topic) return;
    setQuestions(null);
    resetQuestionState();
    fetchPracticeQuestions(token, paper, topic, subject)
      .then((res) => setQuestions(res.questions))
      .catch(() => setError("Could not load practice questions. Please try again."));
  }, [token, paper, topic, subject]);

  function resetQuestionState() {
    setQIndex(0);
    setShowHint(false);
    setAttempt("");
    setVerdict("unchecked");
    setShowSolution(false);
    setRecorded(false);
  }

  function selectQuestion(i: number) {
    setQIndex(i);
    setShowHint(false);
    setAttempt("");
    setVerdict("unchecked");
    setShowSolution(false);
    setRecorded(false);
  }

  async function handleCheck() {
    if (!token || !questions) return;
    setChecking(true);
    try {
      const res = await checkPracticeAnswer(token, attempt, questions[qIndex].final_answer);
      setVerdict(res.correct);
      // Marks only count on a correct check, not just for viewing the
      // solution - matches the web app's Learner Profile behaviour.
      if (res.correct === true && paper && topic && !recorded) {
        setRecorded(true);
        try {
          await recordPracticeSolved(token, paper, topic, questions[qIndex].question);
        } catch {
          // Best-effort progress tracking - not worth surfacing an error for.
        }
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not check your answer. Please try again.");
    } finally {
      setChecking(false);
    }
  }

  function handleShowSolution() {
    setShowSolution(true);
  }

  const q = questions?.[qIndex];

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📝 Practice Questions</Text>
      <Text style={styles.subtitle}>Work through real Grade 12 style questions, topic by topic.</Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.label}>Subject</Text>
      <View style={styles.row}>
        {SUBJECTS.map((s) => (
          <Pressable
            key={s}
            style={[styles.chip, subject === s && styles.chipActive]}
            onPress={() => setSubject(s)}
          >
            <Text textBreakStrategy="simple" style={[styles.chipText, subject === s && styles.chipTextActive]}>
              {s}
            </Text>
          </Pressable>
        ))}
      </View>

      {!topicsByPaper ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : (
        <>
          <Text style={styles.label}>Paper</Text>
          <View style={styles.row}>
            {Object.keys(topicsByPaper).map((p) => (
              <Pressable
                key={p}
                style={[styles.chip, paper === p && styles.chipActive]}
                onPress={() => {
                  setPaper(p);
                  setTopic(topicsByPaper[p][0]);
                }}
              >
                <Text
                  textBreakStrategy="simple"
                  style={[styles.chipText, paper === p && styles.chipTextActive]}
                >
                  {p}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.label}>Topic</Text>
          <View style={styles.row}>
            {(paper ? topicsByPaper[paper] : []).map((t) => (
              <Pressable
                key={t}
                style={[
                  styles.chip,
                  topic === t && { backgroundColor: topicColors[t] ?? colors.primary, borderColor: "transparent" },
                ]}
                onPress={() => setTopic(t)}
              >
                <Text
                  textBreakStrategy="simple"
                  style={[styles.chipText, topic === t && styles.chipTextActive]}
                >
                  {t}
                </Text>
              </Pressable>
            ))}
          </View>

          {!questions ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
          ) : (
            <>
              <Text style={styles.label}>Question</Text>
              <View style={styles.row}>
                {questions.map((_, i) => (
                  <Pressable
                    key={i}
                    style={[styles.chip, styles.qChip, qIndex === i && styles.chipActive]}
                    onPress={() => selectQuestion(i)}
                  >
                    <Text
                      textBreakStrategy="simple"
                      style={[styles.chipText, qIndex === i && styles.chipTextActive]}
                    >
                      Q{i + 1}
                    </Text>
                  </Pressable>
                ))}
              </View>

              {q && (
                <View style={styles.card}>
                  <Text style={styles.meta}>
                    Difficulty: {q.difficulty ?? "—"} · Marks: {q.Marks}
                  </Text>
                  <View style={styles.latexBox}>
                    <LatexView latex={q.question} fontSize={16} />
                  </View>

                  {q.hint ? (
                    <>
                      <Pressable style={styles.hintToggle} onPress={() => setShowHint((v) => !v)}>
                        <Text style={styles.hintToggleText}>
                          {showHint ? "▾" : "▸"} 💡 Need a hint?
                        </Text>
                      </Pressable>
                      {showHint && (
                        <View style={styles.hintBox}>
                          <LatexView latex={q.hint} fontSize={14} />
                        </View>
                      )}
                    </>
                  ) : null}

                  <Text style={styles.label}>Type your final answer here (e.g. x=3 or x=2), then check it</Text>
                  <TextInput
                    style={styles.input}
                    value={attempt}
                    onChangeText={(v) => {
                      setAttempt(v);
                      setVerdict("unchecked");
                    }}
                    placeholder="e.g. x=3 or x=2"
                    autoCapitalize="none"
                  />

                  <View style={styles.buttonRow}>
                    <Pressable
                      style={[styles.actionButton, !attempt.trim() && styles.buttonDisabled]}
                      onPress={handleCheck}
                      disabled={!attempt.trim() || checking}
                    >
                      {checking ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <Text style={styles.actionButtonText}>✅ Check My Answer</Text>
                      )}
                    </Pressable>
                    <Pressable style={styles.actionButtonOutline} onPress={handleShowSolution}>
                      <Text style={styles.actionButtonOutlineText}>📖 Show Solution</Text>
                    </Pressable>
                  </View>

                  {verdict === true && <Text style={styles.verdictCorrect}>Correct! 🎉</Text>}
                  {verdict === false && (
                    <Text style={styles.verdictWrong}>Not quite — try again, or reveal the solution below.</Text>
                  )}

                  {showSolution && (
                    <View style={styles.solutionBox}>
                      <Text style={styles.solutionTitle}>✏️ Step-by-Step Solution</Text>
                      {q.solution_steps.map((step, i) => (
                        <View key={i} style={styles.stepBlock}>
                          <Text style={styles.stepExplain}>
                            Step {i + 1}: {step.explain}
                          </Text>
                          <View style={styles.latexBox}>
                            <LatexView latex={step.latex} fontSize={15} />
                          </View>
                        </View>
                      ))}
                      <Text style={styles.finalAnswerLabel}>Final Answer</Text>
                      <View style={styles.latexBox}>
                        <LatexView latex={q.final_answer} fontSize={16} />
                      </View>
                      <Text style={styles.marksNote}>Total Marks: {q.Marks}</Text>
                      <Text style={styles.marksHint}>
                        Marks are only added to your Learner Profile when you type the final answer above and
                        check it correctly — viewing this solution is just for reference.
                      </Text>
                    </View>
                  )}
                </View>
              )}
            </>
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
    alignSelf: "flex-start",
    flexShrink: 0,
    flexGrow: 0,
  },
  qChip: { paddingHorizontal: 12 },
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipText: { color: colors.text, fontSize: 13, flexShrink: 0 },
  chipTextActive: { color: "#fff", fontWeight: "700" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 18,
  },
  meta: { fontSize: 12, color: colors.textSecondary, marginBottom: 8 },
  latexBox: {
    backgroundColor: "#f3f6fb",
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 6,
  },
  hintToggle: { marginTop: 8 },
  hintToggleText: { fontSize: 13, color: colors.primaryDark, fontWeight: "600" },
  hintBox: {
    backgroundColor: "#fff4e5",
    borderRadius: 10,
    padding: 10,
    marginTop: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: "#fff",
    marginTop: 4,
  },
  buttonRow: { flexDirection: "row", gap: 10, marginTop: 12, flexWrap: "wrap" },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  buttonDisabled: { opacity: 0.5 },
  actionButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  actionButtonOutline: {
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  actionButtonOutlineText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
  verdictCorrect: { color: "#0ca30c", fontWeight: "700", marginTop: 10 },
  verdictWrong: { color: colors.error, fontWeight: "600", marginTop: 10 },
  solutionBox: { marginTop: 16, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 14 },
  solutionTitle: { fontSize: 15, fontWeight: "700", color: colors.text, marginBottom: 8 },
  stepBlock: { marginBottom: 8 },
  stepExplain: { fontSize: 13, color: colors.text, fontWeight: "600", marginBottom: 4 },
  finalAnswerLabel: { fontSize: 13, fontWeight: "700", color: "#0ca30c", marginTop: 8 },
  marksNote: { fontSize: 12, color: colors.textSecondary, marginTop: 6, fontStyle: "italic" },
  marksHint: { fontSize: 11, color: colors.textSecondary, marginTop: 4 },
});
