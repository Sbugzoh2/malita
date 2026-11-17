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
  fetchRequestsNeedingAttention,
  suggestRefundAdmin,
  markRefundProcessingAdmin,
  markRefundProcessedAdmin,
  TutoringPayout,
  fetchPendingPayoutsAdmin,
  markPayoutPaidAdmin,
  PayoutsSummary,
  fetchPayoutsSummaryAdmin,
  settleAllPayoutsAdmin,
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
  seedDefaultCatalog,
  deleteInstitutionAdmin,
  deleteQualificationAdmin,
  deleteModuleAdmin,
  YEAR_LEVEL_LABELS,
  API_BASE_URL,
  AdminAccountSummary,
  fetchAdminAccounts,
  suspendAccountAdmin,
  blockAccountAdmin,
  reinstateAccountAdmin,
  AdminTutorAccountSummary,
  fetchAdminTutorAccounts,
  suspendTutorAccountAdmin,
  blockTutorAccountAdmin,
  reinstateTutorAccountAdmin,
  SupportTicketSummary,
  SupportTicket,
  fetchAdminSupportTickets,
  fetchAdminSupportTicket,
  replyToSupportTicketAdmin,
  resolveSupportTicketAdmin,
  reopenSupportTicketAdmin,
} from "../api/client";
import Dropdown from "../components/Dropdown";
import GradientBackground from "../components/GradientBackground";

type Section =
  | "applications" | "higherEdApplications" | "catalog" | "match" | "refunds" | "sessions" | "tutors" | "payouts"
  | "accounts" | "support";

