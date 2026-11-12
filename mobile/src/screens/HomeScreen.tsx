import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { fetchNotificationsUnreadCount } from "../api/client";
import NotificationBell from "../components/NotificationBell";

// `group` only matters for the Explore list (quick-action tiles don't use
// it) - it's how the list gets sub-headers instead of one long flat stack.
type Tile = { key: string; icon: string; title: string; desc: string; tierNote?: string; color: string; disabled?: boolean; group?: string };

const TILES: Tile[] = [
  {
    key: "AITutor",
    icon: "calculator",
    title: "AI Tutor",
    desc: "Type a question, snap or upload a photo, or upload a PDF — all solved step by step.",
    color: "#2a78d6",
  },
  {
    key: "AITeacher",
    icon: "chart",
    title: "AI Teacher",
    desc: "A narrated, live-style lesson on any topic you choose.",
    tierNote: "Premium",
    color: "#eda100",
    group: "Learning Tools",
  },
  {
    key: "PracticeQuestions",
    icon: "pencil",
    title: "Practice Questions",
    desc: "Work through real Grade 12 questions with hints and worked solutions.",
    color: "#eb6834",
  },
  {
    key: "PastPapersLibrary",
    icon: "folder",
    title: "Past Papers Library",
    desc: "Browse curated past exam papers by year and subject.",
    tierNote: "Premium",
    color: "#4a3aa7",
    group: "Learning Tools",
  },
  {
    key: "Collab",
    icon: "people",
    title: "Collaboration Forum",
    desc: "Ask a question or help another learner.",
    tierNote: "Learner & Premium",
    color: "#1baf7a",
    group: "Learning Tools",
  },
  {
    key: "LearnerProfile",
    icon: "target",
    title: "Learner Profile",
    desc: "Track your progress, badges, and solved-question history.",
    color: "#c0392b",
    group: "Your Account",
  },
  {
    key: "RequestTutor",
    icon: "calendarCheck",
    title: "Request a Tutor",
    desc: "Book a 1-on-1 tutoring session. Billed separately, open to every plan.",
    color: "#e87ba4",
  },
  {
    key: "BrowseTutors",
    icon: "search",
    title: "Browse Tutors",
    desc: "See tutors' subjects/modules, availability, and rates, and pick one directly.",
    color: "#2fa88a",
  },
];

const ADMIN_TILE: Tile = {
  key: "TutoringAdmin",
  icon: "wrench",
  title: "Tutoring Admin",
  desc: "Review tutor applications, match requests, and process payouts.",
  color: "#4a3aa7",
  group: "Admin",
};

// Fixed display order for the Explore list's sub-headers - a tile with no
// group (e.g. Practice Questions, already a quick action) never reaches
// this list, so every entry here is expected to match a group above.
const EXPLORE_GROUP_ORDER = ["Learning Tools", "Your Account", "Admin"];

// The 4 most-used actions get a quick-action square instead of a full list
// row - everything else (including the admin tile, appended below) lives in
// the "Explore" list.
const QUICK_ACTION_KEYS = ["AITutor", "RequestTutor", "BrowseTutors", "PracticeQuestions"];

// University/college accounts get ONLY the tutoring marketplace - every
// other tile above (AI Tutor, past papers, subscription, etc.) is simply
// never shown, same gating principle as app.py's web equivalent.
const HIGHER_ED_TILES: Tile[] = TILES.filter((t) => t.key === "RequestTutor" || t.key === "BrowseTutors");

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

