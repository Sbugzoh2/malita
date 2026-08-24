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
  Alert,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import { useAuth } from "../context/AuthContext";
import { colors, PAPER_TOPICS_BY_SUBJECT, SOLVABLE_TOPICS, topicColors, EXAMPLE_QUESTIONS, SUBJECTS, Subject } from "../theme";
import {
  ApiError,
  solve,
  SolveStep,
  solvePhotoWithAI,
  SolvedPhotoQuestion,
  solvePdfWithAI,
  SolvedPdfQuestion,
} from "../api/client";
import LatexView from "../latex/LatexView";

type Method = "text" | "photo" | "pdf";

const METHODS: { key: Method; label: string }[] = [
  { key: "text", label: "✍️ Type a Question" },
  { key: "photo", label: "📷 Photo" },
  { key: "pdf", label: "📄 PDF" },
];

export default function AITutorScreen() {
  const { me } = useAuth();
  const [method, setMethod] = useState<Method>("text");

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
      removeClippedSubviews={false}
    >
      <Text style={styles.title}>🧮 AI Tutor</Text>
      <Text style={styles.subtitle}>
        Grade 12 Mathematics help, worked out one step at a time — type a question, snap or
        upload a photo, or upload a whole PDF.
      </Text>

      <View style={styles.methodRow}>
        {METHODS.map((m) => (
          <Pressable
            key={m.key}
            style={[styles.methodChip, method === m.key && styles.methodChipActive]}
            onPress={() => setMethod(m.key)}
          >
            <Text style={[styles.methodChipText, method === m.key && styles.methodChipTextActive]}>
              {m.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {method === "text" && <TextSolver />}
      {method === "photo" && <PhotoSolver locked={me?.effective_tier === "free"} />}
      {method === "pdf" && <PdfSolver locked={me?.effective_tier === "free"} />}
    </ScrollView>
  );
}

function TextSolver() {
  const { token, me, refreshMe } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [paper, setPaper] = useState<string>("Paper 1");
  const [topic, setTopic] = useState("Algebra");
  const [question, setQuestion] = useState("");
  const [steps, setSteps] = useState<SolveStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [solving, setSolving] = useState(false);
  const [showExamples, setShowExamples] = useState(false);
  const [solveCount, setSolveCount] = useState(0);

  const paperOptions = Object.keys(PAPER_TOPICS_BY_SUBJECT[subject]);

  function selectSubject(s: Subject) {
    setSubject(s);
    const firstPaper = Object.keys(PAPER_TOPICS_BY_SUBJECT[s])[0];
    setPaper(firstPaper);
    setTopic(PAPER_TOPICS_BY_SUBJECT[s][firstPaper][0]);
    setSteps(null);
    setError(null);
  }

  function selectPaper(p: string) {
    setPaper(p);
    setTopic(PAPER_TOPICS_BY_SUBJECT[subject][p][0]);
    setSteps(null);
    setError(null);
  }

  // Physical Sciences has no deterministic solver at all - every question
  // goes through the LLM fallback server-side, the same paid-tier gate
  // OCR/PDF already use (see api_server.py's /solve).
  const physicalSciencesLocked = subject === "Physical Sciences" && me?.effective_tier === "free";

  async function handleSolve() {
    if (!token || !question.trim()) return;
    setSolving(true);
    setError(null);
    setSteps(null);
    try {
      const res = await solve(token, { paper, topic, question: question.trim(), subject });
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
    <>
      <Text style={styles.label}>Subject</Text>
      <View style={styles.row}>
        {SUBJECTS.map((s) => (
          <Pressable
            key={s}
            style={[styles.chip, subject === s && styles.chipActive]}
            onPress={() => selectSubject(s)}
          >
            <Text textBreakStrategy="simple" style={[styles.chipText, subject === s && styles.chipTextActive]}>
              {s}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Paper</Text>
      <View style={styles.row}>
        {paperOptions.map((p) => (
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
        {PAPER_TOPICS_BY_SUBJECT[subject][paper].map((t) => {
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

      {physicalSciencesLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            Physical Sciences is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
        </View>
      ) : (
        <>
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
        </>
      )}
    </>
  );
}

function PhotoSolver({ locked }: { locked: boolean }) {
  const { token } = useAuth();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SolvedPhotoQuestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  async function solvePhoto(uri: string) {
    if (!token) return;
    setImageUri(uri);
    setQuestions(null);
    setError(null);
    setExpanded(new Set());
    setLoading(true);
    try {
      const res = await solvePhotoWithAI(token, uri);
      setQuestions(res.questions);
      if (res.questions.length > 0) setExpanded(new Set([res.questions[0].number]));
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't read that photo. Please try a clearer picture, better lighting, or less glare."
      );
    } finally {
      setLoading(false);
    }
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Camera permission needed", "Enable camera access in your device settings to take a photo.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.9, allowsEditing: false });
    if (!result.canceled && result.assets?.[0]) {
      await solvePhoto(result.assets[0].uri);
    }
  }

  async function pickFromGallery() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Photo library permission needed", "Enable photo access in your device settings to upload an image.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.9,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets?.[0]) {
      await solvePhoto(result.assets[0].uri);
    }
  }

  function retry() {
    if (imageUri) solvePhoto(imageUri);
  }

  function toggle(number: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(number)) next.delete(number);
      else next.add(number);
      return next;
    });
  }

  function reset() {
    setImageUri(null);
    setQuestions(null);
    setError(null);
  }

  if (locked) {
    return (
      <View style={styles.lockedBanner}>
        <Text style={styles.lockedText}>
          Photo upload & OCR is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
        </Text>
      </View>
    );
  }

  return (
    <>
      <View style={styles.row}>
        <Pressable style={styles.actionButton} onPress={takePhoto}>
          <Text style={styles.actionButtonText}>📸 Take Photo</Text>
        </Pressable>
        <Pressable style={styles.actionButton} onPress={pickFromGallery}>
          <Text style={styles.actionButtonText}>🖼️ Choose from Gallery</Text>
        </Pressable>
      </View>

      {imageUri && <Image source={{ uri: imageUri }} style={styles.preview} resizeMode="contain" />}

      {imageUri && !loading && (
        <Pressable style={styles.cancelButton} onPress={reset}>
          <Text style={styles.cancelButtonText}>← Choose a different photo</Text>
        </Pressable>
      )}

      {loading && (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.loadingText}>
            Reading and solving every question in this photo with AI — this may take a moment…
          </Text>
        </View>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {questions && questions.length > 0 && (
        <View style={{ marginTop: 16 }}>
          {questions.map((q) => {
            const isOpen = expanded.has(q.number);
            return (
              <View key={q.number} style={styles.questionCard}>
                <Pressable style={styles.questionHeader} onPress={() => toggle(q.number)}>
                  <Text style={styles.questionHeaderText}>Question {q.number}</Text>
                  <Text style={styles.chevron}>{isOpen ? "▲" : "▼"}</Text>
                </Pressable>
                {isOpen && (
                  <View style={styles.questionBody}>
                    {q.steps.map((step, i) => (
                      <StepView key={i} step={step} />
                    ))}
                  </View>
                )}
              </View>
            );
          })}

          <Pressable style={styles.retryButton} onPress={retry}>
            <Text style={styles.retryButtonText}>🔄 Not right? Re-read and re-solve this photo</Text>
          </Pressable>
        </View>
      )}

      {questions && questions.length === 0 && (
        <Text style={styles.error}>Couldn't detect any questions in that photo.</Text>
      )}
    </>
  );
}

function PdfSolver({ locked }: { locked: boolean }) {
  const { token } = useAuth();
  const [fileName, setFileName] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SolvedPdfQuestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [lastPicked, setLastPicked] = useState<{ uri: string; name: string } | null>(null);

  async function solvePdf(uri: string, name: string) {
    if (!token) return;
    setFileName(name);
    setLastPicked({ uri, name });
    setQuestions(null);
    setError(null);
    setExpanded(new Set());
    setLoading(true);
    try {
      const res = await solvePdfWithAI(token, uri, name);
      setQuestions(res.questions);
      if (res.questions.length > 0) setExpanded(new Set([res.questions[0].number]));
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't read that document. Please try a clearer scan or a different file."
      );
    } finally {
      setLoading(false);
    }
  }

  async function pickPdf() {
    const result = await DocumentPicker.getDocumentAsync({ type: "application/pdf" });
    if (result.canceled || !result.assets?.[0] || !token) return;
    const asset = result.assets[0];
    await solvePdf(asset.uri, asset.name);
  }

  function retry() {
    if (lastPicked) solvePdf(lastPicked.uri, lastPicked.name);
  }

  function toggle(number: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(number)) next.delete(number);
      else next.add(number);
      return next;
    });
  }

  function reset() {
    setFileName(null);
    setQuestions(null);
    setError(null);
    setLastPicked(null);
  }

  if (locked) {
    return (
      <View style={styles.lockedBanner}>
        <Text style={styles.lockedText}>
          PDF upload is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
        </Text>
      </View>
    );
  }

  return (
    <>
      <Pressable style={styles.actionButton} onPress={pickPdf}>
        <Text style={styles.actionButtonText}>📄 Choose PDF</Text>
      </Pressable>

      {fileName && <Text style={styles.fileName}>{fileName}</Text>}

      {fileName && !loading && (
        <Pressable style={styles.cancelButton} onPress={reset}>
          <Text style={styles.cancelButtonText}>← Choose a different PDF</Text>
        </Pressable>
      )}

      {loading && (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.loadingText}>
            Reading and solving every question in this document with AI — this may take a minute…
          </Text>
        </View>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {questions && questions.length > 0 && (
        <View style={{ marginTop: 16 }}>
          {questions.map((q) => {
            const isOpen = expanded.has(q.number);
            return (
              <View key={q.number} style={styles.questionCard}>
                <Pressable style={styles.questionHeader} onPress={() => toggle(q.number)}>
                  <Text style={styles.questionHeaderText}>Question {q.number}</Text>
                  <Text style={styles.chevron}>{isOpen ? "▲" : "▼"}</Text>
                </Pressable>
                {isOpen && (
                  <View style={styles.questionBody}>
                    {q.steps.map((step, i) => (
                      <StepView key={i} step={step} />
                    ))}
                  </View>
                )}
              </View>
            );
          })}

          <Pressable style={styles.retryButton} onPress={retry}>
            <Text style={styles.retryButtonText}>🔄 Not right? Re-read and re-solve this document</Text>
          </Pressable>
        </View>
      )}

      {questions && questions.length === 0 && (
        <Text style={styles.error}>Couldn't detect individual questions in this document.</Text>
      )}
    </>
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
  methodRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 18 },
  methodChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 16,
    backgroundColor: "#fff",
  },
  methodChipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  methodChipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  methodChipTextActive: { color: "#fff" },
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
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  preview: { width: "100%", height: 220, marginTop: 16, borderRadius: 12, backgroundColor: "#eee" },
  fileName: { marginTop: 10, color: colors.textSecondary, fontStyle: "italic" },
  cancelButton: { marginTop: 10, alignSelf: "flex-start" },
  cancelButtonText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16 },
  loadingText: { color: colors.textSecondary, flexShrink: 1 },
  questionCard: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    marginBottom: 12,
    overflow: "hidden",
  },
  questionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 14,
    paddingHorizontal: 16,
  },
  questionHeaderText: { fontSize: 15, fontWeight: "700", color: colors.text },
  chevron: { fontSize: 12, color: colors.textSecondary },
  questionBody: { paddingHorizontal: 16, paddingBottom: 16 },
  retryButton: {
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 4,
  },
  retryButtonText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00" },
});
