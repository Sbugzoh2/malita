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
  // Physical Sciences topics reuse the same 8 validated hues (cycled, not
  // invented) rather than introducing new, unchecked colors.
  Momentum: "#2a78d6",
  "Vertical Projectile Motion": "#eb6834",
  "Work, Energy & Power": "#1baf7a",
  "Doppler Effect": "#eda100",
  Electrostatics: "#e87ba4",
  "Electric Circuits": "#008300",
  Electrodynamics: "#4a3aa7",
  Stoichiometry: "#e34948",
  "Rate and Extent of Reaction": "#2a78d6",
  "Chemical Equilibrium": "#eb6834",
  "Acids and Bases": "#1baf7a",
  Electrochemistry: "#eda100",
  "Organic Chemistry": "#e87ba4",
};

export const SUBJECTS = ["Mathematics", "Physical Sciences"] as const;
export type Subject = (typeof SUBJECTS)[number];

export const PAPER_TOPICS_BY_SUBJECT: Record<Subject, Record<string, string[]>> = {
  Mathematics: {
    "Paper 1": ["Algebra", "Sequences", "Financial Mathematics", "Calculus", "Functions & Graphs"],
    "Paper 2": ["Analytical Geometry", "Trigonometry", "Statistics", "Probability", "Euclidean Geometry"],
  },
  "Physical Sciences": {
    Physics: ["Momentum", "Vertical Projectile Motion", "Work, Energy & Power", "Doppler Effect", "Electrostatics", "Electric Circuits", "Electrodynamics"],
    Chemistry: ["Stoichiometry", "Rate and Extent of Reaction", "Chemical Equilibrium", "Acids and Bases", "Electrochemistry", "Organic Chemistry"],
  },
};

// Topics api_server.py's /solve can actually answer today - see
// api_server.py's SUPPORTED_SOLVE_TOPICS and README.md section 8.
// Physical Sciences topics are included here too - /solve routes every one
// of them straight through the LLM fallback (no deterministic solver
// exists for this subject), so none of them are "web only".
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
  "Momentum",
  "Vertical Projectile Motion",
  "Work, Energy & Power",
  "Doppler Effect",
  "Electrostatics",
  "Electric Circuits",
  "Electrodynamics",
  "Stoichiometry",
  "Rate and Extent of Reaction",
  "Chemical Equilibrium",
  "Acids and Bases",
  "Electrochemistry",
  "Organic Chemistry",
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
  Momentum: ["A 0.5 kg ball at 4 m/s hits a stationary 1.5 kg ball. After, the 0.5 kg ball moves at 1 m/s. Find the other ball's velocity."],
  "Vertical Projectile Motion": ["A ball is thrown upward at 15 m/s. Find the maximum height reached (g=9.8 m/s^2)."],
  "Work, Energy & Power": ["A 60 kg cyclist speeds up from 4 m/s to 10 m/s. Find the increase in kinetic energy."],
  "Doppler Effect": ["An ambulance emits 600 Hz moving towards you at 30 m/s. Find the frequency heard (speed of sound = 340 m/s)."],
  Electrostatics: ["Find the force between charges of +3x10^-6 C and +5x10^-6 C that are 0.2 m apart (k=9x10^9)."],
  "Electric Circuits": ["A 12 V battery with internal resistance 0.5 ohm is connected to a 5.5 ohm resistor. Find the current."],
  Electrodynamics: ["A 200 turn coil has its flux change from 0.002 Wb to 0.008 Wb in 0.4 s. Find the induced emf."],
  Stoichiometry: ["Calculate the number of moles in 11 g of CO2 (M(C)=12, M(O)=16)."],
  "Rate and Extent of Reaction": ["Concentration drops from 0.80 to 0.50 mol/dm^3 in 25 s. Find the average rate."],
  "Chemical Equilibrium": ["0.4 mol A and 0.6 mol B in a 2 dm^3 container at equilibrium for A<=>B. Calculate Kc."],
  "Acids and Bases": ["Calculate the pH of a solution with [H3O+]=1x10^-3 mol/dm^3."],
  Electrochemistry: ["Given Cu2+/Cu, E°=+0.34 V and Zn2+/Zn, E°=-0.76 V, calculate E°cell."],
  "Organic Chemistry": ["Give the IUPAC name of CH3-CH2-CH2-CH3."],
};
