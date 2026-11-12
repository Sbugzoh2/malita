import React, { useCallback, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import {
  ApiError,
  AppNotification,
  fetchTutorNotifications,
  markTutorNotificationRead,
  markAllTutorNotificationsRead,
} from "../api/client";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-ZA", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      timeZone: "Africa/Johannesburg",
    });
  } catch {
    return iso;
  }
}

export default function TutorNotificationsScreen({ navigation }: any) {
  const { token } = useTutorAuth();
  const [notifications, setNotifications] = useState<AppNotification[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    fetchTutorNotifications(token)
      .then((res) => setNotifications(res.notifications))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your notifications."));
  }, [token]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  async function handleRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function handleTapNotification(n: AppNotification) {
    if (!token || n.read) return;
    try {
      await markTutorNotificationRead(token, n.id);
      setNotifications((prev) => prev && prev.map((p) => (p.id === n.id ? { ...p, read: true } : p)));
    } catch {
      // Best-effort - a failed mark-as-read shouldn't block reading the notification.
    }
  }

  async function handleMarkAllRead() {
    if (!token) return;
    setMarkingAll(true);
    try {
      await markAllTutorNotificationsRead(token);
      setNotifications((prev) => prev && prev.map((p) => ({ ...p, read: true })));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not mark all as read.");
    } finally {
      setMarkingAll(false);
    }
  }

  const hasUnread = !!notifications?.some((n) => !n.read);

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
    >
      <Pressable style={styles.backLink} onPress={() => navigation.navigate("TutorHome")}>
        <Text style={styles.backLinkText}>‹ Back</Text>
      </Pressable>
      <View style={styles.titleRow}>
        <Text style={styles.title}>🔔 Notifications</Text>
        {hasUnread && (
          <Pressable onPress={handleMarkAllRead} disabled={markingAll}>
            <Text style={styles.markAllText}>{markingAll ? "Marking…" : "Mark all as read"}</Text>
          </Pressable>
        )}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!notifications ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : notifications.length === 0 ? (
        <Text style={styles.empty}>No notifications yet.</Text>
      ) : (
        notifications.map((n) => (
          <Pressable key={n.id} style={[styles.card, !n.read && styles.cardUnread]} onPress={() => handleTapNotification(n)}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardTitle}>{n.title}</Text>
              {!n.read && <View style={styles.unreadDot} />}
            </View>
            {n.body ? <Text style={styles.cardBody}>{n.body}</Text> : null}
            <Text style={styles.cardMeta}>{formatDate(n.created_at)}</Text>
          </Pressable>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingBottom: 40, backgroundColor: colors.background, flexGrow: 1 },
  backLink: { marginBottom: 12, alignSelf: "flex-start" },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  titleRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  markAllText: { color: colors.primary, fontWeight: "600", fontSize: 13 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 24 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 14,
  },
  cardUnread: { borderWidth: 1, borderColor: colors.primary },
  cardHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 6 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.text, flex: 1 },
  unreadDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.error, marginTop: 4 },
  cardBody: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  cardMeta: { fontSize: 12, color: colors.textSecondary, marginTop: 8 },
});
