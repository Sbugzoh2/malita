import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  Dimensions,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors, PAPER_TOPICS, SOLVABLE_TOPICS, topicColors, EXAMPLE_QUESTIONS } from "../theme";
import { ApiError, solve, SolveStep } from "../api/client";
import LatexView from "../latex/LatexView";

export default function AITutorScreen({ route }: any) {
  const { token, me, refreshMe } = useAuth();
  const [paper, setPaper] = useState<"Paper 1" | "Paper 2">("Paper 1");
  const [topic, setTopic] = useState("Algebra");
  const [question, setQuestion] = useState("");
  const [steps, setSteps] = useState<SolveStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [solving, setSolving] = useState(false);
  const [showExamples, setShowExamples] = useState(false);
  const [solveCount, setSolveCount] = useState(0);

  // OCR/PDF screens navigate here with a pre-filled question (their own
  // "Transfer to Solver" equivalent) - adopt it once per navigation, the
  // same one-shot pattern app.py's copied_text uses.
  React.useEffect(() => {
    const prefill = route?.params?.prefillQuestion;
    if (prefill) {
      setQuestion(prefill);
      setSteps(null);
      setError(null);
    }
  }, [route?.params?.prefillQuestion]);

  function selectPaper(p: "Paper 1" | "Paper 2") {
    setPaper(p);
    setTopic(PAPER_TOPICS[p][0]);
    setSteps(null);
    setError(null);
  }

  async function handleSolve() {
    if (!token || !question.trim()) return;
    setSolving(true);
    setError(null);
    setSteps(null);
    try {
      const res = await solve(token, { paper, topic, question: question.trim() });
      setSteps(res.steps);
      setSolveCount((c) => c + 1);
      await refreshMe();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSolving(false);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
      removeClippedSubviews={false}
    >
      <Text style={styles.title}>🧮 AI Tutor</Text>
      <Text style={styles.subtitle}>Grade 12 Mathematics help, worked out one step at a time.</Text>

      <Text style={styles.label}>Paper</Text>
      <View style={styles.row}>
        {(["Paper 1", "Paper 2"] as const).map((p) => (
          <Pressable
            key={p}
            style={[styles.chip, paper === p && styles.chipActive]}
            onPress={() => selectPaper(p)}
          >
            <Text textBreakStrategy="simple" style={[styles.chipText, paper === p && styles.chipTextActive]}>
              {p}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Topic</Text>
      <View style={styles.row}>
        {PAPER_TOPICS[paper].map((t) => {
          const solvable = SOLVABLE_TOPICS.has(t);
          return (
            <Pressable
              key={t}
              style={[
                styles.chip,
                topic === t && { backgroundColor: topicColors[t] ?? colors.primary, borderColor: "transparent" },
                !solvable && styles.chipDisabled,
              ]}
              onPress={() => {
                setTopic(t);
                setSteps(null);
                setError(null);
              }}
            >
              <Text textBreakStrategy="simple" style={[styles.chipText, topic === t && styles.chipTextActive]}>
                {t}
                {!solvable ? " (web only)" : ""}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable style={styles.examplesToggle} onPress={() => setShowExamples((v) => !v)}>
        <Text style={styles.examplesToggleText}>
          {showExamples ? "▾" : "▸"} 💡 Not sure what to type? See examples for this topic
        </Text>
      </Pressable>
      {showExamples && (
        <View style={styles.examplesBox}>
          {(EXAMPLE_QUESTIONS[topic] ?? []).map((ex, i) => (
            <Pressable
              key={i}
              style={styles.exampleRow}
              onPress={() => {
                setQuestion(ex);
                setShowExamples(false);
              }}
            >
              <Text style={styles.exampleText}>{ex}</Text>
            </Pressable>
          ))}
        </View>
      )}

      <Text style={styles.label}>Enter your expression or question</Text>
      <TextInput
        style={styles.input}
        value={question}
        onChangeText={setQuestion}
        placeholder="e.g. x^2-5x+6=0"
        autoCapitalize="none"
      />

      {!SOLVABLE_TOPICS.has(topic) && (
        <Text style={styles.notice}>
          {topic} isn't available in the app yet — try Algebra here, or use the web version for this topic.
        </Text>
      )}

      <Pressable
        style={[styles.solveButton, (solving || !question.trim()) && styles.buttonDisabled]}
        onPress={handleSolve}
        disabled={solving || !question.trim()}
      >
        {solving ? <ActivityIndicator color="#fff" /> : <Text style={styles.solveButtonText}>Solve</Text>}
      </Pressable>

      {me?.daily_limit != null && (
        <Text style={styles.usage}>
          {me.used_today}/{me.daily_limit} solves used today
        </Text>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {steps && (
        // key forces a full fresh mount per solve (not an in-place patch
        // of the previous result's views) - a defensive measure against
        // Android sometimes carrying over stale text measurements when
        // ScrollView content is updated rather than freshly laid out.
        <View key={solveCount} style={styles.resultCard}>
          {steps.map((step, i) => (
            <StepView key={i} step={step} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

export function StepView({ step }: { step: SolveStep }) {
  if (step.type === "latex") {
    return (
      <View style={styles.latexBox}>
        <LatexView latex={step.content} fontSize={16} />
      </View>
    );
  }
  if (step.type === "image") {
    // step.content is already a full "data:image/png;base64,...." URI -
    // see backend/solver.py's StepRecorder.pyplot().
    return (
      <Image
        source={{ uri: step.content }}
        style={styles.stepImage}
        resizeMode="contain"
      />
    );
  }
  const emphasis = step.type === "markdown" || step.type === "write";
  const toneStyle =
    step.type === "error"
      ? styles.stepError
      : step.type === "warning"
      ? styles.stepWarning
      : step.type === "success"
      ? styles.stepSuccess
      : step.type === "info"
      ? styles.stepInfo
      : step.type === "caption"
      ? styles.stepCaption
      : undefined;
  return (
    <MixedText
      text={stripMarkdown(step.content)}
      style={[styles.stepText, emphasis && styles.stepEmphasis, toneStyle]}
    />
  );
}

function stripMarkdown(text: string) {
  return text.replace(/\*\*/g, "").replace(/^#+\s*/, "");
}

// The solver's non-"latex" steps (markdown/write/info/...) sometimes embed
// inline math as $...$ (e.g. "Solve quadratic factor: $x^{2}+4x-4=0$") -
// split on that and render those spans through LatexView instead of
// leaving the raw LaTeX source visible.
function MixedText({ text, style }: { text: string; style: any }) {
  const parts = text.split(/\$([^$]+)\$/);
  if (parts.length === 1) {
    return <Text style={style}>{text}</Text>;
  }
  return (
    <View style={styles.mixedRow}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <LatexView key={i} latex={part} fontSize={15} />
        ) : part ? (
          <Text key={i} style={style}>
            {part}
          </Text>
        ) : null
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
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
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipDisabled: { opacity: 0.6 },
  // flexShrink: 0 - Android's Yoga layout can otherwise measure a Text
  // inside a flexWrap row too narrow on first paint and clip it (only
  // showing the full label after a re-render, e.g. on tap) - locking the
  // label to its natural content width avoids that.
  chipText: { color: colors.text, fontSize: 13, flexShrink: 0 },
  chipTextActive: { color: "#fff", fontWeight: "700" },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    backgroundColor: "#fff",
    marginTop: 4,
  },
  notice: { color: colors.textSecondary, fontSize: 12, marginTop: 8, fontStyle: "italic" },
  examplesToggle: { marginTop: 14 },
  examplesToggleText: { fontSize: 13, color: colors.primaryDark, fontWeight: "600" },
  examplesBox: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    marginTop: 8,
    overflow: "hidden",
  },
  exampleRow: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  exampleText: { fontSize: 13, color: colors.text, fontFamily: "monospace" },
  solveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 16,
  },
  buttonDisabled: { opacity: 0.5 },
  solveButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  usage: { textAlign: "center", color: colors.textSecondary, fontSize: 12, marginTop: 8 },
  error: { color: colors.error, marginTop: 12, textAlign: "center" },
  resultCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
  },
  stepText: { fontSize: 15, color: colors.text, marginBottom: 6, lineHeight: 21 },
  stepEmphasis: { fontWeight: "700", marginTop: 8 },
  mixedRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", marginBottom: 6 },
  stepInfo: { color: colors.primaryDark },
  stepWarning: { color: "#a15c00" },
  stepError: { color: colors.error, fontWeight: "600" },
  stepSuccess: { color: "#0ca30c", fontWeight: "600" },
  stepCaption: { fontSize: 12, color: colors.textSecondary, fontStyle: "italic" },
  stepImage: {
    width: Dimensions.get("window").width - 72,
    height: 220,
    marginVertical: 10,
    borderRadius: 10,
  },
  latexBox: {
    backgroundColor: "#f3f6fb",
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 6,
  },
});
