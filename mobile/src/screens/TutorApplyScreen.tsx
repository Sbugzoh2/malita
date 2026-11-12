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
import { colors, HIGH_SCHOOL_TUTORING_SUBJECTS, HighSchoolTutoringSubject, SA_BANKS, BANK_ACCOUNT_TYPES } from "../theme";
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
  label, value, onPick, required = true,
}: {
  label: string;
  value: PickedDoc;
  onPick: (v: PickedDoc) => void;
  required?: boolean;
}) {
  return (
    <View>
      <Text style={styles.label}>{label}{required ? " *" : " (optional)"}</Text>
      <Pressable style={styles.docButton} onPress={async () => onPick(await pickDocument())}>
        <Text style={styles.docButtonText}>{value ? `📄 ${value.name}` : "Choose file"}</Text>
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
  const [bankAccountHolder, setBankAccountHolder] = useState("");
  const [bankName, setBankName] = useState<string | null>(null);
  const [bankNameOther, setBankNameOther] = useState("");
  const [bankBranchCode, setBankBranchCode] = useState("");
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [bankAccountType, setBankAccountType] = useState<string | null>(null);
  const [bankAccountTypeOther, setBankAccountTypeOther] = useState("");
  const [bankAccountNote, setBankAccountNote] = useState("");

  const [subjectRows, setSubjectRows] = useState<Record<HighSchoolTutoringSubject, SubjectRow>>(
    Object.fromEntries(
      HIGH_SCHOOL_TUTORING_SUBJECTS.map((s) => [s, { selected: false, matric: "", topics: "", rate: "" }])
    ) as Record<HighSchoolTutoringSubject, SubjectRow>
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
  // "Other" escape hatch for when the applicant's real qualification isn't
  // in the catalog - modules then have no catalog Module row to point at,
  // so they're entered as free-text name + year instead of picked from a
  // list (see TutorCustomHigherEdModule in backend/db.py).
  const [isCustomQualification, setIsCustomQualification] = useState(false);
  const [customQualificationName, setCustomQualificationName] = useState("");
  const [customModules, setCustomModules] = useState<{ name: string; year_level: number }[]>([]);
  const [newCustomModuleName, setNewCustomModuleName] = useState("");
  const [newCustomModuleYear, setNewCustomModuleYear] = useState<number | null>(null);

  const [idDocument, setIdDocument] = useState<PickedDoc>(null);
  const [matricCertificate, setMatricCertificate] = useState<PickedDoc>(null);
  const [cv, setCv] = useState<PickedDoc>(null);
  const [transcriptDocument, setTranscriptDocument] = useState<PickedDoc>(null);
  const [qualificationCertificate, setQualificationCertificate] = useState<PickedDoc>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [exclusionNotes, setExclusionNotes] = useState<string[]>([]);
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
  // rejected on submit. Eligible YEAR_LEVEL_LABELS entries for the custom
  // module builder below apply the identical rule.
  const eligibleModules = modules.filter(
    (m) => qualificationComplete || (yearOfStudy != null && m.year_level < yearOfStudy)
  );
  const eligibleYearLevels = Object.entries(YEAR_LEVEL_LABELS).filter(
    ([k]) => qualificationComplete || (yearOfStudy != null && parseInt(k, 10) < yearOfStudy)
  );

  function toggleSubject(subject: HighSchoolTutoringSubject) {
    setSubjectRows((prev) => ({
      ...prev,
      [subject]: { ...prev[subject], selected: !prev[subject].selected },
    }));
  }

  function updateSubjectField(subject: HighSchoolTutoringSubject, field: keyof SubjectRow, value: string) {
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

  function addCustomModule() {
    if (!newCustomModuleName.trim() || newCustomModuleYear == null) return;
    setCustomModules((prev) => [...prev, { name: newCustomModuleName.trim(), year_level: newCustomModuleYear }]);
    setNewCustomModuleName("");
    setNewCustomModuleYear(null);
  }

  function removeCustomModule(index: number) {
    setCustomModules((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    setError(null);
    if (!wantsHighSchool && !wantsHigherEd) {
      setError("Please choose high school, university/college, or both.");
      return;
    }
    if (!name.trim()) { setError("Please enter your full name."); return; }
    if (!email.trim()) { setError("Please enter your email."); return; }
    if (!phone.trim()) { setError("Please enter your phone number."); return; }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== passwordConfirm) {
      setError("Passwords don't match.");
      return;
    }
    if (!bio.trim()) { setError("Please enter a short bio."); return; }
    if (!idNumber.trim()) { setError("Please enter your ID number."); return; }
    if (!availabilityNote.trim()) { setError("Please enter your availability."); return; }
    if (!bankAccountHolder.trim()) { setError("Please enter the bank account holder's name."); return; }
    if (!bankName) { setError("Please select your bank."); return; }
    if (bankName === "Other" && !bankNameOther.trim()) { setError("Please enter your bank's name."); return; }
    if (!bankBranchCode.trim()) { setError("Please enter your branch code."); return; }
    if (!bankAccountNumber.trim()) { setError("Please enter your account number."); return; }
    if (!bankAccountType) { setError("Please select your account type."); return; }
    if (bankAccountType === "Other" && !bankAccountTypeOther.trim()) {
      setError("Please enter your account type.");
      return;
    }
    if (!idDocument) { setError("Please upload your ID document."); return; }
    if (!cv) { setError("Please upload your CV."); return; }

    const chosenSubjects = HIGH_SCHOOL_TUTORING_SUBJECTS.filter((s) => subjectRows[s].selected);
    // Selecting "Both" with no high-school subject chosen isn't an error -
    // the profile just defaults to a university/college-only application.
    const isBothMode = wantsHighSchool && wantsHigherEd;
    if (wantsHighSchool && !isBothMode && chosenSubjects.length === 0) {
      setError("Please select at least one subject.");
      return;
    }
    for (const s of chosenSubjects) {
      const pct = parseFloat(subjectRows[s].matric);
      if (isNaN(pct)) {
        setError(`Please enter your matric mark for ${s}.`);
        return;
      }
      if (!subjectRows[s].topics.trim()) {
        setError(`Please enter the topics you specialize in for ${s}.`);
        return;
      }
      if (!subjectRows[s].rate.trim()) {
        setError(`Please enter your asking rate for ${s}.`);
        return;
      }
    }
    const effectiveWantsHighSchool = chosenSubjects.length > 0;
    if (effectiveWantsHighSchool && !matricCertificate) {
      setError("Please upload your matric certificate.");
      return;
    }

    if (wantsHigherEd) {
      if (!institutionId || (!isCustomQualification && !qualificationId)) {
        setError("Please select your institution and qualification.");
        return;
      }
      if (isCustomQualification && !customQualificationName.trim()) {
        setError("Please enter the name of your qualification.");
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
      if (!transcriptNote.trim()) {
        setError("Please enter a transcript note.");
        return;
      }
      if (selectedModuleIds.size === 0 && customModules.length === 0) {
        setError("Please select or add at least one module you're able to tutor.");
        return;
      }
      if (!transcriptDocument) {
        setError("Please upload your academic transcript.");
        return;
      }
      if (qualificationComplete && !qualificationCertificate) {
        setError("Please upload your qualification certificate / proof of completion.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const result = await applyAsTutor({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        phone: phone.trim(),
        bio: bio.trim(),
        id_number: idNumber.trim(),
        availability_note: availabilityNote.trim(),
        bank_account_holder: bankAccountHolder.trim(),
        bank_name: bankName === "Other" ? bankNameOther.trim() : bankName ?? "",
        bank_branch_code: bankBranchCode.trim(),
        bank_account_number: bankAccountNumber.trim(),
        bank_account_type: bankAccountType === "Other" ? bankAccountTypeOther.trim() : bankAccountType ?? "",
        bank_account_note: bankAccountNote.trim(),
        wants_high_school: effectiveWantsHighSchool,
        wants_higher_ed: wantsHigherEd,
        subjects: chosenSubjects.map((s) => ({
          subject: s,
          matric_percentage: parseFloat(subjectRows[s].matric),
          topics: subjectRows[s].topics.trim() || undefined,
          hourly_rate_zar: subjectRows[s].rate ? parseFloat(subjectRows[s].rate) : undefined,
        })),
        higher_ed_institution_id: wantsHigherEd ? institutionId : undefined,
        higher_ed_qualification_id: wantsHigherEd && !isCustomQualification ? qualificationId : undefined,
        higher_ed_qualification_custom_name:
          wantsHigherEd && isCustomQualification ? customQualificationName.trim() : undefined,
        higher_ed_year_of_study: wantsHigherEd ? yearOfStudy : undefined,
        higher_ed_qualification_complete: wantsHigherEd ? qualificationComplete : undefined,
        higher_ed_average: wantsHigherEd ? parseFloat(average) : undefined,
        higher_ed_transcript_note: wantsHigherEd ? transcriptNote.trim() : undefined,
        // Sent independently of each other - a catalog qualification can
        // still have extra custom modules added alongside picked-from-
        // the-list ones (see the merged module section below), not just
        // when the whole qualification itself is custom.
        higher_ed_module_ids: wantsHigherEd && selectedModuleIds.size > 0 ? Array.from(selectedModuleIds) : undefined,
        higher_ed_custom_modules: wantsHigherEd && customModules.length > 0 ? customModules : undefined,
        id_document: idDocument,
        matric_certificate: effectiveWantsHighSchool ? matricCertificate : null,
        cv,
        higher_ed_transcript: wantsHigherEd ? transcriptDocument : null,
        higher_ed_qualification_certificate: wantsHigherEd ? qualificationCertificate : null,
      });
      const notes: string[] = [];
      for (const s of result.excluded_subjects) {
        notes.push(`${s.subject} (${s.matric_percentage ?? "?"}%) wasn't included - ${s.reason}`);
      }
      if (result.excluded_higher_ed_reason) {
        notes.push(`University/college modules weren't included - ${result.excluded_higher_ed_reason}`);
      }
      for (const m of result.excluded_modules) {
        notes.push(`"${m.name}" wasn't included - ${m.reason}`);
      }
      setExclusionNotes(notes);
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
        {exclusionNotes.length > 0 && (
          <View style={styles.exclusionBox}>
            <Text style={styles.exclusionTitle}>A few things weren't included in this submission:</Text>
            {exclusionNotes.map((note, i) => (
              <Text key={i} style={styles.exclusionNote}>• {note}</Text>
            ))}
          </View>
        )}
        <Pressable style={styles.button} onPress={() => navigation.goBack()}>
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

          <Text style={styles.label}>Phone</Text>
          <TextInput style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />

          <Text style={styles.label}>Password</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry />

          <Text style={styles.label}>Confirm password</Text>
          <TextInput style={styles.input} value={passwordConfirm} onChangeText={setPasswordConfirm} secureTextEntry />

          <Text style={styles.label}>Short bio</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={bio}
            onChangeText={setBio}
            multiline
            placeholder="A couple of sentences about your teaching experience"
          />

          <Text style={styles.label}>ID number</Text>
          <TextInput style={styles.input} value={idNumber} onChangeText={setIdNumber} maxLength={13} keyboardType="number-pad" />

          <Text style={styles.label}>Availability</Text>
          <TextInput
            style={styles.input}
            value={availabilityNote}
            onChangeText={setAvailabilityNote}
            placeholder="e.g. Weekdays after 16:00, Saturday mornings"
          />

          <Text style={styles.sectionTitle}>Bank Account Details (for payouts)</Text>
          <Text style={styles.label}>Account holder name</Text>
          <TextInput
            style={styles.input}
            value={bankAccountHolder}
            onChangeText={setBankAccountHolder}
            placeholder="As it appears on your bank statement"
          />
          <Dropdown
            label="Bank"
            options={SA_BANKS.map((b) => ({ label: b, value: b }))}
            value={bankName}
            onChange={setBankName}
          />
          {bankName === "Other" && (
            <>
              <Text style={styles.label}>Bank name</Text>
              <TextInput style={styles.input} value={bankNameOther} onChangeText={setBankNameOther} />
            </>
          )}
          <View style={styles.timeRow}>
            <View style={styles.timeCol}>
              <Text style={styles.label}>Branch code</Text>
              <TextInput
                style={styles.input}
                value={bankBranchCode}
                onChangeText={setBankBranchCode}
                keyboardType="number-pad"
              />
            </View>
            <View style={styles.timeCol}>
              <Text style={styles.label}>Account number</Text>
              <TextInput
                style={styles.input}
                value={bankAccountNumber}
                onChangeText={setBankAccountNumber}
                keyboardType="number-pad"
              />
            </View>
          </View>
          <Dropdown
            label="Account type"
            options={BANK_ACCOUNT_TYPES.map((t) => ({ label: t, value: t }))}
            value={bankAccountType}
            onChange={setBankAccountType}
          />
          {bankAccountType === "Other" && (
            <>
              <Text style={styles.label}>Account type</Text>
              <TextInput style={styles.input} value={bankAccountTypeOther} onChangeText={setBankAccountTypeOther} />
            </>
          )}
          <Text style={styles.label}>Additional notes (optional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={bankAccountNote}
            onChangeText={setBankAccountNote}
            multiline
            placeholder="e.g. a SWIFT code for an international account"
          />

          <DocumentField label="ID document" value={idDocument} onPick={setIdDocument} />
          <DocumentField
            label="Matric certificate"
            value={matricCertificate}
            onPick={setMatricCertificate}
            required={HIGH_SCHOOL_TUTORING_SUBJECTS.some((s) => subjectRows[s].selected)}
          />
          <DocumentField label="CV" value={cv} onPick={setCv} />
        </View>

        {wantsHighSchool && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>High School Subjects</Text>
            <Text style={styles.helperText}>Select every subject you're able to tutor:</Text>
            {HIGH_SCHOOL_TUTORING_SUBJECTS.map((s) => (
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
                    <Text style={styles.label}>Topics you specialize in</Text>
                    <TextInput
                      style={styles.input}
                      value={subjectRows[s].topics}
                      onChangeText={(v) => updateSubjectField(s, "topics", v)}
                    />
                    <Text style={styles.label}>Asking rate (R/hr)</Text>
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
              label="Highest completed qualification, or the one you're currently studying towards"
              options={[
                ...qualifications.map((q) => ({ label: q.name, value: String(q.id) })),
                { label: "Other (not listed)", value: "other" },
              ]}
              value={isCustomQualification ? "other" : qualificationId != null ? String(qualificationId) : null}
              onChange={(v) => {
                if (v === "other") {
                  setIsCustomQualification(true);
                  setQualificationId(null);
                } else {
                  setIsCustomQualification(false);
                  setQualificationId(parseInt(v, 10));
                }
              }}
            />
            {isCustomQualification ? (
              <>
                <Text style={styles.label}>Your qualification</Text>
                <TextInput
                  style={styles.input}
                  value={customQualificationName}
                  onChangeText={setCustomQualificationName}
                  placeholder="e.g. BCom Investment Management"
                />
              </>
            ) : institutionId && qualifications.length === 0 ? (
              <Text style={styles.helperText}>
                No qualifications listed yet for this institution - ask an admin to add it to the catalog.
              </Text>
            ) : null}
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

            <Text style={styles.label}>Transcript note</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={transcriptNote}
              onChangeText={setTranscriptNote}
              multiline
              placeholder="e.g. anything we should know when reviewing your transcript"
            />

            <DocumentField label="Academic transcript" value={transcriptDocument} onPick={setTranscriptDocument} />
            {qualificationComplete && (
              <DocumentField
                label="Qualification certificate / proof of completion"
                value={qualificationCertificate}
                onPick={setQualificationCertificate}
              />
            )}

            <Text style={styles.label}>
              Modules you're able to tutor {yearOfStudy ? `(at least one year behind ${YEAR_LEVEL_LABELS[yearOfStudy]})` : ""}
            </Text>
            {/* Catalog checklist - only possible when the qualification itself
                is a real catalog entry (a custom qualification has no catalog
                Modules to list). Independent of the custom builder below, so
                a catalog qualification can still have extra modules added by
                hand if one isn't listed under it. */}
            {!isCustomQualification &&
              (!qualificationId ? (
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
              ))}
            {/* Custom ("Other") modules - always available, not just when the
                whole qualification is custom, so "my qualification is listed
                but this one module isn't" is covered too. */}
            {customModules.map((m, i) => (
              <View key={i} style={styles.checkboxRow}>
                <Text style={[styles.checkboxLabel, { flex: 1 }]}>
                  {m.name} ({YEAR_LEVEL_LABELS[m.year_level]})
                </Text>
                <Pressable onPress={() => removeCustomModule(i)}>
                  <Text style={styles.removeModuleText}>✕</Text>
                </Pressable>
              </View>
            ))}
            {!isCustomQualification && (
              <Text style={styles.helperText}>Don't see a module you teach? Add it below.</Text>
            )}
            {!yearOfStudy ? (
              <Text style={styles.helperText}>Select your year of study first.</Text>
            ) : eligibleYearLevels.length === 0 ? (
              <Text style={styles.helperText}>No year level is behind your selected year of study.</Text>
            ) : (
              <>
                <View style={styles.timeRow}>
                  <View style={styles.timeCol}>
                    <Text style={styles.label}>Module</Text>
                    <TextInput
                      style={styles.input}
                      value={newCustomModuleName}
                      onChangeText={setNewCustomModuleName}
                      placeholder="Module name"
                    />
                  </View>
                  <View style={styles.timeCol}>
                    <Dropdown
                      label="Year"
                      options={eligibleYearLevels.map(([k, v]) => ({ label: v, value: k }))}
                      value={newCustomModuleYear != null ? String(newCustomModuleYear) : null}
                      onChange={(v) => setNewCustomModuleYear(parseInt(v, 10))}
                    />
                  </View>
                </View>
                <Pressable style={styles.addModuleButton} onPress={addCustomModule}>
                  <Text style={styles.addModuleButtonText}>Add module</Text>
                </Pressable>
              </>
            )}
          </View>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable style={[styles.button, submitting && styles.buttonDisabled]} onPress={handleSubmit} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Submit Application</Text>}
        </Pressable>

        <Pressable onPress={() => navigation.goBack()} style={styles.linkButton}>
          <Text style={styles.link}>Already applied? Log in</Text>
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
  container: { flexGrow: 1, padding: 24, paddingBottom: 64 },
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
  removeModuleText: { color: colors.error, fontSize: 18, fontWeight: "700", paddingHorizontal: 8 },
  // Same paired-column layout as SessionDateTimePicker's Hour/Minute row.
  timeRow: { flexDirection: "row", gap: 12, marginTop: 10 },
  timeCol: { flex: 1 },
  addModuleButton: {
    backgroundColor: colors.primary,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    alignSelf: "flex-start",
    marginTop: 10,
  },
  addModuleButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
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
  linkButton: { marginTop: 16, marginBottom: 32, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  successContainer: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: colors.background },
  successTitle: { fontSize: 22, fontWeight: "700", color: colors.text, marginBottom: 12, textAlign: "center" },
  successBody: { fontSize: 14, color: colors.textSecondary, textAlign: "center", marginBottom: 24, lineHeight: 20 },
  exclusionBox: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 16,
    marginBottom: 24,
    width: "100%",
  },
  exclusionTitle: { fontSize: 13, fontWeight: "700", color: colors.text, marginBottom: 8 },
  exclusionNote: { fontSize: 13, color: colors.textSecondary, marginTop: 4, lineHeight: 18 },
});
