# Running the Malita app on Expo Snack (no Node.js install needed)

Expo Snack (https://snack.expo.dev) runs entirely in your browser, so this
works even with Node.js blocked on your PC.

**Important lesson from last time**: Snack's embedded preview panel runs
inside an iframe that can hit mixed-content/network restrictions on a
locked-down corporate machine. If register/login doesn't work from the
embedded preview, use the "open in new tab" / expand icon on the preview
panel to open it as its own real top-level page instead — that sidesteps
the iframe restriction entirely and is the reliable way to test this.

(If you want to preview on your **phone** via the Expo Go app instead of
the browser, `localhost` won't work from the phone — you'd need your PC's
LAN IP address instead, e.g. `http://192.168.1.23:8002`, with the phone on
the same Wi-Fi — and corporate Wi-Fi often blocks device-to-device traffic
anyway. Browser preview in its own tab is the simplest reliable path.)

## Step 1 — Open a new Snack

Go to https://snack.expo.dev — it opens with a default counter-button demo
project. You'll replace its files with the ones below.

## Step 2 — Add dependencies

In the left sidebar, there's an "Add package" / dependencies search box (or
click the package.json-like icon). Add each of these (Snack will resolve
compatible versions automatically — just search the name and click it):

- `@react-navigation/native`
- `@react-navigation/native-stack`
- `react-native-screens`
- `react-native-safe-area-context`
- `@react-native-async-storage/async-storage`
- `expo-constants`
- `expo-status-bar` (Snack's default template usually includes this
  already — only add it if you get an "Unable to resolve module
  'expo-status-bar'" error)
- `expo-image-picker` (new — powers the OCR screen's Take Photo / Choose
  from Gallery buttons)
- `expo-document-picker` (new — powers the Past Papers (PDF) screen's
  Choose PDF button)

If you're editing a raw `package.json`-style file instead of using the
search box, every entry needs an actual version string, e.g.:
```json
{
  "dependencies": {
    "@react-navigation/native": "^7.3.14",
    "@react-navigation/native-stack": "^7.18.6",
    "react-native-screens": "~4.11.1",
    "react-native-safe-area-context": "~5.4.0",
    "@react-native-async-storage/async-storage": "^2.2.0",
    "expo-constants": "~18.0.0",
    "expo-status-bar": "~57.0.1",
    "expo-image-picker": "~17.0.0",
    "expo-document-picker": "~14.0.0"
  }
}
```

If your Snack has an `app.json`, add this so the camera/photo permission
prompts show a real explanation on iOS/Android (harmless to skip for the
web preview — web has no OS permission dialog):
```json
{
  "expo": {
    "plugins": [
      [
        "expo-image-picker",
        {
          "photosPermission": "Malita needs access to your photos so you can upload a picture of a maths question.",
          "cameraPermission": "Malita needs access to your camera so you can take a photo of a maths question."
        }
      ]
    ]
  }
}
```

## Step 3 — Create the files

In Snack's file panel, create each file below with the **exact path** shown
(Snack supports slashes in filenames to create folders), and paste in its
content. **Delete the default `App.js` file first** and create `App.tsx`
instead — don't just edit `App.js`, actually delete it, otherwise its old
imports (e.g. `react-native-paper`) will still error even after you add
`App.tsx`.

### `App.tsx`
```tsx
import React from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider } from "./src/context/AuthContext";
import RootNavigator from "./src/navigation/RootNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <RootNavigator />
        <StatusBar style="auto" />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
```

### `src/theme.ts`
```ts
// Mirrors the palette used in app.py's CSS / TOPIC_COLORS so the native
// app feels like the same product, not a different one.
export const colors = {
  background: "#f9f9f7",
  surface: "#ffffff",
  border: "#e1e0d9",
  text: "#0b0b0b",
  textSecondary: "#52514e",
  primary: "#2a78d6",
  primaryDark: "#184f95",
  error: "#e34948",
};

export const topicColors: Record<string, string> = {
  Algebra: "#2a78d6",
  Sequences: "#eb6834",
  "Financial Mathematics": "#1baf7a",
  Calculus: "#eda100",
  "Functions & Graphs": "#e87ba4",
  "Analytical Geometry": "#008300",
  Trigonometry: "#4a3aa7",
  Statistics: "#e34948",
  "Statistics & Probability": "#e34948",
  Probability: "#2a78d6",
  "Euclidean Geometry": "#eb6834",
};

export const PAPER_TOPICS: Record<string, string[]> = {
  "Paper 1": ["Algebra", "Sequences", "Financial Mathematics", "Calculus", "Functions & Graphs"],
  "Paper 2": ["Analytical Geometry", "Trigonometry", "Statistics", "Probability", "Euclidean Geometry"],
};

// Topics api_server.py's /solve can actually answer today - see
// api_server.py's SUPPORTED_SOLVE_TOPICS and README.md section 8.
export const SOLVABLE_TOPICS = new Set([
  "Algebra",
  "Sequences",
  "Financial Mathematics",
  "Calculus",
  "Functions & Graphs",
  "Analytical Geometry",
  "Trigonometry",
  "Statistics",
  "Probability",
  "Euclidean Geometry",
]);
```

### `src/api/client.ts`
```ts
// Malita mobile — thin fetch wrapper around api_server.py.
//
// Point API_BASE_URL at your deployed api_server.py before shipping a real
// build (Render/Railway/etc, same hosting story as webhook_server.py).
// Defaults to localhost for local development against
// `uvicorn api_server:app --host 0.0.0.0 --port 8002`.
import Constants from "expo-constants";
import { Platform } from "react-native";

export const API_BASE_URL: string =
  (Constants.expoConfig?.extra as any)?.apiBaseUrl ?? "http://localhost:8002";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null } = {}
): Promise<T> {
  const { method = "GET", body, token } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data));
  }
  return data as T;
}

// FastAPI's `detail` is a plain string for HTTPException, but a list of
// {loc, msg, type} objects for pydantic validation errors (422s) - guard
// against handing that array straight to the Error message.
function errorMessage(data: any, fallback = "Something went wrong. Please try again."): string {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg;
  return fallback;
}

export type UserInfo = {
  id: number;
  name: string;
  email: string;
  tier: string;
  subscription_status: string;
  is_admin: boolean;
};

export type MeResponse = {
  user: UserInfo;
  is_admin: boolean;
  effective_tier: string;
  tier_label: string;
  daily_limit: number | null;
  used_today: number;
};

export type SolveStep = { type: string; content: string };

export type RegisterParams = {
  name: string;
  email: string;
  password: string;
  province: string;
  city_town: string;
  school?: string;
};

export function register(params: RegisterParams) {
  return request<{ token: string; user: UserInfo }>("/auth/register", {
    method: "POST",
    body: params,
  });
}

export function login(email: string, password: string) {
  return request<{ token: string; user: UserInfo }>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function logout(token: string) {
  return request<{ ok: boolean }>("/auth/logout", { method: "POST", token });
}

export function forgotPassword(email: string) {
  return request<{ message: string }>("/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function getMe(token: string) {
  return request<MeResponse>("/me", { token });
}

export function solve(token: string, params: { paper: string; topic: string; question: string }) {
  return request<{ steps: SolveStep[] }>("/solve", { method: "POST", body: params, token });
}

export function fetchProvinces() {
  return request<{ provinces: string[] }>("/meta/provinces");
}

async function uploadFile(
  path: string,
  token: string,
  file: { uri: string; name: string; type: string }
): Promise<{ text: string }> {
  const formData = new FormData();
  if (Platform.OS === "web") {
    // react-native-web has no native {uri,name,type} FormData shim - the
    // uri is a blob:/data: URL that has to be fetched into a real Blob
    // first, or the field ends up stringified as "[object Object]".
    const blob = await (await fetch(file.uri)).blob();
    formData.append("file", blob, file.name);
  } else {
    // React Native's fetch/FormData accepts this {uri,name,type} shape in
    // place of a real Blob/File (which RN doesn't have) - this is the
    // standard RN file-upload pattern, not a mistake.
    formData.append("file", file as any);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, "Upload failed. Please try again."));
  }
  return data;
}

export function ocrImage(token: string, imageUri: string, mimeType: string = "image/jpeg") {
  return uploadFile("/ocr", token, { uri: imageUri, name: "photo.jpg", type: mimeType });
}

export function pdfExtract(token: string, fileUri: string, fileName: string = "paper.pdf") {
  return uploadFile("/pdf-extract", token, { uri: fileUri, name: fileName, type: "application/pdf" });
}
```

### `src/context/AuthContext.tsx`
```tsx
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as api from "../api/client";

const TOKEN_KEY = "malita_token";

type AuthContextValue = {
  token: string | null;
  me: api.MeResponse | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (params: api.RegisterParams) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<api.MeResponse | null>(null);
  // Starts true - we don't know yet whether a token is stored, so the
  // navigator below must wait for this before deciding Login vs Home.
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async (activeToken?: string | null) => {
    const t = activeToken ?? token;
    if (!t) {
      setMe(null);
      return;
    }
    try {
      const info = await api.getMe(t);
      setMe(info);
    } catch (e) {
      // Token expired/revoked server-side - drop it locally too.
      await AsyncStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setMe(null);
    }
  }, [token]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem(TOKEN_KEY);
      if (stored) {
        setToken(stored);
        await refreshMe(stored);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { token: newToken } = await api.login(email, password);
    await AsyncStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    await refreshMe(newToken);
  }, [refreshMe]);

  const register = useCallback(async (params: api.RegisterParams) => {
    const { token: newToken } = await api.register(params);
    await AsyncStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    await refreshMe(newToken);
  }, [refreshMe]);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await api.logout(token);
      } catch {
        // Best-effort - still clear the local session even if the
        // network call fails, so the user isn't stuck "logged in".
      }
    }
    await AsyncStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setMe(null);
  }, [token]);

  return (
    <AuthContext.Provider
      value={{ token, me, loading, refreshMe: () => refreshMe(), login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
```

### `src/navigation/RootNavigator.tsx`
```tsx
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
import OCRScreen from "../screens/OCRScreen";
import PDFScreen from "../screens/PDFScreen";

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
      <AppStack.Screen name="OCR" component={OCRScreen} options={{ title: "OCR Question" }} />
      <AppStack.Screen name="PDF" component={PDFScreen} options={{ title: "Past Papers (PDF)" }} />
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
```

### `src/latex/parseLatex.ts`
```ts
// A small, dependency-free parser for the constrained subset of LaTeX
// backend/solver.py actually emits (equations, fractions, roots, sub/
// superscripts, a handful of symbol commands) - NOT a general LaTeX
// parser. Deliberately avoids any WebView/CDN-based renderer (e.g.
// KaTeX-over-network) since this app has already hit repeated network/
// CSP friction in locked-down environments; this has zero runtime
// dependencies beyond plain string parsing.

export type LatexNode =
  | { type: "text"; value: string }
  | { type: "row"; children: LatexNode[] }
  | { type: "sup"; base: LatexNode; exp: LatexNode }
  | { type: "sub"; base: LatexNode; sub: LatexNode }
  | { type: "frac"; numerator: LatexNode; denominator: LatexNode }
  | { type: "sqrt"; radicand: LatexNode };

const SYMBOL_MAP: Record<string, string> = {
  "\\pm": "±",
  "\\mp": "∓",
  "\\times": "×",
  "\\cdot": "·",
  "\\div": "÷",
  "\\Delta": "Δ",
  "\\delta": "δ",
  "\\infty": "∞",
  "\\leq": "≤",
  "\\geq": "≥",
  "\\neq": "≠",
  "\\approx": "≈",
  "\\pi": "π",
  "\\theta": "θ",
  "\\alpha": "α",
  "\\beta": "β",
  "\\quad": "  ",
  "\\qquad": "    ",
  "\\;": " ",
  "\\,": " ",
  "\\!": "",
  "\\left": "",
  "\\right": "",
};

class Parser {
  private s: string;
  private i = 0;

  constructor(s: string) {
    this.s = s;
  }

  private peek(): string {
    return this.s[this.i] ?? "";
  }

  private eof(): boolean {
    return this.i >= this.s.length;
  }

  private readCommand(): string {
    let j = this.i + 1;
    if (/[a-zA-Z]/.test(this.s[j] ?? "")) {
      while (j < this.s.length && /[a-zA-Z]/.test(this.s[j])) j++;
    } else {
      j++; // single-char escape like \; or \,
    }
    const cmd = this.s.slice(this.i, j);
    this.i = j;
    return cmd;
  }

  private readGroup(): LatexNode {
    if (this.peek() === "{") {
      this.i++;
      const node = this.parseRow("}");
      if (this.peek() === "}") this.i++;
      return node;
    }
    if (this.peek() === "\\") {
      const cmd = this.readCommand();
      return this.commandToNode(cmd);
    }
    const ch = this.peek();
    this.i++;
    return { type: "text", value: ch };
  }

  private commandToNode(cmd: string): LatexNode {
    if (cmd === "\\frac") {
      const numerator = this.readGroup();
      const denominator = this.readGroup();
      return { type: "frac", numerator, denominator };
    }
    if (cmd === "\\sqrt") {
      const radicand = this.readGroup();
      return { type: "sqrt", radicand };
    }
    if (cmd === "\\text") {
      return this.readGroup();
    }
    if (cmd in SYMBOL_MAP) {
      return { type: "text", value: SYMBOL_MAP[cmd] };
    }
    // Unknown command - render literally so nothing silently disappears.
    return { type: "text", value: cmd.replace(/^\\/, "") };
  }

  parseRow(stopChar?: string): LatexNode {
    const children: LatexNode[] = [];
    while (!this.eof() && this.peek() !== stopChar) {
      const ch = this.peek();

      if (ch === "\\") {
        const cmd = this.readCommand();
        children.push(this.commandToNode(cmd));
        continue;
      }

      if (ch === "^" || ch === "_") {
        this.i++;
        const base = children.pop() ?? { type: "text", value: "" };
        const attachment = this.readGroup();
        children.push(
          ch === "^"
            ? { type: "sup", base, exp: attachment }
            : { type: "sub", base, sub: attachment }
        );
        continue;
      }

      if (ch === "{") {
        this.i++;
        children.push(this.parseRow("}"));
        if (this.peek() === "}") this.i++;
        continue;
      }

      this.i++;
      const last = children[children.length - 1];
      if (last && last.type === "text") {
        last.value += ch;
      } else {
        children.push({ type: "text", value: ch });
      }
    }
    return { type: "row", children };
  }
}

export function parseLatex(input: string): Extract<LatexNode, { type: "row" }> {
  return new Parser(input).parseRow() as Extract<LatexNode, { type: "row" }>;
}
```

### `src/latex/LatexView.tsx`
```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { parseLatex, LatexNode } from "./parseLatex";
import { colors } from "../theme";

type FracNode = Extract<LatexNode, { type: "frac" }>;

export default function LatexView({ latex, fontSize = 16 }: { latex: string; fontSize?: number }) {
  const tree = React.useMemo(() => parseLatex(latex), [latex]);
  const groups = React.useMemo(() => groupRowChildren(tree.children), [tree]);

  return (
    <View style={styles.rowWrap}>
      {groups.map((group, i) =>
        group.type === "frac" ? (
          <FracView key={i} node={group.node} fontSize={fontSize} />
        ) : (
          <Text key={i} style={{ fontSize, color: colors.text }}>
            {group.nodes.map((n, j) => (
              <React.Fragment key={j}>{renderInline(n, fontSize)}</React.Fragment>
            ))}
          </Text>
        )
      )}
    </View>
  );
}

// A `frac` needs its own block-level <View> (numerator/bar/denominator
// stacked vertically), which can't sit inside the same <Text> as its
// neighbours - so a row of siblings gets split into runs of plain
// inline content and standalone frac blocks, rendered side by side.
function groupRowChildren(nodes: LatexNode[]) {
  const groups: ({ type: "inline"; nodes: LatexNode[] } | { type: "frac"; node: FracNode })[] = [];
  let current: LatexNode[] = [];
  for (const n of nodes) {
    if (n.type === "frac") {
      if (current.length) {
        groups.push({ type: "inline", nodes: current });
        current = [];
      }
      groups.push({ type: "frac", node: n });
    } else {
      current.push(n);
    }
  }
  if (current.length) groups.push({ type: "inline", nodes: current });
  return groups;
}

// Renders a node as plain Text-nestable content (strings / nested <Text>
// spans only, no <View>) - valid for text/sup/sub/sqrt since none of
// backend/solver.py's LaTeX today nests a `\frac` inside an exponent,
// subscript, or square root. If a future topic ever does, this falls
// back to an inline "(num/den)" rather than crashing.
function renderInline(node: LatexNode, fontSize: number): React.ReactNode {
  switch (node.type) {
    case "text":
      return node.value;
    case "row":
      return node.children.map((c, i) => (
        <React.Fragment key={i}>{renderInline(c, fontSize)}</React.Fragment>
      ));
    case "sup":
      return (
        <>
          {renderInline(node.base, fontSize)}
          <Text style={{ fontSize: fontSize * 0.68, top: -fontSize * 0.32 }}>
            {renderInline(node.exp, fontSize * 0.68)}
          </Text>
        </>
      );
    case "sub":
      return (
        <>
          {renderInline(node.base, fontSize)}
          <Text style={{ fontSize: fontSize * 0.68, top: fontSize * 0.12 }}>
            {renderInline(node.sub, fontSize * 0.68)}
          </Text>
        </>
      );
    case "sqrt":
      return (
        <>
          {"√("}
          {renderInline(node.radicand, fontSize)}
          {")"}
        </>
      );
    case "frac":
      return (
        <>
          ({renderInline(node.numerator, fontSize)}/{renderInline(node.denominator, fontSize)})
        </>
      );
  }
}

function FracView({ node, fontSize }: { node: FracNode; fontSize: number }) {
  return (
    <View style={styles.frac}>
      <Text style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
        {renderInline(node.numerator, fontSize * 0.85)}
      </Text>
      <View style={styles.fracBar} />
      <Text style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
        {renderInline(node.denominator, fontSize * 0.85)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  rowWrap: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
  frac: { alignItems: "center", marginHorizontal: 3 },
  fracText: { color: colors.text, textAlign: "center" },
  fracBar: { height: 1, backgroundColor: colors.text, alignSelf: "stretch", marginVertical: 1 },
});
```

### `src/screens/LoginScreen.tsx`
```tsx
import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, forgotPassword } from "../api/client";

export default function LoginScreen({ navigation }: any) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleLogin() {
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not log in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleForgotPassword() {
    setError(null);
    setInfo(null);
    if (!email.trim()) {
      setError("Enter your email above first, then tap 'Forgot password?'");
      return;
    }
    try {
      const res = await forgotPassword(email.trim().toLowerCase());
      setInfo(res.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>🎓 Malita</Text>
        <Text style={styles.subtitle}>Matric Maths Master</Text>

        <View style={styles.card}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="you@example.com"
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="••••••••"
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}
          {info ? <Text style={styles.info}>{info}</Text> : null}

          <Pressable
            style={[styles.button, submitting && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Log In</Text>
            )}
          </Pressable>

          <Pressable onPress={handleForgotPassword} style={styles.linkButton}>
            <Text style={styles.link}>Forgot your password?</Text>
          </Pressable>
        </View>

        <Pressable onPress={() => navigation.navigate("Register")} style={styles.linkButton}>
          <Text style={styles.link}>New here? Create a free account</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { flexGrow: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 32, fontWeight: "700", textAlign: "center", color: colors.text },
  subtitle: { fontSize: 16, textAlign: "center", color: colors.textSecondary, marginBottom: 24 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: "#fff",
  },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 20,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  linkButton: { marginTop: 16, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  error: { color: colors.error, marginTop: 12 },
  info: { color: colors.primaryDark, marginTop: 12 },
});
```

### `src/screens/RegisterScreen.tsx`
```tsx
import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, fetchProvinces } from "../api/client";

export default function RegisterScreen({ navigation }: any) {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [school, setSchool] = useState("");
  const [province, setProvince] = useState("");
  const [cityTown, setCityTown] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [provinces, setProvinces] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchProvinces()
      .then((res) => setProvinces(res.provinces))
      .catch(() => {
        // Non-fatal - the user can still type a province manually below.
      });
  }, []);

  async function handleRegister() {
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    if (!province.trim()) {
      setError("Please enter your province.");
      return;
    }
    setSubmitting(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        province: province.trim(),
        city_town: cityTown.trim(),
        school: school.trim(),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Create your free account</Text>

        <View style={styles.card}>
          <Text style={styles.label}>Full name</Text>
          <TextInput style={styles.input} value={name} onChangeText={setName} />

          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />

          <Text style={styles.label}>School (optional)</Text>
          <TextInput style={styles.input} value={school} onChangeText={setSchool} />

          <Text style={styles.label}>
            Province{provinces.length > 0 ? ` (e.g. ${provinces[0]})` : ""}
          </Text>
          <TextInput style={styles.input} value={province} onChangeText={setProvince} />

          <Text style={styles.label}>City / Town</Text>
          <TextInput style={styles.input} value={cityTown} onChangeText={setCityTown} />

          <Text style={styles.label}>Password</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry />

          <Text style={styles.label}>Confirm password</Text>
          <TextInput
            style={styles.input}
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Pressable
            style={[styles.button, submitting && styles.buttonDisabled]}
            onPress={handleRegister}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Create Free Account</Text>
            )}
          </Pressable>
        </View>

        <Pressable onPress={() => navigation.navigate("Login")} style={styles.linkButton}>
          <Text style={styles.link}>Already have an account? Log in</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { flexGrow: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "700", textAlign: "center", color: colors.text, marginBottom: 20 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: "#fff",
  },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 20,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  linkButton: { marginTop: 16, alignItems: "center" },
  link: { color: colors.primary, fontWeight: "600" },
  error: { color: colors.error, marginTop: 12 },
});
```

### `src/screens/HomeScreen.tsx`
```tsx
import React from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";

const TILES = [
  {
    key: "AITutor",
    icon: "🧮",
    title: "AI Tutor",
    desc: "Get any Grade 12 question solved step by step.",
    color: "#2a78d6",
  },
  {
    key: "PracticeQuestions",
    icon: "📝",
    title: "Practice Questions",
    desc: "Coming soon in the app — available on the web version today.",
    color: "#eb6834",
    disabled: true,
  },
  {
    key: "OCR",
    icon: "📷",
    title: "OCR Question",
    desc: "Snap a photo of a question and let us read it for you.",
    color: "#1baf7a",
  },
  {
    key: "PDF",
    icon: "📚",
    title: "Past Papers (PDF)",
    desc: "Upload a past paper PDF and pull questions straight from it.",
    color: "#eda100",
  },
];

export default function HomeScreen({ navigation }: any) {
  const { me, logout } = useAuth();

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.greeting}>👋 Welcome back, {me?.user.name.split(" ")[0] ?? ""}!</Text>
      <Text style={styles.plan}>
        Plan: {me?.tier_label ?? "Free"}
        {me?.daily_limit != null ? ` · ${me.used_today}/${me.daily_limit} solves today` : ""}
      </Text>

      <Text style={styles.pick}>Pick where you'd like to start.</Text>

      {TILES.map((tile) => (
        <Pressable
          key={tile.key}
          style={[styles.tile, { backgroundColor: tile.color }, tile.disabled && styles.tileDisabled]}
          onPress={() => !tile.disabled && navigation.navigate(tile.key)}
          disabled={tile.disabled}
        >
          <Text style={styles.tileIcon}>{tile.icon}</Text>
          <Text style={styles.tileTitle}>{tile.title}</Text>
          <Text style={styles.tileDesc}>{tile.desc}</Text>
        </Pressable>
      ))}

      <Pressable style={styles.logoutButton} onPress={logout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  greeting: { fontSize: 26, fontWeight: "700", color: colors.text },
  plan: { fontSize: 14, color: colors.textSecondary, marginTop: 6 },
  pick: { fontSize: 15, color: colors.textSecondary, marginTop: 16, marginBottom: 12 },
  tile: {
    borderRadius: 20,
    padding: 20,
    marginBottom: 14,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  tileDisabled: { opacity: 0.55 },
  tileIcon: { fontSize: 32, marginBottom: 6 },
  tileTitle: { fontSize: 18, fontWeight: "700", color: "#fff", marginBottom: 4 },
  tileDesc: { fontSize: 13, color: "#ffffffeb" },
  logoutButton: {
    marginTop: 24,
    alignSelf: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 28,
  },
  logoutText: { color: "#fff", fontWeight: "700" },
});
```

### `src/screens/AITutorScreen.tsx`
```tsx
import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  Dimensions,
} from "react-native";
import { useAuth } from "../context/AuthContext";
import { colors, PAPER_TOPICS, SOLVABLE_TOPICS, topicColors } from "../theme";
import { ApiError, solve, SolveStep } from "../api/client";
import LatexView from "../latex/LatexView";

export default function AITutorScreen({ route }: any) {
  const { token, me, refreshMe } = useAuth();
  const [paper, setPaper] = useState<"Paper 1" | "Paper 2">("Paper 1");
  const [topic, setTopic] = useState("Algebra");
  const [question, setQuestion] = useState("");
  const [steps, setSteps] = useState<SolveStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [solving, setSolving] = useState(false);

  // OCR/PDF screens navigate here with a pre-filled question (their own
  // "Transfer to Solver" equivalent) - adopt it once per navigation, the
  // same one-shot pattern app.py's copied_text uses.
  React.useEffect(() => {
    const prefill = route?.params?.prefillQuestion;
    if (prefill) {
      setQuestion(prefill);
      setSteps(null);
      setError(null);
    }
  }, [route?.params?.prefillQuestion]);

  function selectPaper(p: "Paper 1" | "Paper 2") {
    setPaper(p);
    setTopic(PAPER_TOPICS[p][0]);
    setSteps(null);
    setError(null);
  }

  async function handleSolve() {
    if (!token || !question.trim()) return;
    setSolving(true);
    setError(null);
    setSteps(null);
    try {
      const res = await solve(token, { paper, topic, question: question.trim() });
      setSteps(res.steps);
      await refreshMe();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSolving(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>🧮 AI Tutor</Text>
      <Text style={styles.subtitle}>Grade 12 Mathematics help, worked out one step at a time.</Text>

      <Text style={styles.label}>Paper</Text>
      <View style={styles.row}>
        {(["Paper 1", "Paper 2"] as const).map((p) => (
          <Pressable
            key={p}
            style={[styles.chip, paper === p && styles.chipActive]}
            onPress={() => selectPaper(p)}
          >
            <Text style={[styles.chipText, paper === p && styles.chipTextActive]}>{p}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Topic</Text>
      <View style={styles.row}>
        {PAPER_TOPICS[paper].map((t) => {
          const solvable = SOLVABLE_TOPICS.has(t);
          return (
            <Pressable
              key={t}
              style={[
                styles.chip,
                topic === t && { backgroundColor: topicColors[t] ?? colors.primary, borderColor: "transparent" },
                !solvable && styles.chipDisabled,
              ]}
              onPress={() => {
                setTopic(t);
                setSteps(null);
                setError(null);
              }}
            >
              <Text style={[styles.chipText, topic === t && styles.chipTextActive]}>
                {t}
                {!solvable ? " (web only)" : ""}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.label}>Enter your expression or question</Text>
      <TextInput
        style={styles.input}
        value={question}
        onChangeText={setQuestion}
        placeholder="e.g. x^2-5x+6=0"
        autoCapitalize="none"
      />

      {!SOLVABLE_TOPICS.has(topic) && (
        <Text style={styles.notice}>
          {topic} isn't available in the app yet — try Algebra here, or use the web version for this topic.
        </Text>
      )}

      <Pressable
        style={[styles.solveButton, (solving || !question.trim()) && styles.buttonDisabled]}
        onPress={handleSolve}
        disabled={solving || !question.trim()}
      >
        {solving ? <ActivityIndicator color="#fff" /> : <Text style={styles.solveButtonText}>Solve</Text>}
      </Pressable>

      {me?.daily_limit != null && (
        <Text style={styles.usage}>
          {me.used_today}/{me.daily_limit} solves used today
        </Text>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {steps && (
        <View style={styles.resultCard}>
          {steps.map((step, i) => (
            <StepView key={i} step={step} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function StepView({ step }: { step: SolveStep }) {
  if (step.type === "latex") {
    return (
      <View style={styles.latexBox}>
        <LatexView latex={step.content} fontSize={16} />
      </View>
    );
  }
  if (step.type === "image") {
    // step.content is already a full "data:image/png;base64,...." URI -
    // see backend/solver.py's StepRecorder.pyplot().
    return (
      <Image
        source={{ uri: step.content }}
        style={styles.stepImage}
        resizeMode="contain"
      />
    );
  }
  const emphasis = step.type === "markdown" || step.type === "write";
  const toneStyle =
    step.type === "error"
      ? styles.stepError
      : step.type === "warning"
      ? styles.stepWarning
      : step.type === "success"
      ? styles.stepSuccess
      : step.type === "info"
      ? styles.stepInfo
      : step.type === "caption"
      ? styles.stepCaption
      : undefined;
  return (
    <MixedText
      text={stripMarkdown(step.content)}
      style={[styles.stepText, emphasis && styles.stepEmphasis, toneStyle]}
    />
  );
}

function stripMarkdown(text: string) {
  return text.replace(/\*\*/g, "").replace(/^#+\s*/, "");
}

// The solver's non-"latex" steps (markdown/write/info/...) sometimes embed
// inline math as $...$ (e.g. "Solve quadratic factor: $x^{2}+4x-4=0$") -
// split on that and render those spans through LatexView instead of
// leaving the raw LaTeX source visible.
function MixedText({ text, style }: { text: string; style: any }) {
  const parts = text.split(/\$([^$]+)\$/);
  if (parts.length === 1) {
    return <Text style={style}>{text}</Text>;
  }
  return (
    <View style={styles.mixedRow}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <LatexView key={i} latex={part} fontSize={15} />
        ) : part ? (
          <Text key={i} style={style}>
            {part}
          </Text>
        ) : null
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 14, marginBottom: 6 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  chipActive: { backgroundColor: colors.primary, borderColor: "transparent" },
  chipDisabled: { opacity: 0.6 },
  chipText: { color: colors.text, fontSize: 13 },
  chipTextActive: { color: "#fff", fontWeight: "700" },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    backgroundColor: "#fff",
    marginTop: 4,
  },
  notice: { color: colors.textSecondary, fontSize: 12, marginTop: 8, fontStyle: "italic" },
  solveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 16,
  },
  buttonDisabled: { opacity: 0.5 },
  solveButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  usage: { textAlign: "center", color: colors.textSecondary, fontSize: 12, marginTop: 8 },
  error: { color: colors.error, marginTop: 12, textAlign: "center" },
  resultCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 20,
  },
  stepText: { fontSize: 15, color: colors.text, marginBottom: 6, lineHeight: 21 },
  stepEmphasis: { fontWeight: "700", marginTop: 8 },
  mixedRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", marginBottom: 6 },
  stepInfo: { color: colors.primaryDark },
  stepWarning: { color: "#a15c00" },
  stepError: { color: colors.error, fontWeight: "600" },
  stepSuccess: { color: "#0ca30c", fontWeight: "600" },
  stepCaption: { fontSize: 12, color: colors.textSecondary, fontStyle: "italic" },
  stepImage: {
    width: Dimensions.get("window").width - 72,
    height: 220,
    marginVertical: 10,
    borderRadius: 10,
  },
  latexBox: {
    backgroundColor: "#f3f6fb",
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 6,
  },
});
```

### `src/screens/OCRScreen.tsx`
```tsx
import React, { useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  TextInput,
  Alert,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, ocrImage } from "../api/client";

export default function OCRScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [recognizedText, setRecognizedText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ocrLocked = me?.effective_tier === "free";

  async function runOcr(uri: string) {
    if (!token) return;
    setImageUri(uri);
    setRecognizedText("");
    setError(null);
    setLoading(true);
    try {
      const res = await ocrImage(token, uri);
      setRecognizedText(res.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read that image. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Camera permission needed", "Enable camera access in your device settings to take a photo.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.9, allowsEditing: false });
    if (!result.canceled && result.assets?.[0]) {
      await runOcr(result.assets[0].uri);
    }
  }

  async function pickFromGallery() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Photo library permission needed", "Enable photo access in your device settings to upload an image.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.9,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets?.[0]) {
      await runOcr(result.assets[0].uri);
    }
  }

  function sendToSolver() {
    navigation.navigate("AITutor", { prefillQuestion: recognizedText });
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>📷 OCR Question</Text>
      <Text style={styles.subtitle}>Snap a photo of a question and let us read it for you.</Text>

      {ocrLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            Photo upload & OCR is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
        </View>
      ) : (
        <>
          <View style={styles.row}>
            <Pressable style={styles.actionButton} onPress={takePhoto}>
              <Text style={styles.actionButtonText}>📸 Take Photo</Text>
            </Pressable>
            <Pressable style={styles.actionButton} onPress={pickFromGallery}>
              <Text style={styles.actionButtonText}>🖼️ Choose from Gallery</Text>
            </Pressable>
          </View>

          {imageUri && <Image source={{ uri: imageUri }} style={styles.preview} resizeMode="contain" />}

          {loading && (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.loadingText}>Reading the image…</Text>
            </View>
          )}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {recognizedText ? (
            <View style={styles.resultCard}>
              <Text style={styles.label}>Recognised expression (edit if needed)</Text>
              <TextInput
                style={styles.input}
                value={recognizedText}
                onChangeText={setRecognizedText}
                multiline
              />
              <Pressable style={styles.solveButton} onPress={sendToSolver}>
                <Text style={styles.solveButtonText}>Send to AI Tutor →</Text>
              </Pressable>
            </View>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  row: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  preview: { width: "100%", height: 220, marginTop: 16, borderRadius: 12, backgroundColor: "#eee" },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16 },
  loadingText: { color: colors.textSecondary },
  error: { color: colors.error, marginTop: 16 },
  resultCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 16 },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 12,
    fontSize: 16,
    backgroundColor: "#fff",
    minHeight: 60,
  },
  solveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 14,
  },
  solveButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00" },
});
```

### `src/screens/PDFScreen.tsx`
```tsx
import React, { useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  TextInput,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import { ApiError, pdfExtract } from "../api/client";

export default function PDFScreen({ navigation }: any) {
  const { token, me } = useAuth();
  const [extractedText, setExtractedText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pdfLocked = me?.effective_tier === "free";

  async function pickPdf() {
    const result = await DocumentPicker.getDocumentAsync({ type: "application/pdf" });
    if (result.canceled || !result.assets?.[0] || !token) return;

    const asset = result.assets[0];
    setFileName(asset.name);
    setExtractedText("");
    setError(null);
    setLoading(true);
    try {
      const res = await pdfExtract(token, asset.uri, asset.name);
      setExtractedText(res.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read that PDF. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function sendToSolver() {
    navigation.navigate("AITutor", { prefillQuestion: extractedText });
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>📚 Past Papers (PDF)</Text>
      <Text style={styles.subtitle}>Upload a past paper PDF and pull questions straight from it.</Text>

      {pdfLocked ? (
        <View style={styles.lockedBanner}>
          <Text style={styles.lockedText}>
            Past paper PDF extraction is a Learner/Premium feature. Upgrade from the Home screen to unlock it.
          </Text>
        </View>
      ) : (
        <>
          <Pressable style={styles.actionButton} onPress={pickPdf}>
            <Text style={styles.actionButtonText}>📄 Choose PDF</Text>
          </Pressable>

          {fileName && <Text style={styles.fileName}>{fileName}</Text>}

          {loading && (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.loadingText}>Extracting text…</Text>
            </View>
          )}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {extractedText ? (
            <View style={styles.resultCard}>
              <Text style={styles.label}>Extracted text (select the part you want, then edit if needed)</Text>
              <TextInput
                style={styles.input}
                value={extractedText}
                onChangeText={setExtractedText}
                multiline
              />
              <Pressable style={styles.solveButton} onPress={sendToSolver}>
                <Text style={styles.solveButtonText}>Send to AI Tutor →</Text>
              </Pressable>
            </View>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: colors.background, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginBottom: 16 },
  actionButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 18,
    alignSelf: "flex-start",
  },
  actionButtonText: { color: "#fff", fontWeight: "700" },
  fileName: { marginTop: 10, color: colors.textSecondary, fontStyle: "italic" },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16 },
  loadingText: { color: colors.textSecondary },
  error: { color: colors.error, marginTop: 16 },
  resultCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginTop: 16 },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 12,
    fontSize: 15,
    backgroundColor: "#fff",
    minHeight: 220,
    textAlignVertical: "top",
  },
  solveButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 14,
  },
  solveButtonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  lockedBanner: {
    backgroundColor: "#fff4e5",
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  lockedText: { color: "#a15c00" },
});
```

## Step 4 — Run it

Snack should auto-refresh the preview as you add files. **Switch to "Web"**
in the device tabs, then use the "open in new tab" icon to open it as a
real standalone page (see the important note at the top).

You should land on the Login screen. Try "New here? Create a free account",
then try the AI Tutor with an Algebra question like `x^2-5x+6=0` or
`x^2+4x-4=0` (the second one exercises the quadratic-formula/fraction
rendering). The equations should now show as real typeset math (proper
superscripts, a stacked fraction with a divider line for the quadratic
formula) rather than raw LaTeX source like `x^{2}`.

All 10 AI Tutor topics (not just Algebra) now solve through the app - the
"(web only)" tag is gone from every topic chip.

From the Home screen, try "OCR Question" (📸 Take Photo only works on a
real device/Expo Go - "🖼️ Choose from Gallery" also works in the browser
preview by opening your OS file picker) and "Past Papers (PDF)". Both read
the file, show the recognised/extracted text in an editable box, and
"Send to AI Tutor →" carries it straight into the AI Tutor's question
field. Free-tier accounts see a locked banner instead - that's expected,
matching the same Learner/Premium gating as the web app.

**Before testing OCR/PDF, update your `api_server.py` deployment:** it
needs two new endpoints (`/ocr`, `/pdf-extract`) and a new Python package,
`python-multipart` (`pip install python-multipart`, or reinstall from the
updated `requirements.txt`) - FastAPI needs it to parse the multipart file
uploads these endpoints receive. Without it, `/ocr` and `/pdf-extract`
will fail at startup or on first request.

## If something doesn't work

- **"Cannot find file './src/...'"**: that file hasn't been created in
  Snack yet, or its path/extension doesn't match exactly (case-sensitive,
  `.tsx` vs `.ts` matters). Go through the full file list above.
- **Blank screen / red error box on load**: usually a leftover default file
  (like `App.js`) still present alongside your new files — delete it.
- **Register/login fails from the embedded preview but the API itself is
  fine**: this is the iframe/mixed-content issue from before — open the
  preview in its own tab (see the note at the top of this guide).
- **"Cannot find module '@react-navigation/...'"**: double check Step 2 —
  the dependency needs to be added in Snack itself, it's not enough that
  it's in this project's package.json.
- **A parse error pointing at a `.tsx` line with `<...>` in it**: Snack's
  transpiler sometimes struggles with advanced TypeScript generic syntax
  (already hit once, fixed in the files above) — if you hit another one,
  tell me the exact file/line and I'll simplify it.
- **OCR/PDF upload fails with a 422 error or shows an unreadable
  "[object Object]" message**: means `api_server.py` is out of date —
  redeploy it with the version that includes the `/ocr` and
  `/pdf-extract` endpoints and make sure `python-multipart` is installed
  (see the note above Step 4).
- **"Camera permission needed" alert on a real device**: tap through to
  your device's Settings and grant Malita camera/photo access, then try
  again — this is a real OS permission, not an app bug.
