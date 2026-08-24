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
  id_number: string;
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
  return request<{ message: string; reset_token: string | null }>("/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function resetPassword(token: string, newPassword: string) {
  return request<{ ok: boolean }>("/auth/reset-password", {
    method: "POST",
    body: { token, new_password: newPassword },
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

async function uploadFile<T = { text: string }>(
  path: string,
  token: string,
  file: { uri: string; name: string; type: string }
): Promise<T> {
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

export type SolvedPhotoQuestion = { number: string; steps: SolveStep[] };

// Reads every question/sub-part in a photographed maths problem and
// solves each one directly - the AI Tutor's Photo input path (Tesseract
// proved too unreliable to trust as a default).
export function solvePhotoWithAI(token: string, imageUri: string, mimeType: string = "image/jpeg") {
  return uploadFile<{ questions: SolvedPhotoQuestion[] }>("/ocr/solve", token, {
    uri: imageUri,
    name: "photo.jpg",
    type: mimeType,
  });
}

export type SolvedPdfQuestion = { number: string; steps: SolveStep[] };

// Reads every question in a learner-uploaded PDF (past paper, worksheet,
// homework - not just an official exam paper) and solves each one
// directly - the AI Tutor's PDF input path. Renders every page as an
// image and reads them with Claude vision server-side, rather than
// relying on the PDF's text layer, which is empty for a scanned/image-only
// PDF (the common case for a real past paper).
export function solvePdfWithAI(token: string, fileUri: string, fileName: string = "paper.pdf") {
  return uploadFile<{ questions: SolvedPdfQuestion[] }>("/pdf/solve", token, {
    uri: fileUri,
    name: fileName,
    type: "application/pdf",
  });
}

export type TierInfo = {
  key: string;
  label: string;
  price_zar: number;
  ai_tutor_daily_limit: number | null;
  ocr_enabled: boolean;
  pdf_enabled: boolean;
  past_papers_enabled: boolean;
};

export function fetchTiers() {
  return request<{ tiers: TierInfo[] }>("/billing/tiers");
}

// PayFast's live environment rejects a plain GET link (only sandbox
// tolerates that) - it requires a real form POST, which a phone browser
// can only do by loading a page that submits one on load. This URL points
// at that page (api_server.py's /billing/checkout-page) instead of at
// PayFast directly.
export function checkoutPageUrl(token: string, tier: string) {
  return `${API_BASE_URL}/billing/checkout-page?tier=${encodeURIComponent(tier)}&token=${encodeURIComponent(token)}`;
}

export function cancelSubscription(token: string) {
  return request<{ payfast_notified: boolean }>("/billing/cancel", { method: "POST", token });
}

export type PracticeSolutionStep = { explain: string; latex: string };

export type PracticeQuestion = {
  question: string;
  hint?: string;
  solution_steps: PracticeSolutionStep[];
  final_answer: string;
  Marks: number;
  difficulty?: string;
};

export function fetchPracticeTopics(token: string) {
  return request<Record<string, string[]>>("/practice/topics", { token });
}

export function fetchPracticeQuestions(token: string, paper: string, topic: string) {
  const params = `?paper=${encodeURIComponent(paper)}&topic=${encodeURIComponent(topic)}`;
  return request<{ questions: PracticeQuestion[] }>(`/practice/questions${params}`, { token });
}

export function checkPracticeAnswer(token: string, answer: string, expectedLatex: string) {
  return request<{ correct: boolean | null }>("/practice/check", {
    method: "POST",
    body: { answer, expected_latex: expectedLatex },
    token,
  });
}

export function recordPracticeSolved(token: string, paper: string, topic: string, question: string) {
  return request<{ ok: boolean }>("/practice/record", {
    method: "POST",
    body: { paper, topic, question },
    token,
  });
}

export type PastPaper = {
  id: number;
  title: string;
  subject: string;
  grade: number;
  year: number;
  month: string | null;
  exam_series: string;
  document_type: string;
  paper_number: number;
  variant: string;
  file_name: string;
  file_size: number;
  uploaded_at: string | null;
};

export function fetchPastPapers(token: string) {
  return request<{ papers: PastPaper[] }>("/past-papers", { token });
}

export function pastPaperDownloadUrl(token: string, paperId: number) {
  return `${API_BASE_URL}/past-papers/${paperId}/download?token=${encodeURIComponent(token)}`;
}

