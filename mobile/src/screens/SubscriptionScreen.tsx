import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
  Alert,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchTiers, createCheckout, cancelSubscription, TierInfo } from "../api/client";

export default function SubscriptionScreen() {
  const { token, me, refreshMe } = useAuth();
  const [tiers, setTiers] = useState<TierInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  useEffect(() => {
    fetchTiers()
      .then((res) => setTiers(res.tiers))
      .catch(() => setError("Could not load subscription plans. Please try again."));
  }, []);

  async function upgrade(tierKey: string) {
    if (!token) return;
    setError(null);
    setBusyTier(tierKey);
    try {
      const res = await createCheckout(token, tierKey);
      await Linking.openURL(res.checkout_url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start checkout. Please try again.");
    } finally {
      setBusyTier(null);
    }
  }

  async function confirmCancel() {
    if (!token) return;
    setConfirmingCancel(false);
    setBusyTier("cancel");
    setError(null);
    try {
      const res = await cancelSubscription(token);
      if (!res.payfast_notified) {
        Alert.alert(
          "Downgraded, but please double check",
          "Your account has been downgraded, but we couldn't confirm the cancellation with PayFast automatically. Please also check your PayFast dashboard to make sure the recurring payment is stopped."
        );
      }
      await refreshMe();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel your subscription. Please try again.");
    } finally {
      setBusyTier(null);
    }
  }

  const currentTier = me?.effective_tier ?? "free";

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>💳 Subscription</Text>
      <Text style={styles.subtitle}>Manage your Malita plan.</Text>

      <View style={styles.currentCard}>
        <Text style={styles.currentLabel}>Current plan</Text>
        <Text style={styles.currentTier}>{me?.tier_label ?? "Free"}</Text>
        {me?.daily_limit != null ? (
          <Text style={styles.currentUsage}>
            {me.used_today}/{me.daily_limit} solves used today
          </Text>
        ) : (
          <Text style={styles.currentUsage}>Unlimited solves</Text>
        )}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!tiers ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : (
        tiers
          .filter((t) => t.price_zar > 0)
          .map((t) => {
            const isCurrent = t.key === currentTier;
            return (
              <View key={t.key} style={styles.planCard}>
                <View style={styles.planHeaderRow}>
                  <Text style={styles.planName}>{t.label}</Text>
                  <Text style={styles.planPrice}>R{t.price_zar}/month</Text>
                </View>
                <Text style={styles.planFeature}>
                  {t.ai_tutor_daily_limit == null ? "Unlimited AI Tutor solves" : `${t.ai_tutor_daily_limit} solves/day`}
                </Text>
                <Text style={styles.planFeature}>{t.ocr_enabled ? "Photo/camera OCR" : "No OCR"}</Text>
                <Text style={styles.planFeature}>{t.pdf_enabled ? "Past paper PDF extraction" : "No PDF extraction"}</Text>
                <Text style={styles.planFeature}>
                  {t.past_papers_enabled ? "Past Papers Library access" : "No Past Papers Library"}
                </Text>

                {isCurrent ? (
                  confirmingCancel ? (
                    <View style={styles.confirmRow}>
                      <Text style={styles.confirmText}>
                        Cancel your subscription? This stops billing and downgrades your account.
                      </Text>
                      <View style={styles.confirmButtonRow}>
                        <Pressable
                          style={[styles.smallButton, styles.dangerButton]}
                          onPress={confirmCancel}
                          disabled={busyTier === "cancel"}
                        >
                          {busyTier === "cancel" ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.smallButtonText}>Yes, cancel</Text>
                          )}
                        </Pressable>
                        <Pressable style={styles.smallButton} onPress={() => setConfirmingCancel(false)}>
                          <Text style={styles.smallButtonTextDark}>Never mind</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : (
                    <Pressable style={styles.cancelButton} onPress={() => setConfirmingCancel(true)}>
                      <Text style={styles.cancelButtonText}>Cancel Subscription</Text>
                    </Pressable>
                  )
                ) : (
                  <Pressable
                    style={[styles.upgradeButton, busyTier === t.key && styles.buttonDisabled]}
                    onPress={() => upgrade(t.key)}
                    disabled={busyTier === t.key}
                  >
                    {busyTier === t.key ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.upgradeButtonText}>Upgrade to {t.label}</Text>
                    )}
                  </Pressable>
                )}
              </View>
            );
          })
      )}

      <Text style={styles.paymentNote}>
        Upgrading opens PayFast's secure checkout in your browser. Once payment completes, come back to the app —
        your plan updates automatically.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  currentCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
  },
  currentLabel: { fontSize: 12, color: colors.textSecondary },
  currentTier: { fontSize: 20, fontWeight: "700", color: colors.text, marginTop: 2 },
  currentUsage: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  error: { color: colors.error, marginTop: 16, textAlign: "center" },
  planCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 14,
  },
  planHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planName: { fontSize: 18, fontWeight: "700", color: colors.text },
  planPrice: { fontSize: 15, fontWeight: "600", color: colors.primary },
  planFeature: { fontSize: 13, color: colors.textSecondary, marginTop: 6 },
  upgradeButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 14,
  },
  buttonDisabled: { opacity: 0.6 },
  upgradeButtonText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  cancelButton: {
    marginTop: 14,
    alignSelf: "flex-start",
  },
  cancelButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  confirmRow: { marginTop: 14 },
  confirmText: { fontSize: 13, color: colors.textSecondary },
  confirmButtonRow: { flexDirection: "row", gap: 10, marginTop: 10 },
  smallButton: {
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
  },
  dangerButton: { backgroundColor: colors.error, borderColor: "transparent" },
  smallButtonText: { color: "#fff", fontWeight: "700" },
  smallButtonTextDark: { color: colors.text, fontWeight: "700" },
  paymentNote: { fontSize: 12, color: colors.textSecondary, marginTop: 20, fontStyle: "italic" },
});
