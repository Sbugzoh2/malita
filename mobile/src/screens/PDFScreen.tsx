import React, { useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  TextInput,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, pdfExtract, solvePdfText, SolvedPdfQuestion } from "../api/client";
import { StepView } from "./AITutorScreen";

export default function PDFScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [extractedText, setExtractedText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [solving, setSolving] = useState(false);
  const [solveError, setSolveError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SolvedPdfQuestion[] | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const pdfLocked = me?.effective_tier === "free";

  async function pickPdf() {
    const result = await DocumentPicker.getDocumentAsync({ type: "application/pdf" });
    if (result.canceled || !result.assets?.[0] || !token) return;

    const asset = result.assets[0];
    setFileName(asset.name);
    setExtractedText("");
    setError(null);
    setQuestions(null);
    setSolveError(null);
    setLoading(true);
    try {
      const res = await pdfExtract(token, asset.uri, asset.name);
      setExtractedText(res.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read that PDF. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function sendToSolver() {
    navigation.navigate("AITutor", { prefillQuestion: extractedText });
  }

  async function solveAll() {
    if (!token || !extractedText) return;
    setSolving(true);
    setSolveError(null);
    try {
      const res = await solvePdfText(token, extractedText, fileName ?? "");
      setQuestions(res.questions);
      if (res.questions.length === 0) {
        setSolveError("Couldn't detect individual questions in this document.");
      }
    } catch (e) {
      setSolveError(e instanceof ApiError ? e.message : "Could not solve this document. Please try again.");
    } finally {
      setSolving(false);
    }
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
    setExtractedText("");
    setError(null);
    setQuestions(null);
    setSolveError(null);
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📄 Upload PDF Document</Text>
      <Text style={styles.subtitle}>
        Upload any PDF with maths questions — a past paper, a worksheet, homework, anything with
        problems on it — not just official exam papers.
      </Text>

      {pdfLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            PDF upload is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
        </View>
      ) : (
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
              <Text style={styles.loadingText}>Extracting text…</Text>
            </View>
          )}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {extractedText ? (
            <View style={styles.resultCard}>
              <Text style={styles.label}>Extracted text (select the part you want, then edit if needed)</Text>
              <TextInput
                style={styles.input}
                value={extractedText}
                onChangeText={setExtractedText}
                multiline
              />
              <Pressable style={styles.solveButton} onPress={sendToSolver}>
                <Text style={styles.solveButtonText}>Send to AI Tutor →</Text>
              </Pressable>

              <Pressable
                style={[styles.aiSolveButton, solving && styles.buttonDisabled]}
                onPress={solveAll}
                disabled={solving}
              >
                {solving ? (
                  <ActivityIndicator color={colors.primary} />
                ) : (
                  <Text style={styles.aiSolveButtonText}>🧠 Solve all questions with AI</Text>
                )}
              </Pressable>
              {solving && (
                <Text style={styles.solvingHint}>
                  Reading the document and solving every question with AI — this can take a minute
                  for a full document…
                </Text>
              )}
              {solveError ? <Text style={styles.error}>{solveError}</Text> : null}
            </View>
          ) : null}

          {questions && questions.length > 0 && (
            <View style={{ marginTop: 16 }}>
              <Text style={styles.sectionTitle}>🧠 AI-Solved Questions</Text>
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
                        <Text style={styles.originalLabel}>
                          Original question (as extracted from the PDF):
                        </Text>
                        <Text style={styles.originalText}>{q.text}</Text>
                        {q.steps.map((step, i) => (
                          <StepView key={i} step={step} />
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
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
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
    alignSelf: "flex-start",
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  fileName: { marginTop: 10, color: colors.textSecondary, fontStyle: "italic" },
  cancelButton: { marginTop: 10, alignSelf: "flex-start" },
  cancelButtonText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16 },
  loadingText: { color: colors.textSecondary },
  error: { color: colors.error, marginTop: 16 },
  resultCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 16 },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 12,
    fontSize: 15,
    backgroundColor: "#fff",
    minHeight: 220,
    textAlignVertical: "top",
  },
  solveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 14,
  },
  solveButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  aiSolveButton: {
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 10,
  },
  aiSolveButtonText: { color: colors.primary, fontWeight: "700", fontSize: 16 },
  buttonDisabled: { opacity: 0.6 },
  solvingHint: { fontSize: 12, color: colors.textSecondary, marginTop: 8, textAlign: "center" },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 10 },
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
  originalLabel: { fontSize: 12, color: colors.textSecondary, marginBottom: 6 },
  originalText: {
    fontSize: 13,
    color: colors.text,
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00" },
});
