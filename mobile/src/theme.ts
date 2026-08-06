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

// Same example questions as app.py's "Not sure what to type?" expander -
// kept in sync by hand since the mobile app doesn't import Python.
export const EXAMPLE_QUESTIONS: Record<string, string[]> = {
  Algebra: ["x^2-5x+6=0", "2x+3<11", "x+y=10, 2x-y=2"],
  Sequences: ["3,7,11,...,99", "2,6,18,54"],
  "Financial Mathematics": [
    "R5000 is invested at 8% p.a. compounded quarterly for 3 years. Find the accumulated amount.",
    "A car worth R240000 depreciates at 12% p.a. on the reducing balance method. Find its value after 5 years.",
    "Thabo saves R800 at the end of every month for 4 years in an account earning 9% p.a. compounded monthly. Find the future value.",
  ],
  Calculus: ["differentiate 3x^2-5x+4", "f(x) = x^3 - 2x"],
  "Functions & Graphs": ["y=x^2-4x+3", "x=y^2", "y=2/(x-1)+3"],
  "Analytical Geometry": ["Find the distance between A(1,2) and B(4,6)", "gradient of A(1,1) and B(5,9)"],
  Trigonometry: ["solve 2sin(x)=1 for 0<=x<=360", "sin(30)"],
  Statistics: ["2,4,6,8,10,12", "mean and standard deviation of 5,8,12,15,20"],
  Probability: [
    "A bag contains 5 red and 3 blue balls. Find the probability of drawing a red ball.",
    "A die is rolled and a coin is tossed. Find the probability of getting a 6 and a head.",
    "P(A)=0.4, P(B)=0.3, A and B are mutually exclusive. Find P(A or B).",
  ],
  "Euclidean Geometry": [
    "angle at centre = 100, find angle at circumference",
    "cyclic quadrilateral angle A = 110, find angle C",
  ],
};
