import React from "react";
import { View, ActivityIndicator, Pressable, Text, StyleSheet } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import LoginScreen from "../screens/LoginScreen";
import RegisterScreen from "../screens/RegisterScreen";
import HomeScreen from "../screens/HomeScreen";
import AITutorScreen from "../screens/AITutorScreen";
import SubscriptionScreen from "../screens/SubscriptionScreen";
import PracticeScreen from "../screens/PracticeScreen";
import PastPapersScreen from "../screens/PastPapersScreen";
import PastPaperViewerScreen from "../screens/PastPaperViewerScreen";

const AuthStack = createNativeStackNavigator();
const AppStack = createNativeStackNavigator();

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Register" component={RegisterScreen} />
    </AuthStack.Navigator>
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

function AppNavigator() {
  return (
    <AppStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { color: colors.text },
        headerTintColor: colors.primary,
      }}
    >
      <AppStack.Screen name="Home" component={HomeScreen} options={{ title: "Malita" }} />
      <AppStack.Screen
        name="AITutor"
        component={AITutorScreen}
        options={{ title: "AI Tutor", headerRight: LogoutHeaderButton }}
      />
      <AppStack.Screen name="Subscription" component={SubscriptionScreen} options={{ title: "Subscription" }} />
      <AppStack.Screen name="PracticeQuestions" component={PracticeScreen} options={{ title: "Practice Questions" }} />
      <AppStack.Screen name="PastPapersLibrary" component={PastPapersScreen} options={{ title: "Past Papers Library" }} />
      <AppStack.Screen name="PastPaperViewer" component={PastPaperViewerScreen} options={{ title: "View Document" }} />
    </AppStack.Navigator>
  );
}

export default function RootNavigator() {
  const { token, loading } = useAuth();

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {token ? <AppNavigator /> : <AuthNavigator />}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  headerButton: { marginRight: 12 },
  headerButtonText: { color: colors.primary, fontWeight: "600" },
});
