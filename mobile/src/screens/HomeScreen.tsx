import React from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, Image } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";

type Tile = { key: string; icon: string; title: string; desc: string; color: string; disabled?: boolean };

const TILES: Tile[] = [
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
    desc: "Work through real Grade 12 questions with hints and worked solutions.",
    color: "#eb6834",
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
  {
    key: "PastPapersLibrary",
    icon: "🗂️",
    title: "Past Papers Library",
    desc: "Browse curated past exam papers by year and subject. Premium.",
    color: "#4a3aa7",
  },
];

export default function HomeScreen({ navigation }: any) {
  const { me, logout } = useAuth();
  const firstName = me?.user.name.split(" ")[0] ?? "";

  return (
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <Image
          source={require("../../assets/hero-student.png")}
          style={styles.heroImage}
          resizeMode="cover"
        />
        <View style={styles.heroScrim} />
        <View style={styles.heroContent}>
          <Text style={styles.heroGreeting}>Welcome back, {firstName}!</Text>
          <Pressable style={styles.planBadge} onPress={() => navigation.navigate("Subscription")}>
            <Text style={styles.planBadgeText}>{me?.tier_label ?? "Free"} plan</Text>
            <Text style={styles.planBadgeArrow}>›</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.body}>
        {me?.daily_limit != null && (
          <Text style={styles.usage}>
            {me.used_today}/{me.daily_limit} solves used today
          </Text>
        )}

        <Text style={styles.pick}>Pick where you'd like to start.</Text>

        {TILES.map((tile) => (
          <Pressable
            key={tile.key}
            style={[styles.tile, tile.disabled && styles.tileDisabled]}
            onPress={() => !tile.disabled && navigation.navigate(tile.key)}
            disabled={tile.disabled}
          >
            <View style={[styles.tileIconBadge, { backgroundColor: tile.color }]}>
              <Text style={styles.tileIcon}>{tile.icon}</Text>
            </View>
            <View style={styles.tileTextCol}>
              <Text style={styles.tileTitle}>{tile.title}</Text>
              <Text style={styles.tileDesc}>{tile.desc}</Text>
            </View>
            <Text style={styles.tileChevron}>›</Text>
          </Pressable>
        ))}

        <Pressable style={styles.logoutButton} onPress={logout}>
          <Text style={styles.logoutText}>Log Out</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flexGrow: 1 },
  hero: { height: 200, position: "relative" },
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
  planBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.92)",
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 12,
    marginTop: 8,
  },
  planBadgeText: { fontSize: 12, fontWeight: "700", color: colors.primaryDark },
  planBadgeArrow: { fontSize: 14, fontWeight: "700", color: colors.primaryDark, marginLeft: 4 },
  body: { padding: 20 },
  usage: { fontSize: 12, color: colors.textSecondary },
  pick: { fontSize: 15, fontWeight: "600", color: colors.text, marginTop: 18, marginBottom: 12 },
  tile: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 18,
    padding: 14,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  tileDisabled: { opacity: 0.5 },
  tileIconBadge: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 14,
  },
  tileIcon: { fontSize: 24 },
  tileTextCol: { flex: 1 },
  tileTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 2 },
  tileDesc: { fontSize: 12, color: colors.textSecondary },
  tileChevron: { fontSize: 22, color: colors.border, fontWeight: "700", marginLeft: 6 },
  logoutButton: {
    marginTop: 12,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 28,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
