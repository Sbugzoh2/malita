import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
  Alert,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  TutorApplication,
  fetchTutorApplications,
  approveTutorApplication,
  rejectTutorApplication,
  fetchTutorDocumentUrl,
  ApprovedTutor,
  fetchApprovedTutors,
  TutoringRequest,
  fetchOpenTutoringRequestsAdmin,
  matchTutorToRequestAdmin,
  TutoringPayout,
  fetchPendingPayoutsAdmin,
  markPayoutPaidAdmin,
  TutorProfile,
  fetchTutorProfile,
  AdminTutoringSession,
  fetchAllTutoringSessionsAdmin,
  TutorHigherEdApplication,
  fetchTutorHigherEdApplications,
  approveTutorHigherEdApplication,
  rejectTutorHigherEdApplication,
  Institution,
  Qualification,
  CatalogModule,
  fetchInstitutions,
  fetchQualifications,
  fetchModules,
  addInstitutionAdmin,
  addQualificationAdmin,
  addModuleAdmin,
  YEAR_LEVEL_LABELS,
  API_BASE_URL,
} from "../api/client";
import Dropdown from "../components/Dropdown";

type Section = "applications" | "higherEdApplications" | "catalog" | "match" | "sessions" | "tutors" | "payouts";

const STATUS_OPTIONS: { label: string; value: TutorApplication["status"] }[] = [
  { label: "Pending Review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Suspended", value: "suspended" },
];

