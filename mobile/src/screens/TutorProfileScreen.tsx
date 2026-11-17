import React, { useCallback, useEffect, useState } from "react";
import { View, Text, TextInput, StyleSheet, ScrollView, ActivityIndicator, Pressable, Alert, Switch } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import Dropdown from "../components/Dropdown";
import GradientBackground from "../components/GradientBackground";
import {
  ApiError,
  TutorProfile,
  Institution,
  Qualification,
  fetchTutorMyProfile,
  fetchTutorMyPayouts,
  updateTutorProfile,
  updateTutorAcceptingSessions,
  updateTutorStudyDetails,
  deleteTutorAccount,
  fetchInstitutions,
  fetchQualifications,
  YEAR_LEVEL_LABELS,
} from "../api/client";

const STATUS_COLOR: Record<string, string> = {
  // A solid tone (not colors.textSecondary's translucent white) - this
  // fills a pill behind white text, where translucency would wash out.
  pending_review: "#5b5570",
  approved: colors.success,
  rejected: colors.error,
  suspended: colors.error,
};

const BADGE_COLORS: Record<string, string> = { bronze: "#cd7f32", silver: "#9aa0a6", gold: "#eda100" };

function formatDateJoined(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

export default function TutorProfileScreen({ navigation }: any) {
  const { token, logout } = useTutorAuth();
  const [profile, setProfile] = useState<TutorProfile | null>(null);
  const [totalEarned, setTotalEarned] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Editing personal info (phone/bio/availability).
  const [editingPersonal, setEditingPersonal] = useState(false);
  const [draftPhone, setDraftPhone] = useState("");
  const [draftBio, setDraftBio] = useState("");
  const [draftAvailability, setDraftAvailability] = useState("");
  const [savingPersonal, setSavingPersonal] = useState(false);
  const [personalError, setPersonalError] = useState<string | null>(null);

  // Editing study details (institution/qualification/year) - same
  // pattern as AccountScreen.tsx's learner-side edit.
  const [institutions, setInstitutions] = useState<Institution[] | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[] | null>(null);
  const [editingStudyDetails, setEditingStudyDetails] = useState(false);
  const [draftInstitutionId, setDraftInstitutionId] = useState<number | null>(null);
  const [draftQualificationId, setDraftQualificationId] = useState<number | null>(null);
  const [draftIsCustomQualification, setDraftIsCustomQualification] = useState(false);
  const [draftCustomQualificationName, setDraftCustomQualificationName] = useState("");
  const [draftYearOfStudy, setDraftYearOfStudy] = useState<number | null>(null);
  const [draftQualifications, setDraftQualifications] = useState<Qualification[]>([]);
  const [savingStudyDetails, setSavingStudyDetails] = useState(false);
  const [studyDetailsError, setStudyDetailsError] = useState<string | null>(null);

  const [deletingAccount, setDeletingAccount] = useState(false);

  // Pausing/resuming new bookings - see client.ts's
  // updateTutorAcceptingSessions. togglingAccepting guards against a
  // double-tap firing two overlapping requests.
  const [togglingAccepting, setTogglingAccepting] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorMyProfile(token)
      .then(setProfile)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your profile."));
    fetchTutorMyPayouts(token)
      .then((res) => setTotalEarned(res.payouts.reduce((sum, p) => sum + p.amount_zar, 0)))
      .catch(() => {});
  }, [token]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  useEffect(() => {
    if (!profile?.wants_higher_ed) return;
    fetchInstitutions().then((res) => setInstitutions(res.institutions)).catch(() => {});
  }, [profile?.wants_higher_ed]);

  useEffect(() => {
    if (!profile?.higher_ed_institution_id) return;
    fetchQualifications(profile.higher_ed_institution_id)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => {});
  }, [profile?.higher_ed_institution_id]);

  useEffect(() => {
    setDraftQualificationId(null);
    if (!draftInstitutionId) {
      setDraftQualifications([]);
      return;
    }
    fetchQualifications(draftInstitutionId).then((res) => setDraftQualifications(res.qualifications)).catch(() => {});
  }, [draftInstitutionId]);

  function openEditPersonal() {
    setPersonalError(null);
    setDraftPhone(profile?.phone ?? "");
    setDraftBio(profile?.bio ?? "");
    setDraftAvailability(profile?.availability_note ?? "");
    setEditingPersonal(true);
  }

  async function handleSavePersonal() {
    if (!token) return;
    setPersonalError(null);
    setSavingPersonal(true);
    try {
      await updateTutorProfile(token, { phone: draftPhone.trim(), bio: draftBio.trim(), availability_note: draftAvailability.trim() });
      load();
      setEditingPersonal(false);
    } catch (e) {
      setPersonalError(e instanceof ApiError ? e.message : "Could not save your changes.");
    } finally {
      setSavingPersonal(false);
    }
  }

  function openEditStudyDetails() {
    setStudyDetailsError(null);
    setDraftInstitutionId(profile?.higher_ed_institution_id ?? null);
    const hasCustom = !!profile?.higher_ed_qualification_custom_name;
    setDraftIsCustomQualification(hasCustom);
    setDraftCustomQualificationName(profile?.higher_ed_qualification_custom_name ?? "");
    setDraftQualificationId(hasCustom ? null : profile?.higher_ed_qualification_id ?? null);
    setDraftYearOfStudy(profile?.higher_ed_year_of_study ?? null);
    setEditingStudyDetails(true);
  }

  async function handleSaveStudyDetails() {
    if (!token) return;
    setStudyDetailsError(null);
    setSavingStudyDetails(true);
    try {
      await updateTutorStudyDetails(token, {
        higher_ed_institution_id: draftInstitutionId,
        higher_ed_qualification_id: draftIsCustomQualification ? null : draftQualificationId,
        higher_ed_qualification_custom_name: draftIsCustomQualification ? draftCustomQualificationName.trim() : "",
        higher_ed_year_of_study: draftYearOfStudy,
      });
      load();
      setEditingStudyDetails(false);
    } catch (e) {
      setStudyDetailsError(e instanceof ApiError ? e.message : "Could not save your study details.");
    } finally {
      setSavingStudyDetails(false);
    }
  }

  async function handleToggleAccepting(next: boolean) {
    if (!token || togglingAccepting) return;
    setTogglingAccepting(true);
    setError(null);
    try {
      await updateTutorAcceptingSessions(token, next);
      // Update locally instead of calling load() (which fires off its
      // own fetch without awaiting it) - that fire-and-forget refetch
      // let setTogglingAccepting(false) below run, and the Switch come
      // back, BEFORE the refetch had actually resolved and updated
      // `profile` - so the Switch briefly flashed back to its OLD value,
      // looking like the tap hadn't registered and prompting a second
      // tap. We already know the new value for certain (the PATCH above
      // just succeeded), so there's no need to round-trip a GET to learn
      // it again.
      setProfile((p) => (p ? { ...p, accepting_new_sessions: next } : p));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update this setting.");
    } finally {
      setTogglingAccepting(false);
    }
  }

  async function runDeleteAccount() {
    if (!token) return;
    setDeletingAccount(true);
    setError(null);
    try {
      await deleteTutorAccount(token);
      await logout();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete your account. Please try again.");
      setDeletingAccount(false);
    }
  }

  function handleDeleteAccount() {
    Alert.alert(
      "Delete your account?",
      "This permanently deletes your Malita tutor account. If you have any completed session history, your " +
        "personal details are removed but that history stays on record (it's also part of the learners' own " +
        "history and Malita's payout records). This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Delete my account", style: "destructive", onPress: runDeleteAccount },
      ]
    );
  }

  if (!profile) {
    return (
      <GradientBackground style={styles.loadingContainer}>
        {error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator color={colors.primary} />}
      </GradientBackground>
    );
  }

  const firstLetter = profile.name.charAt(0).toUpperCase() || "?";
  const institutionName = institutions?.find((i) => i.id === profile.higher_ed_institution_id)?.name;
  const qualificationName =
    profile.higher_ed_qualification_custom_name ||
    qualifications?.find((q) => q.id === profile.higher_ed_qualification_id)?.name;

  return (
    <GradientBackground>
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
      <View style={styles.profileRow}>
        <View style={styles.avatarBadge}>
          <Text style={styles.avatarBadgeText}>{firstLetter}</Text>
        </View>
        <View style={styles.profileTextCol}>
          <Text style={styles.name}>{profile.name}</Text>
          <Text style={styles.email}>{profile.email}</Text>
        </View>
      </View>

      <View style={styles.pillRow}>
        <View style={[styles.pill, { backgroundColor: STATUS_COLOR[profile.status] ?? colors.primary }]}>
          <Text style={styles.pillTextLight}>{profile.status_label}</Text>
        </View>
        {profile.badge ? (
          <View style={[styles.pill, { backgroundColor: BADGE_COLORS[profile.badge] }]}>
            <Text style={styles.pillTextLight}>{profile.badge.toUpperCase()}</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.card}>
        <View style={styles.acceptingRow}>
          <View style={styles.acceptingTextCol}>
            <Text style={styles.sectionLabel}>Accepting new sessions</Text>
            <Text style={styles.acceptingHint}>
              {profile.accepting_new_sessions
                ? "Learners can find and book you for new sessions."
                : "You're hidden from Browse Tutors and won't be offered new requests. Sessions already booked are unaffected."}
            </Text>
          </View>
          {togglingAccepting ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <Switch
              value={profile.accepting_new_sessions}
              onValueChange={handleToggleAccepting}
              trackColor={{ true: colors.primary }}
            />
          )}
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.sectionLabelRow}>
          <Text style={styles.sectionLabel}>Personal info</Text>
          {!editingPersonal ? (
            <Pressable onPress={openEditPersonal}>
              <Text style={styles.editLinkText}>Edit</Text>
            </Pressable>
          ) : null}
        </View>

        {editingPersonal ? (
          <>
            <Text style={styles.fieldLabel}>Phone</Text>
            <TextInput style={styles.input} value={draftPhone} onChangeText={setDraftPhone} keyboardType="phone-pad" />
            <Text style={styles.fieldLabel}>Bio</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={draftBio}
              onChangeText={setDraftBio}
              placeholder="Tell learners a bit about yourself"
              placeholderTextColor={colors.inputPlaceholder}
              multiline
            />
            <Text style={styles.fieldLabel}>Availability</Text>
            <TextInput
              style={styles.input}
              value={draftAvailability}
              onChangeText={setDraftAvailability}
              placeholder="e.g. Weekdays after 16:00, Saturday mornings"
              placeholderTextColor={colors.inputPlaceholder}
            />
            {personalError ? <Text style={styles.error}>{personalError}</Text> : null}
            <View style={styles.editButtonRow}>
              <Pressable style={styles.cancelEditButton} onPress={() => setEditingPersonal(false)} disabled={savingPersonal}>
                <Text style={styles.cancelEditButtonText}>Cancel</Text>
              </Pressable>
              <Pressable style={styles.saveEditButton} onPress={handleSavePersonal} disabled={savingPersonal}>
                {savingPersonal ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveEditButtonText}>Save</Text>}
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Phone</Text>
              <Text style={styles.detailValue}>{profile.phone ?? "—"}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Availability</Text>
              <Text style={styles.detailValue}>{profile.availability_note ?? "—"}</Text>
            </View>
            {profile.bio ? (
              <>
                <Text style={styles.fieldLabel}>Bio</Text>
                <Text style={styles.bioText}>{profile.bio}</Text>
              </>
            ) : null}
          </>
        )}
      </View>

      {profile.wants_higher_ed ? (
        <View style={styles.card}>
          <View style={styles.sectionLabelRow}>
            <Text style={styles.sectionLabel}>Study details</Text>
            {!editingStudyDetails ? (
              <Pressable onPress={openEditStudyDetails}>
                <Text style={styles.editLinkText}>Edit</Text>
              </Pressable>
            ) : null}
          </View>

          {editingStudyDetails ? (
            <>
              <Dropdown
                label="Institution"
                options={(institutions ?? []).map((i) => ({ label: i.name, value: String(i.id) }))}
                value={draftInstitutionId != null ? String(draftInstitutionId) : null}
                onChange={(v) => setDraftInstitutionId(parseInt(v, 10))}
              />
              <Dropdown
                label="Qualification"
                options={[
                  ...draftQualifications.map((q) => ({ label: q.name, value: String(q.id) })),
                  { label: "Other (not listed)", value: "other" },
                ]}
                value={
                  draftIsCustomQualification ? "other" : draftQualificationId != null ? String(draftQualificationId) : null
                }
                onChange={(v) => {
                  if (v === "other") {
                    setDraftIsCustomQualification(true);
                    setDraftQualificationId(null);
                  } else {
                    setDraftIsCustomQualification(false);
                    setDraftQualificationId(parseInt(v, 10));
                  }
                }}
              />
              {draftIsCustomQualification && (
                <>
                  <Text style={styles.fieldLabel}>Your qualification</Text>
                  <TextInput
                    style={styles.input}
                    value={draftCustomQualificationName}
                    onChangeText={setDraftCustomQualificationName}
                    placeholder="e.g. BCom Investment Management"
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                </>
              )}
              <Dropdown
                label="Year of study"
                options={Object.entries(YEAR_LEVEL_LABELS).map(([k, v]) => ({ label: v, value: k }))}
                value={draftYearOfStudy != null ? String(draftYearOfStudy) : null}
                onChange={(v) => setDraftYearOfStudy(parseInt(v, 10))}
              />
              {studyDetailsError ? <Text style={styles.error}>{studyDetailsError}</Text> : null}
              <View style={styles.editButtonRow}>
                <Pressable
                  style={styles.cancelEditButton}
                  onPress={() => setEditingStudyDetails(false)}
                  disabled={savingStudyDetails}
                >
                  <Text style={styles.cancelEditButtonText}>Cancel</Text>
                </Pressable>
                <Pressable style={styles.saveEditButton} onPress={handleSaveStudyDetails} disabled={savingStudyDetails}>
                  {savingStudyDetails ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveEditButtonText}>Save</Text>}
                </Pressable>
              </View>
            </>
          ) : (
            <>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Institution</Text>
                <Text style={styles.detailValue}>{institutionName ?? "—"}</Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Qualification</Text>
                <Text style={styles.detailValue}>{qualificationName ?? "—"}</Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Year of study</Text>
                <Text style={styles.detailValue}>
                  {profile.higher_ed_year_of_study != null ? YEAR_LEVEL_LABELS[profile.higher_ed_year_of_study] ?? "—" : "—"}
                </Text>
              </View>
            </>
          )}
        </View>
      ) : null}

      <View style={styles.card}>
        <Text style={styles.sectionLabel}>Lifetime</Text>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Sessions completed</Text>
          <Text style={styles.detailValue}>{profile.sessions_completed}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Total earned</Text>
          <Text style={styles.detailValue}>{totalEarned != null ? `R${totalEarned.toFixed(0)}` : "—"}</Text>
        </View>
        {profile.average_rating != null ? (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Average rating</Text>
            <Text style={styles.detailValue}>{profile.average_rating.toFixed(1)}★</Text>
          </View>
        ) : null}
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Date joined</Text>
          <Text style={styles.detailValue}>{formatDateJoined(profile.created_at)}</Text>
        </View>
      </View>

      <Pressable style={styles.supportCard} onPress={() => navigation.navigate("TutorSupport")}>
        <Text style={styles.supportCardText}>Contact Support</Text>
        <Text style={styles.supportCardChevron}>›</Text>
      </Pressable>

      <View style={styles.deleteAccountSection}>
        <Text style={styles.deleteAccountTitle}>Account</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable style={styles.deleteAccountButton} onPress={handleDeleteAccount} disabled={deletingAccount}>
          {deletingAccount ? (
            <ActivityIndicator color={colors.error} />
          ) : (
            <Text style={styles.deleteAccountButtonText}>Delete My Account</Text>
          )}
        </Pressable>
      </View>
    </ScrollView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center" },
  container: { flexGrow: 1, padding: 20, paddingBottom: 40 },
  error: { color: colors.error, marginTop: 8 },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  avatarBadge: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: colors.primaryDark,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadgeText: { fontSize: 20, fontWeight: "800", color: "#fff" },
  profileTextCol: { flex: 1, minWidth: 0 },
  name: { fontSize: 19, fontWeight: "800", color: colors.text },
  email: { fontSize: 13, color: colors.textSecondary, marginTop: 2 },
  pillRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  pill: { borderRadius: 999, paddingVertical: 6, paddingHorizontal: 14 },
  pillTextLight: { fontSize: 12, fontWeight: "700", color: "#fff" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  sectionLabel: { fontSize: 12, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 10 },
  sectionLabelRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  acceptingRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  acceptingTextCol: { flex: 1 },
  acceptingHint: { fontSize: 12, color: colors.textSecondary, marginTop: 2, lineHeight: 17 },
  editLinkText: { fontSize: 12, fontWeight: "700", color: colors.primary, marginBottom: 10 },
  bioText: { fontSize: 14, color: colors.text, lineHeight: 20 },
  detailRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 7 },
  detailLabel: { fontSize: 13, color: colors.textSecondary },
  detailValue: { fontSize: 13, fontWeight: "700", color: colors.text },
  fieldLabel: { fontSize: 13, color: colors.textSecondary, marginTop: 10, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.inputText,
    backgroundColor: colors.inputBackground,
  },
  textArea: { minHeight: 80, textAlignVertical: "top" },
  editButtonRow: { flexDirection: "row", gap: 10, marginTop: 16 },
  cancelEditButton: {
    flex: 1,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  cancelEditButtonText: { color: colors.text, fontWeight: "700", fontSize: 14 },
  saveEditButton: { flex: 1, backgroundColor: colors.primary, borderRadius: 999, paddingVertical: 12, alignItems: "center" },
  saveEditButtonText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  supportCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  supportCardText: { fontSize: 14, fontWeight: "700", color: colors.text },
  supportCardChevron: { fontSize: 16, color: colors.textSecondary },
  deleteAccountSection: {
    marginTop: 32,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  deleteAccountTitle: { fontSize: 13, color: colors.textSecondary, marginBottom: 8 },
  deleteAccountButton: { alignSelf: "flex-start" },
  deleteAccountButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
});
