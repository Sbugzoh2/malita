import React from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";

const TILES = [
  {
    key: "AITutor",
    icon: "🧮",
    title: "AI Tutor",
    desc: "Get any Grade 12 question solved step by step.",
    color: "#2a78d6",
  },
  {
    key: "PracticeQuestions",
    icon: "📝",
    title: "Practice Questions",
    desc: "Coming soon in the app — available on the web version today.",
    color: "#eb6834",
    disabled: true,
  },
  {
    key: "OCR",
    icon: "📷",
    title: "OCR Question",
    desc: "Snap a photo of a question and let us read it for you.",
    color: "#1baf7a",
  },
  {
    key: "PDF",
    icon: "📚",
    title: "Past Papers (PDF)",
    desc: "Upload a past paper PDF and pull questions straight from it.",
    color: "#eda100",
  },
];

export default function HomeScreen({ navigation }: any) {
  const { me, logout } = useAuth();
  const firstName = me?.user.name.split(" ")[0] ?? "";
  const initial = firstName ? firstName[0].toUpperCase() : "?";

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initial}</Text>
        </View>
        <View style={styles.profileInfo}>
          <Text style={styles.greeting}>Welcome back, {firstName}!</Text>
          <Pressable
            style={styles.planBadge}
            onPress={() => navigation.navigate("Subscription")}
          >
            <Text style={styles.planBadgeText}>{me?.tier_label ?? "Free"} plan</Text>
            <Text style={styles.planBadgeArrow}>›</Text>
          </Pressable>
        </View>
      </View>

      {me?.daily_limit != null && (
        <Text style={styles.usage}>
          {me.used_today}/{me.daily_limit} solves used today
        </Text>
      )}

      <Text style={styles.pick}>Pick where you'd like to start.</Text>

      {TILES.map((tile) => (
        <Pressable
          key={tile.key}
          style={[styles.tile, { backgroundColor: tile.color }, tile.disabled && styles.tileDisabled]}
          onPress={() => !tile.disabled && navigation.navigate(tile.key)}
          disabled={tile.disabled}
        >
          <Text style={styles.tileIcon}>{tile.icon}</Text>
          <Text style={styles.tileTitle}>{tile.title}</Text>
          <Text style={styles.tileDesc}>{tile.desc}</Text>
        </Pressable>
      ))}

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  profileCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 16,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 14,
  },
  avatarText: { color: "#fff", fontSize: 22, fontWeight: "700" },
  profileInfo: { flex: 1 },
  greeting: { fontSize: 19, fontWeight: "700", color: colors.text },
  planBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: colors.background,
    borderRadius: 999,
    paddingVertical: 4,
    paddingHorizontal: 10,
    marginTop: 6,
  },
  planBadgeText: { fontSize: 12, fontWeight: "600", color: colors.primaryDark },
  planBadgeArrow: { fontSize: 14, fontWeight: "700", color: colors.primaryDark, marginLeft: 4 },
  usage: { fontSize: 12, color: colors.textSecondary, marginTop: 10 },
  pick: { fontSize: 15, color: colors.textSecondary, marginTop: 20, marginBottom: 12 },
  tile: {
    borderRadius: 20,
    padding: 20,
    marginBottom: 14,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  tileDisabled: { opacity: 0.55 },
  tileIcon: { fontSize: 32, marginBottom: 6 },
  tileTitle: { fontSize: 18, fontWeight: "700", color: "#fff", marginBottom: 4 },
  tileDesc: { fontSize: 13, color: "#ffffffeb" },
  logoutButton: {
    marginTop: 24,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 28,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
