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
} from "../api/client";
import Dropdown from "../components/Dropdown";

type Section = "applications" | "match" | "payouts";

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

      <View style={styles.sectionRow}>
        {([
          { key: "applications", label: "Applications" },
          { key: "match", label: "Match Requests" },
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
      {token && section === "match" && <MatchSection token={token} />}
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

  async function handleGetDocUrl(tutorId: number, kind: "id" | "matric_certificate") {
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
                  <Text style={styles.detailLine}>Bank details: {a.bank_account_note || "—"}</Text>

                  {a.has_id_document ? (
                    docUrls[`${a.id}_id`] ? (
                      <Pressable style={styles.docButton} onPress={() => Linking.openURL(docUrls[`${a.id}_id`])}>
                        <Text style={styles.docButtonText}>Open ID document</Text>
                      </Pressable>
                    ) : (
                      <Pressable style={styles.docButton} onPress={() => handleGetDocUrl(a.id, "id")}>
                        <Text style={styles.docButtonText}>🔗 Get ID document link</Text>
                      </Pressable>
                    )
                  ) : (
                    <Text style={styles.detailLine}>ID document: not uploaded</Text>
                  )}

                  {a.has_matric_certificate_document ? (
                    docUrls[`${a.id}_matric_certificate`] ? (
                      <Pressable
                        style={styles.docButton}
                        onPress={() => Linking.openURL(docUrls[`${a.id}_matric_certificate`])}
                      >
                        <Text style={styles.docButtonText}>Open matric certificate</Text>
                      </Pressable>
                    ) : (
                      <Pressable style={styles.docButton} onPress={() => handleGetDocUrl(a.id, "matric_certificate")}>
                        <Text style={styles.docButtonText}>🔗 Get matric certificate link</Text>
                      </Pressable>
                    )
                  ) : (
                    <Text style={styles.detailLine}>Matric certificate: not uploaded</Text>
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

function MatchSection({ token }: { token: string }) {
  const [requests, setRequests] = useState<TutoringRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [candidatesBySubject, setCandidatesBySubject] = useState<Record<string, ApprovedTutor[]>>({});
  const [selectedTutor, setSelectedTutor] = useState<Record<number, number | null>>({});
  const [price, setPrice] = useState<Record<number, string>>({});
  const [duration, setDuration] = useState<Record<number, string>>({});
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
    const priceVal = parseFloat(price[r.id] || "");
    const durationVal = parseInt(duration[r.id] || "60", 10);
    if (!tutorId || isNaN(priceVal) || priceVal <= 0) {
      setError("Please choose a tutor and a valid price.");
      return;
    }
    let scheduled_at: string | null = null;
    const raw = (scheduledAt[r.id] || "").trim();
    if (raw) {
      const parsed = new Date(raw.replace(" ", "T"));
      if (isNaN(parsed.getTime())) {
        setError("Scheduled date/time must look like 2026-11-20 18:00");
        return;
      }
      scheduled_at = parsed.toISOString();
    }
    setBusyId(r.id);
    setError(null);
    try {
      await matchTutorToRequestAdmin(token, r.id, {
        tutor_id: tutorId,
        price_zar: priceVal,
        duration_minutes: durationVal,
        scheduled_at,
      });
      Alert.alert("Matched!", "The learner can now pay to confirm the session.");
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
        <Text style={styles.empty}>No open requests waiting to be matched.</Text>
      ) : (
        requests.map((r) => {
          const expanded = expandedId === r.id;
          const candidates = candidatesBySubject[r.subject] || [];
          return (
            <View key={r.id} style={styles.card}>
              <Pressable onPress={() => expandRequest(r)}>
                <Text style={styles.cardTitle}>
                  #{r.id} — {r.subject}
                  {r.topic ? ` (${r.topic})` : ""}
                </Text>
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
                        options={candidates.map((t) => ({ label: `${t.name} (${t.email})`, value: String(t.id) }))}
                        value={selectedTutor[r.id] != null ? String(selectedTutor[r.id]) : null}
                        onChange={(v) => setSelectedTutor((prev) => ({ ...prev, [r.id]: parseInt(v, 10) }))}
                      />
                      <Text style={styles.label}>Session price (ZAR)</Text>
                      <TextInput
                        style={styles.input}
                        keyboardType="numeric"
                        value={price[r.id] || ""}
                        onChangeText={(v) => setPrice((prev) => ({ ...prev, [r.id]: v }))}
                        placeholder="e.g. 300"
                      />
                      <Text style={styles.label}>Duration (minutes)</Text>
                      <TextInput
                        style={styles.input}
                        keyboardType="numeric"
                        value={duration[r.id] || "60"}
                        onChangeText={(v) => setDuration((prev) => ({ ...prev, [r.id]: v }))}
                      />
                      <Text style={styles.label}>Scheduled date/time (optional)</Text>
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
                          <Text style={styles.approveButtonText}>Match & Generate Payment</Text>
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

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4, marginBottom: 16 },
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
