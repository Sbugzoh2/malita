import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors } from "../theme";

// Purely presentational - the YouTube-style red unread badge on a bell
// icon. The unread count and its refresh (useFocusEffect, not polling)
// live in whatever header button renders this (see RootNavigator.tsx's
// TutorNotificationBellButton and HomeScreen.tsx's own header) and in
// NotificationsScreen/TutorNotificationsScreen, not here.
//
// Built from plain Views (no emoji, no SVG dependency) to match the rest
// of the app's redesigned icon language.
export default function NotificationBell({
  count,
  onPress,
  color = colors.text,
  size = 20,
}: {
  count: number;
  onPress: () => void;
  color?: string;
  size?: number;
}) {
  return (
    <Pressable onPress={onPress} style={styles.container} hitSlop={8}>
      <View style={{ width: size, height: size, alignItems: "center" }}>
        <View
          style={{
            width: size * 0.62,
            height: size * 0.56,
            borderWidth: 1.6,
            borderColor: color,
            borderTopLeftRadius: size * 0.31,
            borderTopRightRadius: size * 0.31,
            borderBottomLeftRadius: size * 0.08,
            borderBottomRightRadius: size * 0.08,
          }}
        />
        <View style={{ width: size * 0.82, height: 1.6, backgroundColor: color, marginTop: 1 }} />
        <View style={{ width: size * 0.14, height: size * 0.14, borderRadius: 999, backgroundColor: color, marginTop: 2 }} />
      </View>
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
