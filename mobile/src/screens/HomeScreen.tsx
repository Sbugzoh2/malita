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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.greeting}>👋 Welcome back, {me?.user.name.split(" ")[0] ?? ""}!</Text>
      <Text style={styles.plan}>
        Plan: {me?.tier_label ?? "Free"}
        {me?.daily_limit != null ? ` · ${me.used_today}/${me.daily_limit} solves today` : ""}
      </Text>

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
  greeting: { fontSize: 26, fontWeight: "700", color: colors.text },
  plan: { fontSize: 14, color: colors.textSecondary, marginTop: 6 },
  pick: { fontSize: 15, color: colors.textSecondary, marginTop: 16, marginBottom: 12 },
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
