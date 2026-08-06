import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { parseLatex, LatexNode } from "./parseLatex";
import { colors } from "../theme";

type FracNode = Extract<LatexNode, { type: "frac" }>;

// Unicode superscript/subscript characters - covers every digit plus the
// handful of non-digit characters this app's LaTeX actually puts in an
// exponent or subscript (see backend/solver.py's output: mostly bare
// numbers, "n", "n-1", "n+1"). Anything outside this set falls back to
// plain "^(...)"/"_(...)" text - always correct, just less pretty.
//
// This is deliberately NOT implemented as nested <Text> with a `top`
// pixel offset (the previous approach). React Native on Android
// flattens nested <Text> into a single native TextView using Android's
// Spannable API rather than positioning real sub-views, and arbitrary
// style props like `top` are not reliably honoured inside that
// flattened span tree - in testing this produced superscripts that
// rendered as subscripts, and in some cases dropped trailing content
// entirely. Folding sup/sub into the surrounding string as real Unicode
// characters means there is nothing for Android to mis-measure: it is
// just plain text, identical on iOS/Android/web.
const SUPERSCRIPT_MAP: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
  "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
  "+": "⁺", "-": "⁻", "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ",
};

const SUBSCRIPT_MAP: Record<string, string> = {
  "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
  "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
  "+": "₊", "-": "₋", "(": "₍", ")": "₎", "n": "ₙ",
};

function toUnicodeScript(s: string, map: Record<string, string>): string | null {
  let out = "";
  for (const ch of s) {
    const mapped = map[ch];
    if (!mapped) return null;
    out += mapped;
  }
  return out;
}

// Flattens a node into a plain string wherever possible - the normal
// case for every LatexNode type except `frac`, which genuinely needs a
// stacked numerator/bar/denominator block layout and can't be expressed
// as a single line of text.
function flatten(node: LatexNode): string {
  switch (node.type) {
    case "text":
      return node.value;
    case "row":
      return node.children.map(flatten).join("");
    case "sup": {
      const base = flatten(node.base);
      const exp = flatten(node.exp);
      // "\circ" (the degree symbol, °) is always used as `X^\circ` in
      // this app's output - it reads correctly as normal-size text
      // right after the base, not raised further like a real exponent.
      if (exp === "°") return base + "°";
      const unicode = toUnicodeScript(exp, SUPERSCRIPT_MAP);
      return unicode !== null ? base + unicode : `${base}^(${exp})`;
    }
    case "sub": {
      const base = flatten(node.base);
      const sub = flatten(node.sub);
      const unicode = toUnicodeScript(sub, SUBSCRIPT_MAP);
      return unicode !== null ? base + unicode : `${base}_(${sub})`;
    }
    case "sqrt":
      return `√(${flatten(node.radicand)})`;
    case "frac":
      // Only reachable if a frac is nested inside a sup/sub/sqrt, which
      // none of backend/solver.py's LaTeX does today - kept as a safe
      // fallback rather than crashing if that ever changes.
      return `(${flatten(node.numerator)}/${flatten(node.denominator)})`;
  }
}

export default function LatexView({ latex, fontSize = 16 }: { latex: string; fontSize?: number }) {
  const tree = React.useMemo(() => parseLatex(latex), [latex]);
  const groups = React.useMemo(() => groupRowChildren(tree.children), [tree]);

  return (
    <View style={styles.rowWrap}>
      {groups.map((group, i) =>
        group.type === "frac" ? (
          <FracView key={i} node={group.node} fontSize={fontSize} />
        ) : (
          <Text
            key={i}
            textBreakStrategy="simple"
            style={{ fontSize, color: colors.text, flexShrink: 0 }}
          >
            {group.nodes.map(flatten).join("")}
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

function FracView({ node, fontSize }: { node: FracNode; fontSize: number }) {
  return (
    <View style={styles.frac}>
      <Text textBreakStrategy="simple" style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
        {flatten(node.numerator)}
      </Text>
      <View style={styles.fracBar} />
      <Text textBreakStrategy="simple" style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
        {flatten(node.denominator)}
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
