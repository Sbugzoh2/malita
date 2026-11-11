import React, { useEffect, useState } from "react";
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
import {
  ApiError, requestTutoringSession,
  Institution, Qualification, CatalogModule,
  fetchInstitutions, fetchQualifications, fetchModules,
} from "../api/client";
import Dropdown from "../components/Dropdown";
import SessionDateTimePicker, {
  SessionDateTimeValue,
  sessionDateTimeToIso,
} from "../components/SessionDateTimePicker";

const MIN_DURATION_MINUTES = 60;

export default function RequestTutorScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const isHigherEd = me?.user.account_type === "higher_ed";

  const [subject, setSubject] = useState<Subject>("Mathematics");

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [qualificationId, setQualificationId] = useState<number | null>(null);
  const [modules, setModules] = useState<CatalogModule[]>([]);
  const [moduleId, setModuleId] = useState<number | null>(null);

  const [price, setPrice] = useState("");
  const [duration, setDuration] = useState("60");
  const [dateTime, setDateTime] = useState<SessionDateTimeValue>(null);
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isHigherEd) return;
    fetchInstitutions()
      .then((res) => {
        setInstitutions(res.institutions);
        if (me?.user.higher_ed_institution_id) setInstitutionId(me.user.higher_ed_institution_id);
      })
      .catch(() => setError("Could not load the list of institutions."));
  }, [isHigherEd]);

  useEffect(() => {
    setQualificationId(null);
    setModules([]);
    setModuleId(null);
    if (!institutionId) {
      setQualifications([]);
      return;
    }
    fetchQualifications(institutionId)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => setError("Could not load qualifications for that institution."));
  }, [institutionId]);

  useEffect(() => {
    setModuleId(null);
    if (!qualificationId) {
      setModules([]);
      return;
    }
    fetchModules(qualificationId)
      .then((res) => setModules(res.modules))
      .catch(() => setError("Could not load modules for that qualification."));
  }, [qualificationId]);

  async function handleSubmit() {
    if (!token) return;
    const priceVal = parseFloat(price);
    if (isNaN(priceVal) || priceVal <= 0) {
      setError("Please enter a price greater than R0.");
      return;
    }
    const durationVal = parseInt(duration, 10) || 0;
    if (durationVal < MIN_DURATION_MINUTES) {
      setError(`Sessions must be at least ${MIN_DURATION_MINUTES} minutes long.`);
      return;
    }
    if (!dateTime) {
      setError("Please select a date and time for your session.");
      return;
    }
    if (isHigherEd && !moduleId) {
      setError("Please select the module you'd like help with.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await requestTutoringSession(token, {
        subject: isHigherEd ? undefined : subject,
        module_id: isHigherEd ? moduleId! : undefined,
        price_zar: priceVal,
        scheduled_at: sessionDateTimeToIso(dateTime),
        duration_minutes: durationVal,
        topic: topic.trim(),
        preferred_times_note: notes.trim(),
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

        {isHigherEd ? (
          <>
            <Dropdown
              label="Institution"
              options={institutions.map((i) => ({ label: i.name, value: String(i.id) }))}
              value={institutionId != null ? String(institutionId) : null}
              onChange={(v) => setInstitutionId(parseInt(v, 10))}
            />
            <Dropdown
              label="Qualification"
              options={qualifications.map((q) => ({ label: q.name, value: String(q.id) }))}
              value={qualificationId != null ? String(qualificationId) : null}
              onChange={(v) => setQualificationId(parseInt(v, 10))}
            />
            <Dropdown
              label="Module"
              options={modules.map((m) => ({ label: `${m.name} (${m.year_level_label})`, value: String(m.id) }))}
              value={moduleId != null ? String(moduleId) : null}
              onChange={(v) => setModuleId(parseInt(v, 10))}
            />
          </>
        ) : (
          <Dropdown
            label="Subject"
            options={SUBJECTS.map((s) => ({ label: s, value: s }))}
            value={subject}
            onChange={(v) => setSubject(v as Subject)}
          />
        )}

        <Text style={styles.label}>What are you willing to pay? (R)</Text>
        <TextInput
          style={styles.input}
          value={price}
          onChangeText={setPrice}
          keyboardType="numeric"
          placeholder="e.g. 250"
        />

        <Text style={styles.label}>Session duration (minutes, 60 min minimum)</Text>
        <TextInput
          style={styles.input}
          value={duration}
          onChangeText={setDuration}
          keyboardType="numeric"
          placeholder="60"
        />

        <SessionDateTimePicker label="Session date & time" value={dateTime} onChange={setDateTime} />

        <Text style={styles.label}>Topic (optional)</Text>
        <TextInput
          style={styles.input}
          value={topic}
          onChangeText={setTopic}
          placeholder="e.g. Calculus, Electric Circuits..."
        />

        <Text style={styles.label}>Additional notes (optional)</Text>
        <TextInput
          style={[styles.input, styles.textArea]}
          value={notes}
          onChangeText={setNotes}
          placeholder="e.g. I'd like help with proofs specifically"
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
          Your request goes straight to tutors who teach this {isHigherEd ? "module" : "subject"} - once one
          accepts your price and time (or proposes a different time for you to approve), you'll be asked to
          pay securely before the session is confirmed.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: 20, paddingBottom: 40, backgroundColor: colors.background, flexGrow: 1 },
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
