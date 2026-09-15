import React from "react";
import { View, Text, StyleSheet } from "react-native";
import LatexView from "./LatexView";
import { colors } from "../theme";

// Splits free-form text on $...$ delimiters (the same convention the web
// app teaches learners in Collaborate) and renders math segments through
// LatexView, inline with the surrounding prose - LatexView already
// renders as a flex-row wrapping View, so nesting it inside another
// flex-row wrap here keeps everything on the same visual line(s).
const MATH_SEGMENT_RE = /\$([^$]+)\$/g;

export default function MixedMathText({ text, fontSize = 14 }: { text: string; fontSize?: number }) {
  const parts: { math: boolean; content: string }[] = [];
  let lastIndex = 0;
  const re = new RegExp(MATH_SEGMENT_RE);
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ math: false, content: text.slice(lastIndex, match.index) });
    }
    parts.push({ math: true, content: match[1] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push({ math: false, content: text.slice(lastIndex) });
  }

  if (parts.length === 0 || !parts.some((p) => p.math)) {
    return <Text style={{ fontSize, color: colors.text }}>{text}</Text>;
  }

  return (
    <View style={styles.wrap}>
      {parts.map((p, i) =>
        p.math ? (
          <LatexView key={i} latex={p.content} fontSize={fontSize} />
        ) : (
          <Text key={i} style={{ fontSize, color: colors.text }}>{p.content}</Text>
        )
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
});
