import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import * as Speech from "expo-speech";
import { useAuth } from "../context/AuthContext";
import { colors, SUBJECTS, Subject } from "../theme";
import { ApiError, fetchAITeacherLesson, LessonStep } from "../api/client";
import { StepView } from "./AITutorScreen";

export default function AITeacherScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [topic, setTopic] = useState("");
  const [lesson, setLesson] = useState<LessonStep[] | null>(null);
  const [lessonTopic, setLessonTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);

  const locked = me != null && me.effective_tier !== "super_premium";

  async function handleStart() {
    if (!token) return;
    if (!topic.trim()) {
      setError("Please tell me what you'd like a lesson on.");
      return;
    }
    setLoading(true);
    setError(null);
    Speech.stop();
    setSpeaking(false);
    try {
      const res = await fetchAITeacherLesson(token, subject, topic.trim());
      setLesson(res.steps);
      setLessonTopic(topic.trim());
    } catch (e) {
      setLesson(null);
      setError(e instanceof ApiError ? e.message : "Couldn't generate a lesson right now - please try again.");
    } finally {
      setLoading(false);
    }
  }

  function handleReadAloud() {
    if (!lesson) return;
    const narrations = lesson.map((s) => s.narration).filter((n): n is string => !!n && n.trim().length > 0);
    if (narrations.length === 0) return;
    Speech.stop();
    setSpeaking(true);
    narrations.forEach((text, i) => {
      const isLast = i === narrations.length - 1;
      Speech.speak(text, {
        rate: 0.95,
        onDone: isLast ? () => setSpeaking(false) : undefined,
        onStopped: isLast ? () => setSpeaking(false) : undefined,
      });
    });
  }

  function handleStop() {
    Speech.stop();
    setSpeaking(false);
  }

  function handleReset() {
    Speech.stop();
    setSpeaking(false);
    setLesson(null);
    setLessonTopic("");
    setTopic("");
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>🧑‍🏫 AI Teacher</Text>
      <Text style={styles.subtitle}>A narrated, live-style lesson on any Mathematics or Physical Sciences topic you choose.</Text>

      {locked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            AI Teacher is a Super Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
          <Pressable style={styles.upgradeButton} onPress={() => navigation.navigate("Subscription")}>
            <Text style={styles.upgradeButtonText}>View Plans</Text>
          </Pressable>
        </View>
      ) : (
        <>
          {!lesson && (
            <>
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

              <Text style={styles.label}>What would you like a lesson on?</Text>
              <TextInput
                style={styles.input}
                value={topic}
                onChangeText={setTopic}
                placeholder="e.g. factorising trinomials, projectile motion, chemical equilibrium..."
              />

              {error ? <Text style={styles.error}>{error}</Text> : null}

              <Pressable
                style={[styles.startButton, loading && styles.buttonDisabled]}
                onPress={handleStart}
                disabled={loading}
              >
                {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.startButtonText}>▶️ Start Lesson</Text>}
              </Pressable>
            </>
          )}

          {lesson && (
            <View style={styles.lessonBox}>
              <Text style={styles.lessonTitle}>📖 {lessonTopic}</Text>

              <View style={styles.narrationRow}>
                <Pressable style={styles.narrationButton} onPress={handleReadAloud}>
                  <Text style={styles.narrationButtonText}>{speaking ? "🔊 Reading..." : "▶️ Read Aloud"}</Text>
                </Pressable>
                <Pressable style={styles.stopButton} onPress={handleStop}>
                  <Text style={styles.stopButtonText}>⏹ Stop</Text>
                </Pressable>
              </View>

              {lesson.map((step, i) => (
                <View key={i} style={styles.stepWrap}>
                  <StepView step={step} />
                </View>
              ))}

              <Pressable style={styles.resetButton} onPress={handleReset}>
                <Text style={styles.resetButtonText}>🔄 Start a new lesson</Text>
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
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: "#fff",
  },
  error: { color: colors.error, marginTop: 12 },
  startButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 18,
  },
  buttonDisabled: { opacity: 0.6 },
  startButtonText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00", marginBottom: 12 },
  upgradeButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
  },
  upgradeButtonText: { color: "#fff", fontWeight: "700" },
  lessonBox: { marginTop: 8 },
  lessonTitle: { fontSize: 19, fontWeight: "700", color: colors.text, marginBottom: 12 },
  narrationRow: { flexDirection: "row", gap: 10, marginBottom: 18 },
  narrationButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 18,
  },
  narrationButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  stopButton: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 18,
  },
  stopButtonText: { color: colors.text, fontWeight: "700", fontSize: 13 },
  stepWrap: { marginBottom: 10 },
  resetButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 10,
  },
  resetButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
});