// Built from plain Views/Text (no SVG dependency - react-native-svg isn't
// installed in this project, and TutorHomeScreen's own redesign deliberately
// avoided adding it too) instead of emoji, same "clean abstract icon, not a
// picture" goal as the Jobs screen redesign.
function TileIcon({ name, size = 20, color = "#fff" }: { name: string; size?: number; color?: string }) {
  const box = { width: size, height: size, alignItems: "center" as const, justifyContent: "center" as const };
  switch (name) {
    case "calculator":
      return (
        <View style={[box, { borderWidth: 1.5, borderColor: color, borderRadius: size * 0.22, padding: size * 0.12 }]}>
          <View style={{ flex: 1, flexDirection: "row", flexWrap: "wrap", alignContent: "space-between", justifyContent: "space-between" }}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <View key={i} style={{ width: size * 0.12, height: size * 0.12, borderRadius: 999, backgroundColor: color }} />
            ))}
          </View>
        </View>
      );
    case "calendarCheck":
      return (
        <View style={[box]}>
          <View style={{ width: size * 0.9, height: size * 0.75, borderWidth: 1.5, borderColor: color, borderRadius: size * 0.15 }}>
            <View style={{ height: size * 0.18, borderBottomWidth: 1.5, borderBottomColor: color }} />
          </View>
        </View>
      );
    case "search":
      return (
        <View style={[box, { position: "relative" }]}>
          <View
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: size * 0.7,
              height: size * 0.7,
              borderRadius: 999,
              borderWidth: 1.6,
              borderColor: color,
            }}
          />
          <View
            style={{
              position: "absolute",
              right: size * 0.02,
              bottom: size * 0.02,
              width: 1.6,
              height: size * 0.32,
              backgroundColor: color,
              borderRadius: 1,
              transform: [{ rotate: "45deg" }],
            }}
          />
        </View>
      );
    case "pencil":
      return (
        <View style={box}>
          <View style={{ width: size * 0.85, height: size * 0.22, borderRadius: 3, backgroundColor: color, transform: [{ rotate: "-45deg" }] }} />
        </View>
      );
    case "chart":
      return (
        <View style={[box, { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }]}>
          <View style={{ width: size * 0.18, height: size * 0.45, backgroundColor: color, borderRadius: 1 }} />
          <View style={{ width: size * 0.18, height: size * 0.7, backgroundColor: color, borderRadius: 1 }} />
          <View style={{ width: size * 0.18, height: size * 0.95, backgroundColor: color, borderRadius: 1 }} />
        </View>
      );
    case "folder":
      return (
        <View style={[box, { position: "relative" }]}>
          <View
            style={{
              position: "absolute",
              top: size * 0.08,
              left: size * 0.08,
              width: size * 0.4,
              height: size * 0.16,
              borderRadius: 2,
              backgroundColor: color,
            }}
          />
          <View
            style={{
              position: "absolute",
              bottom: 0,
              width: size * 0.9,
              height: size * 0.65,
              borderRadius: 3,
              backgroundColor: color,
            }}
          />
        </View>
      );
    case "people":
      return (
        <View style={[box, { position: "relative" }]}>
          <View
            style={{
              position: "absolute",
              left: 0,
              top: size * 0.15,
              width: size * 0.6,
              height: size * 0.6,
              borderRadius: 999,
              borderWidth: 1.5,
              borderColor: color,
            }}
          />
          <View
            style={{
              position: "absolute",
              right: 0,
              top: 0,
              width: size * 0.6,
              height: size * 0.6,
              borderRadius: 999,
              borderWidth: 1.5,
              borderColor: color,
              backgroundColor: "transparent",
            }}
          />
        </View>
      );
    case "target":
      return (
        <View style={[box, { position: "relative" }]}>
          <View style={{ position: "absolute", width: size * 0.9, height: size * 0.9, borderRadius: 999, borderWidth: 1.4, borderColor: color }} />
          <View style={{ position: "absolute", width: size * 0.55, height: size * 0.55, borderRadius: 999, borderWidth: 1.4, borderColor: color }} />
          <View style={{ position: "absolute", width: size * 0.18, height: size * 0.18, borderRadius: 999, backgroundColor: color }} />
        </View>
      );
    case "wrench":
      return (
        <View style={[box, { flexDirection: "row", gap: size * 0.1 }]}>
          <View style={{ width: size * 0.14, height: size * 0.14, borderRadius: 999, backgroundColor: color }} />
          <View style={{ width: size * 0.14, height: size * 0.14, borderRadius: 999, backgroundColor: color }} />
          <View style={{ width: size * 0.14, height: size * 0.14, borderRadius: 999, backgroundColor: color }} />
        </View>
      );
    case "chevron":
      return <Text style={{ fontSize: size * 0.95, fontWeight: "700", color, lineHeight: size }}>{"›"}</Text>;
    case "home":
      return (
        <View style={[box, { position: "relative" }]}>
          <View
            style={{
              position: "absolute",
              bottom: 0,
              width: size * 0.82,
              height: size * 0.56,
              borderWidth: 1.6,
              borderColor: color,
              borderRadius: 2,
            }}
          />
          <View
            style={{
              position: "absolute",
              top: 0,
              width: 0,
              height: 0,
              borderLeftWidth: size * 0.48,
              borderRightWidth: size * 0.48,
              borderBottomWidth: size * 0.38,
              borderLeftColor: "transparent",
              borderRightColor: "transparent",
              borderBottomColor: color,
            }}
          />
        </View>
      );
    case "person":
      return (
        <View style={[box, { position: "relative" }]}>
          <View
            style={{
              position: "absolute",
              top: 0,
              width: size * 0.4,
              height: size * 0.4,
              borderRadius: 999,
              borderWidth: 1.6,
              borderColor: color,
            }}
          />
          <View
            style={{
              position: "absolute",
              bottom: 0,
              width: size * 0.78,
              height: size * 0.4,
              borderTopLeftRadius: size * 0.4,
              borderTopRightRadius: size * 0.4,
              borderWidth: 1.6,
              borderColor: color,
              borderBottomWidth: 0,
            }}
          />
        </View>
      );
    default:
      return null;
  }
}

