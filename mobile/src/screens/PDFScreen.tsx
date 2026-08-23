import React, { useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, solvePdfWithAI, SolvedPdfQuestion } from "../api/client";
import { StepView } from "./AITutorScreen";

export default function PDFScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [fileName, setFileName] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SolvedPdfQuestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [lastPicked, setLastPicked] = useState<{ uri: string; name: string } | null>(null);

  const pdfLocked = me?.effective_tier === "free";

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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📄 Upload PDF Document</Text>
      <Text style={styles.subtitle}>
        Upload any PDF with maths questions — a past paper, a worksheet, homework, anything with
        problems on it — not just official exam papers. Malita reads and solves every question
        directly here, no need to retype anything.
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
              <Text style={styles.loadingText}>
                Reading and solving every question in this document with AI — this may take a
                minute…
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
  loadingText: { color: colors.textSecondary, flexShrink: 1 },
  error: { color: colors.error, marginTop: 16 },
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
