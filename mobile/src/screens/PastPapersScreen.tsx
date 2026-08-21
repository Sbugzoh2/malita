import React, { useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchPastPapers, pastPaperDownloadUrl, PastPaper } from "../api/client";

// Same chronological order as app.py's EXAM_SERIES_OPTIONS, so a year's
// documents always group the same way on both platforms.
const EXAM_SERIES_ORDER = [
  "February/March (Supplementary)",
  "March/April Control Test",
  "June Exam",
  "September (Trial)",
  "November (Final)",
];

export default function PastPapersScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [papers, setPapers] = useState<PastPaper[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedYears, setExpandedYears] = useState<Set<number>>(new Set());

  const locked = me != null && me.effective_tier !== "premium";

  useEffect(() => {
    if (!token || locked) {
      setLoading(false);
      return;
    }
    fetchPastPapers(token)
      .then((res) => {
        setPapers(res.papers);
        const years = [...new Set(res.papers.map((p) => p.year))].sort((a, b) => b - a);
        if (years.length > 0) setExpandedYears(new Set([years[0]]));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load past papers."))
      .finally(() => setLoading(false));
  }, [token, locked]);

  function toggleYear(year: number) {
    setExpandedYears((prev) => {
      const next = new Set(prev);
      if (next.has(year)) next.delete(year);
      else next.add(year);
      return next;
    });
  }

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
        [...new Set(papers.map((p) => p.year))]
          .sort((a, b) => b - a)
          .map((year) => {
            const yearPapers = papers.filter((p) => p.year === year);
            const isExpanded = expandedYears.has(year);
            const seriesForYear = [
              ...EXAM_SERIES_ORDER.filter((s) => yearPapers.some((p) => p.exam_series === s)),
              ...[...new Set(yearPapers.map((p) => p.exam_series))].filter((s) => !EXAM_SERIES_ORDER.includes(s)),
            ];
            return (
              <View key={year} style={styles.yearSection}>
                <Pressable style={styles.yearHeader} onPress={() => toggleYear(year)}>
                  <Text style={styles.yearHeaderText}>
                    📅 {year} ({yearPapers.length} document{yearPapers.length !== 1 ? "s" : ""})
                  </Text>
                  <Text style={styles.yearChevron}>{isExpanded ? "▲" : "▼"}</Text>
                </Pressable>
                {isExpanded &&
                  seriesForYear.map((series) => (
                    <View key={series}>
                      <Text style={styles.seriesLabel}>{series}</Text>
                      {yearPapers
                        .filter((p) => p.exam_series === series)
                        .map((p) => (
                          <View key={p.id} style={styles.paperCard}>
                            <View style={styles.paperCardTopRow}>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.paperTitle}>
                                  {p.subject} Paper {p.paper_number} · {p.document_type} · {p.variant}
                                </Text>
                                <Text style={styles.paperMeta}>{Math.round(p.file_size / 1024)} KB</Text>
                              </View>
                              <View style={styles.actionRow}>
                                <Pressable
                                  style={styles.viewButton}
                                  onPress={() =>
                                    token &&
                                    navigation.navigate("PastPaperViewer", {
                                      url: pastPaperDownloadUrl(token, p.id),
                                      title: `${p.subject} Paper ${p.paper_number} · ${p.document_type}`,
                                    })
                                  }
                                >
                                  <Text style={styles.viewButtonText}>👁️ View</Text>
                                </Pressable>
                                <Pressable
                                  style={styles.downloadButton}
                                  onPress={() => token && Linking.openURL(pastPaperDownloadUrl(token, p.id))}
                                >
                                  <Text style={styles.downloadButtonText}>⬇️</Text>
                                </Pressable>
                              </View>
                            </View>
                          </View>
                        ))}
                    </View>
                  ))}
              </View>
            );
          })
      ) : (
        <View style={styles.emptyState}>
          <Text style={styles.emptyTitle}>No papers here yet</Text>
          <Text style={styles.emptyText}>
            This library is being built out. In the meantime, use "Upload PDF Document" from the Home screen to
            upload any paper you already have — Malita will extract the text and can solve every question
            from it with AI right away.
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
  yearSection: { marginTop: 14 },
  yearHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 16,
  },
  yearHeaderText: { fontSize: 16, fontWeight: "700", color: colors.text },
  yearChevron: { fontSize: 12, color: colors.textSecondary },
  seriesLabel: {
    fontSize: 13,
    fontWeight: "700",
    color: colors.textSecondary,
    marginTop: 12,
    marginLeft: 4,
  },
  paperCard: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 14,
    marginTop: 10,
  },
  paperCardTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  paperTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  paperMeta: { fontSize: 12, color: colors.textSecondary, marginTop: 4 },
  actionRow: { flexDirection: "row", alignItems: "center", marginLeft: 10 },
  viewButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  viewButtonText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  downloadButton: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 10,
    marginLeft: 8,
  },
  downloadButtonText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
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
