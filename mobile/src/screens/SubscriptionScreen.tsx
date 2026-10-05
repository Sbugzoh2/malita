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
  Platform,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  fetchTiers,
  checkoutPageUrl,
  cancelSubscription,
  fetchGooglePlayProducts,
  verifyGooglePlayPurchase,
  logGooglePlayChoice,
  TierInfo,
  API_BASE_URL,
} from "../api/client";

// expo-iap only has anything to initialise on Android (no Apple/App Store
// products exist for this app) - importing it on web would also break the
// build, since it's a native module. useIAP() below is only ever called
// when isAndroid is true.
const isAndroid = Platform.OS === "android";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { useIAP } = isAndroid ? require("expo-iap") : { useIAP: null };

export default function SubscriptionScreen() {
  const { token, me, refreshMe } = useAuth();
  const [tiers, setTiers] = useState<TierInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [googleProducts, setGoogleProducts] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    fetchTiers()
      .then((res) => setTiers(res.tiers))
      .catch(() => setError("Could not load subscription plans. Please try again."));
    if (isAndroid && token) {
      fetchGooglePlayProducts(token)
        .then((res) => setGoogleProducts(res.products))
        .catch(() => {
          // Non-fatal - learners can still subscribe via PayFast.
        });
    }
  }, [token]);

  // Google Play purchase handling (Android only). enableBillingProgramAndroid
  // is set to "user-choice-billing" so that once Google approves Malita's
  // User Choice Billing enrollment, the Play Billing dialog automatically
  // starts showing Google's own PayFast-vs-Play-Billing choice screen with
  // no further app changes - until that approval lands, Play Billing just
  // behaves like a normal purchase.
  const iap = isAndroid
    ? useIAP({
        enableBillingProgramAndroid: "user-choice-billing",
        onPurchaseSuccess: async (purchase: any) => {
          if (!token) return;
          try {
            await verifyGooglePlayPurchase(token, purchase.productId, purchase.purchaseToken ?? "");
            await iap.finishTransaction({ purchase, isConsumable: false });
            await refreshMe();
          } catch (e) {
            Alert.alert(
              "Purchase couldn't be verified",
              e instanceof ApiError ? e.message : "Please contact support with your Google Play receipt."
            );
          } finally {
            setBusyTier(null);
          }
        },
        onPurchaseError: (e: any) => {
          setBusyTier(null);
          if (e?.code !== "E_USER_CANCELLED") {
            setError("Google Play purchase failed. Please try again.");
          }
        },
        onUserChoiceBillingAndroid: async (details: { externalTransactionToken: string; products: string[] }) => {
          // The learner picked the alternative billing option (PayFast) in
          // Google's own choice screen. Google's dialog only records that
          // choice - it doesn't process the alternative payment - so we log
          // it (see GooglePlayChoiceEvent) and send them into the existing
          // PayFast checkout for whichever plan they were buying.
          setBusyTier(null);
          if (token) {
            logGooglePlayChoice(token, details.externalTransactionToken, details.products).catch(() => {});
          }
          const productId = details.products[0];
          const tierKey = googleProducts
            ? Object.keys(googleProducts).find((k) => googleProducts[k] === productId)
            : null;
          if (token && tierKey) {
            Linking.openURL(checkoutPageUrl(token, tierKey));
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

  async function upgradeWithPayfast(tierKey: string) {
    if (!token) return;
    setError(null);
    setBusyTier(tierKey);
    try {
      await Linking.openURL(checkoutPageUrl(token, tierKey));
    } catch (e) {
      setError("Could not start checkout. Please try again.");
    } finally {
      setBusyTier(null);
    }
  }

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

  const currentTier = me?.effective_tier ?? "free";
  const currentProvider = me?.payment_provider;

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
                  <View style={styles.upgradeButtonGroup}>
                    <Pressable
                      style={[styles.upgradeButton, busyTier === t.key && styles.buttonDisabled]}
                      onPress={() => upgradeWithPayfast(t.key)}
                      disabled={busyTier === t.key}
                    >
                      {busyTier === t.key ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <Text style={styles.upgradeButtonText}>Pay with PayFast</Text>
                      )}
                    </Pressable>
                    {hasGooglePlan ? (
                      <Pressable
                        style={[styles.upgradeButtonSecondary, busyTier === t.key && styles.buttonDisabled]}
                        onPress={() => upgradeWithGooglePlay(t.key)}
                        disabled={busyTier === t.key}
                      >
                        <Text style={styles.upgradeButtonSecondaryText}>Pay with Google Play</Text>
                      </Pressable>
                    ) : null}
                  </View>
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
  upgradeButtonGroup: { marginTop: 14, gap: 10 },
  upgradeButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
  },
  upgradeButtonSecondary: {
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.primary,
  },
  upgradeButtonSecondaryText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
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
  legalNote: { fontSize: 12, color: colors.textSecondary, marginTop: 10, lineHeight: 17 },
  legalLink: { color: colors.primary, fontWeight: "600" },
});
