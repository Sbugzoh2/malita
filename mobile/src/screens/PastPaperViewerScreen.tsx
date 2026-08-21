import React, { useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";
import { colors } from "../theme";

// Renders a past paper PDF right inside the app (Android's and iOS's
// built-in WebView both know how to display a PDF loaded by URL) instead
// of handing the learner off to an external browser/download prompt.
export default function PastPaperViewerScreen({ route, navigation }: any) {
  const { url, title } = route.params ?? {};
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  return (
    <View style={styles.flex}>
      <Pressable style={styles.backLink} onPress={() => navigation.goBack()}>
        <Text style={styles.backLinkText}>‹ Back</Text>
      </Pressable>
      {title ? <Text style={styles.title}>{title}</Text> : null}

      {error ? (
        <View style={styles.centerBox}>
          <Text style={styles.errorText}>Couldn't display this document in-app.</Text>
        </View>
      ) : (
        <View style={styles.webviewBox}>
          {loading && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator color={colors.primary} size="large" />
            </View>
          )}
          <WebView
            source={{ uri: url }}
            style={styles.webview}
            onLoadEnd={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setError(true);
            }}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  backLink: { marginTop: 12, marginLeft: 16, marginBottom: 4 },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 15, fontWeight: "700", color: colors.text, marginHorizontal: 16, marginBottom: 8 },
  webviewBox: { flex: 1 },
  webview: { flex: 1, backgroundColor: colors.background },
  loadingOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
    zIndex: 1,
  },
  centerBox: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  errorText: { color: colors.error, textAlign: "center" },
});
