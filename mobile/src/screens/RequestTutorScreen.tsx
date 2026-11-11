import React, { useEffect, useRef, useState } from "react";
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
  ApiError, requestTutoringSession, editTutoringRequest, TutoringRequest,
  Institution, Qualification, CatalogModule,
  fetchInstitutions, fetchQualifications, fetchModules,
} from "../api/client";
import Dropdown from "../components/Dropdown";
import SessionDateTimePicker, {
  SessionDateTimeValue,
  sessionDateTimeToIso,
  isoToSessionDateTime,
} from "../components/SessionDateTimePicker";

const MIN_DURATION_MINUTES = 60;

export default function RequestTutorScreen({ navigation, route }: any) {
  const { token, me } = useAuth();
  const isHigherEd = me?.user.account_type === "higher_ed";

  // Editing an existing not-yet-accepted request (navigated here from
  // MyTutoringRequestsScreen's "Edit" button) instead of creating a new one.
  const editRequest: TutoringRequest | undefined = route?.params?.editRequest;
  const isEdit = !!editRequest;
  // A learner picking a specific tutor from the Browse Tutors directory
  // instead of broadcasting a request - route.params.directoryPrefill
  // carries the chosen tutor's subject/institution/qualification/module
  // so this screen can land straight on it.
  const directoryPrefill = route?.params?.directoryPrefill;
  const preferredTutorId: number | undefined =
    route?.params?.preferredTutorId ?? editRequest?.preferred_tutor_id ?? undefined;

  const [subject, setSubject] = useState<Subject>(
    (editRequest?.subject as Subject) || (directoryPrefill?.subject as Subject) || "Mathematics"
  );

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState<number | null>(
    editRequest?.institution_id ?? directoryPrefill?.institutionId ?? null
  );
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [qualificationId, setQualificationId] = useState<number | null>(null);
  const [modules, setModules] = useState<CatalogModule[]>([]);
  const [moduleId, setModuleId] = useState<number | null>(null);

  // Cascading dropdowns normally reset their children whenever the parent
  // changes. When pre-filling an edit or a directory pick, we want the
  // fetched qualification and module lists to land on the target values
  // instead - these refs carry that one-time target through the
  // fetch-then-reset sequence, then clear themselves once applied.
  const pendingQualificationId = useRef<number | null>(
    editRequest?.qualification_id ?? directoryPrefill?.qualificationId ?? null
  );
  const pendingModuleId = useRef<number | null>(
    editRequest?.module_id ?? directoryPrefill?.moduleId ?? null
  );

  const [price, setPrice] = useState(editRequest ? String(editRequest.price_zar ?? "") : "");
  const [duration, setDuration] = useState(editRequest ? String(editRequest.duration_minutes ?? 60) : "60");
  const [dateTime, setDateTime] = useState<SessionDateTimeValue>(
    editRequest?.scheduled_at ? isoToSessionDateTime(editRequest.scheduled_at) : null
  );
  const [topic, setTopic] = useState(editRequest?.topic ?? "");
  const [notes, setNotes] = useState(editRequest?.preferred_times_note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isHigherEd) return;
    fetchInstitutions()
      .then((res) => {
        setInstitutions(res.institutions);
        if (!institutionId && me?.user.higher_ed_institution_id) {
          setInstitutionId(me.user.higher_ed_institution_id);
        }
      })
      .catch(() => setError("Could not load the list of institutions."));
  }, [isHigherEd]);

  useEffect(() => {
    if (!institutionId) {
      setQualifications([]);
      setQualificationId(null);
      setModules([]);
      setModuleId(null);
      return;
    }
    fetchQualifications(institutionId)
      .then((res) => {
        setQualifications(res.qualifications);
        const target = pendingQualificationId.current;
        pendingQualificationId.current = null;
        if (target && res.qualifications.some((q) => q.id === target)) {
          setQualificationId(target);
        } else {
          setQualificationId(null);
          setModules([]);
          setModuleId(null);
        }
      })
      .catch(() => setError("Could not load qualifications for that institution."));
  }, [institutionId]);

  useEffect(() => {
    if (!qualificationId) {
      setModules([]);
      setModuleId(null);
      return;
    }
    fetchModules(qualificationId)
      .then((res) => {
        setModules(res.modules);
        const target = pendingModuleId.current;
        pendingModuleId.current = null;
        if (target && res.modules.some((m) => m.id === target)) {
          setModuleId(target);
        } else {
          setModuleId(null);
        }
      })
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
      const params = {
        subject: isHigherEd ? undefined : subject,
        module_id: isHigherEd ? moduleId! : undefined,
        price_zar: priceVal,
        scheduled_at: sessionDateTimeToIso(dateTime),
        duration_minutes: durationVal,
        topic: topic.trim(),
        preferred_times_note: notes.trim(),
        preferred_tutor_id: preferredTutorId,
      };
      if (isEdit) {
        await editTutoringRequest(token, editRequest!.id, params);
      } else {
        await requestTutoringSession(token, params);
      }
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
        <Pressable
          style={styles.backLink}
          onPress={() => navigation.navigate(isEdit ? "MyTutoringRequests" : "Home")}
        >
          <Text style={styles.backLinkText}>‹ Back to {isEdit ? "My Requests" : "Home"}</Text>
        </Pressable>
        <Text style={styles.title}>{isEdit ? "✏️ Edit Request" : "🙋 Request a Tutor"}</Text>
        <Text style={styles.subtitle}>
          {isEdit
            ? "Update your request's details below. This is only possible while no tutor has accepted it yet."
            : "Get matched with a real tutor for a 1-on-1 session. Billed separately per session — no subscription required."}
        </Text>
        {!isEdit && preferredTutorId && directoryPrefill?.tutorName ? (
          <Text style={styles.directoryNote}>
            Requesting {directoryPrefill.tutorName} directly - they'll be the only tutor who sees this request.
          </Text>
        ) : null}

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
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitButtonText}>{isEdit ? "Save Changes" : "Submit Request"}</Text>
          )}
        </Pressable>

        <Text style={styles.note}>
          {isEdit
            ? "Changes take effect immediately. A new time must still be at least 24 hours away, unless you and the tutor already agreed otherwise."
            : `Your request goes straight to tutors who teach this ${isHigherEd ? "module" : "subject"} - once one accepts your price and time (or proposes a different time for you to approve), you'll be asked to pay securely before the session is confirmed.`}
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  // Generous bottom padding so the submit button and closing note sit
  // well clear of the device's own bottom nav bar/gesture area.
  container: { padding: 20, paddingBottom: 64, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4 },
  directoryNote: { fontSize: 13, color: colors.primary, fontWeight: "600", marginTop: 10 },
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
