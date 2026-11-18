import React from "react";
import { StyleSheet, ViewStyle, StyleProp, KeyboardAvoidingView, Platform } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { gradientColors } from "../theme";

// The dark purple gradient backdrop used behind every screen - wrap a
// screen's outermost element with this instead of giving it a flat
// colors.background fill. See theme.ts's gradientColors for the stops.
//
// Also wraps every screen's content in a KeyboardAvoidingView, since
// every screen uses this as its outermost element - fixing the keyboard
// covering a TextInput near the bottom edge (reported on, e.g., the
// comment box under a session's star rating) HERE fixes it everywhere
// at once, rather than adding the same wrapper to 25 individual
// screens. "height" on Android rather than "padding" - padding's known
// to measure wrong on some Android keyboards/RN versions, where height
// doesn't.
export default function GradientBackground({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <LinearGradient colors={gradientColors} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={[styles.fill, style]}>
      <KeyboardAvoidingView
        style={styles.fill}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        {children}
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
});
