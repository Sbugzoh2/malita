import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors } from "../theme";

// Purely presentational - the YouTube-style red unread badge on a bell
// icon. The unread count and its refresh (useFocusEffect, not polling)
// live in whatever header button renders this (see RootNavigator.tsx's
// HomeNotificationBellButton/TutorNotificationBellButton) and in
// NotificationsScreen/TutorNotificationsScreen, not here.
export default function NotificationBell({ count, onPress }: { count: number; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={styles.container} hitSlop={8}>
      <Text style={styles.bell}>🔔</Text>
      {count > 0 && (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{count > 99 ? "99+" : count}</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { marginRight: 12, padding: 4 },
  bell: { fontSize: 20 },
  badge: {
    position: "absolute",
    top: -2,
    right: -4,
    backgroundColor: colors.error,
    borderRadius: 9,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },
});
