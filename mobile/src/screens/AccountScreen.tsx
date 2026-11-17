import React, { useEffect, useState, useCallback } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import NotificationBell from "../components/NotificationBell";
import Dropdown from "../components/Dropdown";
import GradientBackground from "../components/GradientBackground";
import {
  ApiError,
  fetchNotificationsUnreadCount,
  fetchInstitutions,
  fetchQualifications,
  fetchMyTutoringRequests,
  fetchProvinces,
  updateStudyDetails,
  updatePersonalInfo,
  Institution,
  Qualification,
  YEAR_LEVEL_LABELS,
} from "../api/client";

const ACCOUNT_TYPE_LABEL: Record<string, string> = {
  high_school: "High School",
  higher_ed: "Higher Ed",
};

// Mirrors backend/db.py's SA_PROVINCES - used only if fetchProvinces()
// hasn't resolved yet (same fallback pattern as RegisterScreen.tsx).
const FALLBACK_PROVINCES = [
  "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
  "Mpumalanga", "Northern Cape", "North West", "Western Cape",
];

function formatDateJoined(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

export default function AccountScreen({ navigation }: any) {
  const { token, me, logout, refreshMe } = useAuth();
  const insets = useSafeAreaInsets();
  const [unreadCount, setUnreadCount] = useState(0);
  const [institutions, setInstitutions] = useState<Institution[] | null>(null);
  const [qualifications, setQualifications] = useState<Qualification[] | null>(null);
  const [sessionsCompleted, setSessionsCompleted] = useState<number | null>(null);

  // Editing study details (institution/qualification/year/student number)
  // - lets a learner fill these in themselves if they're missing (e.g. an
  // account created some other way than the normal higher-ed registration
  // flow), rather than being stuck seeing "—" forever with no fix.
  const [editingStudyDetails, setEditingStudyDetails] = useState(false);
  const [draftInstitutionId, setDraftInstitutionId] = useState<number | null>(null);
  const [draftQualificationId, setDraftQualificationId] = useState<number | null>(null);
  const [draftIsCustomQualification, setDraftIsCustomQualification] = useState(false);
  const [draftCustomQualificationName, setDraftCustomQualificationName] = useState("");
  const [draftYearOfStudy, setDraftYearOfStudy] = useState<number | null>(null);
  const [draftStudentNumber, setDraftStudentNumber] = useState("");
  const [draftQualifications, setDraftQualifications] = useState<Qualification[]>([]);
  const [savingStudyDetails, setSavingStudyDetails] = useState(false);
  const [studyDetailsError, setStudyDetailsError] = useState<string | null>(null);

  // Editing personal info (province/city-town, plus school/grade for a
  // high-school account) - id_number stays read-only (see
  // backend/auth.py's update_personal_info for why).
  const [provinces, setProvinces] = useState<string[]>(FALLBACK_PROVINCES);
  const [editingPersonalInfo, setEditingPersonalInfo] = useState(false);
  const [draftProvince, setDraftProvince] = useState<string | null>(null);
  const [draftCityTown, setDraftCityTown] = useState("");
  const [draftSchool, setDraftSchool] = useState("");
  const [draftGrade, setDraftGrade] = useState<number | null>(null);
  const [savingPersonalInfo, setSavingPersonalInfo] = useState(false);
  const [personalInfoError, setPersonalInfoError] = useState<string | null>(null);

  const isHigherEd = me?.user.account_type === "higher_ed";
  const firstName = me?.user.name.split(" ")[0] ?? "";

  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      fetchNotificationsUnreadCount(token).then((res) => setUnreadCount(res.count)).catch(() => {});
      fetchMyTutoringRequests(token).then((res) => setSessionsCompleted(res.completed_count)).catch(() => {});
    }, [token])
  );

  // Only the IDs are on `me` - resolve them to display names from the same
  // catalog endpoints RequestTutorScreen already uses for its pickers.
  useEffect(() => {
    if (!isHigherEd) return;
    fetchInstitutions().then((res) => setInstitutions(res.institutions)).catch(() => {});
  }, [isHigherEd]);

  useEffect(() => {
    fetchProvinces()
      .then((res) => setProvinces(res.provinces))
      .catch(() => {
        // Non-fatal - FALLBACK_PROVINCES is already in state.
      });
  }, []);

  useEffect(() => {
    if (!me?.user.higher_ed_institution_id) return;
    fetchQualifications(me.user.higher_ed_institution_id)
      .then((res) => setQualifications(res.qualifications))
      .catch(() => {});
  }, [me?.user.higher_ed_institution_id]);

  // The edit form's own institution picker needs qualifications re-fetched
  // whenever ITS selection changes, independent of the committed value above.
  useEffect(() => {
    setDraftQualificationId(null);
    if (!draftInstitutionId) {
      setDraftQualifications([]);
      return;
    }
    fetchQualifications(draftInstitutionId).then((res) => setDraftQualifications(res.qualifications)).catch(() => {});
  }, [draftInstitutionId]);

  const institutionName = institutions?.find((i) => i.id === me?.user.higher_ed_institution_id)?.name;
  const qualificationName =
    me?.user.higher_ed_qualification_custom_name ||
    qualifications?.find((q) => q.id === me?.user.higher_ed_qualification_id)?.name;

  function openEditStudyDetails() {
    setStudyDetailsError(null);
    setDraftInstitutionId(me?.user.higher_ed_institution_id ?? null);
    const hasCustom = !!me?.user.higher_ed_qualification_custom_name;
    setDraftIsCustomQualification(hasCustom);
    setDraftCustomQualificationName(me?.user.higher_ed_qualification_custom_name ?? "");
    setDraftQualificationId(hasCustom ? null : me?.user.higher_ed_qualification_id ?? null);
    setDraftYearOfStudy(me?.user.higher_ed_year_of_study ?? null);
    setDraftStudentNumber(me?.user.student_number ?? "");
    setEditingStudyDetails(true);
  }

  async function handleSaveStudyDetails() {
    if (!token) return;
    setStudyDetailsError(null);
    setSavingStudyDetails(true);
    try {
      await updateStudyDetails(token, {
        higher_ed_institution_id: draftInstitutionId,
        higher_ed_qualification_id: draftIsCustomQualification ? null : draftQualificationId,
        higher_ed_qualification_custom_name: draftIsCustomQualification ? draftCustomQualificationName.trim() : "",
        higher_ed_year_of_study: draftYearOfStudy,
        student_number: draftStudentNumber.trim(),
      });
      await refreshMe();
      setEditingStudyDetails(false);
    } catch (e) {
      setStudyDetailsError(e instanceof ApiError ? e.message : "Could not save your study details.");
    } finally {
      setSavingStudyDetails(false);
    }
  }

  function openEditPersonalInfo() {
    setPersonalInfoError(null);
    setDraftProvince(me?.user.province ?? null);
    setDraftCityTown(me?.user.city_town ?? "");
    setDraftSchool(me?.user.school ?? "");
    setDraftGrade(me?.user.grade ?? null);
    setEditingPersonalInfo(true);
  }

  async function handleSavePersonalInfo() {
    if (!token) return;
    setPersonalInfoError(null);
    setSavingPersonalInfo(true);
    try {
      await updatePersonalInfo(token, {
        province: draftProvince ?? "",
        city_town: draftCityTown.trim(),
        school: isHigherEd ? undefined : draftSchool.trim(),
        grade: isHigherEd ? undefined : draftGrade,
      });
      await refreshMe();
      setEditingPersonalInfo(false);
    } catch (e) {
      setPersonalInfoError(e instanceof ApiError ? e.message : "Could not save your personal info.");
    } finally {
      setSavingPersonalInfo(false);
    }
  }

  if (!me) return null;

  return (
    <GradientBackground>
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      <View style={[styles.headerRow, { paddingTop: insets.top + 12 }]}>
        <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
          <Text style={styles.backLinkText}>‹ Back to Home</Text>
        </Pressable>
        <NotificationBell
          count={unreadCount}
          onPress={() => navigation.navigate("Notifications")}
          color={colors.text}
          size={22}
        />
      </View>

      <View style={styles.profileRow}>
        <View style={styles.avatarBadge}>
          <Text style={styles.avatarBadgeText}>{firstName.charAt(0).toUpperCase() || "?"}</Text>
        </View>
        <View style={styles.profileTextCol}>
          <Text style={styles.name}>{me.user.name}</Text>
          <Text style={styles.email}>{me.user.email}</Text>
        </View>
      </View>

      <View style={styles.pillRow}>
        <View style={styles.pill}>
          <Text style={styles.pillText}>{ACCOUNT_TYPE_LABEL[me.user.account_type] ?? me.user.account_type}</Text>
        </View>
        {me.is_admin ? (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Admin</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.card}>
        <View style={styles.sectionLabelRow}>
          <Text style={styles.sectionLabel}>Personal info</Text>
          {!editingPersonalInfo ? (
            <Pressable onPress={openEditPersonalInfo}>
              <Text style={styles.editLinkText}>Edit</Text>
            </Pressable>
          ) : null}
        </View>

        {editingPersonalInfo ? (
          <>
            <Dropdown
              label="Province"
              options={provinces.map((p) => ({ label: p, value: p }))}
              value={draftProvince}
              onChange={setDraftProvince}
            />
            <Text style={styles.fieldLabel}>City / Town</Text>
            <TextInput style={styles.input} value={draftCityTown} onChangeText={setDraftCityTown} />

            {!isHigherEd ? (
              <>
                <Text style={styles.fieldLabel}>School</Text>
                <TextInput style={styles.input} value={draftSchool} onChangeText={setDraftSchool} />
                <Dropdown
                  label="Grade"
                  options={[10, 11, 12].map((g) => ({ label: `Grade ${g}`, value: String(g) }))}
                  value={draftGrade != null ? String(draftGrade) : null}
                  onChange={(v) => setDraftGrade(parseInt(v, 10))}
                />
              </>
            ) : null}

            {personalInfoError ? <Text style={styles.error}>{personalInfoError}</Text> : null}

            <View style={styles.editButtonRow}>
              <Pressable
                style={styles.cancelEditButton}
                onPress={() => setEditingPersonalInfo(false)}
                disabled={savingPersonalInfo}
              >
                <Text style={styles.cancelEditButtonText}>Cancel</Text>
              </Pressable>
              <Pressable style={styles.saveEditButton} onPress={handleSavePersonalInfo} disabled={savingPersonalInfo}>
                {savingPersonalInfo ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveEditButtonText}>Save</Text>}
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Province</Text>
              <Text style={styles.detailValue}>{me.user.province ?? "—"}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>City / Town</Text>
              <Text style={styles.detailValue}>{me.user.city_town ?? "—"}</Text>
            </View>
            {!isHigherEd ? (
              <>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>School</Text>
                  <Text style={styles.detailValue}>{me.user.school ?? "—"}</Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Grade</Text>
                  <Text style={styles.detailValue}>{me.user.grade ?? "—"}</Text>
                </View>
              </>
            ) : null}
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>ID number</Text>
              <Text style={styles.detailValue}>{me.user.id_number ?? "—"}</Text>
            </View>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionLabel}>Lifetime</Text>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Sessions held</Text>
          <Text style={styles.detailValue}>{sessionsCompleted ?? "—"}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Date joined</Text>
          <Text style={styles.detailValue}>{formatDateJoined(me.user.created_at)}</Text>
        </View>
      </View>

      {isHigherEd ? (
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
                  />
                </>
              )}
              <Dropdown
                label="Year of study"
                options={Object.entries(YEAR_LEVEL_LABELS).map(([k, v]) => ({ label: v, value: k }))}
                value={draftYearOfStudy != null ? String(draftYearOfStudy) : null}
                onChange={(v) => setDraftYearOfStudy(parseInt(v, 10))}
              />
              <Text style={styles.fieldLabel}>Student number</Text>
              <TextInput style={styles.input} value={draftStudentNumber} onChangeText={setDraftStudentNumber} />

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
                  {me.user.higher_ed_year_of_study != null ? YEAR_LEVEL_LABELS[me.user.higher_ed_year_of_study] ?? "—" : "—"}
                </Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Student number</Text>
                <Text style={styles.detailValue}>{me.user.student_number ?? "—"}</Text>
              </View>
            </>
          )}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>Plan</Text>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Current plan</Text>
            <Text style={styles.detailValue}>{me.tier_label}</Text>
          </View>
          {me.daily_limit != null ? (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Solves today</Text>
              <Text style={styles.detailValue}>
                {me.used_today} / {me.daily_limit}
              </Text>
            </View>
          ) : null}
          <Pressable style={styles.managePlanLink} onPress={() => navigation.navigate("Subscription")}>
            <Text style={styles.managePlanLinkText}>Manage plan ›</Text>
          </Pressable>
        </View>
      )}

      <Pressable style={styles.supportCard} onPress={() => navigation.navigate("Support")}>
        <Text style={styles.supportCardText}>Contact Support</Text>
        <Text style={styles.supportCardChevron}>›</Text>
      </Pressable>

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </ScrollView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, paddingBottom: 40 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backLink: { alignSelf: "flex-start" },
  backLinkText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13 },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 14, marginTop: 20 },
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
  pill: { backgroundColor: colors.primary, borderRadius: 999, paddingVertical: 6, paddingHorizontal: 14 },
  pillText: { fontSize: 12, fontWeight: "700", color: "#fff" },
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
  editLinkText: { fontSize: 12, fontWeight: "700", color: colors.primary, marginBottom: 10 },
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
  error: { color: colors.error, marginTop: 12, fontSize: 13 },
  managePlanLink: { marginTop: 6 },
  managePlanLinkText: { fontSize: 13, fontWeight: "700", color: colors.primary },
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
  logoutButton: {
    marginTop: 28,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
