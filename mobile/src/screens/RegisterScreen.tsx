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
import {
  ApiError, fetchProvinces, API_BASE_URL, YEAR_LEVEL_LABELS,
  Institution, Qualification, fetchInstitutions, fetchQualifications,
} from "../api/client";
import Dropdown from "../components/Dropdown";

export default function RegisterScreen({ navigation }: any) {
  const { register } = useAuth();
  const [accountType, setAccountType] = useState<"high_school" | "higher_ed">("high_school");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [school, setSchool] = useState("");
  const [province, setProvince] = useState("");
  const [cityTown, setCityTown] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [provinces, setProvinces] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [qualificationId, setQualificationId] = useState<number | null>(null);
  const [yearOfStudy, setYearOfStudy] = useState<number | null>(null);
  const [studentNumber, setStudentNumber] = useState("");

  useEffect(() => {
    fetchProvinces()
      .then((res) => setProvinces(res.provinces))
      .catch(() => {
        // Non-fatal - the user can still type a province manually below.
      });
  }, []);

  useEffect(() => {
    if (accountType !== "higher_ed") return;
    fetchInstitutions()
      .then((res) => setInstitutions(res.institutions))
      .catch(() => setError("Could not load the list of institutions. Please try again."));
  }, [accountType]);

  useEffect(() => {
    setQualificationId(null);
    if (!institutionId) {
      setQualifications([]);
      return;
    }
    fetchQualifications(institutionId)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => setError("Could not load qualifications for that institution."));
  }, [institutionId]);

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
    if (!/^\d{13}$/.test(idNumber.trim())) {
      setError("ID number must be exactly 13 digits.");
      return;
    }
    if (accountType === "higher_ed") {
      if (!institutionId || !qualificationId) {
        setError("Please select your institution and qualification.");
        return;
      }
      if (!yearOfStudy) {
        setError("Please select your year of study.");
        return;
      }
      if (!studentNumber.trim()) {
        setError("Please enter your student number.");
        return;
      }
    }
    setSubmitting(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        province: province.trim(),
        city_town: cityTown.trim(),
        id_number: idNumber.trim(),
        school: school.trim(),
        account_type: accountType,
        higher_ed_institution_id: accountType === "higher_ed" ? institutionId : undefined,
        higher_ed_qualification_id: accountType === "higher_ed" ? qualificationId : undefined,
        higher_ed_year_of_study: accountType === "higher_ed" ? yearOfStudy : undefined,
        student_number: accountType === "higher_ed" ? studentNumber.trim() : undefined,
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
          <Text style={styles.label}>I am a...</Text>
          <View style={styles.chipRow}>
            <Pressable
              style={[styles.chip, accountType === "high_school" && styles.chipActive]}
              onPress={() => setAccountType("high_school")}
            >
              <Text style={[styles.chipText, accountType === "high_school" && styles.chipTextActive]}>
                High School Learner
              </Text>
            </Pressable>
            <Pressable
              style={[styles.chip, accountType === "higher_ed" && styles.chipActive]}
              onPress={() => setAccountType("higher_ed")}
            >
              <Text style={[styles.chipText, accountType === "higher_ed" && styles.chipTextActive]}>
                University / College Student
              </Text>
            </Pressable>
          </View>

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

          <Text style={styles.label}>
            Province{provinces.length > 0 ? ` (e.g. ${provinces[0]})` : ""}
          </Text>
          <TextInput style={styles.input} value={province} onChangeText={setProvince} />

          <Text style={styles.label}>City / Town</Text>
          <TextInput style={styles.input} value={cityTown} onChangeText={setCityTown} />

          <Text style={styles.label}>ID number</Text>
          <TextInput
            style={styles.input}
            value={idNumber}
            onChangeText={setIdNumber}
            keyboardType="number-pad"
            maxLength={13}
            placeholder="13-digit South African ID number"
          />
          <Text style={styles.helperText}>
            We use this to work out your date of birth automatically - no need to type it separately.
          </Text>

          {accountType === "high_school" ? (
            <>
              <Text style={styles.label}>School (optional)</Text>
              <TextInput style={styles.input} value={school} onChangeText={setSchool} />
            </>
          ) : (
            <>
              <Dropdown
                label="Institution"
                options={institutions.map((i) => ({ label: i.name, value: String(i.id) }))}
                value={institutionId != null ? String(institutionId) : null}
                onChange={(v) => setInstitutionId(parseInt(v, 10))}
              />
              {institutionId && qualifications.length === 0 ? (
                <Text style={styles.helperText}>No qualifications listed yet for this institution.</Text>
              ) : null}
              <Dropdown
                label="Qualification"
                options={qualifications.map((q) => ({ label: q.name, value: String(q.id) }))}
                value={qualificationId != null ? String(qualificationId) : null}
                onChange={(v) => setQualificationId(parseInt(v, 10))}
              />
              <Dropdown
                label="Year of study"
                options={Object.entries(YEAR_LEVEL_LABELS).map(([k, v]) => ({ label: v, value: k }))}
                value={yearOfStudy != null ? String(yearOfStudy) : null}
                onChange={(v) => setYearOfStudy(parseInt(v, 10))}
              />
              <Text style={styles.label}>Student number</Text>
              <TextInput style={styles.input} value={studentNumber} onChangeText={setStudentNumber} />
            </>
          )}

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
  // Generous bottom padding so the last field/button sits well clear of
  // the device's own bottom nav bar/gesture area - too close risks an
  // accidental system back/home gesture instead of the intended tap.
  container: { flexGrow: 1, padding: 24, paddingBottom: 64, justifyContent: "center" },
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
  chipRow: { flexDirection: "row", gap: 8, marginTop: 6 },
  chip: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 10,
    alignItems: "center",
    backgroundColor: "#fff",
  },
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipText: { color: colors.text, fontSize: 12, fontWeight: "600", textAlign: "center" },
  chipTextActive: { color: "#fff" },
  helperText: { fontSize: 12, color: colors.textSecondary, marginTop: 4, lineHeight: 16 },
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
  // Generous top/bottom margins so this sits well clear of the device's
  // own bottom nav bar/gesture area - too close caused accidental
  // system back/home taps instead of navigating to Login (same issue
  // HomeScreen's Log Out button had).
  linkButton: { marginTop: 16, marginBottom: 32, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  error: { color: colors.error, marginTop: 12 },
  legalNote: { fontSize: 12, color: colors.textSecondary, marginTop: 14, lineHeight: 17 },
  legalLink: { color: colors.primary, fontWeight: "600" },
});
