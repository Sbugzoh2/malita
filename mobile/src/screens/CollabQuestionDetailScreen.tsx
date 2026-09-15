import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  fetchCollabQuestion,
  createCollabAnswer,
  reportCollabContent,
  CollabQuestionDetail,
  CollabAnswer,
} from "../api/client";
import MixedMathText from "../latex/MixedMathText";

function formatDate(iso: string | null): string {
  if (!iso) return "Unknown date";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "Unknown date";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

// A small inline "report" widget, reused for both the question and every
// answer. Deliberately not Alert.prompt() - that's iOS-only in React
// Native and silently doesn't work on Android, which is this app's
// primary platform.
function ReportControl({
  targetType,
  targetId,
  token,
}: {
  targetType: "question" | "answer";
  targetId: number;
  token: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function submit() {
    if (!token) return;
    setSubmitting(true);
    try {
      await reportCollabContent(token, { target_type: targetType, target_id: targetId, reason });
      setDone(true);
      setOpen(false);
    } catch (e) {
      Alert.alert("Error", e instanceof ApiError ? e.message : "Could not submit the report.");
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return <Text style={styles.reportDoneText}>🚩 Reported — thanks, an admin will review this.</Text>;
  }

  return (
    <View>
      <Pressable onPress={() => setOpen(!open)}>
        <Text style={styles.reportLink}>🚩 Report this {targetType}</Text>
      </Pressable>
      {open && (
        <View style={styles.reportBox}>
          <TextInput
            style={styles.reportInput}
            value={reason}
            onChangeText={setReason}
            placeholder="Why are you reporting this? (optional)"
          />
          <Pressable
            style={[styles.reportSubmitButton, submitting && styles.buttonDisabled]}
            onPress={submit}
            disabled={submitting}
          >
            {submitting ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.reportSubmitText}>Submit report</Text>}
          </Pressable>
        </View>
      )}
    </View>
  );
}

type ReplyTarget = { id: number; name: string } | null;

function AnswerCard({
  answer,
  isReply,
  token,
  onReply,
}: {
  answer: CollabAnswer;
  isReply: boolean;
  token: string | null;
  onReply: (target: ReplyTarget) => void;
}) {
  return (
    <View style={[styles.answerCard, isReply && styles.replyCard]}>
      <Text style={styles.answerMeta}>
        {isReply ? "↳ " : ""}{answer.answerer_name} · {formatDate(answer.created_at)}
      </Text>
      <MixedMathText text={answer.body} fontSize={14} />
      <View style={styles.answerActions}>
        <Pressable onPress={() => onReply({ id: answer.id, name: answer.answerer_name })}>
          <Text style={styles.replyLink}>↩️ Reply</Text>
        </Pressable>
      </View>
      <ReportControl targetType="answer" targetId={answer.id} token={token} />
    </View>
  );
}

export default function CollabQuestionDetailScreen({ navigation, route }: any) {
  const { token } = useAuth();
  const questionId: number = route.params.questionId;
  const [question, setQuestion] = useState<CollabQuestionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [answerBody, setAnswerBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [replyTarget, setReplyTarget] = useState<ReplyTarget>(null);

  function load() {
    if (!token) return;
    setError(null);
    fetchCollabQuestion(token, questionId)
      .then(setQuestion)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load this question. Please try again.")
      );
  }

  useEffect(load, [token, questionId]);

  function handleReply(target: ReplyTarget) {
    setReplyTarget(target);
    setAnswerBody(target ? `@${target.name} ` : "");
  }

  async function handlePostAnswer() {
    if (!token) return;
    if (!answerBody.trim()) {
      setError("Please write out your answer.");
      return;
    }
    setPosting(true);
    setError(null);
    try {
      // A reply to a reply still targets the original top-level answer
      // (backend.collab enforces this too, as a safety net) - @mentioning
      // the actual person is how it stays clear who's being addressed.
      await createCollabAnswer(token, questionId, answerBody.trim(), replyTarget?.id ?? null);
      setAnswerBody("");
      setReplyTarget(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not post your answer. Please try again.");
    } finally {
      setPosting(false);
    }
  }

  if (!question) {
    return (
      <View style={styles.center}>
        {error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator color={colors.primary} />}
      </View>
    );
  }

  const topLevel = question.answers.filter((a) => !a.parent_id);
  const repliesByParent: Record<number, CollabAnswer[]> = {};
  for (const a of question.answers) {
    if (a.parent_id) {
      (repliesByParent[a.parent_id] ??= []).push(a);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Pressable style={styles.backLink} onPress={() => navigation.goBack()}>
        <Text style={styles.backLinkText}>‹ Back to questions</Text>
      </Pressable>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.title}>{question.title}</Text>
      <Text style={styles.meta}>
        Asked by {question.asker_name} · {question.topic || "No topic"} · {formatDate(question.created_at)}
      </Text>
      <MixedMathText text={question.body} fontSize={14} />
      <View style={{ marginTop: 8 }}>
        <ReportControl targetType="question" targetId={question.id} token={token} />
      </View>

      <View style={styles.divider} />

      <Text style={styles.sectionTitle}>
        {question.answers.length} answer{question.answers.length !== 1 ? "s" : ""}
      </Text>
      {topLevel.map((a) => (
        <View key={a.id}>
          <AnswerCard answer={a} isReply={false} token={token} onReply={handleReply} />
          {(repliesByParent[a.id] ?? []).map((reply) => (
            <AnswerCard key={reply.id} answer={reply} isReply token={token} onReply={handleReply} />
          ))}
        </View>
      ))}

      <View style={styles.answerBox}>
        {replyTarget ? (
          <View style={styles.replyBanner}>
            <Text style={styles.replyBannerText}>↩️ Replying to {replyTarget.name}</Text>
            <Pressable onPress={() => handleReply(null)}>
              <Text style={styles.replyBannerCancel}>Cancel</Text>
            </Pressable>
          </View>
        ) : null}
        <Text style={styles.label}>Your answer</Text>
        <TextInput
          style={[styles.input, styles.textArea]}
          value={answerBody}
          onChangeText={setAnswerBody}
          placeholder="Write your answer..."
          multiline
        />
        <Text style={styles.mathTip}>Tip: put math between two dollar signs to render it as a real equation, e.g. $x^2-5x+6=0$.</Text>
        <Pressable
          style={[styles.actionButton, posting && styles.buttonDisabled]}
          onPress={handlePostAnswer}
          disabled={posting}
        >
          {posting ? <ActivityIndicator color="#fff" /> : <Text style={styles.actionButtonText}>Post answer</Text>}
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background, padding: 20 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  error: { color: colors.error, marginBottom: 12 },
  title: { fontSize: 22, fontWeight: "700", color: colors.text },
  meta: { fontSize: 12, color: colors.textSecondary, marginTop: 4, marginBottom: 10 },
  body: { fontSize: 14, color: colors.text, marginBottom: 8 },
  reportLink: { fontSize: 12, color: colors.error, marginBottom: 4 },
  reportDoneText: { fontSize: 12, color: colors.textSecondary, fontStyle: "italic" },
  reportBox: { marginTop: 6, marginBottom: 6 },
  reportInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
    backgroundColor: "#fff",
    marginBottom: 8,
  },
  reportSubmitButton: {
    backgroundColor: colors.error,
    borderRadius: 999,
    paddingVertical: 8,
    alignItems: "center",
    alignSelf: "flex-start",
    paddingHorizontal: 16,
  },
  reportSubmitText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 18 },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 10 },
  answerCard: { backgroundColor: colors.surface, borderRadius: 14, padding: 14, marginBottom: 10 },
  replyCard: { marginLeft: 24, backgroundColor: "#f3f6fb" },
  answerMeta: { fontSize: 12, fontWeight: "700", color: colors.primaryDark, marginBottom: 6 },
  answerActions: { marginTop: 8, marginBottom: 4 },
  replyLink: { fontSize: 12, color: colors.primary, fontWeight: "700" },
  answerBox: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 10 },
  replyBanner: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "#eaf2fc",
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: 10,
  },
  replyBannerText: { fontSize: 13, color: colors.primaryDark, fontWeight: "600" },
  replyBannerCancel: { fontSize: 13, color: colors.error, fontWeight: "700" },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginBottom: 6 },
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
  mathTip: { fontSize: 11, color: colors.textSecondary, fontStyle: "italic", marginTop: 6 },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 14,
  },
  buttonDisabled: { opacity: 0.6 },
  actionButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
});
