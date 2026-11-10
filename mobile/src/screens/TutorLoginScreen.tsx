import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from "react-native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import { ApiError } from "../api/client";

export default function TutorLoginScreen({ navigation }: any) {
  const { login } = useTutorAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleLogin() {
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not log in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>🙋 Tutor Login</Text>
        <Text style={styles.subtitle}>Log in with the email and password you applied with.</Text>

        <View style={styles.card}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="you@example.com"
          />

          <Text style={styles.label}>Password</Text>
          <View style={styles.passwordRow}>
            <TextInput
              style={[styles.input, styles.passwordInput]}
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              placeholder="••••••••"
            />
            <Pressable onPress={() => setShowPassword((s) => !s)} style={styles.showPasswordButton}>
              <Text style={styles.showPasswordText}>{showPassword ? "Hide" : "Show"}</Text>
            </Pressable>
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Pressable
            style={[styles.button, submitting && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Log In</Text>
            )}
          </Pressable>
        </View>

        <Pressable onPress={() => navigation.goBack()} style={styles.linkButton}>
          <Text style={styles.link}>‹ Back to learner login</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { flexGrow: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 28, fontWeight: "700", textAlign: "center", color: colors.text },
  subtitle: { fontSize: 14, textAlign: "center", color: colors.textSecondary, marginTop: 6, marginBottom: 24 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: "#fff",
  },
  passwordRow: { flexDirection: "row", alignItems: "center" },
  passwordInput: { flex: 1 },
  showPasswordButton: { marginLeft: 10, paddingHorizontal: 4, paddingVertical: 10 },
  showPasswordText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 20,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  linkButton: { marginTop: 16, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  error: { color: colors.error, marginTop: 12 },
});
