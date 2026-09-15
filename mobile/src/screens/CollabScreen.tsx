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
import { colors, SUBJECTS, Subject } from "../theme";
import {
  ApiError,
  fetchCollabQuestions,
  createCollabQuestion,
  CollabQuestionSummary,
} from "../api/client";
import MixedMathText from "../latex/MixedMathText";

function formatDate(iso: string | null): string {
  if (!iso) return "Unknown date";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "Unknown date";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export default function CollabScreen({ navigation }: any) {
  const { token } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [questions, setQuestions] = useState<CollabQuestionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showAsk, setShowAsk] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);

  function load() {
    if (!token) return;
    setQuestions(null);
    setError(null);
    fetchCollabQuestions(token, subject)
      .then((res) => setQuestions(res.questions))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load questions. Please try again.")
      );
  }

  useEffect(load, [token, subject]);

  async function handlePost() {
    if (!token) return;
    if (!title.trim() || !body.trim()) {
      setError("Please add a title and your question.");
      return;
    }
    setPosting(true);
    setError(null);
    try {
      await createCollabQuestion(token, { subject, title: title.trim(), body: body.trim() });
      setTitle("");
      setBody("");
      setShowAsk(false);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not post your question. Please try again.");
    } finally {
      setPosting(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>🤝 Collaboration Forum</Text>
      <Text style={styles.subtitle}>Ask a question, help another learner, or browse what others are stuck on.</Text>

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

      <Pressable style={styles.askToggle} onPress={() => setShowAsk(!showAsk)}>
        <Text style={styles.askToggleText}>{showAsk ? "▾" : "▸"} ➕ Ask a question</Text>
      </Pressable>

      {showAsk && (
        <View style={styles.askBox}>
          <Text style={styles.label}>Title</Text>
          <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="e.g. How do I factorise a quadratic?" />
          <Text style={styles.label}>Your question</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={body}
            onChangeText={setBody}
            placeholder="Write out your question..."
            multiline
          />
          <Text style={styles.mathTip}>Tip: put math between two dollar signs to render it as a real equation, e.g. $x^2-5x+6=0$.</Text>
          <Pressable
            style={[styles.actionButton, posting && styles.buttonDisabled]}
            onPress={handlePost}
            disabled={posting}
          >
            {posting ? <ActivityIndicator color="#fff" /> : <Text style={styles.actionButtonText}>Post question</Text>}
          </Pressable>
        </View>
      )}

      {!questions ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : questions.length === 0 ? (
        <Text style={styles.emptyNote}>No {subject} questions yet — be the first to ask!</Text>
      ) : (
        questions.map((q) => (
          <Pressable
            key={q.id}
            style={styles.card}
            onPress={() => navigation.navigate("CollabQuestionDetail", { questionId: q.id })}
          >
            <Text style={styles.cardTitle}>{q.title}</Text>
            <Text style={styles.cardMeta}>
              {q.asker_name} · {q.topic || "No topic"} · {formatDate(q.created_at)} · {q.answer_count} answer
              {q.answer_count !== 1 ? "s" : ""}
            </Text>
            <View style={styles.cardBodyWrap}>
              <MixedMathText text={q.body.length > 200 ? q.body.slice(0, 200) + "…" : q.body} fontSize={13} />
            </View>
          </Pressable>
        ))
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
  askToggle: { marginTop: 18 },
  askToggleText: { fontSize: 15, fontWeight: "700", color: colors.primaryDark },
  askBox: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 10 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: "#fff",
  },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 14,
  },
  buttonDisabled: { opacity: 0.6 },
  actionButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  emptyNote: { fontSize: 13, color: colors.textSecondary, fontStyle: "italic", marginTop: 24 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 14,
  },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 4 },
  cardMeta: { fontSize: 12, color: colors.textSecondary, marginBottom: 6 },
  cardBody: { fontSize: 13, color: colors.text },
  cardBodyWrap: { marginTop: 2 },
  mathTip: { fontSize: 11, color: colors.textSecondary, fontStyle: "italic", marginTop: 6 },
});
