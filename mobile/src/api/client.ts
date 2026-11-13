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
  account_type: "high_school" | "higher_ed";
  // Rare admin override (see backend/set_cross_segment_access.py) - when
  // true, this account sees BOTH the high_school and higher_ed
  // experiences at once, regardless of its own account_type.
  cross_segment_access?: boolean;
  higher_ed_institution_id?: number | null;
  higher_ed_qualification_id?: number | null;
  higher_ed_year_of_study?: number | null;
  student_number?: string | null;
};

export const YEAR_LEVEL_LABELS: Record<number, string> = {
  1: "1st Year", 2: "2nd Year", 3: "3rd Year", 4: "4th Year / Honours",
  5: "Postgraduate (Masters/Doctoral)",
};

export type Institution = { id: number; name: string };
export type Qualification = { id: number; name: string; institution_id: number };
export type CatalogModule = {
  id: number; name: string; year_level: number;
  year_level_label: string; qualification_id: number;
};

export function fetchInstitutions() {
  return request<{ institutions: Institution[] }>("/catalog/institutions");
}

export function fetchQualifications(institutionId: number) {
  return request<{ qualifications: Qualification[] }>(`/catalog/qualifications?institution_id=${institutionId}`);
}

export function fetchModules(qualificationId: number) {
  return request<{ modules: CatalogModule[]; year_levels: Record<string, string> }>(
    `/catalog/modules?qualification_id=${qualificationId}`
  );
}

// Admin-only catalog management - mirrors app.py's web "Higher-Ed
// Catalog" admin tab, since an admin using only the mobile app would
// otherwise have no way to populate institutions/qualifications/modules
// for learners/tutors to select from.
export function addInstitutionAdmin(token: string, name: string) {
  return request<Institution>("/admin/catalog/institutions", { method: "POST", body: { name }, token });
}

export function addQualificationAdmin(token: string, institutionId: number, name: string) {
  return request<Qualification>("/admin/catalog/qualifications", {
    method: "POST",
    body: { institution_id: institutionId, name },
    token,
  });
}

export function addModuleAdmin(token: string, qualificationId: number, name: string, yearLevel: number) {
  return request<CatalogModule>("/admin/catalog/modules", {
    method: "POST",
    body: { qualification_id: qualificationId, name, year_level: yearLevel },
    token,
  });
}

export type CatalogSeedResult = {
  created: { institutions: number; qualifications: number; modules: number };
  skipped: { institutions: number; qualifications: number; modules: number };
};

// One-click starter catalog (SA's 26 public universities with a generic
// qualification/module set) instead of adding institutions/qualifications/
// modules one at a time - see backend/tutoring.py's
// seed_default_higher_ed_catalog for exactly what this is and isn't.
// Idempotent - safe to tap more than once.
export function seedDefaultCatalog(token: string) {
  return request<CatalogSeedResult>("/admin/catalog/seed-default", { method: "POST", token });
}

// Removes a catalog entry - blocked server-side if a tutor or tutoring
// request still references one of its modules (deleting an institution
// or qualification cascades to everything under it).
export function deleteInstitutionAdmin(token: string, institutionId: number) {
  return request<{ deleted: string }>(`/admin/catalog/institutions/${institutionId}`, { method: "DELETE", token });
}

export function deleteQualificationAdmin(token: string, qualificationId: number) {
  return request<{ deleted: string }>(`/admin/catalog/qualifications/${qualificationId}`, { method: "DELETE", token });
}

