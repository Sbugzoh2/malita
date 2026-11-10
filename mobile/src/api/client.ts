// Malita mobile — thin fetch wrapper around api_server.py.
//
// Point API_BASE_URL at your deployed api_server.py before shipping a real
// build (Render/Railway/etc, same hosting story as webhook_server.py).
// Defaults to localhost for local development against
// `uvicorn api_server:app --host 0.0.0.0 --port 8002`.
import Constants from "expo-constants";

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
  ai_teacher_enabled: boolean;
  payment_provider: "payfast" | "play_billing" | null;
  pending_tier: string | null;
  pending_tier_label: string | null;
  current_period_end: string | null;
  google_product_id: string | null;
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

export function solve(token: string, params: { paper: string; topic: string; question: string; subject?: string }) {
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
  // Expo SDK 57 replaced fetch/FormData on EVERY platform (not just web)
  // with its own spec-compliant "winter" runtime - its request-body
  // serializer (expo/src/winter/fetch/convertFormData.ts) only accepts a
  // real Blob/File-like part; the classic React Native {uri,name,type}
  // shape this used to append directly on native is silently stored by
  // FormData.append() but then rejected at send time with "Unsupported
  // FormDataPart implementation", since it's neither a string nor a Blob
  // nor has a .bytes() method. Fetching the uri into a real Blob first -
  // already required on web for the same reason - now works uniformly on
  // every platform, so there's no longer a native/web split here at all.
  const formData = new FormData();
  const blob = await (await fetch(file.uri)).blob();
  formData.append("file", blob, file.name);

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

export function cancelSubscription(token: string) {
  return request<{ had_subscription: boolean; provider: "payfast" | "play_billing" | null; payfast_notified: boolean | null }>(
    "/billing/cancel",
    { method: "POST", token }
  );
}

// Tier -> Play Console subscription product id, so the purchase code below
// never hardcodes a product id (backend/tiers.py is the single source).
export function fetchGooglePlayProducts(token: string) {
  return request<{ products: Record<string, string> }>("/billing/google/products", { token });
}

// Sent right after a Play Billing purchase completes - verified server-side
// against Google's own API before the tier is actually granted (see
// api_server.py's /billing/google/verify).
export function verifyGooglePlayPurchase(token: string, productId: string, purchaseToken: string) {
  return request<{ ok: boolean; tier: string }>("/billing/google/verify", {
    method: "POST",
    body: { product_id: productId, purchase_token: purchaseToken },
    token,
  });
}

// Schedules a move to a LOWER tier at the end of the current paid period
// (not immediately) - see api_server.py's /billing/downgrade. For a
// Play-billed subscription, call this right after the native deferred-
// replacement purchase has already been requested via expo-iap.
export function scheduleDowngrade(token: string, tier: string) {
  return request<{ scheduled: boolean; effective_date: string | null; new_tier?: string; payfast_notified?: boolean | null }>(
    "/billing/downgrade",
    { method: "POST", body: { tier }, token }
  );
}

export function deleteAccount(token: string) {
  return request<{ deleted: boolean; had_active_subscription: boolean; provider?: string | null; payfast_notified?: boolean | null }>(
    "/account",
    { method: "DELETE", token }
  );
}

// 1-on-1 tutoring, billed separately from the subscription - available
// regardless of tier. inDrive-style self-service matching: the LEARNER
// sets the price/duration when requesting, and any qualifying tutor can
// accept it - see backend/tutoring.py.
export type TutoringRequest = {
  id: number;
  subject: string;
  topic: string | null;
  preferred_times_note: string | null;
  status: "requested" | "time_proposed" | "awaiting_payment" | "confirmed" | "completed" | "cancelled";
  status_label: string;
  tutor_id: number | null;
  tutor_name: string | null;
  duration_minutes: number | null;
  price_zar: number | null;
  platform_cut_percent: number | null;
  scheduled_at: string | null;
  proposed_scheduled_at: string | null;
  created_at: string | null;
  matched_at: string | null;
  paid_at: string | null;
  meet_link: string | null;
  learner_confirmed: boolean;
  learner_rating: number | null;
  tutor_confirmed: boolean;
  tutor_rating: number | null;
};

export function requestTutoringSession(
  token: string,
  params: {
    subject: string;
    price_zar: number;
    scheduled_at: string; // ISO 8601, required
    duration_minutes?: number;
    topic?: string;
    preferred_times_note?: string;
  }
) {
  return request<{ id: number; status: string }>("/tutoring/requests", {
    method: "POST",
    body: {
      subject: params.subject,
      price_zar: params.price_zar,
      scheduled_at: params.scheduled_at,
      duration_minutes: params.duration_minutes ?? 60,
      topic: params.topic ?? "",
      preferred_times_note: params.preferred_times_note ?? "",
    },
    token,
  });
}

export function respondToTimeProposal(token: string, requestId: number, accept: boolean) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/respond-to-proposal`, {
    method: "POST",
    body: { accept },
    token,
  });
}

export function confirmTutoringSessionAsLearner(
  token: string, requestId: number, rating: number, comment?: string
) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/confirm`, {
    method: "POST",
    body: { rating, comment: comment ?? "" },
    token,
  });
}

