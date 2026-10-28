import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
  Alert,
  Platform,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  fetchTiers,
  cancelSubscription,
  scheduleDowngrade,
  fetchGooglePlayProducts,
  verifyGooglePlayPurchase,
  deleteAccount,
  TierInfo,
  API_BASE_URL,
} from "../api/client";

// New subscriptions on mobile go through Google Play only - PayFast's
// hosted checkout proved too unreliable in the native app's external-
// browser flow (see the deep-link bridge-page saga in git history). The
// web app (malita-maths.streamlit.app) still offers PayFast; existing
// learners who already subscribed via PayFast through this app keep
// working as before (cancel/downgrade still understand that provider),
// this only removes PayFast as an option for NEW purchases here.
const WEB_APP_URL = "https://malita-maths.streamlit.app";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-ZA", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return iso;
  }
}

// expo-iap only has anything to initialise on Android (no Apple/App Store
// products exist for this app) - importing it on web would also break the
// build, since it's a native module. useIAP() below is only ever called
// when isAndroid is true.
const isAndroid = Platform.OS === "android";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { useIAP } = isAndroid ? require("expo-iap") : { useIAP: null };

export default function SubscriptionScreen() {
  const { token, me, refreshMe, logout } = useAuth();
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [tiers, setTiers] = useState<TierInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [confirmingDowngrade, setConfirmingDowngrade] = useState<string | null>(null);
  const [googleProducts, setGoogleProducts] = useState<Record<string, string> | null>(null);
  // Set right before a deferred-replacement purchase is requested so the
  // onPurchaseSuccess handler below knows to call scheduleDowngrade
  // instead of the normal immediate-grant verifyGooglePlayPurchase path.
  const [downgradeInFlightTier, setDowngradeInFlightTier] = useState<string | null>(null);

  // Refreshes the learner's plan every time this screen regains focus -
  // in particular, when PayFast's checkout redirects back into the app
  // via the malita:// deep link (see RootNavigator's linking config),
  // this is what actually picks up the new tier without needing the
  // learner to restart the app.
  useFocusEffect(
    useCallback(() => {
      refreshMe();
    }, [refreshMe])
  );

  useEffect(() => {
    fetchTiers()
      .then((res) => setTiers(res.tiers))
      .catch(() => setError("Could not load subscription plans. Please try again."));
    if (isAndroid && token) {
      fetchGooglePlayProducts(token)
        .then((res) => setGoogleProducts(res.products))
        .catch(() => {
          // Non-fatal - the fallback "Subscribe via the Malita website"
          // link below still works if this fails to load.
        });
    }
  }, [token]);

  // Google Play purchase handling (Android only) - the only way to buy a
  // new subscription on mobile now (see the WEB_APP_URL note above).
  const iap = isAndroid
    ? useIAP({
        onPurchaseSuccess: async (purchase: any) => {
          if (!token) return;
          try {
            if (downgradeInFlightTier) {
              // Play Billing handles the deferred swap itself at the next
              // renewal - this just mirrors "keep current tier until then"
              // in our own records, same as the PayFast downgrade path.
              const result = await scheduleDowngrade(token, downgradeInFlightTier);
              await iap.finishTransaction({ purchase, isConsumable: false });
              await refreshMe();
              Alert.alert(
                "Downgrade scheduled",
                result.effective_date
                  ? `You'll keep your current plan until ${formatDate(result.effective_date)}, then move to the new plan.`
                  : "Your plan will change at the end of your current billing period."
              );
            } else {
              await verifyGooglePlayPurchase(token, purchase.productId, purchase.purchaseToken ?? "");
              await iap.finishTransaction({ purchase, isConsumable: false });
              await refreshMe();
            }
          } catch (e) {
            Alert.alert(
              "Purchase couldn't be verified",
              e instanceof ApiError ? e.message : "Please contact support with your Google Play receipt."
            );
          } finally {
            setBusyTier(null);
            setDowngradeInFlightTier(null);
          }
        },
        onPurchaseError: (e: any) => {
          setBusyTier(null);
          setDowngradeInFlightTier(null);
          if (e?.code !== "E_USER_CANCELLED") {
            setError("Google Play purchase failed. Please try again.");
          }
        },
      })
    : null;

  useEffect(() => {
    if (isAndroid && iap?.connected && googleProducts) {
      iap.fetchProducts({ skus: Object.values(googleProducts), type: "subs" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAndroid && iap?.connected, googleProducts]);

  async function upgradeWithGooglePlay(tierKey: string) {
    if (!token || !googleProducts || !iap) return;
    const productId = googleProducts[tierKey];
    if (!productId) {
      setError("This plan isn't available via Google Play yet.");
      return;
    }
    setError(null);
    setBusyTier(tierKey);
    const product = iap.subscriptions.find((s: any) => s.id === productId);
    const offer = product?.subscriptionOffers?.[0];
    try {
      await iap.requestPurchase({
        type: "subs",
        request: {
          google: {
            skus: [productId],
            subscriptionOffers: offer?.offerTokenAndroid
              ? [{ sku: productId, offerToken: offer.offerTokenAndroid }]
              : undefined,
          },
        },
      });
      // busyTier is cleared in onPurchaseSuccess/onPurchaseError above, once
      // the Play Billing dialog actually resolves.
    } catch (e) {
      setBusyTier(null);
      setError("Could not start Google Play checkout. Please try again.");
    }
  }

  async function downgradeWithGooglePlay(tierKey: string) {
    if (!token || !googleProducts || !iap || !me?.google_product_id) return;
    const productId = googleProducts[tierKey];
    if (!productId) {
      setError("This plan isn't available via Google Play yet.");
      return;
    }
    setError(null);
    setBusyTier(tierKey);
    setDowngradeInFlightTier(tierKey);
    const product = iap.subscriptions.find((s: any) => s.id === productId);
    const offer = product?.subscriptionOffers?.[0];
    try {
      await iap.requestPurchase({
        type: "subs",
        request: {
          google: {
            skus: [productId],
            subscriptionOffers: offer?.offerTokenAndroid
              ? [{ sku: productId, offerToken: offer.offerTokenAndroid }]
              : undefined,
            // DEFERRED: Play Billing swaps to the new plan at the next
            // renewal instead of charging now - no payment dialog shows
            // for a deferred change, it just schedules it on Google's side.
            subscriptionProductReplacementParams: {
              oldProductId: me.google_product_id,
              replacementMode: "deferred",
            },
          },
        },
      });
      // busyTier/downgradeInFlightTier are cleared in onPurchaseSuccess/
      // onPurchaseError above, once Play Billing actually resolves this.
    } catch (e) {
      setBusyTier(null);
      setDowngradeInFlightTier(null);
      setError("Could not schedule the Google Play downgrade. Please try again.");
    }
  }

  async function downgradeWithPayfast(tierKey: string) {
    if (!token) return;
    setError(null);
    setBusyTier(tierKey);
    try {
      const result = await scheduleDowngrade(token, tierKey);
      await refreshMe();
      Alert.alert(
        "Downgrade scheduled",
        result.effective_date
          ? `You'll keep your current plan until ${formatDate(result.effective_date)}. After that, you'll need to come back here and subscribe to the new plan to keep paid access - otherwise your account moves to Free.`
          : "Your plan will change at the end of your current billing period."
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not schedule the downgrade. Please try again.");
    } finally {
      setBusyTier(null);
    }
  }

  function confirmDowngrade(tierKey: string) {
    setConfirmingDowngrade(null);
    if (currentProvider === "play_billing") {
      downgradeWithGooglePlay(tierKey);
    } else {
      downgradeWithPayfast(tierKey);
    }
  }

  async function confirmCancel() {
    if (!token) return;
    setConfirmingCancel(false);
    setBusyTier("cancel");
    setError(null);
    try {
      const res = await cancelSubscription(token);
      if (res.provider === "play_billing") {
        Alert.alert(
          "Manage this subscription in Google Play",
          "This subscription was bought through Google Play, so Google requires you to cancel it from the Play Store app (Subscriptions), not from here. Your Malita account has been downgraded, but please also cancel it there so Google Play stops billing you."
        );
      } else if (res.payfast_notified === false) {
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

  async function runDeleteAccount() {
    if (!token) return;
    setDeletingAccount(true);
    setError(null);
    try {
      const res = await deleteAccount(token);
      if (res.had_active_subscription && res.provider === "play_billing") {
        Alert.alert(
          "One more step in Google Play",
          "Your Malita account has been deleted, but Google requires subscriptions to be cancelled from the Play Store app (Subscriptions) separately - please cancel it there too so Google Play stops billing you."
        );
      } else if (res.provider === "payfast" && res.payfast_notified === false) {
        Alert.alert(
          "Account deleted, but please double check",
          "Your Malita account has been deleted, but we couldn't confirm the cancellation with PayFast automatically. Please also check your PayFast dashboard to make sure the recurring payment is stopped."
        );
      }
      await logout();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete your account. Please try again.");
      setDeletingAccount(false);
    }
  }

  function handleDeleteAccount() {
    Alert.alert(
      "Delete your account?",
      "This permanently deletes your Malita account and all associated data - your profile, subscription, study history, and Collaboration Forum posts. This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Delete my account", style: "destructive", onPress: runDeleteAccount },
      ]
    );
  }

  const currentTier = me?.effective_tier ?? "free";
  const currentProvider = me?.payment_provider;
  // tiers (from /billing/tiers) comes back in TIER_ORDER already - used to
  // tell an upgrade apart from a downgrade for each plan card below.
  const currentTierRank = tiers ? tiers.findIndex((t) => t.key === currentTier) : -1;

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
        {currentProvider === "play_billing" ? (
          <Text style={styles.currentUsage}>Billed through Google Play</Text>
        ) : null}
        {me?.pending_tier ? (
          <Text style={styles.pendingNotice}>
            Moving to {me.pending_tier_label} on {formatDate(me.current_period_end)}
          </Text>
        ) : null}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!tiers ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      ) : (
        tiers
          .filter((t) => t.price_zar > 0)
          .map((t) => {
            const isCurrent = t.key === currentTier;
            const hasGooglePlan = isAndroid && !!googleProducts?.[t.key];
            const tierRank = tiers.findIndex((x) => x.key === t.key);
            const isDowngrade = !isCurrent && currentTier !== "free" && tierRank < currentTierRank;
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
                ) : isDowngrade ? (
                  confirmingDowngrade === t.key ? (
                    <View style={styles.confirmRow}>
                      <Text style={styles.confirmText}>
                        Move to {t.label} at the end of your current billing period? You'll keep your current
                        plan's access until then.
                      </Text>
                      <View style={styles.confirmButtonRow}>
                        <Pressable
                          style={styles.smallButton}
                          onPress={() => confirmDowngrade(t.key)}
                          disabled={busyTier === t.key}
                        >
                          {busyTier === t.key ? (
                            <ActivityIndicator color={colors.text} />
                          ) : (
                            <Text style={styles.smallButtonTextDark}>Yes, schedule it</Text>
                          )}
                        </Pressable>
                        <Pressable style={styles.smallButton} onPress={() => setConfirmingDowngrade(null)}>
                          <Text style={styles.smallButtonTextDark}>Never mind</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : (
                    <Pressable style={styles.downgradeButton} onPress={() => setConfirmingDowngrade(t.key)}>
                      <Text style={styles.downgradeButtonText}>Downgrade to {t.label}</Text>
                    </Pressable>
                  )
                ) : hasGooglePlan ? (
                  <Pressable
                    style={[styles.upgradeButton, busyTier === t.key && styles.buttonDisabled]}
                    onPress={() => upgradeWithGooglePlay(t.key)}
                    disabled={busyTier === t.key}
                  >
                    {busyTier === t.key ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.upgradeButtonText}>Upgrade to {t.label}</Text>
                    )}
                  </Pressable>
                ) : (
                  <Pressable
                    style={styles.upgradeButtonSecondary}
                    onPress={() => Linking.openURL(WEB_APP_URL)}
                  >
                    <Text style={styles.upgradeButtonSecondaryText}>
                      {isAndroid ? "Loading Google Play…" : "Subscribe via the Malita website"}
                    </Text>
                  </Pressable>
                )}
              </View>
            );
          })
      )}

      <Text style={styles.paymentNote}>
        Upgrading opens secure checkout for your chosen payment method. Once payment completes, come back to the
        app — your plan updates automatically.
      </Text>

      <Text style={styles.legalNote}>
        Subscriptions are governed by Malita's{" "}
        <Text style={styles.legalLink} onPress={() => Linking.openURL(`${API_BASE_URL}/terms`)}>
          Terms &amp; Conditions
        </Text>
        , including the Refund and Cancellation Policy.
      </Text>

      <View style={styles.deleteAccountSection}>
        <Text style={styles.deleteAccountTitle}>Account</Text>
        <Pressable
          style={styles.deleteAccountButton}
          onPress={handleDeleteAccount}
          disabled={deletingAccount}
        >
          {deletingAccount ? (
            <ActivityIndicator color={colors.error} />
          ) : (
            <Text style={styles.deleteAccountButtonText}>Delete My Account</Text>
          )}
        </Pressable>
      </View>
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
  pendingNotice: { fontSize: 12, color: colors.primary, marginTop: 8, fontWeight: "600" },
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
  upgradeButtonSecondary: {
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.primary,
    marginTop: 14,
  },
  upgradeButtonSecondaryText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  buttonDisabled: { opacity: 0.6 },
  upgradeButtonText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  cancelButton: {
    marginTop: 14,
    alignSelf: "flex-start",
  },
  cancelButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  downgradeButton: {
    marginTop: 14,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  downgradeButtonText: { color: colors.textSecondary, fontWeight: "700", fontSize: 15 },
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
  legalNote: { fontSize: 12, color: colors.textSecondary, marginTop: 10, lineHeight: 17 },
  legalLink: { color: colors.primary, fontWeight: "600" },
  deleteAccountSection: {
    marginTop: 32,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  deleteAccountTitle: { fontSize: 13, color: colors.textSecondary, marginBottom: 8 },
  deleteAccountButton: { alignSelf: "flex-start" },
  deleteAccountButtonText: { color: colors.error, fontWeight: "700", fontSize: 14 },
});
