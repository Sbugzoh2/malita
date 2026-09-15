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
  fetchCollabReports,
  resolveCollabReport,
  CollabReport,
} from "../api/client";
import MixedMathText from "../latex/MixedMathText";

function formatDate(iso: string | null): string {
  if (!iso) return "Unknown date";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "Unknown date";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function ModerationQueue({ token }: { token: string }) {
  const [expanded, setExpanded] = useState(false);
  const [reports, setReports] = useState<CollabReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notify, setNotify] = useState<Record<number, boolean>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});

  function load() {
    setReports(null);
    setError(null);
    fetchCollabReports(token)
      .then((res) => setReports(res.reports))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load reports."));
  }

  useEffect(() => {
    if (expanded) load();
  }, [expanded]);

  async function act(reportId: number, action: "hide" | "delete" | "dismiss") {
    setBusyId(reportId);
    setError(null);
    try {
      await resolveCollabReport(token, reportId, {
        action,
        notify_reporter: !!notify[reportId],
        note: notes[reportId] || "",
      });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update that report.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <View style={styles.modBox}>
      <Pressable style={styles.modToggle} onPress={() => setExpanded(!expanded)}>
        <Text style={styles.modToggleText}>
          {expanded ? "▾" : "▸"} 🛠️ Moderation queue (admin){reports ? ` — ${reports.length} open` : ""}
        </Text>
      </Pressable>

      {expanded && (
        <View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          {!reports ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: 12 }} />
          ) : reports.length === 0 ? (
            <Text style={styles.emptyNote}>No open reports.</Text>
          ) : (
            reports.map((rep) => (
              <View key={rep.id} style={styles.modCard}>
                <Text style={styles.modCardTitle}>
                  {rep.target_type[0].toUpperCase() + rep.target_type.slice(1)} #{rep.target_id} — reported by {rep.reporter_name}
                </Text>
                {rep.reason ? <Text style={styles.modCardMeta}>Reason given: {rep.reason}</Text> : null}
                <Text style={styles.modCardPreview}>{rep.preview}</Text>
                {rep.already_hidden ? (
                  <Text style={styles.modCardMeta}>Already hidden by an earlier report.</Text>
                ) : null}

                <Pressable
                  style={styles.checkboxRow}
                  onPress={() => setNotify({ ...notify, [rep.id]: !notify[rep.id] })}
                >
                  <Text style={styles.checkboxBox}>{notify[rep.id] ? "☑" : "☐"}</Text>
                  <Text style={styles.checkboxLabel}>Let the reporter know the outcome</Text>
                </Pressable>
                {notify[rep.id] && (
                  <TextInput
                    style={styles.input}
                    value={notes[rep.id] || ""}
                    onChangeText={(t) => setNotes({ ...notes, [rep.id]: t })}
                    placeholder="Optional note to include"
                  />
                )}

                <View style={styles.modActionsRow}>
                  <Pressable
                    style={[styles.modActionButton, busyId === rep.id && styles.buttonDisabled]}
                    onPress={() => act(rep.id, "hide")}
                    disabled={busyId === rep.id}
                  >
                    <Text style={styles.modActionButtonText}>Hide</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.modActionButton, styles.modActionButtonDanger, busyId === rep.id && styles.buttonDisabled]}
                    onPress={() => act(rep.id, "delete")}
                    disabled={busyId === rep.id}
                  >
                    <Text style={styles.modActionButtonText}>Delete</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.modActionButton, styles.modActionButtonSecondary, busyId === rep.id && styles.buttonDisabled]}
                    onPress={() => act(rep.id, "dismiss")}
                    disabled={busyId === rep.id}
                  >
                    <Text style={styles.modActionButtonTextSecondary}>Dismiss</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>
      )}
    </View>
  );
}

export default function CollabScreen({ navigation }: any) {
  const { token, me } = useAuth();
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

      {me?.is_admin && token ? <ModerationQueue token={token} /> : null}

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
  modBox: { backgroundColor: colors.surface, borderRadius: 16, padding: 14, marginBottom: 16 },
  modToggle: {},
  modToggleText: { fontSize: 14, fontWeight: "700", color: colors.primaryDark },
  modCard: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: 12, paddingTop: 12 },
  modCardTitle: { fontSize: 13, fontWeight: "700", color: colors.text, marginBottom: 4 },
  modCardMeta: { fontSize: 12, color: colors.textSecondary, marginBottom: 4 },
  modCardPreview: { fontSize: 13, color: colors.text, marginBottom: 8 },
  checkboxRow: { flexDirection: "row", alignItems: "center", marginTop: 4, marginBottom: 6 },
  checkboxBox: { fontSize: 16, marginRight: 8, color: colors.primaryDark },
  checkboxLabel: { fontSize: 12, color: colors.textSecondary },
  modActionsRow: { flexDirection: "row", gap: 8, marginTop: 8 },
  modActionButton: {
    flex: 1,
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 9,
    alignItems: "center",
  },
  modActionButtonDanger: { backgroundColor: colors.error },
  modActionButtonSecondary: { backgroundColor: "#fff", borderWidth: 1, borderColor: colors.border },
  modActionButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  modActionButtonTextSecondary: { color: colors.text, fontWeight: "700", fontSize: 13 },
});
