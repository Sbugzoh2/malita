import React, { useCallback, useEffect, useState } from "react";
import { Alert, View, Text, Pressable, TextInput, StyleSheet, ScrollView, ActivityIndicator, Linking, Image } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "@react-navigation/native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import {
  ApiError,
  TutorProfile,
  TutorPayout,
  TutoringRequest,
  fetchTutorMyProfile,
  fetchTutorMyPayouts,
  fetchTutorOpenRequests,
  acceptTutoringRequest,
  proposeNewTime,
  confirmTutoringSessionAsTutor,
  respondToAdminMatch,
  cancelTutoringSessionAsTutor,
  submitSessionRecording,
  YEAR_LEVEL_LABELS,
} from "../api/client";
import SessionDateTimePicker, {
  SessionDateTimeValue,
  sessionDateTimeToIso,
} from "../components/SessionDateTimePicker";

type Section = "open" | "sessions" | "payouts";

function formatScheduled(iso: string): string {
  // Always render in SAST (fixed UTC+2, no daylight saving), regardless of
  // the device's own timezone - otherwise the same stored instant displays
  // as a different wall-clock time depending on where the phone's clock is
  // set, which looked like scheduling itself being "hours off".
  return new Date(iso).toLocaleString("en-ZA", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Africa/Johannesburg",
  });
}

function payoutPreview(priceZar: number, cutPercent: number): string {
  return `R${(priceZar * (1 - cutPercent / 100)).toFixed(2)}`;
}

// "Grade 12" for a high-school request, "1st Year"/"2nd Year"/etc. for a
// higher-ed one (real catalog module or a custom/"Other" one) - previously
// only the grade case was shown, so a module request's year never
// appeared on its job card at all.
function levelLabelFor(r: { grade: number | null; module_year_level: number | null; custom_module_year_level: number | null }): string | null {
  if (r.grade) return `Grade ${r.grade}`;
  const yearLevel = r.module_year_level ?? r.custom_module_year_level;
  return yearLevel != null ? YEAR_LEVEL_LABELS[yearLevel] ?? null : null;
}

function lastDayOfMonth(year: number, monthIndex0: number): Date {
  return new Date(year, monthIndex0 + 1, 0);
}

// Malita's payout cycle: a session completed the 16th through the end of
// a month is paid on the 15th of the FOLLOWING month; one completed the
// 1st through the 15th is paid at the end of that SAME month. This is a
// plain civil-calendar rule (no particular time of day), so it works off
// local Date components directly rather than an ISO instant.
function nextPayDay(from: Date = new Date()): Date {
  if (from.getDate() <= 15) return lastDayOfMonth(from.getFullYear(), from.getMonth());
  return new Date(from.getFullYear(), from.getMonth() + 1, 15);
}

function formatPayDay(d: Date): string {
  return d.toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

// "3h ago" / "2d ago" for a job card's request timestamp - coarser than
// formatScheduled on purpose, this is just a freshness signal, not a time
// someone needs to act on.
function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60));
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Compact "Tue 18:00" (SAST) for a job card row - formatScheduled's full
// "12 Nov 2026, 18:00" is reserved for the Accept button/expanded detail,
// where the exact date actually matters.
function formatScheduledShort(iso: string): string {
  const d = new Date(iso);
  const weekday = d.toLocaleString("en-ZA", { weekday: "short", timeZone: "Africa/Johannesburg" });
  const time = d.toLocaleString("en-ZA", {
    hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Africa/Johannesburg",
  });
  return `${weekday} ${time}`;
}

// Same 8-hue palette as theme.ts's topicColors, but hashed by subject name
// instead of hand-mapped - open requests can carry any subject string
// (including higher-ed modules), so there's no fixed catalog to map from.
const JOB_GROUP_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
function colorForGroup(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return JOB_GROUP_PALETTE[hash % JOB_GROUP_PALETTE.length];
}

// A custom ("Other") higher-ed module always falls into the "Other"
// bucket regardless of its real subject text - those requests need admin
// sign-off before they're even a real match (see acceptTutoringRequest's
// pending_admin_approval path), so they don't belong grouped in with a
// catalog subject's ordinary jobs.
function groupKeyFor(r: TutoringRequest): string {
  if (r.is_custom_higher_ed) return "Other";
  return r.subject && r.subject.trim() ? r.subject : "Other";
}

type JobGroup = { name: string; items: TutoringRequest[] };

function buildJobGroups(requests: TutoringRequest[]): JobGroup[] {
  const map = new Map<string, TutoringRequest[]>();
  for (const r of requests) {
    const key = groupKeyFor(r);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  }
  const otherItems = map.get("Other") ?? [];
  map.delete("Other");
  const groups = Array.from(map.entries()).map(([name, items]) => ({ name, items }));
  groups.sort((a, b) => b.items.length - a.items.length);
  if (otherItems.length > 0) groups.push({ name: "Other", items: otherItems });
  return groups;
}

