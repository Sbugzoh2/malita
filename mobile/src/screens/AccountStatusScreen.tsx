import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { useAuth } from "../context/AuthContext";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";

// Shown instead of every other screen while an account is suspended or
// blocked (see RootNavigator.tsx - in that state, this and the matching
// Support/TutorSupport screen are the ONLY routes registered at all, so
// there's no way to reach a feature screen even by deep link). Works for
// both a learner and a tutor: whichever auth context actually has a
// token is the one that's logged in right now, since RootNavigator only
// ever mounts one of AppNavigator/TutorAppNavigator at a time.
export default function AccountStatusScreen({ navigation }: any) {
  const learnerAuth = useAuth();
  const tutorAuth = useTutorAuth();
  const isTutor = !!tutorAuth.token;

  const status = isTutor ? tutorAuth.me?.account_status : learnerAuth.me?.user.account_status;
  const reason = isTutor ? tutorAuth.me?.account_status_reason : learnerAuth.me?.user.account_status_reason;
  const logout = isTutor ? tutorAuth.logout : learnerAuth.logout;
  const supportRoute = isTutor ? "TutorSupport" : "Support";

  const isBlocked = status === "blocked";

  return (
    <View style={styles.container}>
      <Text style={styles.emoji}>{isBlocked ? "⛔" : "⏸️"}</Text>
      <Text style={styles.title}>{isBlocked ? "Account blocked" : "Account suspended"}</Text>
      <Text style={styles.body}>
        {isBlocked
          ? "Your Malita account has been blocked. You won't be able to use the app while this is in place."
          : "Your Malita account has been temporarily suspended while we look into a matter. You won't be " +
            "able to use the app until this is lifted."}
      </Text>
      {reason ? (
        <View style={styles.reasonBox}>
          <Text style={styles.reasonLabel}>Reason given</Text>
          <Text style={styles.reasonText}>{reason}</Text>
        </View>
      ) : null}

      <Pressable style={styles.supportButton} onPress={() => navigation.navigate(supportRoute)}>
        <Text style={styles.supportButtonText}>Contact Support</Text>
      </Pressable>

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, padding: 24, justifyContent: "center", alignItems: "center" },
  emoji: { fontSize: 48, marginBottom: 16 },
  title: { fontSize: 22, fontWeight: "800", color: colors.text, textAlign: "center" },
  body: { fontSize: 14, color: colors.textSecondary, textAlign: "center", marginTop: 12, lineHeight: 20 },
  reasonBox: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
    alignSelf: "stretch",
  },
  reasonLabel: { fontSize: 11, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 0.4 },
  reasonText: { fontSize: 14, color: colors.text, marginTop: 6, lineHeight: 20 },
  supportButton: {
    marginTop: 28,
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  supportButtonText: { color: "#fff", fontWeight: "700" },
  logoutButton: {
    marginTop: 14,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
    borderWidth: 1,
    borderColor: colors.border,
  },
  logoutText: { color: colors.text, fontWeight: "700" },
});
