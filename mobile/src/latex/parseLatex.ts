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