// Quick-nav bar fixed at the bottom of Home - same custom-icon, no-SVG
// approach as the Jobs/My Requests bottom tab bars, but navigates across
// top-level screens (stack pushes) rather than switching an in-screen
// section, since Home/Requests/Browse/Account are separate registered
// routes, not sections of one screen.
const HOME_BOTTOM_TABS: { key: string; label: string; icon: string; route?: string }[] = [
  { key: "home", label: "Home", icon: "home" },
  { key: "requests", label: "Requests", icon: "calendarCheck", route: "MyTutoringRequests" },
  { key: "browse", label: "Browse", icon: "search", route: "BrowseTutors" },
  { key: "profile", label: "Profile", icon: "person", route: "Account" },
];

export default function HomeScreen({ navigation }: any) {
  const { token, me, logout } = useAuth();
  const insets = useSafeAreaInsets();
  const firstName = me?.user.name.split(" ")[0] ?? "";
  const [unreadCount, setUnreadCount] = useState(0);

  // Refreshed on focus only (no polling/websocket) - this screen now owns
  // its own header, including the notification bell, rather than relying
  // on RootNavigator's native header bar (previously a second, redundant
  // header stacked above this screen's own greeting row).
  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      fetchNotificationsUnreadCount(token).then((res) => setUnreadCount(res.count)).catch(() => {});
    }, [token])
  );
  // cross_segment_access (a rare admin override - see
  // backend/set_cross_segment_access.py) unlocks the full tile set and
  // subscription UI regardless of the account's own account_type.
  const isHigherEd = me?.user.account_type === "higher_ed" && !me?.user.cross_segment_access;
  const quickTiles = TILES.filter((t) => QUICK_ACTION_KEYS.includes(t.key));
  const exploreTiles = [
    ...TILES.filter((t) => !QUICK_ACTION_KEYS.includes(t.key)),
    ...(me?.is_admin ? [ADMIN_TILE] : []),
  ];
  const usagePct =
    me?.daily_limit != null ? Math.min(100, Math.round((me.used_today / me.daily_limit) * 100)) : null;

  function ListCard({ tile, big }: { tile: Tile; big?: boolean }) {
    const isAdminTile = tile.key === "TutoringAdmin";
    return (
      <Pressable
        key={tile.key}
        style={[styles.listCard, isAdminTile && styles.listCardAdmin]}
        onPress={() => !tile.disabled && navigation.navigate(tile.key)}
        disabled={tile.disabled}
      >
        <View
          style={[
            styles.listCardIcon,
            big && styles.listCardIconBig,
            { backgroundColor: isAdminTile ? colors.textSecondary : tile.color },
          ]}
        >
          <TileIcon name={tile.icon} size={big ? 22 : 20} />
        </View>
        <View style={styles.listCardTextCol}>
          <View style={styles.listCardTitleRow}>
            <Text style={[styles.listCardTitle, big && styles.listCardTitleBig]}>{tile.title}</Text>
            {tile.tierNote ? (
              <View style={styles.tierPill}>
                <Text style={styles.tierPillText}>{tile.tierNote.toUpperCase()}</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.listCardDesc}>{tile.desc}</Text>
        </View>
        <TileIcon name="chevron" size={18} color="#8a8984" />
      </Pressable>
    );
  }

  return (
    <View style={styles.screen}>
    <ScrollView style={styles.scrollView} contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <View>
          <Text style={styles.greetingLabel}>{greeting()}</Text>
          <Text style={styles.greetingName}>{firstName}</Text>
        </View>
        <View style={styles.headerRight}>
          <NotificationBell
            count={unreadCount}
            onPress={() => navigation.navigate("Notifications")}
            color={colors.text}
            size={22}
          />
          <View style={styles.avatarBadge}>
            <Text style={styles.avatarBadgeText}>{firstName.charAt(0).toUpperCase() || "?"}</Text>
          </View>
        </View>
      </View>

      <View style={styles.body}>
        {!isHigherEd ? (
          <>
            <View style={styles.statCard}>
              <View style={styles.statCardRow}>
                {me?.daily_limit != null ? (
                  <View>
                    <Text style={styles.statLabel}>Solves today</Text>
                    <Text style={styles.statValue}>
                      {me.used_today} <Text style={styles.statValueMax}>/ {me.daily_limit}</Text>
                    </Text>
                  </View>
                ) : (
                  <Text style={styles.statUnlimited}>Unlimited solves on your plan.</Text>
                )}
                <Pressable style={styles.planPill} onPress={() => navigation.navigate("Subscription")}>
                  <Text style={styles.planPillText}>{me?.tier_label ?? "Free"} plan</Text>
                  <TileIcon name="chevron" size={12} />
                </Pressable>
              </View>
              {usagePct != null ? (
                <View style={styles.usageTrack}>
                  <View style={[styles.usageFill, { width: `${usagePct}%` }]} />
                </View>
              ) : null}
            </View>

            <Text style={styles.sectionLabel}>Quick actions</Text>
            <View style={styles.quickRow}>
              {quickTiles.map((tile) => (
                <Pressable
                  key={tile.key}
                  style={styles.quickTile}
                  onPress={() => !tile.disabled && navigation.navigate(tile.key)}
                  disabled={tile.disabled}
                  accessibilityRole="button"
                  accessibilityLabel={tile.title}
                >
                  <View style={[styles.quickTileIcon, { backgroundColor: tile.color }]}>
                    <TileIcon name={tile.icon} size={24} />
                  </View>
                  <Text style={styles.quickTileLabel}>{tile.title}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.sectionLabel}>Explore</Text>
            {EXPLORE_GROUP_ORDER.map((groupName) => {
              const tiles = exploreTiles.filter((t) => t.group === groupName);
              if (tiles.length === 0) return null;
              return (
                <View key={groupName} style={styles.exploreGroup}>
                  <Text style={styles.exploreGroupLabel}>{groupName}</Text>
                  <View style={styles.listCol}>
                    {tiles.map((tile) => (
                      <ListCard key={tile.key} tile={tile} />
                    ))}
                  </View>
                </View>
              );
            })}
          </>
        ) : (
          <>
            <View style={styles.statCard}>
              <Text style={styles.statLabel}>Account</Text>
              <Text style={styles.statUnlimited}>Set up for tutoring</Text>
              <Text style={styles.higherEdNote}>
                Your plan only includes the human tutoring marketplace below - the AI features aren't part of it.
              </Text>
            </View>

            <View style={[styles.listCol, { marginTop: 20 }]}>
              {HIGHER_ED_TILES.map((tile) => (
                <ListCard key={tile.key} tile={tile} big />
              ))}
            </View>
          </>
        )}

        <Pressable style={styles.logoutButton} onPress={logout}>
          <Text style={styles.logoutText}>Log Out</Text>
        </Pressable>
      </View>
    </ScrollView>

    <View style={[styles.bottomBar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
      {HOME_BOTTOM_TABS.map((tab) => {
        const active = tab.key === "home";
        const tint = active ? colors.primary : "#8a8984";
        return (
          <Pressable
            key={tab.key}
            style={styles.bottomBarItem}
            onPress={() => tab.route && navigation.navigate(tab.route)}
            accessibilityRole="button"
            accessibilityLabel={tab.label}
          >
            <TileIcon name={tab.icon} size={20} color={tint} />
            <Text style={[styles.bottomBarLabel, { color: tint, fontWeight: active ? "700" : "500" }]}>
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  scrollView: { flex: 1 },
  container: { backgroundColor: colors.background, flexGrow: 1 },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    paddingHorizontal: 20,
  },
  greetingLabel: { fontSize: 13, color: colors.textSecondary, fontWeight: "600" },
  greetingName: { fontSize: 22, fontWeight: "800", color: colors.text, marginTop: 2 },
  headerRight: { flexDirection: "row", alignItems: "center" },
  avatarBadge: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: "#0b0b0b",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadgeText: { fontSize: 15, fontWeight: "800", color: "#fff" },
  body: { padding: 20 },
  statCard: { backgroundColor: "#0b0b0b", borderRadius: 20, padding: 18 },
  statCardRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  statLabel: { fontSize: 11, color: "#b9b8b3", fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.4 },
  statValue: { fontSize: 26, color: "#fff", fontWeight: "800", marginTop: 4 },
  statValueMax: { fontSize: 15, color: "#8a8984", fontWeight: "600" },
  statUnlimited: { fontSize: 16, color: "#fff", fontWeight: "700", marginTop: 4, maxWidth: 200 },
  higherEdNote: { fontSize: 12, color: "#8a8984", marginTop: 6, lineHeight: 17 },
  planPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(255,255,255,0.1)",
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  planPillText: { fontSize: 12, fontWeight: "700", color: "#fff" },
  usageTrack: { marginTop: 14, height: 6, borderRadius: 999, backgroundColor: "#2b2b29", overflow: "hidden" },
  usageFill: { height: "100%", backgroundColor: "#4ade9a", borderRadius: 999 },
  sectionLabel: { fontSize: 13, fontWeight: "700", color: colors.text, marginTop: 20, marginBottom: 10 },
  exploreGroup: { marginTop: 4 },
  exploreGroupLabel: {
    fontSize: 11,
    fontWeight: "700",
    color: colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginTop: 14,
    marginBottom: 8,
  },
  quickRow: { flexDirection: "row", gap: 10 },
  quickTile: { flex: 1, alignItems: "center", gap: 8 },
  quickTileIcon: {
    width: 56,
    height: 56,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  quickTileLabel: { fontSize: 11, fontWeight: "600", color: colors.text, textAlign: "center" },
  listCol: { gap: 10 },
  listCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 14,
    shadowColor: "#0b0b0b",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  listCardAdmin: { borderWidth: 1, borderColor: "#d8d7d1", borderStyle: "dashed", shadowOpacity: 0 },
  listCardIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  listCardIconBig: { width: 48, height: 48, borderRadius: 14 },
  listCardTextCol: { flex: 1, minWidth: 0 },
  listCardTitleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  listCardTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  listCardTitleBig: { fontSize: 16 },
  listCardDesc: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  tierPill: { backgroundColor: "#e8f0fb", borderRadius: 999, paddingVertical: 2, paddingHorizontal: 7 },
  tierPillText: { fontSize: 10, fontWeight: "700", color: colors.primaryDark },
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
  bottomBar: {
    flexDirection: "row",
    backgroundColor: "#fff",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 10,
  },
  bottomBarItem: { flex: 1, alignItems: "center", gap: 4 },
  bottomBarLabel: { fontSize: 11 },
});
