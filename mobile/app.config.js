// Dynamic config so ONE codebase builds TWO separately-listed apps:
//
//   APP_VARIANT=highschool (default) -> "Malita", for Grade 12 learners.
//   APP_VARIANT=campus              -> "Malita Campus", for the
//                                       university/college tutoring
//                                       marketplace (see backend's
//                                       account_type="higher_ed" gating
//                                       in HomeScreen.tsx/RootNavigator.tsx
//                                       - that gating is unchanged by
//                                       this file; it just controls which
//                                       app a person is holding when they
//                                       log into either account type).
//
// Build with: EAS_BUILD_PROFILE picks this up via eas.json's per-profile
// "env", e.g. `eas build --profile production-campus`. Locally,
// `APP_VARIANT=campus npx expo start` previews the Campus variant.
//
// ONE-TIME SETUP STILL NEEDED before the campus variant can actually be
// submitted anywhere (none of this is something code can do - see
// backend/google_calendar.py for the same kind of "code is ready, a
// human still has to click through a console once" split):
//   1. Run `eas init` for a NEW, second EAS project (not this one) and
//      replace CAMPUS_EAS_PROJECT_ID / CAMPUS_UPDATES_URL below with
//      what it gives you.
//   2. Register the new bundle identifier/package name below
//      (com.malita.campus) in App Store Connect and Google Play Console
//      - a fresh app listing in each, under the same developer accounts
//      you already have (no new Apple/Google account needed).
//   3. Swap the placeholder icon assets (assets/icon-campus.png,
//      assets/android-icon-*-campus.png) for real artwork whenever it's
//      ready - everything else here stays the same.
const APP_VARIANT = process.env.APP_VARIANT === "campus" ? "campus" : "highschool";
const IS_CAMPUS = APP_VARIANT === "campus";

// Placeholder until step 1 above is done.
const CAMPUS_EAS_PROJECT_ID = "REPLACE_WITH_CAMPUS_EAS_PROJECT_ID";
const CAMPUS_UPDATES_URL = `https://u.expo.dev/${CAMPUS_EAS_PROJECT_ID}`;

module.exports = {
  expo: {
    name: IS_CAMPUS ? "Malita Campus" : "Malita",
    slug: IS_CAMPUS ? "malita-campus" : "mobileapp",
    owner: "malita-app",
    // Also read dynamically by RootNavigator.tsx's deep-link config and
    // api_server.py's PayFast return bridge (via the `scheme` query
    // param) - change it here only, nowhere else.
    scheme: IS_CAMPUS ? "malitacampus" : "malita",
    version: "1.0.0",
    orientation: "portrait",
    icon: IS_CAMPUS ? "./assets/icon-campus.png" : "./assets/icon.png",
    userInterfaceStyle: "light",
    runtimeVersion: {
      policy: "fingerprint",
    },
    updates: {
      url: IS_CAMPUS
        ? CAMPUS_UPDATES_URL
        : "https://u.expo.dev/dea19c46-b69f-485e-95d3-0694e5ab06f2",
    },
    extra: {
      apiBaseUrl: "https://malita-api.onrender.com",
      appVariant: APP_VARIANT,
      eas: {
        projectId: IS_CAMPUS ? CAMPUS_EAS_PROJECT_ID : "dea19c46-b69f-485e-95d3-0694e5ab06f2",
      },
    },
    ios: {
      supportsTablet: true,
      bundleIdentifier: IS_CAMPUS ? "com.malita.campus" : "com.malita.mathstutor",
    },
    android: {
      package: IS_CAMPUS ? "com.malita.campus" : "com.malita.mathstutor",
      adaptiveIcon: {
        backgroundColor: IS_CAMPUS ? "#4a3aa7" : "#E6F4FE",
        foregroundImage: IS_CAMPUS
          ? "./assets/android-icon-foreground-campus.png"
          : "./assets/android-icon-foreground.png",
        backgroundImage: IS_CAMPUS
          ? "./assets/android-icon-background-campus.png"
          : "./assets/android-icon-background.png",
        monochromeImage: IS_CAMPUS
          ? "./assets/android-icon-monochrome-campus.png"
          : "./assets/android-icon-monochrome.png",
      },
      predictiveBackGestureEnabled: false,
    },
    web: {
      favicon: "./assets/favicon.png",
    },
    plugins: [
      [
        "expo-image-picker",
        {
          photosPermission:
            "Malita needs access to your photos so you can upload a picture of a Mathematics or Physical Sciences question.",
          cameraPermission:
            "Malita needs access to your camera so you can take a photo of a Mathematics or Physical Sciences question.",
        },
      ],
      "expo-iap",
      "expo-build-properties",
      // Marks android.hardware.screen.portrait as optional rather than
      // required, so Google Play doesn't block tablets/desktops/Android XR
      // from installing the app just because it's locked to portrait on
      // phones (orientation: "portrait" above) - see the plugin file for
      // the full explanation.
      "./plugins/withOptionalHardwareFeatures",
    ],
  },
};