const STATUS_COLOR: Record<string, string> = {
  pending_review: colors.textSecondary,
  approved: colors.success,
  rejected: colors.error,
  suspended: colors.error,
};

type SessionGroup = "active" | "completed" | "cancelled" | "lapsed";

// Keeps cancelled/lapsed sessions out of the same list as upcoming ones -
// previously everything rendered in one flat list regardless of status.
function groupForStatus(status: string): SessionGroup {
  if (status === "cancelled") return "cancelled";
  if (status === "lapsed") return "lapsed";
  if (status === "completed") return "completed";
  return "active";
}

const SESSION_GROUP_TABS: { key: SessionGroup; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "lapsed", label: "Lapsed" },
];

const SESSION_GROUP_EMPTY_LABEL: Record<SessionGroup, string> = {
  active: "No active or upcoming sessions.",
  completed: "No completed sessions yet.",
  cancelled: "No cancelled sessions.",
  lapsed: "No lapsed sessions.",
};

// Built from plain Views (no SVG dependency, no emoji) - same icon
// language as the My Requests screen's bottom tab bar.
function SectionTabIcon({ name, size = 20, color }: { name: Section; size?: number; color: string }) {
  const box = { width: size, height: size, alignItems: "center" as const, justifyContent: "center" as const, position: "relative" as const };
  switch (name) {
    case "open":
      return (
        <View style={box}>
          <View
            style={{
              position: "absolute",
              bottom: 0,
              width: size * 0.82,
              height: size * 0.56,
              borderWidth: 1.6,
              borderColor: color,
              borderRadius: 3,
            }}
          />
          <View
            style={{
              position: "absolute",
              top: size * 0.14,
              width: size * 0.3,
              height: size * 0.2,
              borderWidth: 1.6,
              borderColor: color,
              borderBottomWidth: 0,
              borderTopLeftRadius: 4,
              borderTopRightRadius: 4,
            }}
          />
        </View>
      );
    case "sessions":
      return (
        <View style={box}>
          <View style={{ width: size * 0.82, height: size * 0.72, borderWidth: 1.6, borderColor: color, borderRadius: 3 }}>
            <View style={{ height: size * 0.2, borderBottomWidth: 1.6, borderBottomColor: color }} />
          </View>
        </View>
      );
    case "payouts":
      return (
        <View style={box}>
          <View style={{ width: size * 0.68, height: size * 0.82, borderWidth: 1.6, borderColor: color, borderRadius: 3, padding: size * 0.12, justifyContent: "space-evenly" }}>
            <View style={{ height: 1.4, backgroundColor: color }} />
            <View style={{ height: 1.4, backgroundColor: color }} />
            <View style={{ height: 1.4, width: "60%", backgroundColor: color }} />
          </View>
        </View>
      );
    default:
      return null;
  }
}