export function deleteModuleAdmin(token: string, moduleId: number) {
  return request<{ deleted: string }>(`/admin/catalog/modules/${moduleId}`, { method: "DELETE", token });
}

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
  account_type?: "high_school" | "higher_ed";
  higher_ed_institution_id?: number | null;
  higher_ed_qualification_id?: number | null;
  // "Other" escape hatch instead of higher_ed_qualification_id, when the
  // learner's real qualification isn't in the catalog.
  higher_ed_qualification_custom_name?: string;
  higher_ed_year_of_study?: number | null;
  student_number?: string;
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
  module_id: number | null;
  // Only set for a higher-ed (module-based) request - derived server-side
  // so the edit flow can pre-select the Institution/Qualification/Module
  // cascade without an extra lookup.
  qualification_id: number | null;
  institution_id: number | null;
  // Set only for a real catalog module (module_id above) - YEAR_LEVEL_LABELS
  // maps it to a display label the same way custom_module_year_level
  // already is. Null for a high-school request or a custom ("Other") module.
  module_year_level: number | null;
  // The learner's name - shown to a tutor deciding whether to accept an
  // open request, same as tutor_name/preferred_tutor_name already are.
  learner_name: string | null;
  // Set when the learner picked "Other" for their qualification/module -
  // module_id is null in that case (no catalog Module row exists), so this
  // holds the free-text name instead and is_custom_higher_ed flags it as
  // routed to admin's manual match flow rather than tutor self-accept.
  custom_module_name: string | null;
  custom_module_year_level: number | null;
  // Set instead of qualification_id when the qualification itself was
  // "Other" - independent of custom_module_name (either escape hatch can
  // be used on its own).
  custom_qualification_name: string | null;
  admin_match_note: string | null;
  is_custom_higher_ed: boolean;
  // The learner's own CAPS grade (10/11/12) - high-school requests only,
  // null for a higher-ed one. Informational, not a matching filter.
  grade: number | null;
  topic: string | null;
  preferred_times_note: string | null;
  status:
    | "requested" | "time_proposed" | "admin_proposed" | "awaiting_payment"
    | "confirmed" | "tutor_cancelled" | "completed" | "cancelled" | "lapsed";
  status_label: string;
  tutor_id: number | null;
  tutor_name: string | null;
  preferred_tutor_id: number | null;
  preferred_tutor_name: string | null;
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
  cancelled_by: "learner" | "tutor" | "admin" | null;
  cancellation_reason: string | null;
  // Set once the learner chooses a refund after a tutor cancelled an
  // already-paid session (status "tutor_cancelled" -> "cancelled");
  // refund_processed_at is set once an admin has actually arranged it
  // (no automated PayFast refund - see backend/tutoring.py).
  refund_requested_at: string | null;
  refund_processed_at: string | null;
  lapsed_at: string | null;
  recording_link: string | null;
  recording_shared_at: string | null;
};

export type TutoringRequestParams = {
  subject?: string;
  // Required for a high-school request (10/11/12) - ignored for a
  // higher-ed one.
  grade?: number;
  price_zar: number;
  scheduled_at: string; // ISO 8601, required, at least 24h ahead
  duration_minutes?: number;
  topic: string;
  preferred_times_note?: string;
  // A higher-ed catalog Module id - set this INSTEAD OF subject for a
  // university/college tutoring request (the server looks up the
  // module's own name).
  module_id?: number;
  // "Other" escape hatch instead of module_id, when the learner's real
  // module isn't in the catalog - routed to admin's manual match flow
  // instead of tutor self-accept (see backend/tutoring.py). Independent
  // of custom_qualification_name below - either can be used on its own.
  custom_module_name?: string;
  custom_module_year_level?: number;
  // Always sent for a higher-ed request (stored directly server-side,
  // not derived through module_id - see TutoringSessionRequest's
  // docstring in backend/db.py).
  institution_id?: number;
  qualification_id?: number;
  // "Other" escape hatch instead of qualification_id.
  custom_qualification_name?: string;
  // Set when the learner picked a specific tutor from the directory
  // (see fetchTutorsDirectory) instead of broadcasting the request.
  preferred_tutor_id?: number;
};

function tutoringRequestBody(params: TutoringRequestParams) {
  return {
    subject: params.subject ?? "",
    grade: params.grade,
    price_zar: params.price_zar,
    scheduled_at: params.scheduled_at,
    duration_minutes: params.duration_minutes ?? 60,
    topic: params.topic ?? "",
    preferred_times_note: params.preferred_times_note ?? "",
    module_id: params.module_id,
    custom_module_name: params.custom_module_name,
    custom_module_year_level: params.custom_module_year_level,
    institution_id: params.institution_id,
    qualification_id: params.qualification_id,
    custom_qualification_name: params.custom_qualification_name,
    preferred_tutor_id: params.preferred_tutor_id,
  };
}

export function requestTutoringSession(token: string, params: TutoringRequestParams) {
  return request<{ id: number; status: string }>("/tutoring/requests", {
    method: "POST",
    body: tutoringRequestBody(params),
    token,
  });
}