// Shared by ApplicationsSection/HigherEdApplicationsSection/PayoutsSection
// below - falls back to the free-text note for a tutor who applied before
// the structured bank fields existed (see backend/db.py's TutorAccount).
function formatBankDetails(opts: {
  holder: string | null; bank: string | null; branchCode: string | null;
  accountNumber: string | null; accountType: string | null; note: string | null;
}): string {
  const parts: string[] = [];
  if (opts.holder) parts.push(opts.holder);
  if (opts.bank) parts.push(opts.bank);
  if (opts.accountNumber) parts.push(`Acc: ${opts.accountNumber}`);
  if (opts.branchCode) parts.push(`Branch: ${opts.branchCode}`);
  if (opts.accountType) parts.push(opts.accountType);
  if (parts.length === 0) return opts.note || "— (not provided)";
  const line = parts.join(" · ");
  return opts.note ? `${line} (${opts.note})` : line;
}

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
    <GradientBackground>
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
          { key: "refunds", label: "Needs Attention" },
          { key: "sessions", label: "All Sessions" },
          { key: "tutors", label: "Tutors" },
          { key: "payouts", label: "Payouts" },
          { key: "accounts", label: "Accounts" },
          { key: "support", label: "Support" },
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
      {token && section === "refunds" && <RefundsSection token={token} />}
      {token && section === "sessions" && <SessionsSection token={token} />}
      {token && section === "tutors" && <TutorsSection token={token} />}
      {token && section === "payouts" && <PayoutsSection token={token} />}
      {token && section === "accounts" && <AccountsSection token={token} />}
      {token && section === "support" && <SupportSection token={token} />}
    </ScrollView>
    </GradientBackground>
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
                  <Text style={styles.detailLine}>
                    Bank details: {formatBankDetails({
                      holder: a.bank_account_holder, bank: a.bank_name, branchCode: a.bank_branch_code,
                      accountNumber: a.bank_account_number, accountType: a.bank_account_type, note: a.bank_account_note,
                    })}
                  </Text>

                  {([
                    ["id", "ID document", a.has_id_document] as const,
                    ["matric_certificate", "Matric certificate", a.has_matric_certificate_document] as const,
                    ["cv", "CV", a.has_cv_document] as const,
                    ["bank_proof", "Bank proof", a.has_bank_proof_document] as const,
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
                            placeholderTextColor={colors.inputPlaceholder}
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
                  <Text style={styles.detailLine}>
                    Bank details: {formatBankDetails({
                      holder: a.bank_account_holder, bank: a.bank_name, branchCode: a.bank_branch_code,
                      accountNumber: a.bank_account_number, accountType: a.bank_account_type, note: a.bank_account_note,
                    })}
                  </Text>
                  {a.wants_high_school ? (
                    <Text style={styles.detailLine}>This tutor also applied for high-school tutoring.</Text>
                  ) : null}

                  {([
                    ["id", "ID document", a.has_id_document] as const,
                    ["cv", "CV", a.has_cv_document] as const,
                    ["bank_proof", "Bank proof", a.has_bank_proof_document] as const,
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
                            placeholderTextColor={colors.inputPlaceholder}
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
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<string | null>(null);

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

  async function handleSeedDefaultCatalog() {
    setError(null);
    setSeedResult(null);
    setSeeding(true);
    try {
      const res = await seedDefaultCatalog(token);
      setSeedResult(
        `Added ${res.created.institutions} institution(s), ${res.created.qualifications} qualification(s), ` +
          `${res.created.modules} module(s). Already there: ${res.skipped.institutions} institution(s), ` +
          `${res.skipped.qualifications} qualification(s), ${res.skipped.modules} module(s).`
      );
      loadInstitutions();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not seed the default catalog.");
    } finally {
      setSeeding(false);
    }
  }

  function confirmSeedDefaultCatalog() {
    Alert.alert(
      "Seed starter catalog?",
      "Adds South Africa's 26 public universities with a generic BSc/BCom/BA/BEd " +
        "(+ BEng/BEngTech where applicable) qualification and module set, plus an " +
        "Honours/Master's/PhD track for each, AND its public TVET colleges with just " +
        "the NCV's standard fundamental subjects - a starting point to edit/extend, " +
        "not each institution's actual official curriculum (and the TVET college " +
        "names are lower-confidence than the universities - double-check these). " +
        "Safe to run again later; existing entries are never duplicated.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Seed It", onPress: handleSeedDefaultCatalog },
      ]
    );
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

  function confirmDeleteInstitution(id: number, name: string) {
    Alert.alert(
      `Delete "${name}"?`,
      "This also removes every qualification and module under it. Blocked if a tutor or " +
        "tutoring request still references one of those modules.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setError(null);
            try {
              await deleteInstitutionAdmin(token, id);
              if (qualInstitutionId === id) setQualInstitutionId(null);
              if (modInstitutionId === id) setModInstitutionId(null);
              loadInstitutions();
            } catch (e) {
              setError(e instanceof ApiError ? e.message : "Could not delete institution.");
            }
          },
        },
      ]
    );
  }

  function confirmDeleteQualification(id: number, name: string) {
    Alert.alert(
      `Delete "${name}"?`,
      "This also removes every module under it. Blocked if a tutor or tutoring request " +
        "still references one of those modules.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setError(null);
            try {
              await deleteQualificationAdmin(token, id);
              if (qualInstitutionId) fetchQualifications(qualInstitutionId).then((res) => setQualifications(res.qualifications));
              if (modQualificationId === id) setModQualificationId(null);
              if (modInstitutionId) fetchQualifications(modInstitutionId).then((res) => setModQualifications(res.qualifications));
            } catch (e) {
              setError(e instanceof ApiError ? e.message : "Could not delete qualification.");
            }
          },
        },
      ]
    );
  }

  function confirmDeleteModule(id: number, name: string) {
    Alert.alert(
      `Delete "${name}"?`,
      "Blocked if a tutor or tutoring request still references it.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setError(null);
            try {
              await deleteModuleAdmin(token, id);
              if (modQualificationId) fetchModules(modQualificationId).then((res) => setModules(res.modules));
            } catch (e) {
              setError(e instanceof ApiError ? e.message : "Could not delete module.");
            }
          },
        },
      ]
    );
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Pressable
        style={[styles.seedButton, seeding && styles.buttonDisabled]}
        onPress={confirmSeedDefaultCatalog}
        disabled={seeding}
      >
        {seeding ? (
          <ActivityIndicator color={colors.primary} />
        ) : (
          <Text style={styles.seedButtonText}>🌱 Seed SA Universities (starter catalog)</Text>
        )}
      </Pressable>
      {seedResult ? <Text style={styles.seedResultText}>{seedResult}</Text> : null}

      <Text style={styles.sectionTitle}>Institutions</Text>
      {institutions.map((i) => (
        <View key={i.id} style={styles.catalogRow}>
          <Text style={styles.catalogRowText}>• {i.name}</Text>
          <Pressable onPress={() => confirmDeleteInstitution(i.id, i.name)} hitSlop={8}>
            <Text style={styles.deleteIcon}>🗑</Text>
          </Pressable>
        </View>
      ))}
      <TextInput
        style={styles.input}
        placeholder="New institution name"
        placeholderTextColor={colors.inputPlaceholder}
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
        <View key={q.id} style={styles.catalogRow}>
          <Text style={styles.catalogRowText}>• {q.name}</Text>
          <Pressable onPress={() => confirmDeleteQualification(q.id, q.name)} hitSlop={8}>
            <Text style={styles.deleteIcon}>🗑</Text>
          </Pressable>
        </View>
      ))}
      {qualInstitutionId ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="New qualification name"
            placeholderTextColor={colors.inputPlaceholder}
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
        <View key={m.id} style={styles.catalogRow}>
          <Text style={styles.catalogRowText}>• {m.name} ({m.year_level_label})</Text>
          <Pressable onPress={() => confirmDeleteModule(m.id, m.name)} hitSlop={8}>
            <Text style={styles.deleteIcon}>🗑</Text>
          </Pressable>
        </View>
      ))}
      {modQualificationId ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="New module name"
            placeholderTextColor={colors.inputPlaceholder}
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
  // Every approved tutor, regardless of subject/module - an admin can
  // manually match any request to any tutor (e.g. assign a Physical
  // Sciences request to a Mathematics tutor), same reasoning as
  // match_tutor_to_request's own lack of a subject check server-side.
  const [candidates, setCandidates] = useState<ApprovedTutor[] | null>(null);
  const [selectedTutor, setSelectedTutor] = useState<Record<number, number | null>>({});
  const [adminNote, setAdminNote] = useState<Record<number, string>>({});
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
    if (nowExpanded !== null && candidates === null) {
      try {
        const res = await fetchApprovedTutors(token);
        setCandidates(res.tutors);
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
    setBusyId(r.id);
    setError(null);
    try {
      await matchTutorToRequestAdmin(token, r.id, { tutor_id: tutorId, admin_note: adminNote[r.id] || "" });
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
          const requestCandidates = candidates || [];
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
                  {requestCandidates.length === 0 ? (
                    <Text style={styles.detailLine}>No approved tutors yet.</Text>
                  ) : (
                    <>
                      <Dropdown
                        label="Tutor"
                        options={requestCandidates.map((t) => ({
                          label: `${t.name} (${t.email}) — ${t.sessions_completed} completed`,
                          value: String(t.id),
                        }))}
                        value={selectedTutor[r.id] != null ? String(selectedTutor[r.id]) : null}
                        onChange={(v) => setSelectedTutor((prev) => ({ ...prev, [r.id]: parseInt(v, 10) }))}
                      />
                      <Text style={styles.label}>Note to tutor (optional)</Text>
                      <TextInput
                        style={[styles.input, styles.textArea]}
                        value={adminNote[r.id] || ""}
                        onChangeText={(v) => setAdminNote((prev) => ({ ...prev, [r.id]: v }))}
                        placeholder="e.g. why you picked them, anything the learner mentioned"
                        placeholderTextColor={colors.inputPlaceholder}
                        multiline
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

// Two situations real money is sitting in limbo on and nobody reviewing
// the console on a fixed schedule would otherwise notice (see backend/
// tutoring.py's list_requests_needing_attention): a paid session a tutor
// just cancelled, where the learner hasn't yet chosen re-allocation vs. a
// refund, and a refund the learner HAS chosen/requested that no admin has
// marked processed yet. Previously the app only ever notified admins of
// these by email/push - there was no button anywhere to actually act on
// one in the console itself.
function RefundsSection({ token }: { token: string }) {
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetchRequestsNeedingAttention(token)
      .then((res) => setRequests(res.requests))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load this list."));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSuggestRefund(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await suggestRefundAdmin(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not suggest a refund.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleMarkProcessing(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await markRefundProcessingAdmin(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not mark this refund as processing.");
    } finally {
      setBusyId(null);
    }
  }

  function confirmMarkProcessed(id: number) {
    Alert.alert(
      "Mark this refund as processed?",
      "Only do this once you've actually sent the learner their money back (bank transfer/PayFast console) - this tells them it's done.",
      [
        { text: "Not yet", style: "cancel" },
        { text: "Mark Processed", onPress: () => handleMarkProcessed(id) },
      ]
    );
  }

  async function handleMarkProcessed(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await markRefundProcessedAdmin(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not mark this refund as processed.");
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
        <Text style={styles.empty}>Nothing needs attention right now.</Text>
      ) : (
        requests.map((r) => (
          <View key={r.id} style={styles.card}>
            <Text style={styles.cardTitle}>
              Request #{r.id} — {r.subject}{r.topic ? ` (${r.topic})` : ""}
            </Text>
            <Text style={styles.cardSubtitle}>Learner: {r.learner_name ?? "—"}</Text>
            {r.price_zar != null ? (
              <Text style={styles.detailLine}>R{r.price_zar.toFixed(2)}</Text>
            ) : null}
            {r.scheduled_at ? (
              <Text style={styles.detailLine}>
                Scheduled: {new Date(r.scheduled_at).toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg" })}
              </Text>
            ) : null}

            {r.status === "tutor_cancelled" ? (
              <>
                <Text style={styles.detailLine}>
                  Tutor cancelled this paid session - the learner hasn't yet chosen between re-allocation and a
                  refund.
                </Text>
                <Pressable
                  style={styles.approveButton}
                  onPress={() => handleSuggestRefund(r.id)}
                  disabled={busyId === r.id}
                >
                  {busyId === r.id ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.approveButtonText}>Suggest a Refund to the Learner</Text>
                  )}
                </Pressable>
              </>
            ) : (
              <>
                <Text style={styles.detailLine}>
                  {r.refund_processing_at
                    ? "Processing - the learner has been told to expect it within 5-7 working days."
                    : "Refund requested - not yet started."}
                </Text>
                <View style={styles.actionRow}>
                  {!r.refund_processing_at && (
                    <Pressable
                      style={[styles.approveButton, { flex: 1 }]}
                      onPress={() => handleMarkProcessing(r.id)}
                      disabled={busyId === r.id}
                    >
                      {busyId === r.id ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <Text style={styles.approveButtonText}>Mark as Processing</Text>
                      )}
                    </Pressable>
                  )}
                  <Pressable
                    style={[styles.approveButton, { flex: 1 }]}
                    onPress={() => confirmMarkProcessed(r.id)}
                    disabled={busyId === r.id}
                  >
                    {busyId === r.id ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.approveButtonText}>Mark Refund Processed</Text>
                    )}
                  </Pressable>
                </View>
              </>
            )}
          </View>
        ))
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
  const [standingReason, setStandingReason] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

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

  async function refreshProfile(tutorId: number) {
    const profile = await fetchTutorProfile(token, tutorId);
    setProfiles((prev) => ({ ...prev, [tutorId]: profile }));
  }

  async function handleSuspendTutor(tutorId: number) {
    setBusyId(tutorId);
    setError(null);
    try {
      await suspendTutorAccountAdmin(token, tutorId, standingReason[tutorId] || "");
      await refreshProfile(tutorId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not suspend this tutor.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleBlockTutor(tutorId: number) {
    setBusyId(tutorId);
    setError(null);
    try {
      await blockTutorAccountAdmin(token, tutorId, standingReason[tutorId] || "");
      await refreshProfile(tutorId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not block this tutor.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReinstateTutor(tutorId: number) {
    setBusyId(tutorId);
    setError(null);
    try {
      await reinstateTutorAccountAdmin(token, tutorId);
      await refreshProfile(tutorId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reinstate this tutor.");
    } finally {
      setBusyId(null);
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

                      <View style={styles.standingBox}>
                        <Text style={styles.detailLabel}>
                          Account standing: {profile.account_status_label}
                          {profile.account_status_reason ? ` — ${profile.account_status_reason}` : ""}
                        </Text>
                        {profile.account_status === "active" ? (
                          <>
                            <TextInput
                              style={styles.input}
                              placeholder="Reason (e.g. pending investigation)"
                              placeholderTextColor={colors.inputPlaceholder}
                              value={standingReason[t.id] || ""}
                              onChangeText={(v) => setStandingReason((prev) => ({ ...prev, [t.id]: v }))}
                            />
                            <View style={styles.standingButtonRow}>
                              <Pressable
                                style={[styles.smallButton, styles.suspendButton]}
                                onPress={() => handleSuspendTutor(t.id)}
                                disabled={busyId === t.id}
                              >
                                <Text style={styles.smallButtonText}>Suspend</Text>
                              </Pressable>
                              <Pressable
                                style={[styles.smallButton, styles.blockButton]}
                                onPress={() => handleBlockTutor(t.id)}
                                disabled={busyId === t.id}
                              >
                                <Text style={styles.smallButtonText}>Block</Text>
                              </Pressable>
                            </View>
                          </>
                        ) : (
                          <Pressable
                            style={[styles.smallButton, styles.reinstateButton]}
                            onPress={() => handleReinstateTutor(t.id)}
                            disabled={busyId === t.id}
                          >
                            <Text style={styles.smallButtonText}>
                              {profile.account_status === "blocked" ? "Unblock" : "Unsuspend"}
                            </Text>
                          </Pressable>
                        )}
                      </View>
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

// Learner account management (suspend/block/reinstate) - there was NO
// admin view at all for learner accounts before this (every other admin
// screen is tutoring-marketplace-specific). Tutor accounts get the same
// three actions inside TutorsSection above, next to their own profile.
const ACCOUNT_STATUS_COLOR: Record<string, string> = {
  active: colors.success, suspended: colors.textSecondary, blocked: colors.error,
};

function AccountsSection({ token }: { token: string }) {
  const [kind, setKind] = useState<"user" | "tutor">("user");
  const [search, setSearch] = useState("");
  const [accounts, setAccounts] = useState<AdminAccountSummary[] | null>(null);
  const [tutorAccounts, setTutorAccounts] = useState<AdminTutorAccountSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reasonDraft, setReasonDraft] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    if (kind === "user") {
      fetchAdminAccounts(token, search)
        .then((res) => setAccounts(res.users))
        .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load accounts."));
    } else {
      fetchAdminTutorAccounts(token, search)
        .then((res) => setTutorAccounts(res.tutors))
        .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load tutor accounts."));
    }
  }, [token, search, kind]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSuspend(id: number) {
    setBusyId(id);
    setError(null);
    try {
      if (kind === "user") await suspendAccountAdmin(token, id, reasonDraft[id] || "");
      else await suspendTutorAccountAdmin(token, id, reasonDraft[id] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not suspend this account.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleBlock(id: number) {
    setBusyId(id);
    setError(null);
    try {
      if (kind === "user") await blockAccountAdmin(token, id, reasonDraft[id] || "");
      else await blockTutorAccountAdmin(token, id, reasonDraft[id] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not block this account.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReinstate(id: number) {
    setBusyId(id);
    setError(null);
    try {
      if (kind === "user") await reinstateAccountAdmin(token, id);
      else await reinstateTutorAccountAdmin(token, id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reinstate this account.");
    } finally {
      setBusyId(null);
    }
  }

  // Normalize both AdminAccountSummary (learner) and AdminTutorAccountSummary
  // (tutor) to the same shape, so the list below renders either one with
  // one chunk of markup instead of two near-duplicate branches.
  const rows = (kind === "user" ? accounts : tutorAccounts)?.map((a) => ({
    id: a.id,
    name: a.name,
    email: a.email,
    account_status: a.account_status,
    account_status_label: a.account_status_label,
    account_status_reason: a.account_status_reason,
    isAdmin: kind === "user" ? (a as AdminAccountSummary).is_admin : false,
  })) ?? null;

  return (
    <View>
      <View style={styles.sectionRow}>
        {([{ key: "user" as const, label: "Learners" }, { key: "tutor" as const, label: "Tutors" }]).map((k) => (
          <Pressable
            key={k.key}
            style={[styles.sectionChip, kind === k.key && styles.sectionChipActive]}
            onPress={() => {
              setAccounts(null);
              setTutorAccounts(null);
              setKind(k.key);
            }}
          >
            <Text style={[styles.sectionChipText, kind === k.key && styles.sectionChipTextActive]}>{k.label}</Text>
          </Pressable>
        ))}
      </View>
      <TextInput
        style={styles.searchInput}
        placeholder="Search by name or email..."
        placeholderTextColor={colors.inputPlaceholder}
        value={search}
        onChangeText={setSearch}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : rows.length === 0 ? (
        <Text style={styles.empty}>No accounts found.</Text>
      ) : (
        rows.map((a) => (
          <View key={a.id} style={styles.card}>
            <Text style={styles.cardTitle}>{a.name}</Text>
            <Text style={styles.cardSubtitle}>{a.email}</Text>
            <View style={[styles.accountStatusPill, { backgroundColor: ACCOUNT_STATUS_COLOR[a.account_status] }]}>
              <Text style={styles.accountStatusPillText}>{a.account_status_label}</Text>
            </View>
            {a.account_status_reason ? (
              <Text style={styles.detailLine}>Reason: {a.account_status_reason}</Text>
            ) : null}
            {a.isAdmin ? (
              <Text style={styles.detailLine}>Admin accounts can't be suspended or blocked here.</Text>
            ) : a.account_status === "active" ? (
              <View style={styles.standingBox}>
                <TextInput
                  style={styles.input}
                  placeholder="Reason (e.g. pending investigation)"
                  placeholderTextColor={colors.inputPlaceholder}
                  value={reasonDraft[a.id] || ""}
                  onChangeText={(v) => setReasonDraft((prev) => ({ ...prev, [a.id]: v }))}
                />
                <View style={styles.standingButtonRow}>
                  <Pressable
                    style={[styles.smallButton, styles.suspendButton]}
                    onPress={() => handleSuspend(a.id)}
                    disabled={busyId === a.id}
                  >
                    <Text style={styles.smallButtonText}>Suspend</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.smallButton, styles.blockButton]}
                    onPress={() => handleBlock(a.id)}
                    disabled={busyId === a.id}
                  >
                    <Text style={styles.smallButtonText}>Block</Text>
                  </Pressable>
                </View>
              </View>
            ) : (
              <Pressable
                style={[styles.smallButton, styles.reinstateButton]}
                onPress={() => handleReinstate(a.id)}
                disabled={busyId === a.id}
              >
                <Text style={styles.smallButtonText}>{a.account_status === "blocked" ? "Unblock" : "Unsuspend"}</Text>
              </Pressable>
            )}
          </View>
        ))
      )}
    </View>
  );
}

// The admin's "contact admin" queue (see backend/support.py) - a real
// back-and-forth thread per ticket, not a one-shot message.
function SupportSection({ token }: { token: string }) {
  const [statusFilter, setStatusFilter] = useState<"open" | "resolved" | undefined>("open");
  const [tickets, setTickets] = useState<SupportTicketSummary[] | null>(null);
  const [thread, setThread] = useState<SupportTicket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(() => {
    fetchAdminSupportTickets(token, statusFilter)
      .then((res) => setTickets(res.tickets))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load support tickets."));
  }, [token, statusFilter]);

  useEffect(() => {
    if (!thread) loadList();
  }, [loadList, thread]);

  async function openTicket(ticketId: number) {
    setError(null);
    try {
      const t = await fetchAdminSupportTicket(token, ticketId);
      setThread(t);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this ticket.");
    }
  }

  async function handleReply() {
    if (!thread || !reply.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const t = await replyToSupportTicketAdmin(token, thread.id, reply.trim());
      setThread(t);
      setReply("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send your reply.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve() {
    if (!thread) return;
    setBusy(true);
    try {
      const t = await resolveSupportTicketAdmin(token, thread.id);
      setThread(t);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not resolve this ticket.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReopen() {
    if (!thread) return;
    setBusy(true);
    try {
      const t = await reopenSupportTicketAdmin(token, thread.id);
      setThread(t);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reopen this ticket.");
    } finally {
      setBusy(false);
    }
  }

  if (thread) {
    return (
      <View>
        <Pressable onPress={() => setThread(null)}>
          <Text style={styles.cardLink}>‹ All tickets</Text>
        </Pressable>
        <Text style={styles.cardTitle}>{thread.subject}</Text>
        <Text style={styles.cardSubtitle}>
          {thread.sender_kind === "tutor" ? "Tutor" : "Learner"}: {thread.sender_name} ({thread.sender_email})
        </Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}

        {thread.messages.map((m) => {
          const isAdmin = m.sender_kind === "admin";
          return (
            <View key={m.id} style={[styles.bubble, isAdmin ? styles.bubbleMine : styles.bubbleTheirs]}>
              <Text style={isAdmin ? styles.bubbleSenderDark : styles.bubbleSender}>
                {isAdmin ? "You (admin)" : thread.sender_name}
              </Text>
              <Text style={isAdmin ? styles.bubbleBodyDark : styles.bubbleBody}>{m.body}</Text>
              <Text style={isAdmin ? styles.bubbleDateDark : styles.bubbleDate}>{m.created_at}</Text>
            </View>
          );
        })}

        <TextInput
          style={[styles.input, { minHeight: 90, textAlignVertical: "top", marginTop: 12 }]}
          placeholder="Write a reply..."
          placeholderTextColor={colors.inputPlaceholder}
          value={reply}
          onChangeText={setReply}
          multiline
        />
        <View style={styles.standingButtonRow}>
          <Pressable style={[styles.smallButton, styles.suspendButton]} onPress={handleReply} disabled={busy}>
            <Text style={styles.smallButtonText}>Reply</Text>
          </Pressable>
          {thread.status === "open" ? (
            <Pressable style={[styles.smallButton, styles.reinstateButton, { flex: 1, marginTop: 0 }]} onPress={handleResolve} disabled={busy}>
              <Text style={styles.smallButtonText}>Mark Resolved</Text>
            </Pressable>
          ) : (
            <Pressable style={[styles.smallButton, styles.blockButton]} onPress={handleReopen} disabled={busy}>
              <Text style={styles.smallButtonText}>Reopen</Text>
            </Pressable>
          )}
        </View>
      </View>
    );
  }

  return (
    <View>
      <View style={styles.sectionRow}>
        {([
          { key: "open" as const, label: "Open" },
          { key: "resolved" as const, label: "Resolved" },
          { key: undefined, label: "All" },
        ]).map((f) => (
          <Pressable
            key={f.label}
            style={[styles.sectionChip, statusFilter === f.key && styles.sectionChipActive]}
            onPress={() => setStatusFilter(f.key)}
          >
            <Text style={[styles.sectionChipText, statusFilter === f.key && styles.sectionChipTextActive]}>
              {f.label}
            </Text>
          </Pressable>
        ))}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!tickets ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
      ) : tickets.length === 0 ? (
        <Text style={styles.empty}>No tickets here.</Text>
      ) : (
        tickets.map((t) => (
          <Pressable key={t.id} style={styles.card} onPress={() => openTicket(t.id)}>
            <Text style={styles.cardTitle}>{t.subject}</Text>
            <Text style={styles.cardSubtitle}>
              {t.sender_kind === "tutor" ? "Tutor" : "Learner"}: {t.sender_name} ({t.sender_email})
            </Text>
            <View
              style={[
                styles.ticketStatusPill,
                t.status === "open" ? styles.ticketStatusOpen : styles.ticketStatusResolved,
                { alignSelf: "flex-start", marginTop: 8 },
              ]}
            >
              <Text style={styles.ticketStatusPillText}>{t.status === "open" ? "Open" : "Resolved"}</Text>
            </View>
          </Pressable>
        ))
      )}
    </View>
  );
}

const PAY_DAY_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// Plain string math on the "YYYY-MM-DD" the backend sends, not a parsed
// Date - next_pay_day is a civil calendar date, not an instant, so there's
// no timezone to get wrong this way.
function formatPayDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${PAY_DAY_MONTH_LABELS[m - 1]} ${y}`;
}

function PayoutsSection({ token }: { token: string }) {
  const [payouts, setPayouts] = useState<TutoringPayout[] | null>(null);
  const [summary, setSummary] = useState<PayoutsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refByPayout, setRefByPayout] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [settleReference, setSettleReference] = useState("");
  const [settling, setSettling] = useState(false);

  const load = useCallback(() => {
    fetchPendingPayoutsAdmin(token)
      .then((res) => setPayouts(res.payouts))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load payouts."));
    fetchPayoutsSummaryAdmin(token)
      .then(setSummary)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the payouts summary."));
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

  function confirmSettleAll() {
    if (!summary || summary.overall.count === 0) return;
    Alert.alert(
      "Settle this payday?",
      `This marks all ${summary.overall.count} pending payout(s) — R${summary.overall.net_zar.toFixed(2)} total — as paid. ` +
        "Only do this once you've actually sent every tutor their EFT.",
      [
        { text: "Not yet", style: "cancel" },
        { text: "Settle all", style: "destructive", onPress: handleSettleAll },
      ]
    );
  }

  async function handleSettleAll() {
    setSettling(true);
    setError(null);
    try {
      await settleAllPayoutsAdmin(token, settleReference.trim());
      setSettleReference("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not settle payouts.");
    } finally {
      setSettling(false);
    }
  }

  return (
    <View>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {summary && (
        <View style={styles.payoutsSummaryCard}>
          <View style={styles.payoutsSummaryRow}>
            <View>
              <Text style={styles.payoutsSummaryLabel}>Expected next payday</Text>
              <Text style={styles.payoutsSummaryValue}>{formatPayDay(summary.next_pay_day)}</Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={styles.payoutsSummaryLabel}>Net to pay out</Text>
              <Text style={styles.payoutsSummaryValuePayout}>R{summary.overall.net_zar.toFixed(2)}</Text>
            </View>
          </View>
          <Text style={styles.payoutsSummaryFooter}>
            R{summary.overall.gross_zar.toFixed(2)} gross (before Malita's cut) across {summary.overall.count} session(s)
          </Text>

          {summary.by_tutor.length > 0 && (
            <View style={styles.payoutsByTutorCol}>
              <Text style={styles.payoutsByTutorHeading}>By tutor</Text>
              {summary.by_tutor.map((t) => (
                <View key={t.tutor_id} style={styles.payoutsByTutorRow}>
                  <Text style={styles.payoutsByTutorName}>
                    {t.tutor_name ?? `Tutor #${t.tutor_id}`} ({t.count})
                  </Text>
                  <Text style={styles.payoutsByTutorAmount}>
                    R{t.net_zar.toFixed(2)} <Text style={styles.payoutsByTutorGross}>(R{t.gross_zar.toFixed(2)} gross)</Text>
                  </Text>
                </View>
              ))}
            </View>
          )}

          {summary.overall.count > 0 && (
            <View style={{ marginTop: 14 }}>
              <TextInput
                style={styles.input}
                placeholder="Batch payment reference (optional)"
                placeholderTextColor={colors.inputPlaceholder}
                value={settleReference}
                onChangeText={setSettleReference}
              />
              <Pressable style={styles.approveButton} onPress={confirmSettleAll} disabled={settling}>
                {settling ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.approveButtonText}>Settle This Payday ({summary.overall.count})</Text>
                )}
              </Pressable>
            </View>
          )}
        </View>
      )}

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
            <Text style={styles.detailLine}>
              Bank details: {formatBankDetails({
                holder: p.tutor_bank_account_holder, bank: p.tutor_bank_name, branchCode: p.tutor_bank_branch_code,
                accountNumber: p.tutor_bank_account_number, accountType: p.tutor_bank_account_type, note: p.tutor_bank_note,
              })}
            </Text>
            <TextInput
              style={styles.input}
              placeholder="Payment reference (e.g. EFT ref)"
              placeholderTextColor={colors.inputPlaceholder}
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
  container: { padding: 20, paddingBottom: 40, flexGrow: 1 },
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
  seedButton: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  buttonDisabled: { opacity: 0.6 },
  seedButtonText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
  seedResultText: { fontSize: 12, color: colors.textSecondary, marginBottom: 16, lineHeight: 17 },
  sectionRow: { flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: 16 },
  sectionChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: colors.surface,
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
  catalogRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 4,
  },
  catalogRowText: { fontSize: 13, color: colors.text, flex: 1 },
  deleteIcon: { fontSize: 15, marginLeft: 10 },
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
    color: colors.inputText,
    backgroundColor: colors.inputBackground,
    marginBottom: 8,
  },
  textArea: { minHeight: 70, textAlignVertical: "top" },
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
  payoutsSummaryCard: { backgroundColor: colors.primaryDark, borderRadius: 20, padding: 18, marginBottom: 16 },
  payoutsSummaryRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  payoutsSummaryLabel: { fontSize: 11, color: "rgba(255,255,255,0.7)", fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.4 },
  payoutsSummaryValue: { fontSize: 18, color: "#fff", fontWeight: "800", marginTop: 4 },
  payoutsSummaryValuePayout: { fontSize: 24, color: colors.success, fontWeight: "800", marginTop: 4 },
  payoutsSummaryFooter: { fontSize: 11, color: "rgba(255,255,255,0.6)", fontWeight: "500", marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.18)" },
  payoutsByTutorCol: { marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.18)", gap: 8 },
  payoutsByTutorHeading: { fontSize: 11, color: "rgba(255,255,255,0.7)", fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 2 },
  payoutsByTutorRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  payoutsByTutorName: { fontSize: 13, color: "#fff", fontWeight: "600", flex: 1, marginRight: 8 },
  payoutsByTutorAmount: { fontSize: 13, color: "#fff", fontWeight: "700" },
  payoutsByTutorGross: { fontSize: 11, color: "rgba(255,255,255,0.5)", fontWeight: "500" },
  standingBox: { marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border },
  standingButtonRow: { flexDirection: "row", gap: 10, marginTop: 10 },
  smallButton: { flex: 1, borderRadius: 999, paddingVertical: 10, alignItems: "center" },
  smallButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  suspendButton: { backgroundColor: colors.textSecondary },
  blockButton: { backgroundColor: colors.error },
  reinstateButton: { backgroundColor: colors.success, marginTop: 10, alignSelf: "flex-start", paddingHorizontal: 20 },
  searchInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.inputText,
    backgroundColor: colors.inputBackground,
    marginBottom: 16,
  },
  accountStatusPill: { borderRadius: 999, paddingVertical: 4, paddingHorizontal: 10, alignSelf: "flex-start", marginTop: 6 },
  accountStatusPillText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  ticketStatusPill: { borderRadius: 999, paddingVertical: 4, paddingHorizontal: 10 },
  ticketStatusOpen: { backgroundColor: colors.primary },
  ticketStatusResolved: { backgroundColor: colors.success },
  ticketStatusPillText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  bubble: { borderRadius: 16, padding: 14, marginBottom: 10, maxWidth: "90%" },
  // A richer purple (not colors.surface's translucent white) so the
  // admin's own bubble still stands apart from the ticket opener's -
  // the old near-black bg would have blended into the dark background.
  bubbleMine: { backgroundColor: colors.primaryDark, alignSelf: "flex-end" },
  bubbleTheirs: { backgroundColor: colors.surface, alignSelf: "flex-start" },
  bubbleSender: { fontSize: 11, fontWeight: "700", color: colors.textSecondary, marginBottom: 4 },
  bubbleSenderDark: { fontSize: 11, fontWeight: "700", color: "rgba(255,255,255,0.7)", marginBottom: 4 },
  bubbleBody: { fontSize: 14, color: colors.text, lineHeight: 20 },
  bubbleBodyDark: { fontSize: 14, color: "#fff", lineHeight: 20 },
  bubbleDate: { fontSize: 11, color: colors.textSecondary, marginTop: 6 },
  bubbleDateDark: { fontSize: 11, color: "rgba(255,255,255,0.5)", marginTop: 6 },
});
