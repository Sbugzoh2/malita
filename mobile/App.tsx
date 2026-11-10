import React from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider } from "./src/context/AuthContext";
import { TutorAuthProvider } from "./src/context/TutorAuthContext";
import RootNavigator from "./src/navigation/RootNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <TutorAuthProvider>
          <RootNavigator />
          <StatusBar style="auto" />
        </TutorAuthProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
