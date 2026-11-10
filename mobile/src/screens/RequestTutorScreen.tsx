import React, { useState } from "react";
import {
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors, SUBJECTS, Subject } from "../theme";
import { ApiError, requestTutoringSession } from "../api/client";
import Dropdown from "../components/Dropdown";

export default function RequestTutorScreen({ navigation }: any) {
  const { token } = useAuth();
  const [subject, setSubject] = useState<Subject>("Mathematics");
  const [topic, setTopic] = useState("");
  const [preferredTimes, setPreferredTimes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!token) return;
    setSubmitting(true);
    setError(null);
    try {
      await requestTutoringSession(token, {
        subject,
        topic: topic.trim(),
        preferred_times_note: preferredTimes.trim(),
      });
      navigation.replace("MyTutoringRequests");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit your request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
          <Text style={styles.backLinkText}>‹ Back to Home</Text>
        </Pressable>
        <Text style={styles.title}>🙋 Request a Tutor</Text>
        <Text style={styles.subtitle}>
          Get matched with a real tutor for a 1-on-1 session. Billed separately per session — no
          subscription required.
        </Text>

        <Pressable style={styles.myRequestsLink} onPress={() => navigation.navigate("MyTutoringRequests")}>
          <Text style={styles.myRequestsLinkText}>View my existing requests ›</Text>
        </Pressable>

        <Dropdown
          label="Subject"
          options={SUBJECTS.map((s) => ({ label: s, value: s }))}
          value={subject}
          onChange={(v) => setSubject(v as Subject)}
        />

        <Text style={styles.label}>Topic (optional)</Text>
        <TextInput
          style={styles.input}
          value={topic}
          onChangeText={setTopic}
          placeholder="e.g. Calculus, Electric Circuits..."
        />

        <Text style={styles.label}>Preferred times (optional)</Text>
        <TextInput
          style={[styles.input, styles.textArea]}
          value={preferredTimes}
          onChangeText={setPreferredTimes}
          placeholder="e.g. Weekday evenings after 5pm, or Saturday mornings"
          multiline
        />

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable
          style={[styles.submitButton, submitting && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={submitting}
        >
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitButtonText}>Submit Request</Text>}
        </Pressable>

        <Text style={styles.note}>
          Once submitted, our team will match you with a suitable tutor and let you know the session
          price and time. You'll then be asked to pay securely before the session is confirmed.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4 },
  myRequestsLink: { marginTop: 14, alignSelf: "flex-start" },
  myRequestsLinkText: { color: colors.primary, fontWeight: "600", fontSize: 13 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 14, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.text,
    backgroundColor: "#fff",
  },
  textArea: { minHeight: 80, textAlignVertical: "top" },
  error: { color: colors.error, marginTop: 14 },
  submitButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 20,
  },
  buttonDisabled: { opacity: 0.6 },
  submitButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  note: { fontSize: 12, color: colors.textSecondary, marginTop: 16, lineHeight: 17, fontStyle: "italic" },
});
