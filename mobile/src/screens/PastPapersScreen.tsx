import React, { useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchPastPapers, pastPaperDownloadUrl, PastPaper } from "../api/client";

export default function PastPapersScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [papers, setPapers] = useState<PastPaper[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const locked = me != null && me.effective_tier !== "premium";

  useEffect(() => {
    if (!token || locked) {
      setLoading(false);
      return;
    }
    fetchPastPapers(token)
      .then((res) => setPapers(res.papers))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load past papers."))
      .finally(() => setLoading(false));
  }, [token, locked]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("Home")}>
        <Text style={styles.backLinkText}>‹ Back to Home</Text>
      </Pressable>
      <Text style={styles.title}>📚 Past Papers Library</Text>
      <Text style={styles.subtitle}>Browse real past exam papers, organised by year and subject.</Text>

      {locked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            The Past Papers Library is a Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
          <Pressable style={styles.upgradeButton} onPress={() => navigation.navigate("Subscription")}>
            <Text style={styles.upgradeButtonText}>View Plans</Text>
          </Pressable>
        </View>
      ) : loading ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : error ? (
        <Text style={styles.error}>{error}</Text>
      ) : papers && papers.length > 0 ? (
        papers.map((p) => (
          <View key={p.id} style={styles.paperCard}>
            <View style={{ flex: 1 }}>
              <Text style={styles.paperTitle}>
                {p.subject} Paper {p.paper_number} · {p.variant}
              </Text>
              <Text style={styles.paperMeta}>
                {p.title} · {Math.round(p.file_size / 1024)} KB
              </Text>
            </View>
            <Pressable
              style={styles.downloadButton}
              onPress={() => token && Linking.openURL(pastPaperDownloadUrl(token, p.id))}
            >
              <Text style={styles.downloadButtonText}>⬇️ Open</Text>
            </Pressable>
          </View>
        ))
      ) : (
        <View style={styles.emptyState}>
          <Text style={styles.emptyTitle}>No papers here yet</Text>
          <Text style={styles.emptyText}>
            This library is being built out. In the meantime, use "Past Papers (PDF)" from the Home screen to
            upload any paper you already have — Malita will extract the text and can solve individual questions
            from it right away.
          </Text>
          <Pressable style={styles.emptyButton} onPress={() => navigation.navigate("PDF")}>
            <Text style={styles.emptyButtonText}>Upload a PDF instead →</Text>
          </Pressable>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  error: { color: colors.error, marginTop: 12 },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00", marginBottom: 12 },
  upgradeButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
  },
  upgradeButtonText: { color: "#fff", fontWeight: "700" },
  paperCard: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 14,
    marginTop: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  paperTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  paperMeta: { fontSize: 12, color: colors.textSecondary, marginTop: 4 },
  downloadButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    marginLeft: 10,
  },
  downloadButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  emptyState: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 20,
    marginTop: 16,
    alignItems: "center",
  },
  emptyTitle: { fontSize: 16, fontWeight: "700", color: colors.text, marginBottom: 8 },
  emptyText: { fontSize: 13, color: colors.textSecondary, textAlign: "center", lineHeight: 19 },
  emptyButton: { marginTop: 16 },
  emptyButtonText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
});
