import React, { useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  Alert,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, solvePhotoWithAI, SolvedPhotoQuestion } from "../api/client";
import { StepView } from "./AITutorScreen";

export default function OCRScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SolvedPhotoQuestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const ocrLocked = me?.effective_tier === "free";

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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📷 OCR Question</Text>
      <Text style={styles.subtitle}>
        Take or upload a photo of one or more maths questions — Malita reads and solves every
        question directly here, no need to retype anything.
      </Text>

      {ocrLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            Photo upload & OCR is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
        </View>
      ) : (
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
  row: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  preview: { width: "100%", height: 220, marginTop: 16, borderRadius: 12, backgroundColor: "#eee" },
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