// The learner editing their own request while it's still fully open
// (status=="requested") - same shape as creating one.
export function editTutoringRequest(token: string, requestId: number, params: TutoringRequestParams) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}`, {
    method: "PUT",
    body: tutoringRequestBody(params),
    token,
  });
}

// The learner withdrawing their own request before a tutor has fully
// accepted it (status in "requested"/"time_proposed") - no 24h
// restriction, since nothing is committed yet.
export function withdrawTutoringRequest(token: string, requestId: number) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/withdraw`, {
    method: "POST",
    token,
  });
}

// Either party cancelling an ALREADY-ACCEPTED session (awaiting_payment
// or confirmed) - blocked within 24 hours of the scheduled time.
export function cancelTutoringSessionAsLearner(token: string, requestId: number, reason: string = "") {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/cancel`, {
    method: "POST",
    body: { reason },
    token,
  });
}

export function cancelTutoringSessionAsTutor(token: string, requestId: number, reason: string = "") {
  return request<{ id: number; status: string }>(`/tutor/sessions/${requestId}/cancel`, {
    method: "POST",
    body: { reason },
    token,
  });
}

// The two choices a learner gets after a tutor cancels an already-paid
// session (status "tutor_cancelled" - see backend/tutoring.py's
// cancel_accepted_session).
export function reallocateAfterTutorCancellation(token: string, requestId: number) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/reallocate`, {
    method: "POST",
    token,
  });
}

export function requestRefundForCancelledSession(token: string, requestId: number) {
  return request<{ id: number; status: string }>(`/tutoring/requests/${requestId}/request-refund`, {
    method: "POST",
    token,
  });
}

// There's no API that can force a recording on a non-Google-Workspace
// Meet call, so the tutor records manually (Meet's own "Record meeting"
// button) and submits the resulting link here afterward - Malita emails
// every admin the link plus the session's full details.
export function submitSessionRecording(token: string, requestId: number, recordingLink: string) {
  return request<{ id: number; status: string }>(`/tutor/sessions/${requestId}/recording`, {
    method: "POST",
    body: { recording_link: recordingLink },
    token,
  });
}

export type DirectoryTutor = {
  id: number;
  name: string;
  email: string;
  bio: string | null;
  availability_note: string | null;
  sessions_completed: number;
  subjects: { subject: string; matric_percentage: number; topics: string | null; hourly_rate_zar: number | null }[];
  higher_ed_modules: {
    id: number; name: string; year_level: number; year_level_label: string;
    qualification: string | null; qualification_id: number | null;
    institution: string | null; institution_id: number | null;
  }[];
};

