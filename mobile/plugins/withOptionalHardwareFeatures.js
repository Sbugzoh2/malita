const { withAndroidManifest } = require("@expo/config-plugins");

// Expo's `orientation: "portrait"` (see app.config.js) locks the app to
// portrait, which the Android build tags as a *required* hardware feature
// (android.hardware.screen.portrait) rather than a mere UI preference.
// Google Play then blocks install on any device that doesn't declare that
// feature - tablets, desktops, Android XR - even though nothing about this
// app actually needs portrait-only hardware. Marking it `required="false"`
// here keeps the portrait lock for phones while letting the listing stay
// installable everywhere else.
function withOptionalHardwareFeatures(config) {
  return withAndroidManifest(config, (config) => {
    const manifest = config.modResults.manifest;
    manifest["uses-feature"] = manifest["uses-feature"] || [];

    const featureName = "android.hardware.screen.portrait";
    const existing = manifest["uses-feature"].find((f) => f.$["android:name"] === featureName);
    if (existing) {
      existing.$["android:required"] = "false";
    } else {
      manifest["uses-feature"].push({
        $: { "android:name": featureName, "android:required": "false" },
      });
    }

    return config;
  });
}

module.exports = withOptionalHardwareFeatures;
