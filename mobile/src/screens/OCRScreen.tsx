import React, { useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  TextInput,
  Alert,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, ocrImage } from "../api/client";

export default function OCRScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [recognizedText, setRecognizedText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ocrLocked = me?.effective_tier === "free";

  async function runOcr(uri: string) {
    if (!token) return;
    setImageUri(uri);
    setRecognizedText("");
    setError(null);
    setLoading(true);
    try {
      const res = await ocrImage(token, uri);
      setRecognizedText(res.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read that image. Please try again.");
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
      await runOcr(result.assets[0].uri);
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
      await runOcr(result.assets[0].uri);
    }
  }

  function sendToSolver() {
    navigation.navigate("AITutor", { prefillQuestion: recognizedText });
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>📷 OCR Question</Text>
      <Text style={styles.subtitle}>Snap a photo of a question and let us read it for you.</Text>

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

          {loading && (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.loadingText}>Reading the image…</Text>
            </View>
          )}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {recognizedText ? (
            <View style={styles.resultCard}>
              <Text style={styles.label}>Recognised expression (edit if needed)</Text>
              <TextInput
                style={styles.input}
                value={recognizedText}
                onChangeText={setRecognizedText}
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
  row: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  preview: { width: "100%", height: 220, marginTop: 16, borderRadius: 12, backgroundColor: "#eee" },
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
    fontSize: 16,
    backgroundColor: "#fff",
    minHeight: 60,
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
