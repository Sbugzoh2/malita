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
