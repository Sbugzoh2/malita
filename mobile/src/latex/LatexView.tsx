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
          // flexShrink: 0 - Android's Yoga layout can measure a Text
          // inside this flexWrap row too narrow on first paint and clip
          // its tail (only showing fully after a re-render) - locking it
          // to its natural content width avoids that.
          // textBreakStrategy="simple" - Android-only prop that disables
          // the default "highQuality" line-breaking algorithm, which has
          // a known bug miscalculating text bounds inside flex containers
          // and clipping the tail on first paint (ignored on iOS/web).
          <Text
            key={i}
            textBreakStrategy="simple"
            style={{ fontSize, color: colors.text, flexShrink: 0 }}
          >
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
          <Text textBreakStrategy="simple" style={{ fontSize: fontSize * 0.68, top: -fontSize * 0.32 }}>
            {renderInline(node.exp, fontSize * 0.68)}
          </Text>
        </>
      );
    case "sub":
      return (
        <>
          {renderInline(node.base, fontSize)}
          <Text textBreakStrategy="simple" style={{ fontSize: fontSize * 0.68, top: fontSize * 0.12 }}>
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
      <Text textBreakStrategy="simple" style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
        {renderInline(node.numerator, fontSize * 0.85)}
      </Text>
      <View style={styles.fracBar} />
      <Text textBreakStrategy="simple" style={[styles.fracText, { fontSize: fontSize * 0.85 }]}>
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
