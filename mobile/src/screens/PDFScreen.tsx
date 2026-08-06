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
import { ApiError, pdfExtract } from "../api/client";

export default function PDFScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [extractedText, setExtractedText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pdfLocked = me?.effective_tier === "free";

  async function pickPdf() {
    const result = await DocumentPicker.getDocumentAsync({ type: "application/pdf" });
    if (result.canceled || !result.assets?.[0] || !token) return;

    const asset = result.assets[0];
    setFileName(asset.name);
    setExtractedText("");
    setError(null);
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

  function reset() {
    setFileName(null);
    setExtractedText("");
    setError(null);
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>📚 Past Papers (PDF)</Text>
      <Text style={styles.subtitle}>Upload a past paper PDF and pull questions straight from it.</Text>

      {pdfLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            Past paper PDF extraction is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
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
            </View>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
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
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00" },
});