export function fetchMyTutoringRequests(token: string) {
  return request<{ requests: TutoringRequest[] }>("/tutoring/requests/mine", { token });
}

// Linking.openURL can't attach an Authorization header, so (same pattern
// as pastPaperDownloadUrl) the token rides along as a query param instead.
export function tutoringCheckoutUrl(token: string, requestId: number) {
  return `${API_BASE_URL}/tutoring/requests/${requestId}/checkout-page?token=${encodeURIComponent(token)}`;
}

// --- Tutor self-service (a tutor's OWN login, entirely separate from a
// learner's /auth/* account - see backend/tutoring.py's login_tutor) ---

export type TutorMe = {
  id: number;
  name: string;
  email: string;
  status: TutorApplication["status"];
  status_label: string;
};

export function tutorLogin(email: string, password: string) {
  return request<{ token: string; tutor: TutorMe }>("/tutor/login", {
    method: "POST",
    body: { email, password },
  });
}

export function tutorLogout(token: string) {
  return request<{ ok: boolean }>("/tutor/logout", { method: "POST", token });
}

export function tutorForgotPassword(email: string) {
  return request<{ message: string; reset_token: string | null }>("/tutor/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function tutorResetPassword(token: string, newPassword: string) {
  return request<{ ok: boolean }>("/tutor/reset-password", {
    method: "POST",
    body: { token, new_password: newPassword },
  });
}

export function fetchTutorMe(token: string) {
  return request<TutorMe>("/tutor/me", { token });
}

// Returns the same shape as the admin's TutorProfile (see below) - the
// tutor_id is derived from the bearer token server-side, so a tutor can
// only ever see their own record this way.
export function fetchTutorMyProfile(token: string) {
  return request<TutorProfile>("/tutor/me/profile", { token });
}

export type TutorPayout = {
  id: number;
  session_id: number;
  amount_zar: number;
  status: "pending" | "paid";
  payment_reference: string | null;
  created_at: string | null;
  paid_at: string | null;
};

export function fetchTutorMyPayouts(token: string) {
  return request<{ payouts: TutorPayout[] }>("/tutor/me/payouts", { token });
}

// A tutor's own "open requests" queue - only requests for subjects
// they're approved and active to teach - and the self-accept action.
// platform_cut_percent is the live default (not yet snapshotted on these
// unmatched requests), for an accurate "you'll receive ~R..." preview.
export function fetchTutorOpenRequests(token: string) {
  return request<{ requests: TutoringRequest[]; platform_cut_percent: number }>("/tutor/requests/open", { token });
}

export function acceptTutoringRequest(token: string, requestId: number) {
  return request<{ id: number; status: string; m_payment_id: string; meet_link: string | null }>(
    `/tutor/requests/${requestId}/accept`,
    { method: "POST", token }
  );
}

// A tutor proposing an alternative time when they can't make the
// learner's exact requested time - goes to the learner for approval.
export function proposeNewTime(token: string, requestId: number, proposedScheduledAtIso: string) {
  return request<{ id: number; status: string }>(`/tutor/requests/${requestId}/propose-time`, {
    method: "POST",
    body: { proposed_scheduled_at: proposedScheduledAtIso },
    token,
  });
}

export function confirmTutoringSessionAsTutor(
  token: string, requestId: number, rating: number, comment?: string
) {
  return request<{ id: number; status: string }>(`/tutor/sessions/${requestId}/confirm`, {
    method: "POST",
    body: { rating, comment: comment ?? "" },
    token,
  });
}

// --- Tutoring admin (mirrors app.py's "Tutoring Admin" screen) ---
// Every function here requires an admin account - the API itself enforces
// this (403 otherwise), this is just the client side of the same 3 tabs
// the web admin screen has: applications, matching, payouts.

export type TutorApplication = {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  bio: string | null;
  id_number: string | null;
  id_verification_note: string | null;
  matric_certificate_note: string | null;
  has_id_document: boolean;
  has_matric_certificate_document: boolean;
  cv_note: string | null;
  has_cv_document: boolean;
  availability_note: string | null;
  bank_account_note: string | null;
  status: "pending_review" | "approved" | "rejected" | "suspended";
  status_label: string;
  admin_notes: string | null;
  created_at: string | null;
  reviewed_at: string | null;
  subjects: {
    subject: string;
    matric_percentage: number;
    topics: string | null;
    hourly_rate_zar: number | null;
    is_active: boolean;
  }[];
};

export function fetchTutorApplications(token: string, status?: TutorApplication["status"]) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<{ applications: TutorApplication[] }>(`/admin/tutoring/applications${qs}`, { token });
}