function StarPicker({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <View style={styles.starRow}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable key={n} onPress={() => onChange(n)}>
          <Text style={styles.star}>{n <= value ? "⭐" : "☆"}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export default function TutorHomeScreen() {
  const { token, me, logout } = useTutorAuth();
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<TutorProfile | null>(null);
  const [payouts, setPayouts] = useState<TutorPayout[] | null>(null);
  const [openRequests, setOpenRequests] = useState<TutoringRequest[] | null>(null);
  const [openCutPercent, setOpenCutPercent] = useState<number>(30);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("open");
  const [proposingId, setProposingId] = useState<number | null>(null);
  const [proposeDateTime, setProposeDateTime] = useState<Record<number, SessionDateTimeValue>>({});
  const [acceptingId, setAcceptingId] = useState<number | null>(null);
  const [sendingProposalId, setSendingProposalId] = useState<number | null>(null);
  const [ratingDraft, setRatingDraft] = useState<Record<number, number>>({});
  const [commentDraft, setCommentDraft] = useState<Record<number, string>>({});
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [respondingAdminMatchId, setRespondingAdminMatchId] = useState<number | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [cancelReasonId, setCancelReasonId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [recordingDraft, setRecordingDraft] = useState<Record<number, string>>({});
  const [submittingRecordingId, setSubmittingRecordingId] = useState<number | null>(null);
  const [sessionGroup, setSessionGroup] = useState<SessionGroup>("active");
  const [jobFilter, setJobFilter] = useState<string>("All");
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorMyProfile(token)
      .then(setProfile)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your profile."));
    fetchTutorMyPayouts(token)
      .then((res) => setPayouts(res.payouts))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your payouts."));
    fetchTutorOpenRequests(token)
      .then((res) => {
        setOpenRequests(res.requests);
        setOpenCutPercent(res.platform_cut_percent);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load open requests."));
  }, [token]);

  async function handleAccept(requestId: number) {
    if (!token) return;
    setAcceptingId(requestId);
    setError(null);
    try {
      const result = await acceptTutoringRequest(token, requestId);
      // A custom ("Other") module claim doesn't finalize immediately -
      // an admin has to confirm it's actually in your field first (see
      // backend/tutoring.py's accept_tutoring_request).
      if (result.status === "pending_admin_approval") {
        Alert.alert(
          "Submitted for review",
          "This module isn't in our catalog, so an admin needs to confirm it's a good match for your " +
            "qualification before it's finalized. You'll be notified once it's approved."
        );
      }
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not accept this request.");
    } finally {
      setAcceptingId(null);
    }
  }

  async function handleSendProposal(requestId: number) {
    if (!token) return;
    const dt = proposeDateTime[requestId];
    if (!dt) {
      setError("Please pick a date and time to propose.");
      return;
    }
    setSendingProposalId(requestId);
    setError(null);
    try {
      await proposeNewTime(token, requestId, sessionDateTimeToIso(dt));
      setProposingId(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send that proposal.");
    } finally {
      setSendingProposalId(null);
    }
  }

  async function handleAdminMatchResponse(requestId: number, accept: boolean) {
    if (!token) return;
    setRespondingAdminMatchId(requestId);
    setError(null);
    try {
      await respondToAdminMatch(token, requestId, accept);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record your response.");
    } finally {
      setRespondingAdminMatchId(null);
    }
  }

  async function handleConfirm(requestId: number) {
    if (!token) return;
    const rating = ratingDraft[requestId];
    if (!rating) {
      setError("Please pick a rating (tap a star) before confirming.");
      return;
    }
    setConfirmingId(requestId);
    setError(null);
    try {
      await confirmTutoringSessionAsTutor(token, requestId, rating, commentDraft[requestId] || "");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not confirm this session.");
    } finally {
      setConfirmingId(null);
    }
  }

  async function handleCancel(requestId: number) {
    if (!token) return;
    setCancelingId(requestId);
    setError(null);
    try {
      await cancelTutoringSessionAsTutor(token, requestId, cancelReason.trim());
      setCancelReasonId(null);
      setCancelReason("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel this session.");
    } finally {
      setCancelingId(null);
    }
  }

  async function handleSubmitRecording(requestId: number) {
    if (!token) return;
    const link = (recordingDraft[requestId] || "").trim();
    if (!link) {
      setError("Please paste in the recording link.");
      return;
    }
    setSubmittingRecordingId(requestId);
    setError(null);
    try {
      await submitSessionRecording(token, requestId, link);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit the recording link.");
    } finally {
      setSubmittingRecordingId(null);
    }
  }

  function confirmCancel(requestId: number) {
    Alert.alert(
      "Cancel this session?",
      "The learner will be notified. This can't be undone.",
      [
        { text: "Never mind", style: "cancel" },
        { text: "Cancel Session", style: "destructive", onPress: () => handleCancel(requestId) },
      ]
    );
  }

  // Refreshes every time this screen regains focus, so a new match or a
  // payout being marked paid shows up without needing to log out/in.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  if (!me) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
    <ScrollView style={styles.scrollView} contentContainerStyle={styles.container}>
      <View style={styles.hero}>
        <Image
          source={require("../../assets/hero-student.png")}
          style={styles.heroImage}
          resizeMode="cover"
        />
        <View style={styles.heroScrim} />
        <View style={styles.heroContent}>
          <Text style={styles.heroGreeting}>🙋 Welcome, {me.name.split(" ")[0]}!</Text>
          <View style={[styles.statusBadgePill, { backgroundColor: STATUS_COLOR[me.status] ?? colors.primary }]}>
            <Text style={styles.statusBadgeText}>{me.status_label}</Text>
          </View>
        </View>
      </View>

      <View style={styles.body}>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {me.status !== "approved" ? (
        <View style={styles.card}>
          <Text style={styles.cardText}>
            {me.status === "pending_review"
              ? "Your application is still being reviewed - we'll email you once a decision is made."
              : me.status === "rejected"
              ? "Your application was not approved. Check your email for details."
              : "Your tutor account is currently suspended."}
          </Text>
        </View>
      ) : (
        <>
          {section === "open" ? (
            !openRequests ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
            ) : openRequests.length === 0 ? (
              <Text style={styles.empty}>No open requests for your subjects right now.</Text>
            ) : (() => {
              const jobGroups = buildJobGroups(openRequests);
              const totalRaw = openRequests.reduce((sum, r) => sum + (r.price_zar ?? 0), 0);
              const totalAfterCut = totalRaw * (1 - openCutPercent / 100);
              const visibleGroups = jobFilter === "All" ? jobGroups : jobGroups.filter((g) => g.name === jobFilter);
              return (
                <>
                  <View style={styles.statCard}>
                    <View style={styles.statCardRow}>
                      <View>
                        <Text style={styles.statLabel}>Open right now</Text>
                        <Text style={styles.statValue}>{openRequests.length} job{openRequests.length === 1 ? "" : "s"}</Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.statLabel}>Your est. payout</Text>
                        <Text style={styles.statValuePayout}>R{totalAfterCut.toFixed(0)}</Text>
                      </View>
                    </View>
                    <View style={styles.statCardFooterRow}>
                      <Text style={styles.statFooterText}>R{totalRaw.toFixed(0)} total if all accepted</Text>
                      <Text style={styles.statFooterText}>after Malita's {openCutPercent}% fee</Text>
                    </View>
                  </View>

                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterRow} contentContainerStyle={styles.filterRowContent}>
                    <Pressable
                      style={[styles.filterChip, jobFilter === "All" && styles.filterChipActive]}
                      onPress={() => setJobFilter("All")}
                    >
                      <Text style={[styles.filterChipText, jobFilter === "All" && styles.filterChipTextActive]}>
                        All · {openRequests.length}
                      </Text>
                    </Pressable>
                    {jobGroups.map((g) => (
                      <Pressable
                        key={g.name}
                        style={[styles.filterChip, jobFilter === g.name && styles.filterChipActive]}
                        onPress={() => setJobFilter(g.name)}
                      >
                        <Text style={[styles.filterChipText, jobFilter === g.name && styles.filterChipTextActive]}>
                          {g.name} · {g.items.length}
                        </Text>
                      </Pressable>
                    ))}
                  </ScrollView>

                  {visibleGroups.length === 0 ? (
                    <Text style={styles.empty}>No open jobs in this filter right now.</Text>
                  ) : null}
                  {visibleGroups.map((group) => (
                    <View key={group.name} style={styles.jobGroupBlock}>
                      <View style={styles.groupHeaderRow}>
                        <View
                          style={[
                            styles.groupAvatar,
                            { backgroundColor: group.name === "Other" ? colors.textSecondary : colorForGroup(group.name) },
                          ]}
                        >
                          <Text style={styles.groupAvatarText}>
                            {group.name === "Other" ? "•••" : group.name.charAt(0).toUpperCase()}
                          </Text>
                        </View>
                        <Text style={styles.groupName}>{group.name}</Text>
                        <Text style={styles.groupCount}>{group.items.length}</Text>
                      </View>

                      {group.items.map((r) => (
                        <View key={r.id} style={[styles.jobCard, group.name === "Other" && styles.jobCardOther]}>
                          <Pressable
                            style={styles.jobCardRow}
                            onPress={() => setExpandedJobId(expandedJobId === r.id ? null : r.id)}
                          >
                            <View style={styles.jobCardInfo}>
                              <Text style={styles.jobTitle}>{r.topic || r.custom_module_name || r.subject}</Text>
                              {(() => {
                                const levelLabel = levelLabelFor(r);
                                return r.learner_name || levelLabel ? (
                                  <Text style={styles.jobMetaText}>
                                    {r.learner_name ?? ""}
                                    {r.learner_name && levelLabel ? " · " : ""}
                                    {levelLabel ?? ""}
                                  </Text>
                                ) : null;
                              })()}
                              {(r.duration_minutes || r.scheduled_at) ? (
                                <Text style={styles.jobMetaText}>
                                  {r.duration_minutes ? `${r.duration_minutes} min` : ""}
                                  {r.duration_minutes && r.scheduled_at ? " · " : ""}
                                  {r.scheduled_at ? formatScheduledShort(r.scheduled_at) : ""}
                                </Text>
                              ) : null}
                              <Text style={styles.jobRequestedAgo}>
                                {r.is_custom_higher_ed ? "Custom module · " : ""}
                                {r.created_at ? `Requested ${timeAgo(r.created_at)}` : ""}
                              </Text>
                            </View>
                            <View style={styles.jobPriceCol}>
                              <Text style={styles.jobPrice}>{r.price_zar != null ? `R${r.price_zar}` : "—"}</Text>
                              <Text style={styles.jobChevron}>{expandedJobId === r.id ? "⌄" : "›"}</Text>
                            </View>
                          </Pressable>

                          {expandedJobId === r.id && (
                            <View style={styles.jobCardExpanded}>
                              <Text style={styles.payoutNote}>
                                Estimated payout: ~{r.price_zar != null ? payoutPreview(r.price_zar, openCutPercent) : "—"} after
                                Malita's {openCutPercent}% cut — the amount above is not your final payout.
                              </Text>
                              {r.preferred_times_note ? (
                                <Text style={styles.cardMeta}>Notes: {r.preferred_times_note}</Text>
                              ) : null}

                              <Pressable
                                style={styles.acceptButton}
                                onPress={() => handleAccept(r.id)}
                                disabled={acceptingId === r.id}
                              >
                                {acceptingId === r.id ? (
                                  <ActivityIndicator color="#fff" />
                                ) : (
                                  <Text style={styles.acceptButtonText}>
                                    Accept{r.scheduled_at ? ` at ${formatScheduled(r.scheduled_at)}` : ""}
                                  </Text>
                                )}
                              </Pressable>

                              <Pressable
                                style={styles.proposeLinkButton}
                                onPress={() => setProposingId(proposingId === r.id ? null : r.id)}
                              >
                                <Text style={styles.proposeLinkText}>
                                  {proposingId === r.id ? "Cancel" : "Can't make that time? Propose a different one"}
                                </Text>
                              </Pressable>

                              {proposingId === r.id && (
                                <View style={styles.confirmBox}>
                                  <SessionDateTimePicker
                                    label="Propose a new date & time"
                                    value={proposeDateTime[r.id] || null}
                                    onChange={(v) => setProposeDateTime((prev) => ({ ...prev, [r.id]: v }))}
                                  />
                                  <Pressable
                                    style={styles.acceptButton}
                                    onPress={() => handleSendProposal(r.id)}
                                    disabled={sendingProposalId === r.id}
                                  >
                                    {sendingProposalId === r.id ? (
                                      <ActivityIndicator color="#fff" />
                                    ) : (
                                      <Text style={styles.acceptButtonText}>Send Proposal</Text>
                                    )}
                                  </Pressable>
                                </View>
                              )}
                            </View>
                          )}
                        </View>
                      ))}
                    </View>
                  ))}
                </>
              );
            })()
          ) : section === "sessions" ? (
            !profile ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
            ) : profile.sessions.length === 0 ? (
              <Text style={styles.empty}>No sessions yet - accept an open request to get started.</Text>
            ) : (() => {
              const lostSessions = profile.sessions.filter((s) => {
                const g = groupForStatus(s.status);
                return g === "cancelled" || g === "lapsed";
              });
              const lostRaw = lostSessions.reduce((sum, s) => sum + (s.price_zar ?? 0), 0);
              const lostAfterCut = lostSessions.reduce(
                (sum, s) => sum + (s.price_zar ?? 0) * (1 - (s.platform_cut_percent ?? openCutPercent) / 100),
                0
              );
              return (
              <>
                {lostSessions.length > 0 ? (
                  <View style={styles.statCard}>
                    <View style={styles.statCardRow}>
                      <View>
                        <Text style={styles.statLabel}>Lost to cancels & lapses</Text>
                        <Text style={styles.statValue}>
                          {lostSessions.length} session{lostSessions.length === 1 ? "" : "s"}
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.statLabel}>Payout you missed</Text>
                        <Text style={styles.statValueLost}>R{lostAfterCut.toFixed(0)}</Text>
                      </View>
                    </View>
                    <View style={styles.statCardFooterRow}>
                      <Text style={styles.statFooterText}>R{lostRaw.toFixed(0)} total before Malita's fee</Text>
                      <Text style={styles.statFooterText}>confirm early to avoid lapses</Text>
                    </View>
                  </View>
                ) : null}
                <View style={styles.sectionRow}>
                  {SESSION_GROUP_TABS.map((tab) => {
                    const count = profile.sessions.filter((s) => groupForStatus(s.status) === tab.key).length;
                    return (
                      <Pressable
                        key={tab.key}
                        style={[styles.sectionChip, sessionGroup === tab.key && styles.sectionChipActive]}
                        onPress={() => setSessionGroup(tab.key)}
                      >
                        <Text style={[styles.sectionChipText, sessionGroup === tab.key && styles.sectionChipTextActive]}>
                          {tab.label}{count ? ` (${count})` : ""}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
                {profile.sessions.filter((s) => groupForStatus(s.status) === sessionGroup).length === 0 ? (
                  <Text style={styles.empty}>{SESSION_GROUP_EMPTY_LABEL[sessionGroup]}</Text>
                ) : (
                  profile.sessions
                    .filter((s) => groupForStatus(s.status) === sessionGroup)
                    .map((sess) => (
                <View key={sess.id} style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {sess.subject}
                    {sess.topic ? ` · ${sess.topic}` : ""}
                  </Text>
                  <Text style={styles.cardStatus}>{sess.status_label}</Text>
                  {sess.price_zar != null ? (
                    <>
                      <Text style={styles.cardMeta}>
                        R{sess.price_zar}{sess.duration_minutes ? ` · ${sess.duration_minutes} min` : ""}
                      </Text>
                      <Text style={styles.payoutNote}>
                        Estimated payout: ~{payoutPreview(sess.price_zar, sess.platform_cut_percent ?? openCutPercent)} after
                        Malita's {sess.platform_cut_percent ?? openCutPercent}% cut — not your final payout.
                      </Text>
                    </>
                  ) : null}
                  {sess.status === "time_proposed" ? (
                    <Text style={styles.cardMeta}>
                      Your proposed time: {sess.proposed_scheduled_at ? formatScheduled(sess.proposed_scheduled_at) : "—"} -
                      awaiting the learner's approval.
                    </Text>
                  ) : sess.status === "admin_proposed" ? (
                    <Text style={styles.cardMeta}>
                      {sess.proposed_scheduled_at
                        ? `An admin proposed: ${formatScheduled(sess.proposed_scheduled_at)}`
                        : `Learner's requested time: ${sess.scheduled_at ? formatScheduled(sess.scheduled_at) : "—"}`}
                    </Text>
                  ) : sess.scheduled_at ? (
                    <Text style={styles.cardMeta}>Scheduled: {formatScheduled(sess.scheduled_at)}</Text>
                  ) : null}
                  {sess.meet_link ? (
                    <Pressable onPress={() => Linking.openURL(sess.meet_link!)}>
                      <Text style={styles.meetLink}>🎥 Join via Google Meet</Text>
                    </Pressable>
                  ) : sess.status === "awaiting_payment" ? (
                    <Text style={styles.cardMeta}>
                      The Google Meet link will be created once the learner's payment is confirmed.
                    </Text>
                  ) : null}

                  {(sess.status === "confirmed" || sess.status === "completed") && (
                    sess.recording_link ? (
                      <Text style={styles.cardMeta}>✓ Recording shared with Malita.</Text>
                    ) : (
                      <View style={styles.cancelBox}>
                        <Text style={styles.confirmLabel}>
                          Please record this session (Meet's own "Record meeting" button) and share the link:
                        </Text>
                        <TextInput
                          style={styles.input}
                          placeholder="Paste the recording link (e.g. Google Drive)"
                          value={recordingDraft[sess.id] || ""}
                          onChangeText={(v) => setRecordingDraft((prev) => ({ ...prev, [sess.id]: v }))}
                        />
                        <Pressable
                          style={styles.acceptButton}
                          onPress={() => handleSubmitRecording(sess.id)}
                          disabled={submittingRecordingId === sess.id}
                        >
                          {submittingRecordingId === sess.id ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.acceptButtonText}>Submit Recording Link</Text>
                          )}
                        </Pressable>
                      </View>
                    )
                  )}

                  {sess.status === "admin_proposed" && (
                    <View style={styles.proposalButtonRow}>
                      <Pressable
                        style={[styles.acceptButton, styles.proposalApproveButton]}
                        onPress={() => handleAdminMatchResponse(sess.id, true)}
                        disabled={respondingAdminMatchId === sess.id}
                      >
                        {respondingAdminMatchId === sess.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.acceptButtonText}>Confirm</Text>
                        )}
                      </Pressable>
                      <Pressable
                        style={[styles.acceptButton, styles.proposalDeclineButton]}
                        onPress={() => handleAdminMatchResponse(sess.id, false)}
                        disabled={respondingAdminMatchId === sess.id}
                      >
                        {respondingAdminMatchId === sess.id ? (
                          <ActivityIndicator color={colors.primary} />
                        ) : (
                          <Text style={styles.proposalDeclineButtonText}>Decline</Text>
                        )}
                      </Pressable>
                    </View>
                  )}

                  {sess.status === "confirmed" && !sess.tutor_confirmed && (
                    <View style={styles.confirmBox}>
                      <Text style={styles.confirmLabel}>Did this session happen? Rate the learner:</Text>
                      <StarPicker
                        value={ratingDraft[sess.id] || 0}
                        onChange={(v) => setRatingDraft((prev) => ({ ...prev, [sess.id]: v }))}
                      />
                      <TextInput
                        style={styles.input}
                        placeholder="Comment (optional)"
                        value={commentDraft[sess.id] || ""}
                        onChangeText={(v) => setCommentDraft((prev) => ({ ...prev, [sess.id]: v }))}
                      />
                      <Pressable
                        style={styles.acceptButton}
                        onPress={() => handleConfirm(sess.id)}
                        disabled={confirmingId === sess.id}
                      >
                        {confirmingId === sess.id ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.acceptButtonText}>Confirm & Rate</Text>
                        )}
                      </Pressable>
                    </View>
                  )}
                  {sess.status === "confirmed" && sess.tutor_confirmed && (
                    <Text style={styles.cardMeta}>✓ You confirmed this session - waiting on the learner too.</Text>
                  )}
                  {sess.status === "completed" && sess.tutor_rating != null && (
                    <Text style={styles.cardMeta}>You rated this session {sess.tutor_rating}/5 ⭐</Text>
                  )}

                  {(sess.status === "awaiting_payment" || sess.status === "confirmed") && (
                    cancelReasonId === sess.id ? (
                      <View style={styles.cancelBox}>
                        <Text style={styles.label}>Reason (optional)</Text>
                        <TextInput
                          style={styles.input}
                          placeholder="e.g. I'm no longer available at this time"
                          value={cancelReason}
                          onChangeText={setCancelReason}
                        />
                        <View style={styles.proposalButtonRow}>
                          <Pressable
                            style={[styles.acceptButton, styles.proposalDeclineButton]}
                            onPress={() => { setCancelReasonId(null); setCancelReason(""); }}
                          >
                            <Text style={styles.proposalDeclineButtonText}>Never mind</Text>
                          </Pressable>
                          <Pressable
                            style={[styles.acceptButton, styles.proposalApproveButton, styles.dangerButton]}
                            onPress={() => confirmCancel(sess.id)}
                            disabled={cancelingId === sess.id}
                          >
                            {cancelingId === sess.id ? (
                              <ActivityIndicator color="#fff" />
                            ) : (
                              <Text style={styles.acceptButtonText}>Confirm Cancel</Text>
                            )}
                          </Pressable>
                        </View>
                        <Text style={styles.payoutNote}>
                          Not available within 24 hours of the session - contact support for anything that close.
                        </Text>
                      </View>
                    ) : (
                      <Pressable style={styles.proposeLinkButton} onPress={() => setCancelReasonId(sess.id)}>
                        <Text style={styles.dangerLinkText}>Cancel this session</Text>
                      </Pressable>
                    )
                  )}
                  {sess.status === "cancelled" && (
                    <Text style={styles.cardMeta}>
                      Cancelled by {sess.cancelled_by ?? "—"}
                      {sess.cancellation_reason ? `: ${sess.cancellation_reason}` : "."}
                    </Text>
                  )}
                  {sess.status === "lapsed" && (
                    <Text style={styles.cardMeta}>
                      Lapsed - the learner didn't pay within 24 hours of being matched. They'll need to submit a new request.
                    </Text>
                  )}
                </View>
                    ))
                )}
              </>
              );
            })()
          ) : !payouts ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
          ) : (() => {
            const totalAmount = payouts.reduce((sum, p) => sum + p.amount_zar, 0);
            const paidAmount = payouts.filter((p) => p.status === "paid").reduce((sum, p) => sum + p.amount_zar, 0);
            const pendingAmount = payouts
              .filter((p) => p.status === "pending")
              .reduce((sum, p) => sum + p.amount_zar, 0);
            return (
              <>
                <View style={styles.statCard}>
                  <View style={styles.statCardRow}>
                    <View>
                      <Text style={styles.statLabel}>Total payouts</Text>
                      <Text style={styles.statValue}>R{totalAmount.toFixed(0)}</Text>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={styles.statLabel}>Next pay day</Text>
                      <Text style={styles.statValueDate}>{formatPayDay(nextPayDay())}</Text>
                    </View>
                  </View>
                  <View style={styles.statCardFooterRow}>
                    <Text style={styles.statFooterText}>R{paidAmount.toFixed(0)} paid</Text>
                    <Text style={styles.statFooterText}>R{pendingAmount.toFixed(0)} pending</Text>
                  </View>
                </View>

                {payouts.length === 0 ? (
                  <Text style={styles.empty}>No payouts yet.</Text>
                ) : (
                  payouts.map((p) => (
                    <View key={p.id} style={styles.card}>
                      <Text style={styles.cardTitle}>Session #{p.session_id}</Text>
                      <Text
                        style={[
                          styles.cardStatus,
                          { color: p.status === "paid" ? colors.success : colors.textSecondary },
                        ]}
                      >
                        {p.status === "paid" ? "Paid" : "Pending"}
                      </Text>
                      <Text style={styles.cardMeta}>R{p.amount_zar.toFixed(2)}</Text>
                      {p.payment_reference ? (
                        <Text style={styles.cardMeta}>Reference: {p.payment_reference}</Text>
                      ) : null}
                    </View>
                  ))
                )}
              </>
            );
          })()}
        </>
      )}

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
      </View>
    </ScrollView>

    {me.status === "approved" && (
      <View style={[styles.bottomBar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        {([
          { key: "open", label: "Jobs" },
          { key: "sessions", label: "Sessions" },
          { key: "payouts", label: "Payouts" },
        ] as { key: Section; label: string }[]).map((s) => {
          const active = section === s.key;
          const tint = active ? colors.primary : "#8a8984";
          return (
            <Pressable
              key={s.key}
              style={styles.bottomBarItem}
              onPress={() => setSection(s.key)}
              accessibilityRole="button"
              accessibilityLabel={s.label}
            >
              <SectionTabIcon name={s.key} color={tint} />
              <Text style={[styles.bottomBarLabel, { color: tint, fontWeight: active ? "700" : "500" }]}>
                {s.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    )}
    </View>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  screen: { flex: 1, backgroundColor: colors.background },
  scrollView: { flex: 1 },
  container: { backgroundColor: colors.background, flexGrow: 1 },
  bottomBar: {
    flexDirection: "row",
    backgroundColor: "#fff",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 10,
  },
  bottomBarItem: { flex: 1, alignItems: "center", gap: 4 },
  bottomBarLabel: { fontSize: 11 },
  body: { padding: 20, paddingBottom: 40 },
  hero: { height: 160, position: "relative" },
  heroImage: { width: "100%", height: "100%" },
  heroScrim: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    backgroundColor: "rgba(11,11,11,0.45)",
  },
  heroContent: { position: "absolute", left: 20, right: 20, bottom: 18 },
  heroGreeting: { fontSize: 22, fontWeight: "700", color: "#fff" },
  statusBadgePill: {
    alignSelf: "flex-start",
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 12,
    marginTop: 8,
  },
  statusBadgeText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 16 },
  // flexWrap so a 4th+ chip (e.g. the inner Active/Completed/Cancelled/
  // Lapsed tabs) wraps to a second line instead of being clipped off the
  // right edge of the screen - this row is reused for both the outer
  // Open Requests/My Sessions/My Payouts tabs (3 chips, never wraps) and
  // the inner session-status tabs (4 chips, needs to wrap).
  sectionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 16 },
  sectionChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 16,
    backgroundColor: "#fff",
  },
  sectionChipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  sectionChipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  sectionChipTextActive: { color: "#fff" },
  statCard: {
    backgroundColor: "#0b0b0b",
    borderRadius: 20,
    padding: 18,
    marginBottom: 16,
  },
  statCardRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  statLabel: { fontSize: 12, color: "#b9b8b3", fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.4 },
  statValue: { fontSize: 28, color: "#fff", fontWeight: "800", marginTop: 4 },
  statValuePayout: { fontSize: 22, color: colors.success, fontWeight: "800", marginTop: 4 },
  statValueLost: { fontSize: 22, color: colors.error, fontWeight: "800", marginTop: 4 },
  statValueDate: { fontSize: 20, color: "#fff", fontWeight: "800", marginTop: 4 },
  statCardFooterRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: "#2b2b29",
  },
  statFooterText: { fontSize: 11, color: "#8a8984", fontWeight: "500" },
  filterRow: { flexGrow: 0, marginBottom: 16 },
  filterRowContent: { gap: 8, paddingRight: 8 },
  filterChip: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#fff",
  },
  filterChipActive: { backgroundColor: "#0b0b0b", borderColor: "transparent" },
  filterChipText: { fontSize: 13, fontWeight: "600", color: colors.text },
  filterChipTextActive: { color: "#fff" },
  jobGroupBlock: { marginBottom: 22 },
  groupHeaderRow: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 10 },
  groupAvatar: {
    width: 28,
    height: 28,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },
  groupAvatarText: { fontSize: 13, fontWeight: "800", color: "#fff" },
  groupName: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.text },
  groupCount: {
    fontSize: 12,
    fontWeight: "700",
    color: colors.textSecondary,
    backgroundColor: "#efeeea",
    borderRadius: 999,
    paddingVertical: 3,
    paddingHorizontal: 9,
  },
  jobCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    marginBottom: 10,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  jobCardOther: { borderWidth: 1, borderColor: "#d8d7d1", borderStyle: "dashed" },
  jobCardRow: { flexDirection: "row", alignItems: "center", gap: 14, padding: 14 },
  jobCardInfo: { flex: 1, minWidth: 0 },
  jobTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  jobMetaText: { fontSize: 12, color: colors.textSecondary, marginTop: 5 },
  jobRequestedAgo: { fontSize: 11, color: "#8a8984", marginTop: 2 },
  jobPriceCol: { alignItems: "flex-end" },
  jobPrice: { fontSize: 17, fontWeight: "800", color: colors.success },
  jobChevron: { fontSize: 16, color: "#8a8984", marginTop: 6 },
  jobCardExpanded: { paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardText: { fontSize: 14, color: colors.text, lineHeight: 20 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.text },
  cardStatus: { fontSize: 13, fontWeight: "700", color: colors.primary, marginTop: 4 },
  cardMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 10, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    color: colors.text,
    backgroundColor: "#fff",
  },
  acceptButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 10,
  },
  acceptButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  payoutNote: { fontSize: 12, color: colors.textSecondary, marginTop: 4, fontStyle: "italic" },
  meetLink: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 10 },
  proposalButtonRow: { flexDirection: "row", gap: 10, marginTop: 10 },
  proposalApproveButton: { flex: 1, marginTop: 0 },
  proposalDeclineButton: {
    flex: 1,
    marginTop: 0,
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: colors.primary,
  },
  proposalDeclineButtonText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  proposeLinkButton: { marginTop: 10, alignItems: "center" },
  proposeLinkText: { color: colors.primary, fontWeight: "600", fontSize: 13 },
  confirmBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  cancelBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  dangerButton: { backgroundColor: colors.error },
  dangerLinkText: { color: colors.error, fontWeight: "600", fontSize: 13 },
  confirmLabel: { fontSize: 13, color: colors.text, fontWeight: "600", marginBottom: 8 },
  starRow: { flexDirection: "row", gap: 6 },
  star: { fontSize: 26 },
  logoutButton: {
    marginTop: 24,
    marginBottom: 24,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