// Public "Browse Tutors" directory - pick a specific tutor instead of
// broadcasting a request (pass the resulting tutor's id as
// preferred_tutor_id when calling requestTutoringSession).
export function fetchTutorsDirectory(token: string, params: { subject?: string; module_id?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.subject) qs.set("subject", params.subject);
  if (params.module_id) qs.set("module_id", String(params.module_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<{ tutors: DirectoryTutor[] }>(`/tutoring/tutors/directory${suffix}`, { token });
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
  wants_high_school: boolean;
  wants_higher_ed: boolean;
  higher_ed_status: TutorApplication["status"] | null;
  higher_ed_status_label: string | null;
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

export type TutorApplySubjectInput = {
  subject: string;
  matric_percentage: number;
  topics?: string;
  hourly_rate_zar?: number;
};

export type TutorApplyParams = {
  name: string;
  email: string;
  password: string;
  phone?: string;
  bio?: string;
  id_number?: string;
  id_verification_note?: string;
  matric_certificate_note?: string;
  cv_note?: string;
  availability_note?: string;
  bank_account_holder?: string;
  bank_name?: string;
  bank_branch_code?: string;
  bank_account_number?: string;
  bank_account_type?: string;
  // Optional extra notes alongside the structured fields above (e.g. a
  // SWIFT code for an international account) - not the primary bank
  // info anymore, see backend/db.py's TutorAccount docstring.
  bank_account_note?: string;
  wants_high_school: boolean;
  wants_higher_ed: boolean;
  subjects?: TutorApplySubjectInput[];
  higher_ed_institution_id?: number | null;
  higher_ed_qualification_id?: number | null;
  // "Other" escape hatch instead of higher_ed_qualification_id/
  // higher_ed_module_ids, when the applicant's real qualification isn't
  // in the catalog (see backend/db.py's TutorCustomHigherEdModule).
  higher_ed_qualification_custom_name?: string;
  higher_ed_custom_modules?: { name: string; year_level: number }[];
  higher_ed_year_of_study?: number | null;
  higher_ed_qualification_complete?: boolean;
  higher_ed_average?: number | null;
  higher_ed_transcript_note?: string;
  higher_ed_module_ids?: number[];
  id_document?: { uri: string; name: string; type: string } | null;
  matric_certificate?: { uri: string; name: string; type: string } | null;
  cv?: { uri: string; name: string; type: string } | null;
  // Required (a one-page bank statement or account confirmation letter)
  // - see backend/db.py's TutorAccount.bank_proof_document_path.
  bank_proof?: { uri: string; name: string; type: string } | null;
  higher_ed_transcript?: { uri: string; name: string; type: string } | null;
  higher_ed_qualification_certificate?: { uri: string; name: string; type: string } | null;
};

// A prospective tutor's application - public, unauthenticated, multipart
// (the three document fields are optional file uploads). See
// backend/tutoring.py's apply_as_tutor for the full validation this hits:
// matric marks / higher-ed average must meet Malita's 65% minimum, and a
// higher-ed module must be at least one year behind the applicant's own
// year of study.
export type TutorApplyResult = {
  id: number;
  status: string;
  higher_ed_status: string | null;
  // Qualification is checked per subject/module, not all-or-nothing - see
  // apply_as_tutor's docstring. Empty/null fields mean nothing was excluded.
  excluded_subjects: { subject: string; matric_percentage: number | null; reason: string }[];
  excluded_higher_ed_reason: string | null;
  excluded_modules: { name: string; year_level: number | null; reason: string }[];
};

export async function applyAsTutor(params: TutorApplyParams): Promise<TutorApplyResult> {
  const formData = new FormData();
  const textFields: Record<string, string> = {
    name: params.name,
    email: params.email,
    password: params.password,
    phone: params.phone ?? "",
    bio: params.bio ?? "",
    id_number: params.id_number ?? "",
    id_verification_note: params.id_verification_note ?? "",
    matric_certificate_note: params.matric_certificate_note ?? "",
    cv_note: params.cv_note ?? "",
    availability_note: params.availability_note ?? "",
    bank_account_holder: params.bank_account_holder ?? "",
    bank_name: params.bank_name ?? "",
    bank_branch_code: params.bank_branch_code ?? "",
    bank_account_number: params.bank_account_number ?? "",
    bank_account_type: params.bank_account_type ?? "",
    bank_account_note: params.bank_account_note ?? "",
    wants_high_school: String(params.wants_high_school),
    wants_higher_ed: String(params.wants_higher_ed),
    subjects: JSON.stringify(params.subjects ?? []),
    higher_ed_qualification_complete: String(params.higher_ed_qualification_complete ?? false),
    higher_ed_transcript_note: params.higher_ed_transcript_note ?? "",
    higher_ed_module_ids: JSON.stringify(params.higher_ed_module_ids ?? []),
    higher_ed_custom_modules: JSON.stringify(params.higher_ed_custom_modules ?? []),
  };
  if (params.higher_ed_institution_id != null) {
    textFields.higher_ed_institution_id = String(params.higher_ed_institution_id);
  }
  if (params.higher_ed_qualification_id != null) {
    textFields.higher_ed_qualification_id = String(params.higher_ed_qualification_id);
  }
  if (params.higher_ed_qualification_custom_name) {
    textFields.higher_ed_qualification_custom_name = params.higher_ed_qualification_custom_name;
  }
  if (params.higher_ed_year_of_study != null) {
    textFields.higher_ed_year_of_study = String(params.higher_ed_year_of_study);
  }
  if (params.higher_ed_average != null) {
    textFields.higher_ed_average = String(params.higher_ed_average);
  }
  for (const [key, value] of Object.entries(textFields)) {
    formData.append(key, value);
  }

  // Same Blob-conversion technique as uploadFile() above - Expo SDK 57's
  // fetch/FormData only accepts a real Blob/File-like part, not the
  // classic React Native {uri,name,type} shape.
  const fileFields: [string, TutorApplyParams["id_document"]][] = [
    ["id_document", params.id_document],
    ["matric_certificate", params.matric_certificate],
    ["cv", params.cv],
    ["bank_proof", params.bank_proof],
    ["higher_ed_transcript", params.higher_ed_transcript],
    ["higher_ed_qualification_certificate", params.higher_ed_qualification_certificate],
  ];
  for (const [field, file] of fileFields) {
    if (!file) continue;
    const blob = await (await fetch(file.uri)).blob();
    formData.append(field, blob, file.name);
  }

  const response = await fetch(`${API_BASE_URL}/tutoring/apply`, { method: "POST", body: formData });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data));
  }
  return data;
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
  // m_payment_id/meet_link are null when status comes back as
  // "pending_admin_approval" - a custom ("Other") module claim, not
  // finalized until an admin approves it (see backend/tutoring.py's
  // accept_tutoring_request).
  return request<{ id: number; status: string; m_payment_id: string | null; meet_link: string | null }>(
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
  has_bank_proof_document: boolean;
  availability_note: string | null;
  bank_account_holder: string | null;
  bank_name: string | null;
  bank_branch_code: string | null;
  bank_account_number: string | null;
  bank_account_type: string | null;
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

export function fetchTutorDocumentUrl(
  token: string,
  tutorId: number,
  kind: "id" | "matric_certificate" | "cv" | "bank_proof" | "higher_ed_transcript" | "higher_ed_qualification_certificate"
) {
  return request<{ url: string }>(`/admin/tutoring/applications/${tutorId}/documents/${kind}`, { token });
}

export type TutorHigherEdApplication = {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  bio: string | null;
  id_number: string | null;
  id_verification_note: string | null;
  has_id_document: boolean;
  cv_note: string | null;
  has_cv_document: boolean;
  has_bank_proof_document: boolean;
  availability_note: string | null;
  bank_account_holder: string | null;
  bank_name: string | null;
  bank_branch_code: string | null;
  bank_account_number: string | null;
  bank_account_type: string | null;
  bank_account_note: string | null;
  wants_high_school: boolean;
  higher_ed_status: "pending_review" | "approved" | "rejected" | "suspended";
  higher_ed_status_label: string;
  higher_ed_institution: string | null;
  higher_ed_qualification: string | null;
  higher_ed_year_of_study: number | null;
  higher_ed_year_of_study_label: string | null;
  higher_ed_qualification_complete: boolean;
  higher_ed_average: number | null;
  higher_ed_transcript_note: string | null;
  has_higher_ed_transcript_document: boolean;
  has_higher_ed_qualification_certificate_document: boolean;
  admin_notes: string | null;
  created_at: string | null;
  higher_ed_reviewed_at: string | null;
  modules: { id: number; name: string; year_level: number; year_level_label: string; is_active: boolean }[];
};

export function fetchTutorHigherEdApplications(token: string, status?: TutorHigherEdApplication["higher_ed_status"]) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<{ applications: TutorHigherEdApplication[] }>(`/admin/tutoring/applications/higher-ed${qs}`, { token });
}

export function approveTutorHigherEdApplication(token: string, tutorId: number) {
  return request<{ status: string }>(`/admin/tutoring/applications/${tutorId}/higher-ed/approve`, {
    method: "POST",
    token,
  });
}

export function rejectTutorHigherEdApplication(token: string, tutorId: number, reason: string) {
  return request<{ status: string }>(`/admin/tutoring/applications/${tutorId}/higher-ed/reject`, {
    method: "POST",
    body: { reason },
    token,
  });
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

export type AdminTutoringSession = {
  id: number;
  subject: string;
  topic: string | null;
  status: string;
  status_label: string;
  learner_name: string;
  learner_email: string;
  tutor_name: string;
  tutor_email: string;
  scheduled_at: string | null;
  duration_minutes: number | null;
  price_zar: number | null;
  platform_cut_percent: number | null;
  meet_link: string | null;
  recording_link: string | null;
  learner_rating: number | null;
  tutor_rating: number | null;
};

export function fetchAllTutoringSessionsAdmin(token: string, filter: "upcoming" | "completed" | "all" = "upcoming") {
  return request<{ sessions: AdminTutoringSession[] }>(`/admin/tutoring/sessions?filter=${filter}`, { token });
}

// Admin override only - price/duration are set by the learner at
// request time now, not here (see backend/tutoring.py's
// match_tutor_to_request docstring).
export function matchTutorToRequestAdmin(
  token: string,
  requestId: number,
  // admin_note: optional free-text context/instructions sent to the
  // tutor alongside the suggestion - admin can no longer propose a
  // different time here (see backend/tutoring.py's match_tutor_to_request).
  params: { tutor_id: number; admin_note?: string }
) {
  // Suggests a tutor - doesn't finalize. The tutor still has to confirm
  // (respondToAdminMatch) before anything is booked, so this only ever
  // returns the request moving to 'admin_proposed', not a payment ref.
  return request<{ id: number; status: string }>(
    `/admin/tutoring/requests/${requestId}/match`,
    { method: "POST", body: params, token }
  );
}

// The tutor confirming or declining an admin-suggested match (status
// "admin_proposed"). Declining reopens the request; accepting either
// finalizes directly (if the time is unchanged) or moves to
// "time_proposed" so the learner also approves a changed time.
export function respondToAdminMatch(token: string, requestId: number, accept: boolean) {
  return request<{ id: number; status: string }>(`/tutor/requests/${requestId}/admin-match/respond`, {
    method: "POST",
    body: { accept },
    token,
  });
}

// Paid sessions a tutor just cancelled (awaiting the learner's
// re-allocation/refund choice) plus refunds requested but not yet
// marked processed - see backend/tutoring.py's
// list_requests_needing_attention.
export function fetchRequestsNeedingAttention(token: string) {
  return request<{ requests: TutoringRequest[] }>("/admin/tutoring/requests/needing-attention", { token });
}

export function suggestRefundAdmin(token: string, requestId: number) {
  return request<{ id: number; status: string }>(`/admin/tutoring/requests/${requestId}/suggest-refund`, {
    method: "POST",
    token,
  });
}

export function markRefundProcessedAdmin(token: string, requestId: number) {
  return request<{ id: number; status: string }>(`/admin/tutoring/requests/${requestId}/mark-refund-processed`, {
    method: "POST",
    token,
  });
}

export type TutoringPayout = {
  id: number;
  session_id: number;
  tutor_id: number;
  tutor_name: string | null;
  tutor_bank_account_holder: string | null;
  tutor_bank_name: string | null;
  tutor_bank_branch_code: string | null;
  tutor_bank_account_number: string | null;
  tutor_bank_account_type: string | null;
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

export type PayoutsByTutor = { tutor_id: number; tutor_name: string | null; gross_zar: number; net_zar: number; count: number };
export type PayoutsSummary = {
  overall: { gross_zar: number; net_zar: number; count: number };
  by_tutor: PayoutsByTutor[];
  next_pay_day: string;
};

export function fetchPayoutsSummaryAdmin(token: string) {
  return request<PayoutsSummary>("/admin/tutoring/payouts/summary", { token });
}

export function settleAllPayoutsAdmin(token: string, paymentReference: string) {
  return request<{ settled_count: number; settled_net_zar: number }>("/admin/tutoring/payouts/settle-all", {
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

// --- In-app notifications - the same events that already email a
// learner/tutor (see backend/tutoring.py's _notify_* functions) also
// land here, so the bell icon has something to show without an inbox.
export type AppNotification = {
  id: number;
  title: string;
  body: string | null;
  created_at: string | null;
  read: boolean;
};

export function fetchNotifications(token: string) {
  return request<{ notifications: AppNotification[] }>("/notifications", { token });
}

export function fetchNotificationsUnreadCount(token: string) {
  return request<{ count: number }>("/notifications/unread-count", { token });
}

export function markNotificationRead(token: string, notificationId: number) {
  return request<{ status: string }>(`/notifications/${notificationId}/read`, { method: "POST", token });
}

export function markAllNotificationsRead(token: string) {
  return request<{ status: string }>("/notifications/read-all", { method: "POST", token });
}

export function fetchTutorNotifications(token: string) {
  return request<{ notifications: AppNotification[] }>("/tutor/notifications", { token });
}

export function fetchTutorNotificationsUnreadCount(token: string) {
  return request<{ count: number }>("/tutor/notifications/unread-count", { token });
}

export function markTutorNotificationRead(token: string, notificationId: number) {
  return request<{ status: string }>(`/tutor/notifications/${notificationId}/read`, { method: "POST", token });
}

export function markAllTutorNotificationsRead(token: string) {
  return request<{ status: string }>("/tutor/notifications/read-all", { method: "POST", token });
}