export function approveTutorApplication(token: string, tutorId: number) {
  return request<{ status: string }>(`/admin/tutoring/applications/${tutorId}/approve`, {
    method: "POST",
    token,
  });
}

export function rejectTutorApplication(token: string, tutorId: number, reason: string) {
  return request<{ status: string }>(`/admin/tutoring/applications/${tutorId}/reject`, {
    method: "POST",
    body: { reason },
    token,
  });
}

export function fetchTutorDocumentUrl(token: string, tutorId: number, kind: "id" | "matric_certificate" | "cv") {
  return request<{ url: string }>(`/admin/tutoring/applications/${tutorId}/documents/${kind}`, { token });
}

export type ApprovedTutor = {
  id: number;
  name: string;
  email: string;
  sessions_completed: number;
  subjects: { subject: string; matric_percentage: number; topics: string | null; hourly_rate_zar: number | null }[];
};

export function fetchApprovedTutors(token: string, subject?: string) {
  const qs = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return request<{ tutors: ApprovedTutor[] }>(`/admin/tutoring/tutors${qs}`, { token });
}

// A tutor's full standing record - subjects plus every session they've
// ever been matched to - so an admin can review their track record
// before re-matching them to a new request. An approved tutor's record
// persists indefinitely, like an employee's, rather than disappearing
// once a session ends.
export type TutorProfile = {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  bio: string | null;
  status: TutorApplication["status"];
  status_label: string;
  availability_note: string | null;
  sessions_completed: number;
  subjects: {
    subject: string;
    matric_percentage: number;
    topics: string | null;
    hourly_rate_zar: number | null;
    is_active: boolean;
  }[];
  sessions: TutoringRequest[];
};

export function fetchTutorProfile(token: string, tutorId: number) {
  return request<TutorProfile>(`/admin/tutoring/tutors/${tutorId}/profile`, { token });
}

export function fetchOpenTutoringRequestsAdmin(token: string) {
  return request<{ requests: TutoringRequest[] }>("/admin/tutoring/requests/open", { token });
}

// Admin override only - price/duration are set by the learner at
// request time now, not here (see backend/tutoring.py's
// match_tutor_to_request docstring).
export function matchTutorToRequestAdmin(
  token: string,
  requestId: number,
  params: { tutor_id: number; scheduled_at?: string | null }
) {
  return request<{ id: number; status: string; m_payment_id: string; meet_link: string | null }>(
    `/admin/tutoring/requests/${requestId}/match`,
    { method: "POST", body: params, token }
  );
}

export type TutoringPayout = {
  id: number;
  session_id: number;
  tutor_id: number;
  tutor_name: string | null;
  tutor_bank_note: string | null;
  amount_zar: number;
  created_at: string | null;
};

export function fetchPendingPayoutsAdmin(token: string) {
  return request<{ payouts: TutoringPayout[] }>("/admin/tutoring/payouts", { token });
}

