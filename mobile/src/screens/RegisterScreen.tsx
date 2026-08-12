import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Linking,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchProvinces, API_BASE_URL } from "../api/client";

export default function RegisterScreen({ navigation }: any) {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [school, setSchool] = useState("");
  const [province, setProvince] = useState("");
  const [cityTown, setCityTown] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [provinces, setProvinces] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchProvinces()
      .then((res) => setProvinces(res.provinces))
      .catch(() => {
        // Non-fatal - the user can still type a province manually below.
      });
  }, []);

  async function handleRegister() {
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    if (!province.trim()) {
      setError("Please enter your province.");
      return;
    }
    setSubmitting(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        province: province.trim(),
        city_town: cityTown.trim(),
        school: school.trim(),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Create your free account</Text>

        <View style={styles.card}>
          <Text style={styles.label}>Full name</Text>
          <TextInput style={styles.input} value={name} onChangeText={setName} />

          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />

          <Text style={styles.label}>School (optional)</Text>
          <TextInput style={styles.input} value={school} onChangeText={setSchool} />

          <Text style={styles.label}>
            Province{provinces.length > 0 ? ` (e.g. ${provinces[0]})` : ""}
          </Text>
          <TextInput style={styles.input} value={province} onChangeText={setProvince} />

          <Text style={styles.label}>City / Town</Text>
          <TextInput style={styles.input} value={cityTown} onChangeText={setCityTown} />

          <Text style={styles.label}>Password</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry />

          <Text style={styles.label}>Confirm password</Text>
          <TextInput
            style={styles.input}
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Text style={styles.legalNote}>
            By creating an account you agree to Malita's{" "}
            <Text style={styles.legalLink} onPress={() => Linking.openURL(`${API_BASE_URL}/terms`)}>
              Terms &amp; Conditions
            </Text>{" "}
            and{" "}
            <Text style={styles.legalLink} onPress={() => Linking.openURL(`${API_BASE_URL}/privacy`)}>
              Privacy Policy
            </Text>
            .
          </Text>

          <Pressable
            style={[styles.button, submitting && styles.buttonDisabled]}
            onPress={handleRegister}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Create Free Account</Text>
            )}
          </Pressable>
        </View>

        <Pressable onPress={() => navigation.navigate("Login")} style={styles.linkButton}>
          <Text style={styles.link}>Already have an account? Log in</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { flexGrow: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "700", textAlign: "center", color: colors.text, marginBottom: 20 },
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
  legalNote: { fontSize: 12, color: colors.textSecondary, marginTop: 14, lineHeight: 17 },
  legalLink: { color: colors.primary, fontWeight: "600" },
});