export default function TutoringAdminScreen({ navigation }: any) {
  const { token } = useAuth();
  const [section, setSection] = useState<Section>("applications");

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>🛠️ Tutoring Admin</Text>
      <Text style={styles.subtitle}>v1 is manual by design — see backend/tutoring.py.</Text>
      <Pressable
        style={styles.connectCalendarButton}
        onPress={() => Linking.openURL(`${API_BASE_URL}/admin/google-calendar/connect`)}
      >
        <Text style={styles.connectCalendarButtonText}>🔗 Connect Google Calendar (for session Meet links)</Text>
      </Pressable>

      <View style={styles.sectionRow}>
        {([
          { key: "applications", label: "Applications" },
          { key: "higherEdApplications", label: "Higher-Ed Applications" },
          { key: "catalog", label: "Higher-Ed Catalog" },
          { key: "match", label: "Match Requests" },
          { key: "sessions", label: "All Sessions" },
          { key: "tutors", label: "Tutors" },
          { key: "payouts", label: "Payouts" },
        ] as { key: Section; label: string }[]).map((s) => (
          <Pressable
            key={s.key}
            style={[styles.sectionChip, section === s.key && styles.sectionChipActive]}
            onPress={() => setSection(s.key)}
          >
            <Text style={[styles.sectionChipText, section === s.key && styles.sectionChipTextActive]}>
              {s.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {token && section === "applications" && <ApplicationsSection token={token} />}
      {token && section === "higherEdApplications" && <HigherEdApplicationsSection token={token} />}
      {token && section === "catalog" && <CatalogSection token={token} />}
      {token && section === "match" && <MatchSection token={token} />}
      {token && section === "sessions" && <SessionsSection token={token} />}
      {token && section === "tutors" && <TutorsSection token={token} />}
      {token && section === "payouts" && <PayoutsSection token={token} />}
    </ScrollView>
  );
}

function ApplicationsSection({ token }: { token: string }) {
  const [status, setStatus] = useState<TutorApplication["status"]>("pending_review");
  const [apps, setApps] = useState<TutorApplication[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [docUrls, setDocUrls] = useState<Record<string, string>>({});
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetchTutorApplications(token, status)
      .then((res) => setApps(res.applications))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load applications."));
  }, [token, status]);

  useEffect(() => {
    setApps(null);
    load();
  }, [load]);

  async function handleApprove(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await approveTutorApplication(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not approve.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await rejectTutorApplication(token, id, rejectReason);
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reject.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleGetDocUrl(tutorId: number, kind: "id" | "matric_certificate" | "cv") {
    try {
      const res = await fetchTutorDocumentUrl(token, tutorId, kind);
      setDocUrls((prev) => ({ ...prev, [`${tutorId}_${kind}`]: res.url }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not get document link.");
    }
  }

  return (
    <View>
      <Dropdown
        label="Status"
        options={STATUS_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
        value={status}
        onChange={(v) => setStatus(v as TutorApplication["status"])}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!apps ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : apps.length === 0 ? (
        <Text style={styles.empty}>No applications with this status.</Text>
      ) : (
        apps.map((a) => {
          const expanded = expandedId === a.id;
          return (
            <View key={a.id} style={styles.card}>
              <Pressable onPress={() => setExpandedId(expanded ? null : a.id)}>
                <Text style={styles.cardTitle}>
                  {a.name} — {a.email}
                </Text>
                <Text style={styles.cardSubtitle}>{a.status_label}</Text>
              </Pressable>
              {expanded && (
                <View style={styles.cardDetail}>
                  <Text style={styles.detailLine}>Phone: {a.phone || "—"}</Text>
                  <Text style={styles.detailLine}>Bio: {a.bio || "—"}</Text>
                  <Text style={styles.detailLine}>ID number: {a.id_number || "—"}</Text>
                  <Text style={styles.detailLine}>ID verification note: {a.id_verification_note || "—"}</Text>
                  <Text style={styles.detailLine}>Matric certificate note: {a.matric_certificate_note || "—"}</Text>
                  <Text style={styles.detailLine}>CV note: {a.cv_note || "—"}</Text>
                  <Text style={styles.detailLine}>Availability: {a.availability_note || "—"}</Text>
                  <Text style={styles.detailLine}>Bank details: {a.bank_account_note || "—"}</Text>

                  {([
                    ["id", "ID document", a.has_id_document] as const,
                    ["matric_certificate", "Matric certificate", a.has_matric_certificate_document] as const,
                    ["cv", "CV", a.has_cv_document] as const,
                  ]).map(([kind, label, hasDoc]) =>
                    hasDoc ? (
                      docUrls[`${a.id}_${kind}`] ? (
                        <Pressable
                          key={kind}
                          style={styles.docButton}
                          onPress={() => Linking.openURL(docUrls[`${a.id}_${kind}`])}
                        >
                          <Text style={styles.docButtonText}>Open {label}</Text>
                        </Pressable>
                      ) : (
                        <Pressable key={kind} style={styles.docButton} onPress={() => handleGetDocUrl(a.id, kind)}>
                          <Text style={styles.docButtonText}>🔗 Get {label} link</Text>
                        </Pressable>
                      )
                    ) : (
                      <Text key={kind} style={styles.detailLine}>{label}: not uploaded</Text>
                    )
                  )}

                  <Text style={styles.detailLabel}>Subjects applied for:</Text>
                  {a.subjects.map((s, i) => (
                    <Text key={i} style={styles.detailLine}>
                      • {s.subject}: {s.matric_percentage.toFixed(0)}%
                      {s.hourly_rate_zar ? `, asking R${s.hourly_rate_zar}/hr` : ""}
                      {s.topics ? ` — topics: ${s.topics}` : ""}
                    </Text>
                  ))}

                  {a.status === "pending_review" && (
                    <>
                      <View style={styles.actionRow}>
                        <Pressable
                          style={styles.approveButton}
                          onPress={() => handleApprove(a.id)}
                          disabled={busyId === a.id}
                        >
                          {busyId === a.id ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.approveButtonText}>✅ Approve</Text>
                          )}
                        </Pressable>
                        <Pressable
                          style={styles.rejectButton}
                          onPress={() => setRejectingId(rejectingId === a.id ? null : a.id)}
                        >
                          <Text style={styles.rejectButtonText}>❌ Reject</Text>
                        </Pressable>
                      </View>
                      {rejectingId === a.id && (
                        <View style={styles.rejectBox}>
                          <TextInput
                            style={styles.input}
                            placeholder="Reason (optional)"
                            value={rejectReason}
                            onChangeText={setRejectReason}
                          />
                          <Pressable
                            style={styles.approveButton}
                            onPress={() => handleReject(a.id)}
                            disabled={busyId === a.id}
                          >
                            <Text style={styles.approveButtonText}>Confirm Reject</Text>
                          </Pressable>
                        </View>
                      )}
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

const HIGHER_ED_STATUS_OPTIONS: { label: string; value: TutorHigherEdApplication["higher_ed_status"] }[] = [
  { label: "Pending Review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Suspended", value: "suspended" },
];

function HigherEdApplicationsSection({ token }: { token: string }) {
  const [status, setStatus] = useState<TutorHigherEdApplication["higher_ed_status"]>("pending_review");
  const [apps, setApps] = useState<TutorHigherEdApplication[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [docUrls, setDocUrls] = useState<Record<string, string>>({});
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetchTutorHigherEdApplications(token, status)
      .then((res) => setApps(res.applications))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load applications."));
  }, [token, status]);

  useEffect(() => {
    setApps(null);
    load();
  }, [load]);

  async function handleApprove(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await approveTutorHigherEdApplication(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not approve.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await rejectTutorHigherEdApplication(token, id, rejectReason);
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reject.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleGetDocUrl(
    tutorId: number,
    kind: "id" | "cv" | "higher_ed_transcript" | "higher_ed_qualification_certificate"
  ) {
    try {
      const res = await fetchTutorDocumentUrl(token, tutorId, kind);
      setDocUrls((prev) => ({ ...prev, [`${tutorId}_${kind}`]: res.url }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not get document link.");
    }
  }

  return (
    <View>
      <Dropdown
        label="Status"
        options={HIGHER_ED_STATUS_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
        value={status}
        onChange={(v) => setStatus(v as TutorHigherEdApplication["higher_ed_status"])}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!apps ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : apps.length === 0 ? (
        <Text style={styles.empty}>No applications with this status.</Text>
      ) : (
        apps.map((a) => {
          const expanded = expandedId === a.id;
          return (
            <View key={a.id} style={styles.card}>
              <Pressable onPress={() => setExpandedId(expanded ? null : a.id)}>
                <Text style={styles.cardTitle}>
                  {a.name} — {a.email}
                </Text>
                <Text style={styles.cardSubtitle}>{a.higher_ed_status_label}</Text>
              </Pressable>
              {expanded && (
                <View style={styles.cardDetail}>
                  <Text style={styles.detailLine}>Phone: {a.phone || "—"}</Text>
                  <Text style={styles.detailLine}>Institution: {a.higher_ed_institution || "—"}</Text>
                  <Text style={styles.detailLine}>Qualification: {a.higher_ed_qualification || "—"}</Text>
                  <Text style={styles.detailLine}>Year of study: {a.higher_ed_year_of_study_label || "—"}</Text>
                  {a.higher_ed_qualification_complete ? (
                    <Text style={styles.detailLine}>Qualification already completed.</Text>
                  ) : null}
                  <Text style={styles.detailLine}>
                    Semester/final average: {a.higher_ed_average != null ? `${a.higher_ed_average}%` : "—"}
                  </Text>
                  <Text style={styles.detailLine}>Transcript note: {a.higher_ed_transcript_note || "—"}</Text>
                  <Text style={styles.detailLine}>Bio: {a.bio || "—"}</Text>
                  <Text style={styles.detailLine}>Availability: {a.availability_note || "—"}</Text>
                  <Text style={styles.detailLine}>Bank details: {a.bank_account_note || "—"}</Text>
                  {a.wants_high_school ? (
                    <Text style={styles.detailLine}>This tutor also applied for high-school tutoring.</Text>
                  ) : null}

                  {([
                    ["id", "ID document", a.has_id_document] as const,
                    ["cv", "CV", a.has_cv_document] as const,
                    ["higher_ed_transcript", "Academic transcript", a.has_higher_ed_transcript_document] as const,
                    [
                      "higher_ed_qualification_certificate",
                      "Qualification certificate",
                      a.has_higher_ed_qualification_certificate_document,
                    ] as const,
                  ]).map(([kind, label, hasDoc]) =>
                    hasDoc ? (
                      docUrls[`${a.id}_${kind}`] ? (
                        <Pressable
                          key={kind}
                          style={styles.docButton}
                          onPress={() => Linking.openURL(docUrls[`${a.id}_${kind}`])}
                        >
                          <Text style={styles.docButtonText}>Open {label}</Text>
                        </Pressable>
                      ) : (
                        <Pressable key={kind} style={styles.docButton} onPress={() => handleGetDocUrl(a.id, kind)}>
                          <Text style={styles.docButtonText}>🔗 Get {label} link</Text>
                        </Pressable>
                      )
                    ) : (
                      <Text key={kind} style={styles.detailLine}>{label}: not uploaded</Text>
                    )
                  )}

                  <Text style={styles.detailLabel}>Modules applied for:</Text>
                  {a.modules.map((m) => (
                    <Text key={m.id} style={styles.detailLine}>
                      • {m.name} ({m.year_level_label})
                    </Text>
                  ))}

                  {a.higher_ed_status === "pending_review" && (
                    <>
                      <View style={styles.actionRow}>
                        <Pressable
                          style={styles.approveButton}
                          onPress={() => handleApprove(a.id)}
                          disabled={busyId === a.id}
                        >
                          {busyId === a.id ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.approveButtonText}>✅ Approve</Text>
                          )}
                        </Pressable>
                        <Pressable
                          style={styles.rejectButton}
                          onPress={() => setRejectingId(rejectingId === a.id ? null : a.id)}
                        >
                          <Text style={styles.rejectButtonText}>❌ Reject</Text>
                        </Pressable>
                      </View>
                      {rejectingId === a.id && (
                        <View style={styles.rejectBox}>
                          <TextInput
                            style={styles.input}
                            placeholder="Reason (optional)"
                            value={rejectReason}
                            onChangeText={setRejectReason}
                          />
                          <Pressable
                            style={styles.approveButton}
                            onPress={() => handleReject(a.id)}
                            disabled={busyId === a.id}
                          >
                            <Text style={styles.approveButtonText}>Confirm Reject</Text>
                          </Pressable>
                        </View>
                      )}
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

function CatalogSection({ token }: { token: string }) {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newInstitutionName, setNewInstitutionName] = useState("");

  const [qualInstitutionId, setQualInstitutionId] = useState<number | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [newQualificationName, setNewQualificationName] = useState("");

  const [modInstitutionId, setModInstitutionId] = useState<number | null>(null);
  const [modQualifications, setModQualifications] = useState<Qualification[]>([]);
  const [modQualificationId, setModQualificationId] = useState<number | null>(null);
  const [modules, setModules] = useState<CatalogModule[]>([]);
  const [newModuleName, setNewModuleName] = useState("");
  const [newModuleYear, setNewModuleYear] = useState<number>(1);

  const loadInstitutions = useCallback(() => {
    fetchInstitutions()
      .then((res) => setInstitutions(res.institutions))
      .catch(() => setError("Could not load institutions."));
  }, []);

  useEffect(() => {
    loadInstitutions();
  }, [loadInstitutions]);

  useEffect(() => {
    if (!qualInstitutionId) {
      setQualifications([]);
      return;
    }
    fetchQualifications(qualInstitutionId)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => setError("Could not load qualifications."));
  }, [qualInstitutionId]);

  useEffect(() => {
    setModQualificationId(null);
    if (!modInstitutionId) {
      setModQualifications([]);
      return;
    }
    fetchQualifications(modInstitutionId)
      .then((res) => setModQualifications(res.qualifications))
      .catch(() => setError("Could not load qualifications."));
  }, [modInstitutionId]);

  useEffect(() => {
    if (!modQualificationId) {
      setModules([]);
      return;
    }
    fetchModules(modQualificationId)
      .then((res) => setModules(res.modules))
      .catch(() => setError("Could not load modules."));
  }, [modQualificationId]);

  async function handleAddInstitution() {
    setError(null);
    if (!newInstitutionName.trim()) {
      setError("Please enter an institution name.");
      return;
    }
    try {
      await addInstitutionAdmin(token, newInstitutionName.trim());
      setNewInstitutionName("");
      loadInstitutions();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add institution.");
    }
  }

  async function handleAddQualification() {
    setError(null);
    if (!qualInstitutionId) {
      setError("Please select an institution first.");
      return;
    }
    if (!newQualificationName.trim()) {
      setError("Please enter a qualification name.");
      return;
    }
    try {
      await addQualificationAdmin(token, qualInstitutionId, newQualificationName.trim());
      setNewQualificationName("");
      fetchQualifications(qualInstitutionId).then((res) => setQualifications(res.qualifications));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add qualification.");
    }
  }

  async function handleAddModule() {
    setError(null);
    if (!modQualificationId) {
      setError("Please select an institution and qualification first.");
      return;
    }
    if (!newModuleName.trim()) {
      setError("Please enter a module name.");
      return;
    }
    try {
      await addModuleAdmin(token, modQualificationId, newModuleName.trim(), newModuleYear);
      setNewModuleName("");
      fetchModules(modQualificationId).then((res) => setModules(res.modules));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add module.");
    }
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.sectionTitle}>Institutions</Text>
      {institutions.map((i) => (
        <Text key={i.id} style={styles.detailLine}>• {i.name}</Text>
      ))}
      <TextInput
        style={styles.input}
        placeholder="New institution name"
        value={newInstitutionName}
        onChangeText={setNewInstitutionName}
      />
      <Pressable style={styles.approveButton} onPress={handleAddInstitution}>
        <Text style={styles.approveButtonText}>Add Institution</Text>
      </Pressable>

      <Text style={[styles.sectionTitle, styles.catalogSectionSpacing]}>Qualifications</Text>
      <Dropdown
        label="Institution"
        options={institutions.map((i) => ({ label: i.name, value: String(i.id) }))}
        value={qualInstitutionId != null ? String(qualInstitutionId) : null}
        onChange={(v) => setQualInstitutionId(parseInt(v, 10))}
      />
      {qualifications.map((q) => (
        <Text key={q.id} style={styles.detailLine}>• {q.name}</Text>
      ))}
      {qualInstitutionId ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="New qualification name"
            value={newQualificationName}
            onChangeText={setNewQualificationName}
          />
          <Pressable style={styles.approveButton} onPress={handleAddQualification}>
            <Text style={styles.approveButtonText}>Add Qualification</Text>
          </Pressable>
        </>
      ) : null}

      <Text style={[styles.sectionTitle, styles.catalogSectionSpacing]}>Modules</Text>
      <Dropdown
        label="Institution"
        options={institutions.map((i) => ({ label: i.name, value: String(i.id) }))}
        value={modInstitutionId != null ? String(modInstitutionId) : null}
        onChange={(v) => setModInstitutionId(parseInt(v, 10))}
      />
      {modInstitutionId ? (
        <Dropdown
          label="Qualification"
          options={modQualifications.map((q) => ({ label: q.name, value: String(q.id) }))}
          value={modQualificationId != null ? String(modQualificationId) : null}
          onChange={(v) => setModQualificationId(parseInt(v, 10))}
        />
      ) : null}
      {modules.map((m) => (
        <Text key={m.id} style={styles.detailLine}>• {m.name} ({m.year_level_label})</Text>
      ))}
      {modQualificationId ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="New module name"
            value={newModuleName}
            onChangeText={setNewModuleName}
          />
          <Dropdown
            label="Year level"
            options={Object.entries(YEAR_LEVEL_LABELS).map(([k, v]) => ({ label: v, value: k }))}
            value={String(newModuleYear)}
            onChange={(v) => setNewModuleYear(parseInt(v, 10))}
          />
          <Pressable style={styles.approveButton} onPress={handleAddModule}>
            <Text style={styles.approveButtonText}>Add Module</Text>
          </Pressable>
        </>
      ) : null}
    </View>
  );
}

function MatchSection({ token }: { token: string }) {
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [candidatesBySubject, setCandidatesBySubject] = useState<Record<string, ApprovedTutor[]>>({});
  const [selectedTutor, setSelectedTutor] = useState<Record<number, number | null>>({});
  const [scheduledAt, setScheduledAt] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetchOpenTutoringRequestsAdmin(token)
      .then((res) => setRequests(res.requests))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load requests."));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function expandRequest(r: TutoringRequest) {
    const nowExpanded = expandedId === r.id ? null : r.id;
    setExpandedId(nowExpanded);
    if (nowExpanded !== null && !candidatesBySubject[r.subject]) {
      try {
        const res = await fetchApprovedTutors(token, r.subject);
        setCandidatesBySubject((prev) => ({ ...prev, [r.subject]: res.tutors }));
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not load tutors.");
      }
    }
  }

  async function handleMatch(r: TutoringRequest) {
    const tutorId = selectedTutor[r.id];
    if (!tutorId) {
      setError("Please choose a tutor.");
      return;
    }
    let scheduled_at: string | null = null;
    const raw = (scheduledAt[r.id] || "").trim();
    if (raw) {
      // A strict 4-digit-year format check, not just "did Date() accept
      // it" - Hermes (React Native's JS engine) parses malformed strings
      // like a mistyped 5-digit year far more leniently than Node/Chrome
      // do, so isNaN(parsed.getTime()) alone let a typo ("20126-...")
      // through as a "valid" but nonsensical date that then crashed the
      // backend (datetime.fromisoformat can't parse what toISOString()
      // produces for a year that far out).
      const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(raw);
      if (!match) {
        setError("Scheduled date/time must look like 2026-11-20 18:00 (SAST)");
        return;
      }
      // Entered as SAST (fixed UTC+2), same as SessionDateTimePicker - NOT
      // new Date(string).toISOString(), which would parse this as the
      // ADMIN'S OWN DEVICE timezone and silently shift it by however many
      // hours that differs from SAST.
      const [, y, mo, d, h, mi] = match.map(Number);
      const utcMillis = Date.UTC(y, mo - 1, d, h - 2, mi, 0);
      if (isNaN(utcMillis)) {
        setError("Scheduled date/time must look like 2026-11-20 18:00 (SAST)");
        return;
      }
      scheduled_at = new Date(utcMillis).toISOString();
    }
    setBusyId(r.id);
    setError(null);
    try {
      await matchTutorToRequestAdmin(token, r.id, { tutor_id: tutorId, scheduled_at });
      Alert.alert(
        "Suggested!",
        "The tutor needs to confirm in their app before anything is booked - nothing is final yet."
      );
      setExpandedId(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not match tutor.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!requests ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : requests.length === 0 ? (
        <Text style={styles.empty}>No open requests right now (tutors can accept these directly in their app).</Text>
      ) : (
        requests.map((r) => {
          const expanded = expandedId === r.id;
          const candidates = candidatesBySubject[r.subject] || [];
          return (
            <View key={r.id} style={styles.card}>
              <Pressable onPress={() => expandRequest(r)}>
                <Text style={styles.cardTitle}>
                  #{r.id} — {r.subject}
                  {r.topic ? ` (${r.topic})` : ""} — R{r.price_zar} ({r.duration_minutes} min)
                </Text>
                {r.scheduled_at ? (
                  <Text style={styles.cardSubtitle}>
                    Requested: {new Date(r.scheduled_at).toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg" })}
                  </Text>
                ) : null}
                {r.preferred_times_note ? (
                  <Text style={styles.cardSubtitle}>{r.preferred_times_note}</Text>
                ) : null}
              </Pressable>
              {expanded && (
                <View style={styles.cardDetail}>
                  {candidates.length === 0 ? (
                    <Text style={styles.detailLine}>No approved tutors for {r.subject} yet.</Text>
                  ) : (
                    <>
                      <Dropdown
                        label="Tutor"
                        options={candidates.map((t) => ({
                          label: `${t.name} (${t.email}) — ${t.sessions_completed} completed`,
                          value: String(t.id),
                        }))}
                        value={selectedTutor[r.id] != null ? String(selectedTutor[r.id]) : null}
                        onChange={(v) => setSelectedTutor((prev) => ({ ...prev, [r.id]: parseInt(v, 10) }))}
                      />
                      <Text style={styles.label}>Propose a different date/time (optional, SAST)</Text>
                      <TextInput
                        style={styles.input}
                        value={scheduledAt[r.id] || ""}
                        onChangeText={(v) => setScheduledAt((prev) => ({ ...prev, [r.id]: v }))}
                        placeholder="e.g. 2026-11-20 18:00"
                      />
                      <Pressable
                        style={styles.approveButton}
                        onPress={() => handleMatch(r)}
                        disabled={busyId === r.id}
                      >
                        {busyId === r.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.approveButtonText}>Suggest This Tutor</Text>
                        )}
                      </Pressable>
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

// Approved tutors' standing record - subjects plus full session history,
// so an admin can review a tutor's track record before re-matching them
// to a new request. An approved tutor's record never goes away, the
// same way you'd keep recalling a reliable employee for new work.
function TutorsSection({ token }: { token: string }) {
  const [tutors, setTutors] = useState<ApprovedTutor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [profiles, setProfiles] = useState<Record<number, TutorProfile>>({});

  const load = useCallback(() => {
    fetchApprovedTutors(token)
      .then((res) => setTutors(res.tutors))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load tutors."));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function expandTutor(t: ApprovedTutor) {
    const nowExpanded = expandedId === t.id ? null : t.id;
    setExpandedId(nowExpanded);
    if (nowExpanded !== null && !profiles[t.id]) {
      try {
        const profile = await fetchTutorProfile(token, t.id);
        setProfiles((prev) => ({ ...prev, [t.id]: profile }));
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not load tutor profile.");
      }
    }
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!tutors ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : tutors.length === 0 ? (
        <Text style={styles.empty}>No approved tutors yet.</Text>
      ) : (
        tutors.map((t) => {
          const expanded = expandedId === t.id;
          const profile = profiles[t.id];
          return (
            <View key={t.id} style={styles.card}>
              <Pressable onPress={() => expandTutor(t)}>
                <Text style={styles.cardTitle}>
                  {t.name} — {t.sessions_completed} completed session(s)
                </Text>
                <Text style={styles.cardSubtitle}>{t.email}</Text>
              </Pressable>
              {expanded && (
                <View style={styles.cardDetail}>
                  {!profile ? (
                    <ActivityIndicator color={colors.primary} />
                  ) : (
                    <>
                      <Text style={styles.detailLine}>Phone: {profile.phone || "—"}</Text>
                      <Text style={styles.detailLine}>Bio: {profile.bio || "—"}</Text>
                      <Text style={styles.detailLine}>Availability: {profile.availability_note || "—"}</Text>
                      <Text style={styles.detailLabel}>Subjects:</Text>
                      {profile.subjects.map((s, i) => (
                        <Text key={i} style={styles.detailLine}>
                          • {s.subject}: {s.matric_percentage.toFixed(0)}% matric
                          {s.hourly_rate_zar ? `, R${s.hourly_rate_zar}/hr` : ""}
                        </Text>
                      ))}
                      <Text style={styles.detailLabel}>Session history:</Text>
                      {profile.sessions.length === 0 ? (
                        <Text style={styles.detailLine}>No sessions yet.</Text>
                      ) : (
                        profile.sessions.map((sess) => {
                          const when = sess.scheduled_at || sess.created_at;
                          const whenStr = when
                            ? new Date(when).toLocaleDateString("en-ZA", { timeZone: "Africa/Johannesburg" })
                            : "—";
                          return (
                            <Text key={sess.id} style={styles.detailLine}>
                              • {sess.subject}
                              {sess.topic ? ` (${sess.topic})` : ""} — {sess.status_label} — {whenStr}
                            </Text>
                          );
                        })
                      )}
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

function PayoutsSection({ token }: { token: string }) {
  const [payouts, setPayouts] = useState<TutoringPayout[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refByPayout, setRefByPayout] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetchPendingPayoutsAdmin(token)
      .then((res) => setPayouts(res.payouts))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load payouts."));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleMarkPaid(p: TutoringPayout) {
    setBusyId(p.id);
    setError(null);
    try {
      await markPayoutPaidAdmin(token, p.id, refByPayout[p.id] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not mark as paid.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!payouts ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : payouts.length === 0 ? (
        <Text style={styles.empty}>No pending payouts.</Text>
      ) : (
        payouts.map((p) => (
          <View key={p.id} style={styles.card}>
            <Text style={styles.cardTitle}>
              Session #{p.session_id} — {p.tutor_name}
            </Text>
            <Text style={styles.cardSubtitle}>R{p.amount_zar.toFixed(2)}</Text>
            <Text style={styles.detailLine}>Bank details: {p.tutor_bank_note || "— (not provided)"}</Text>
            <TextInput
              style={styles.input}
              placeholder="Payment reference (e.g. EFT ref)"
              value={refByPayout[p.id] || ""}
              onChangeText={(v) => setRefByPayout((prev) => ({ ...prev, [p.id]: v }))}
            />
            <Pressable style={styles.approveButton} onPress={() => handleMarkPaid(p)} disabled={busyId === p.id}>
              {busyId === p.id ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.approveButtonText}>Mark as Paid</Text>
              )}
            </Pressable>
          </View>
        ))
      )}
    </View>
  );
}

function SessionsSection({ token }: { token: string }) {
  const [filter, setFilter] = useState<"upcoming" | "completed" | "all">("upcoming");
  const [sessions, setSessions] = useState<AdminTutoringSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setSessions(null);
    fetchAllTutoringSessionsAdmin(token, filter)
      .then((res) => setSessions(res.sessions))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load sessions."));
  }, [token, filter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View>
      <View style={styles.sectionRow}>
        {(["upcoming", "completed", "all"] as const).map((f) => (
          <Pressable
            key={f}
            style={[styles.sectionChip, filter === f && styles.sectionChipActive]}
            onPress={() => setFilter(f)}
          >
            <Text style={[styles.sectionChipText, filter === f && styles.sectionChipTextActive]}>
              {f === "upcoming" ? "Upcoming" : f === "completed" ? "Completed" : "All"}
            </Text>
          </Pressable>
        ))}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!sessions ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : sessions.length === 0 ? (
        <Text style={styles.empty}>No sessions to show.</Text>
      ) : (
        sessions.map((s) => (
          <View key={s.id} style={styles.card}>
            <Text style={styles.cardTitle}>
              {s.subject}
              {s.topic ? ` (${s.topic})` : ""} — {s.status_label}
            </Text>
            <Text style={styles.cardSubtitle}>Learner: {s.learner_name} ({s.learner_email})</Text>
            <Text style={styles.cardSubtitle}>Tutor: {s.tutor_name} ({s.tutor_email})</Text>
            <Text style={styles.detailLine}>
              {s.scheduled_at
                ? new Date(s.scheduled_at).toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg" })
                : "—"}
              {s.duration_minutes ? ` · ${s.duration_minutes} min` : ""}
            </Text>
            {s.price_zar != null ? (
              <Text style={styles.detailLine}>
                R{s.price_zar.toFixed(2)}
                {s.platform_cut_percent != null ? ` · Malita's cut: ${s.platform_cut_percent.toFixed(0)}%` : ""}
              </Text>
            ) : null}
            {s.meet_link ? (
              <Pressable onPress={() => Linking.openURL(s.meet_link!)}>
                <Text style={styles.cardLink}>🎥 Open Google Meet link</Text>
              </Pressable>
            ) : null}
            {s.recording_link ? (
              <Pressable onPress={() => Linking.openURL(s.recording_link!)}>
                <Text style={styles.cardLink}>🎬 Open session recording</Text>
              </Pressable>
            ) : null}
            {s.learner_rating != null ? (
              <Text style={styles.detailLine}>Learner rated: {s.learner_rating}/5</Text>
            ) : null}
            {s.tutor_rating != null ? (
              <Text style={styles.detailLine}>Tutor rated: {s.tutor_rating}/5</Text>
            ) : null}
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingBottom: 40, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4, marginBottom: 12 },
  connectCalendarButton: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    marginBottom: 16,
  },
  connectCalendarButtonText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
  sectionRow: { flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: 16 },
  sectionChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  sectionChipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  sectionChipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  sectionChipTextActive: { color: "#fff" },
  error: { color: colors.error, marginTop: 10, marginBottom: 6 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 16 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  cardSubtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  cardDetail: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  detailLine: { fontSize: 13, color: colors.text, marginTop: 4 },
  cardLink: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 8 },
  sectionTitle: { fontSize: 15, fontWeight: "700", color: colors.text, marginBottom: 8 },
  catalogSectionSpacing: { marginTop: 20 },
  detailLabel: { fontSize: 13, fontWeight: "700", color: colors.text, marginTop: 10 },
  docButton: { marginTop: 8, alignSelf: "flex-start" },
  docButtonText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 12, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.text,
    backgroundColor: "#fff",
    marginBottom: 8,
  },
  actionRow: { flexDirection: "row", gap: 10, marginTop: 14 },
  approveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 6,
    paddingHorizontal: 16,
    flexGrow: 1,
  },
  approveButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  rejectButton: {
    borderWidth: 1,
    borderColor: colors.error,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  rejectButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  rejectBox: { marginTop: 10 },
});