export function markPayoutPaidAdmin(token: string, payoutId: number, paymentReference: string) {
  return request<{ status: string }>(`/admin/tutoring/payouts/${payoutId}/mark-paid`, {
    method: "POST",
    body: { payment_reference: paymentReference },
    token,
  });
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

export function fetchPracticeTopics(token: string, subject: string = "Mathematics") {
  return request<Record<string, string[]>>(`/practice/topics?subject=${encodeURIComponent(subject)}`, { token });
}

export function fetchPracticeQuestions(token: string, paper: string, topic: string, subject: string = "Mathematics") {
  const params = `?paper=${encodeURIComponent(paper)}&topic=${encodeURIComponent(topic)}&subject=${encodeURIComponent(subject)}`;
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

export type LearnerProfileActivity = {
  source: "ai_tutor" | "practice";
  paper: string | null;
  topic: string | null;
  question: string | null;
  solved_at: string | null;
};

export type LearnerProfileBadge = {
  label: string;
  next_milestone: number | null;
  remaining_to_next: number | null;
};

export type LearnerProfile = {
  solved: number;
  marks: number;
  topic_counts: Record<string, number>;
  badge: LearnerProfileBadge;
  recent: LearnerProfileActivity[];
};

export function fetchLearnerProfile(token: string, subject: string = "Mathematics") {
  return request<LearnerProfile>(`/learner-profile?subject=${encodeURIComponent(subject)}`, { token });
}

export function fetchPastPapers(token: string) {
  return request<{ papers: PastPaper[] }>("/past-papers", { token });
}

export function pastPaperDownloadUrl(token: string, paperId: number) {
  return `${API_BASE_URL}/past-papers/${paperId}/download?token=${encodeURIComponent(token)}`;
}

export type CollabQuestionSummary = {
  id: number;
  subject: string;
  topic: string | null;
  title: string;
  body: string;
  asker_name: string;
  created_at: string | null;
  answer_count: number;
};

export type CollabAnswer = {
  id: number;
  body: string;
  answerer_name: string;
  created_at: string | null;
  parent_id: number | null;
  user_id: number;
  is_edited: boolean;
};

export type CollabQuestionDetail = {
  id: number;
  subject: string;
  topic: string | null;
  title: string;
  body: string;
  asker_name: string;
  created_at: string | null;
  user_id: number;
  is_edited: boolean;
  answers: CollabAnswer[];
};

export function fetchCollabQuestions(token: string, subject: string = "Mathematics", topic: string = "") {
  const params = `?subject=${encodeURIComponent(subject)}${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`;
  return request<{ questions: CollabQuestionSummary[] }>(`/collab/questions${params}`, { token });
}

export function createCollabQuestion(
  token: string,
  params: { subject: string; topic?: string; title: string; body: string }
) {
  return request<{ id: number }>("/collab/questions", { method: "POST", body: params, token });
}

export function fetchCollabQuestion(token: string, questionId: number) {
  return request<CollabQuestionDetail>(`/collab/questions/${questionId}`, { token });
}

export function createCollabAnswer(token: string, questionId: number, body: string, parentId: number | null = null) {
  return request<{ id: number }>(`/collab/questions/${questionId}/answers`, {
    method: "POST",
    body: { body, parent_id: parentId },
    token,
  });
}

export function reportCollabContent(
  token: string,
  params: { target_type: "question" | "answer"; target_id: number; reason?: string }
) {
  return request<{ ok: boolean }>("/collab/report", { method: "POST", body: params, token });
}

export function editCollabQuestion(token: string, questionId: number, title: string, body: string) {
  return request<{ ok: boolean }>(`/collab/questions/${questionId}/edit`, {
    method: "POST",
    body: { title, body },
    token,
  });
}

export function editCollabAnswer(token: string, answerId: number, body: string) {
  return request<{ ok: boolean }>(`/collab/answers/${answerId}/edit`, {
    method: "POST",
    body: { body },
    token,
  });
}

export type CollabReport = {
  id: number;
  target_type: "question" | "answer";
  target_id: number;
  reason: string;
  created_at: string | null;
  preview: string;
  already_hidden: boolean;
  reporter_name: string;
};

export function fetchCollabReports(token: string) {
  return request<{ reports: CollabReport[] }>("/collab/reports", { token });
}

export function resolveCollabReport(
  token: string,
  reportId: number,
  params: { action: "hide" | "delete" | "dismiss"; notify_reporter?: boolean; note?: string }
) {
  return request<{ ok: boolean }>(`/collab/reports/${reportId}/resolve`, {
    method: "POST",
    body: params,
    token,
  });
}

export type LessonStep = SolveStep & { narration?: string };

export function fetchAITeacherLesson(token: string, subject: string, topic: string) {
  return request<{ steps: LessonStep[] }>("/ai-teacher/lesson", {
    method: "POST",
    body: { subject, topic },
    token,
  });
}

