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
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, forgotPassword, resetPassword } from "../api/client";

export default function LoginScreen({ navigation }: any) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [resetToken, setResetToken] = useState<string | null>(null);
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  async function handleLogin() {
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not log in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleForgotPassword() {
    setError(null);
    setInfo(null);
    setResetDone(false);
    if (!email.trim()) {
      setError("Enter your email above first, then tap 'Forgot password?'");
      return;
    }
    try {
      const res = await forgotPassword(email.trim().toLowerCase());
      setInfo(res.message);
      // SMTP isn't configured yet in this environment, so the API hands the
      // reset code straight back - reveal the code + new-password fields
      // right here instead of leaving the learner stuck with no inbox to check.
      if (res.reset_token) {
        setResetToken(res.reset_token);
        setResetCode(res.reset_token);
      } else {
        setResetToken(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }

  async function handleResetPassword() {
    setError(null);
    if (!resetCode.trim()) {
      setError("Enter the reset code first.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      setError("Passwords don't match.");
      return;
    }
    setResetSubmitting(true);
    try {
      await resetPassword(resetCode.trim(), newPassword);
      setResetDone(true);
      setResetToken(null);
      setInfo("Password updated! You can now log in with your new password.");
      setNewPassword("");
      setNewPasswordConfirm("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setResetSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>🎓 Malita</Text>
        <Text style={styles.subtitle}>Matric Study Master</Text>

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
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="••••••••"
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}
          {info ? <Text style={styles.info}>{info}</Text> : null}

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

          <Pressable onPress={handleForgotPassword} style={styles.linkButton}>
            <Text style={styles.link}>Forgot your password?</Text>
          </Pressable>

          {resetToken && !resetDone ? (
            <View style={styles.resetBox}>
              <Text style={styles.label}>Reset code</Text>
              <TextInput
                style={styles.input}
                value={resetCode}
                onChangeText={setResetCode}
                autoCapitalize="none"
                placeholder="Reset code"
              />

              <Text style={styles.label}>New password</Text>
              <TextInput
                style={styles.input}
                value={newPassword}
                onChangeText={setNewPassword}
                secureTextEntry
                placeholder="••••••••"
              />

              <Text style={styles.label}>Confirm new password</Text>
              <TextInput
                style={styles.input}
                value={newPasswordConfirm}
                onChangeText={setNewPasswordConfirm}
                secureTextEntry
                placeholder="••••••••"
              />

              <Pressable
                style={[styles.button, resetSubmitting && styles.buttonDisabled]}
                onPress={handleResetPassword}
                disabled={resetSubmitting}
              >
                {resetSubmitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>Update Password</Text>
                )}
              </Pressable>
            </View>
          ) : null}
        </View>

        <Pressable onPress={() => navigation.navigate("Register")} style={styles.linkButton}>
          <Text style={styles.link}>New here? Create a free account</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  resetBox: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  container: { flexGrow: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 32, fontWeight: "700", textAlign: "center", color: colors.text },
  subtitle: { fontSize: 16, textAlign: "center", color: colors.textSecondary, marginBottom: 24 },
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
  info: { color: colors.primaryDark, marginTop: 12 },
});
