import React, { useCallback, useState } from "react";
import { View, ActivityIndicator, Pressable, Text, StyleSheet } from "react-native";
import Constants from "expo-constants";
import { NavigationContainer, useFocusEffect, useNavigation } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useAuth } from "../context/AuthContext";
import { useTutorAuth } from "../context/TutorAuthContext";
import { colors } from "../theme";
import NotificationBell from "../components/NotificationBell";
import { fetchTutorNotificationsUnreadCount } from "../api/client";
import LoginScreen from "../screens/LoginScreen";
import RegisterScreen from "../screens/RegisterScreen";
import TutorLoginScreen from "../screens/TutorLoginScreen";
import TutorApplyScreen from "../screens/TutorApplyScreen";
import TutorHomeScreen from "../screens/TutorHomeScreen";
import HomeScreen from "../screens/HomeScreen";
import AITutorScreen from "../screens/AITutorScreen";
import AITeacherScreen from "../screens/AITeacherScreen";
import SubscriptionScreen from "../screens/SubscriptionScreen";
import PracticeScreen from "../screens/PracticeScreen";
import PastPapersScreen from "../screens/PastPapersScreen";
import PastPaperViewerScreen from "../screens/PastPaperViewerScreen";
import LearnerProfileScreen from "../screens/LearnerProfileScreen";
import CollabScreen from "../screens/CollabScreen";
import CollabQuestionDetailScreen from "../screens/CollabQuestionDetailScreen";
import RequestTutorScreen from "../screens/RequestTutorScreen";
import MyTutoringRequestsScreen from "../screens/MyTutoringRequestsScreen";
import BrowseTutorsScreen from "../screens/BrowseTutorsScreen";
import TutoringAdminScreen from "../screens/TutoringAdminScreen";
import NotificationsScreen from "../screens/NotificationsScreen";
import TutorNotificationsScreen from "../screens/TutorNotificationsScreen";

const AuthStack = createNativeStackNavigator();
const AppStack = createNativeStackNavigator();
const TutorStack = createNativeStackNavigator();

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Register" component={RegisterScreen} />
      <AuthStack.Screen name="TutorLogin" component={TutorLoginScreen} />
      <AuthStack.Screen name="TutorApply" component={TutorApplyScreen} />
    </AuthStack.Navigator>
  );
}

// A tutor's own app, entirely separate from AppNavigator (learner) -
// just one screen for now (sessions + payouts), since a tutor's app
// surface is intentionally small in v1.
function TutorAppNavigator() {
  return (
    <TutorStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { color: colors.text },
        headerTintColor: colors.primary,
      }}
    >
      <TutorStack.Screen
        name="TutorHome"
        component={TutorHomeScreen}
        options={{ title: "Malita Tutor", headerRight: TutorNotificationBellButton }}
      />
      <TutorStack.Screen
        name="TutorNotifications"
        component={TutorNotificationsScreen}
        options={{ title: "Notifications" }}
      />
    </TutorStack.Navigator>
  );
}

function LogoutHeaderButton() {
  const { logout } = useAuth();
  return (
    <Pressable onPress={logout} style={styles.headerButton}>
      <Text style={styles.headerButtonText}>Log Out</Text>
    </Pressable>
  );
}

function TutorNotificationBellButton() {
  const { token } = useTutorAuth();
  const navigation = useNavigation();
  const [count, setCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      fetchTutorNotificationsUnreadCount(token).then((res) => setCount(res.count)).catch(() => {});
    }, [token])
  );

  return <NotificationBell count={count} onPress={() => navigation.navigate("TutorNotifications" as never)} />;
}

function AppNavigator() {
  const { me } = useAuth();
  // University/college accounts get ONLY the tutoring marketplace -
  // these screens aren't just hidden from Home's tile list (see
  // HomeScreen.tsx), they're not even registered in the stack, so
  // there's no route to navigate to even in principle. cross_segment_access
  // (a rare admin override - see backend/set_cross_segment_access.py)
  // registers every screen regardless of the account's own account_type.
  const isHigherEd = me?.user.account_type === "higher_ed" && !me?.user.cross_segment_access;

  return (
    <AppStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { color: colors.text },
        headerTintColor: colors.primary,
      }}
    >
      {/* HomeScreen builds its own header (greeting, avatar, notification
          bell) in its body, matching the redesigned Jobs/Home look rather
          than stacking a second native header bar above it. */}
      <AppStack.Screen name="Home" component={HomeScreen} options={{ headerShown: false }} />
      <AppStack.Screen name="Notifications" component={NotificationsScreen} options={{ title: "Notifications" }} />
      <AppStack.Screen name="RequestTutor" component={RequestTutorScreen} options={{ title: "Request a Tutor" }} />
      <AppStack.Screen name="BrowseTutors" component={BrowseTutorsScreen} options={{ title: "Browse Tutors" }} />
      <AppStack.Screen
        name="MyTutoringRequests"
        component={MyTutoringRequestsScreen}
        options={{ title: "My Tutoring Requests" }}
      />
      {!isHigherEd && (
        <>
          <AppStack.Screen
            name="AITutor"
            component={AITutorScreen}
            options={{ title: "AI Tutor", headerRight: LogoutHeaderButton }}
          />
          <AppStack.Screen name="AITeacher" component={AITeacherScreen} options={{ title: "AI Teacher" }} />
          <AppStack.Screen name="Subscription" component={SubscriptionScreen} options={{ title: "Subscription" }} />
          <AppStack.Screen name="PracticeQuestions" component={PracticeScreen} options={{ title: "Practice Questions" }} />
          <AppStack.Screen name="PastPapersLibrary" component={PastPapersScreen} options={{ title: "Past Papers Library" }} />
          <AppStack.Screen name="PastPaperViewer" component={PastPaperViewerScreen} options={{ title: "View Document" }} />
          <AppStack.Screen name="LearnerProfile" component={LearnerProfileScreen} options={{ title: "Learner Profile" }} />
          <AppStack.Screen name="Collab" component={CollabScreen} options={{ title: "Collaboration Forum" }} />
          <AppStack.Screen name="CollabQuestionDetail" component={CollabQuestionDetailScreen} options={{ title: "Question" }} />
          <AppStack.Screen
            name="TutoringAdmin"
            component={TutoringAdminScreen}
            options={{ title: "Tutoring Admin" }}
          />
        </>
      )}
    </AppStack.Navigator>
  );
}

export default function RootNavigator() {
  const { token, loading } = useAuth();
  const { token: tutorToken, loading: tutorLoading } = useTutorAuth();

  if (loading || tutorLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer
      linking={{
        // Lets PayFast's checkout redirect (return_url/cancel_url) bring
        // the learner straight back into the app instead of landing in a
        // browser with nowhere to go - see api_server.py's
        // /billing/checkout-page, which points PayFast at
        // {scheme}://billing rather than the web app's URL for exactly
        // this reason. Read from app.config.js's own "scheme" field
        // (not hardcoded) since the Malita Campus variant uses a
        // different scheme ("malitacampus") - see api_server.py's
        // SCHEME_BY_ACCOUNT_TYPE for the matching server-side half.
        prefixes: [`${Constants.expoConfig?.scheme ?? "malita"}://`],
        config: {
          screens: {
            Subscription: "billing",
            MyTutoringRequests: "tutoring",
          },
        },
      }}
    >
      {token ? <AppNavigator /> : tutorToken ? <TutorAppNavigator /> : <AuthNavigator />}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  headerButton: { marginRight: 12 },
  headerButtonText: { color: colors.primary, fontWeight: "600" },
});
