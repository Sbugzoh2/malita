import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { colors, SUBJECTS, Subject } from "../theme";
import Dropdown from "../components/Dropdown";
import {
  ApiError, applyAsTutor, YEAR_LEVEL_LABELS,
  Institution, Qualification, CatalogModule,
  fetchInstitutions, fetchQualifications, fetchModules,
} from "../api/client";

type PickedDoc = { uri: string; name: string; type: string } | null;

type SubjectRow = { selected: boolean; matric: string; topics: string; rate: string };

async function pickDocument(): Promise<PickedDoc> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ["image/*", "application/pdf"],
  });
  if (result.canceled || !result.assets?.[0]) return null;
  const asset = result.assets[0];
  return { uri: asset.uri, name: asset.name, type: asset.mimeType ?? "application/octet-stream" };
}

function DocumentField({
  label, value, onPick,
}: {
  label: string;
  value: PickedDoc;
  onPick: (v: PickedDoc) => void;
}) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable style={styles.docButton} onPress={async () => onPick(await pickDocument())}>
        <Text style={styles.docButtonText}>{value ? `📄 ${value.name}` : "Choose file (optional)"}</Text>
      </Pressable>
    </View>
  );
}

export default function TutorApplyScreen({ navigation }: any) {
  const [wantsHighSchool, setWantsHighSchool] = useState(true);
  const [wantsHigherEd, setWantsHigherEd] = useState(false);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [phone, setPhone] = useState("");
  const [bio, setBio] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [availabilityNote, setAvailabilityNote] = useState("");
  const [bankAccountNote, setBankAccountNote] = useState("");

  const [subjectRows, setSubjectRows] = useState<Record<Subject, SubjectRow>>(
    Object.fromEntries(SUBJECTS.map((s) => [s, { selected: false, matric: "", topics: "", rate: "" }])) as Record<
      Subject,
      SubjectRow
    >
  );

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [qualificationId, setQualificationId] = useState<number | null>(null);
  const [yearOfStudy, setYearOfStudy] = useState<number | null>(null);
  const [qualificationComplete, setQualificationComplete] = useState(false);
  const [average, setAverage] = useState("");
  const [transcriptNote, setTranscriptNote] = useState("");
  const [modules, setModules] = useState<CatalogModule[]>([]);
  const [selectedModuleIds, setSelectedModuleIds] = useState<Set<number>>(new Set());

  const [idDocument, setIdDocument] = useState<PickedDoc>(null);
  const [matricCertificate, setMatricCertificate] = useState<PickedDoc>(null);
  const [cv, setCv] = useState<PickedDoc>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!wantsHigherEd) return;
    fetchInstitutions()
      .then((res) => setInstitutions(res.institutions))
      .catch(() => setError("Could not load the list of institutions."));
  }, [wantsHigherEd]);

  useEffect(() => {
    setQualificationId(null);
    setModules([]);
    setSelectedModuleIds(new Set());
    if (!institutionId) {
      setQualifications([]);
      return;
    }
    fetchQualifications(institutionId)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => setError("Could not load qualifications for that institution."));
  }, [institutionId]);

  useEffect(() => {
    setSelectedModuleIds(new Set());
    if (!qualificationId) {
      setModules([]);
      return;
    }
    fetchModules(qualificationId)
      .then((res) => setModules(res.modules))
      .catch(() => setError("Could not load modules for that qualification."));
  }, [qualificationId]);

  // Only modules at least one year behind the applicant's own year of
  // study are eligible to tutor - same rule enforced server-side, shown
  // here so an applicant never picks something that will just get
  // rejected on submit.
  const eligibleModules = modules.filter(
    (m) => qualificationComplete || (yearOfStudy != null && m.year_level < yearOfStudy)
  );

  function toggleSubject(subject: Subject) {
    setSubjectRows((prev) => ({
      ...prev,
      [subject]: { ...prev[subject], selected: !prev[subject].selected },
    }));
  }

  function updateSubjectField(subject: Subject, field: keyof SubjectRow, value: string) {
    setSubjectRows((prev) => ({ ...prev, [subject]: { ...prev[subject], [field]: value } }));
  }

  function toggleModule(moduleId: number) {
    setSelectedModuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(moduleId)) next.delete(moduleId);
      else next.add(moduleId);
      return next;
    });
  }

  async function handleSubmit() {
    setError(null);
    if (!wantsHighSchool && !wantsHigherEd) {
      setError("Please choose high school, university/college, or both.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== passwordConfirm) {
      setError("Passwords don't match.");
      return;
    }

    const chosenSubjects = SUBJECTS.filter((s) => subjectRows[s].selected);
    if (wantsHighSchool && chosenSubjects.length === 0) {
      setError("Please select at least one subject.");
      return;
    }
    for (const s of chosenSubjects) {
      const pct = parseFloat(subjectRows[s].matric);
      if (isNaN(pct)) {
        setError(`Please enter your matric mark for ${s}.`);
        return;
      }
    }

    if (wantsHigherEd) {
      if (!institutionId || !qualificationId) {
        setError("Please select your institution and qualification.");
        return;
      }
      if (!yearOfStudy) {
        setError("Please select your year of study.");
        return;
      }
      const avgNum = parseFloat(average);
      if (isNaN(avgNum)) {
        setError("Please enter your semester/final average.");
        return;
      }
      if (selectedModuleIds.size === 0) {
        setError("Please select at least one module you're able to tutor.");
        return;
      }
    }

    setSubmitting(true);
    try {
      await applyAsTutor({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        phone: phone.trim(),
        bio: bio.trim(),
        id_number: idNumber.trim(),
        availability_note: availabilityNote.trim(),
        bank_account_note: bankAccountNote.trim(),
        wants_high_school: wantsHighSchool,
        wants_higher_ed: wantsHigherEd,
        subjects: chosenSubjects.map((s) => ({
          subject: s,
          matric_percentage: parseFloat(subjectRows[s].matric),
          topics: subjectRows[s].topics.trim() || undefined,
          hourly_rate_zar: subjectRows[s].rate ? parseFloat(subjectRows[s].rate) : undefined,
        })),
        higher_ed_institution_id: wantsHigherEd ? institutionId : undefined,
        higher_ed_qualification_id: wantsHigherEd ? qualificationId : undefined,
        higher_ed_year_of_study: wantsHigherEd ? yearOfStudy : undefined,
        higher_ed_qualification_complete: wantsHigherEd ? qualificationComplete : undefined,
        higher_ed_average: wantsHigherEd ? parseFloat(average) : undefined,
        higher_ed_transcript_note: wantsHigherEd ? transcriptNote.trim() : undefined,
        higher_ed_module_ids: wantsHigherEd ? Array.from(selectedModuleIds) : undefined,
        id_document: idDocument,
        matric_certificate: matricCertificate,
        cv,
      });
      setSuccess(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit your application. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <View style={styles.successContainer}>
        <Text style={styles.successTitle}>🎉 Application submitted!</Text>
        <Text style={styles.successBody}>
          We'll email you once an admin has reviewed your application. You can log in anytime to check its status.
        </Text>
        <Pressable style={styles.button} onPress={() => navigation.navigate("TutorLogin")}>
          <Text style={styles.buttonText}>Go to Tutor Login</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>🙋 Apply to Tutor</Text>
        <Text style={styles.subtitle}>
          Malita's minimum bar is a 65% mark (matric subject or semester/final average) to apply.
        </Text>

        <View style={styles.card}>
          <Text style={styles.label}>I want to tutor...</Text>
          <View style={styles.chipRow}>
            <Pressable
              style={[styles.chip, wantsHighSchool && !wantsHigherEd && styles.chipActive]}
              onPress={() => { setWantsHighSchool(true); setWantsHigherEd(false); }}
            >
              <Text style={[styles.chipText, wantsHighSchool && !wantsHigherEd && styles.chipTextActive]}>
                High School
              </Text>
            </Pressable>
            <Pressable
              style={[styles.chip, wantsHigherEd && !wantsHighSchool && styles.chipActive]}
              onPress={() => { setWantsHighSchool(false); setWantsHigherEd(true); }}
            >
              <Text style={[styles.chipText, wantsHigherEd && !wantsHighSchool && styles.chipTextActive]}>
                University / College
              </Text>
            </Pressable>
            <Pressable
              style={[styles.chip, wantsHighSchool && wantsHigherEd && styles.chipActive]}
              onPress={() => { setWantsHighSchool(true); setWantsHigherEd(true); }}
            >
              <Text style={[styles.chipText, wantsHighSchool && wantsHigherEd && styles.chipTextActive]}>Both</Text>
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

          <Text style={styles.label}>Phone (optional)</Text>
          <TextInput style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />

          <Text style={styles.label}>Password</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry />

          <Text style={styles.label}>Confirm password</Text>
          <TextInput style={styles.input} value={passwordConfirm} onChangeText={setPasswordConfirm} secureTextEntry />

          <Text style={styles.label}>Short bio (optional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={bio}
            onChangeText={setBio}
            multiline
            placeholder="A couple of sentences about your teaching experience"
          />

          <Text style={styles.label}>ID number (optional)</Text>
          <TextInput style={styles.input} value={idNumber} onChangeText={setIdNumber} maxLength={13} keyboardType="number-pad" />

          <Text style={styles.label}>Availability (optional)</Text>
          <TextInput
            style={styles.input}
            value={availabilityNote}
            onChangeText={setAvailabilityNote}
            placeholder="e.g. Weekdays after 16:00, Saturday mornings"
          />

          <Text style={styles.label}>Bank account details (optional, for payouts)</Text>
          <TextInput style={[styles.input, styles.textArea]} value={bankAccountNote} onChangeText={setBankAccountNote} multiline />

          <DocumentField label="ID document" value={idDocument} onPick={setIdDocument} />
          <DocumentField label="Matric certificate" value={matricCertificate} onPick={setMatricCertificate} />
          <DocumentField label="CV" value={cv} onPick={setCv} />
        </View>

        {wantsHighSchool && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>High School Subjects</Text>
            {SUBJECTS.map((s) => (
              <View key={s} style={styles.subjectBlock}>
                <Pressable style={styles.checkboxRow} onPress={() => toggleSubject(s)}>
                  <View style={[styles.checkbox, subjectRows[s].selected && styles.checkboxChecked]}>
                    {subjectRows[s].selected ? <Text style={styles.checkboxMark}>✓</Text> : null}
                  </View>
                  <Text style={styles.checkboxLabel}>{s}</Text>
                </Pressable>
                {subjectRows[s].selected && (
                  <View style={styles.subjectDetail}>
                    <Text style={styles.label}>Your matric mark (%)</Text>
                    <TextInput
                      style={styles.input}
                      value={subjectRows[s].matric}
                      onChangeText={(v) => updateSubjectField(s, "matric", v)}
                      keyboardType="numeric"
                    />
                    <Text style={styles.label}>Topics you specialize in (optional)</Text>
                    <TextInput
                      style={styles.input}
                      value={subjectRows[s].topics}
                      onChangeText={(v) => updateSubjectField(s, "topics", v)}
                    />
                    <Text style={styles.label}>Asking rate (R/hr, optional)</Text>
                    <TextInput
                      style={styles.input}
                      value={subjectRows[s].rate}
                      onChangeText={(v) => updateSubjectField(s, "rate", v)}
                      keyboardType="numeric"
                    />
                  </View>
                )}
              </View>
            ))}
          </View>
        )}

        {wantsHigherEd && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>University / College Details</Text>
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
              label="Your year of study"
              options={Object.entries(YEAR_LEVEL_LABELS).map(([k, v]) => ({ label: v, value: k }))}
              value={yearOfStudy != null ? String(yearOfStudy) : null}
              onChange={(v) => setYearOfStudy(parseInt(v, 10))}
            />
            <Pressable style={styles.checkboxRow} onPress={() => setQualificationComplete((c) => !c)}>
              <View style={[styles.checkbox, qualificationComplete && styles.checkboxChecked]}>
                {qualificationComplete ? <Text style={styles.checkboxMark}>✓</Text> : null}
              </View>
              <Text style={styles.checkboxLabel}>I've already completed this qualification</Text>
            </Pressable>

            <Text style={styles.label}>Semester / final average (%)</Text>
            <TextInput style={styles.input} value={average} onChangeText={setAverage} keyboardType="numeric" />

            <Text style={styles.label}>Transcript note (optional)</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={transcriptNote}
              onChangeText={setTranscriptNote}
              multiline
              placeholder="e.g. a link to where you've uploaded your transcript"
            />

            <Text style={styles.label}>
              Modules you're able to tutor {yearOfStudy ? `(at least one year behind ${YEAR_LEVEL_LABELS[yearOfStudy]})` : ""}
            </Text>
            {!qualificationId ? (
              <Text style={styles.helperText}>Select a qualification first.</Text>
            ) : eligibleModules.length === 0 ? (
              <Text style={styles.helperText}>
                No eligible modules yet - either none are listed for this qualification, or none are behind your
                selected year of study.
              </Text>
            ) : (
              eligibleModules.map((m) => (
                <Pressable key={m.id} style={styles.checkboxRow} onPress={() => toggleModule(m.id)}>
                  <View style={[styles.checkbox, selectedModuleIds.has(m.id) && styles.checkboxChecked]}>
                    {selectedModuleIds.has(m.id) ? <Text style={styles.checkboxMark}>✓</Text> : null}
                  </View>
                  <Text style={styles.checkboxLabel}>
                    {m.name} ({m.year_level_label})
                  </Text>
                </Pressable>
              ))
            )}
          </View>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable style={[styles.button, submitting && styles.buttonDisabled]} onPress={handleSubmit} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Submit Application</Text>}
        </Pressable>

        <Pressable onPress={() => navigation.navigate("TutorLogin")} style={styles.linkButton}>
          <Text style={styles.link}>Already applied? Log in</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { flexGrow: 1, padding: 24, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: "700", textAlign: "center", color: colors.text },
  subtitle: { fontSize: 13, textAlign: "center", color: colors.textSecondary, marginTop: 6, marginBottom: 20 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 20,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 8 },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  helperText: { fontSize: 12, color: colors.textSecondary, marginTop: 6, fontStyle: "italic" },
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
  textArea: { minHeight: 70, textAlignVertical: "top" },
  chipRow: { flexDirection: "row", gap: 8, marginTop: 6 },
  chip: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 8,
    alignItems: "center",
    backgroundColor: "#fff",
  },
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipText: { color: colors.text, fontSize: 12, fontWeight: "600", textAlign: "center" },
  chipTextActive: { color: "#fff" },
  docButton: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  docButtonText: { color: colors.text, fontSize: 14 },
  subjectBlock: { marginTop: 14, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 14 },
  subjectDetail: { marginTop: 4 },
  checkboxRow: { flexDirection: "row", alignItems: "center", marginTop: 12 },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },
  checkboxChecked: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkboxMark: { color: "#fff", fontWeight: "700", fontSize: 13 },
  checkboxLabel: { fontSize: 14, color: colors.text, flexShrink: 1 },
  error: { color: colors.error, marginTop: 4, marginBottom: 8 },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  linkButton: { marginTop: 16, marginBottom: 24, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  successContainer: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: colors.background },
  successTitle: { fontSize: 22, fontWeight: "700", color: colors.text, marginBottom: 12, textAlign: "center" },
  successBody: { fontSize: 14, color: colors.textSecondary, textAlign: "center", marginBottom: 24, lineHeight: 20 },
});
