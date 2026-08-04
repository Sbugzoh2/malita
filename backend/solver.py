"""
Malita (Pty) Ltd — pure math-solving logic, extracted from the Streamlit
AI Tutor so both app.py (Streamlit) and api_server.py (FastAPI, used by
the native app) can call the exact same solving code.

Each solve_<topic>(question) function returns a list of structured steps:
    [{"type": "markdown" | "latex" | "write" | "info" | "warning" | "error" | "caption",
      "content": str}, ...]
so callers can render however they like (Streamlit widgets, JSON for an
API, plain text, ...) without the solving logic needing to know or care.
"""

import re
import io
import base64
from contextlib import nullcontext
import numpy as np
import sympy as sp
import matplotlib
matplotlib.use("Agg")  # headless rendering - no display server in an API/server process
import matplotlib.pyplot as plt
from sympy.solvers.inequalities import solve_univariate_inequality

from .math_utils import safe_parse, detect_variables, _fmt_num


class _StopSolving(BaseException):
    """Raised by StepRecorder.stop() to mimic Streamlit's st.stop() - halts
    the rest of the solving function early, keeping whatever steps were
    already recorded. Every solve_<topic>() function catches this at its
    top level (mirroring Streamlit, where st.stop() halts the whole script
    but here must only halt that one function). Deliberately a
    BaseException, NOT an Exception - ported solving code has its own
    "except Exception as e:" handlers (mirroring the original Streamlit
    code), and those must NOT swallow this control-flow signal the way
    they would if it were a plain Exception subclass."""


class StepRecorder:
    """Mimics the handful of Streamlit calls the solving logic used to make
    directly (st.markdown/st.latex/st.write/st.info/st.warning/st.error/
    st.caption/st.pyplot), but records each as a structured step instead of
    rendering a widget - the exact same solving code runs either way,
    it just writes to this recorder instead of to the page."""

    def __init__(self):
        self.steps = []

    def _add(self, kind, content):
        self.steps.append({"type": kind, "content": str(content)})

    def write(self, content):
        self._add("write", content)

    def markdown(self, content):
        self._add("markdown", content)

    def latex(self, content):
        self._add("latex", content)

    def info(self, content):
        self._add("info", content)

    def warning(self, content):
        self._add("warning", content)

    def error(self, content):
        self._add("error", content)

    def success(self, content):
        self._add("success", content)

    def caption(self, content):
        self._add("caption", content)

    def stop(self):
        raise _StopSolving()

    def pyplot(self, fig, **kwargs):
        """Encode a matplotlib figure as a base64 PNG data URI - a single
        representation that both app.py (decode -> st.image) and
        api_server.py (send straight through as JSON) can use unchanged.
        Accepts/ignores Streamlit-only kwargs like use_container_width so
        solving code ported verbatim from app.py doesn't need editing."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        self._add("image", f"data:image/png;base64,{encoded}")

    def subheader(self, content):
        self._add("markdown", f"#### {content}")

    def columns(self, spec, **kwargs):
        """Streamlit's side-by-side layout has no meaning for a JSON step
        list or a single-column mobile screen - ported code that does
        `col1, col2 = st.columns(2)` then `with col1: ...` still calls
        st.xxx(...) (not col1.xxx(...)) inside each block, so the steps
        just end up sequential instead of side-by-side. These no-op
        context managers exist only so that `with col:` doesn't error."""
        n = spec if isinstance(spec, int) else len(spec)
        return [nullcontext() for _ in range(n)]

    def expander(self, label, expanded=False):
        """No collapse/expand concept for a step list - the label becomes
        a heading and the content that follows (inside `with
        st.expander(...):`) is recorded as normal steps right after it,
        always "open"."""
        self._add("markdown", f"**{label}**")
        return nullcontext()


def solve_algebra(question: str) -> list:
    """Solve a Grade 12 Algebra question - a single equation, an
    inequality, or a 2x2 simultaneous system - and return a list of
    structured steps. Ported from the Streamlit AI Tutor's Algebra
    branch: `st` below is a StepRecorder, not Streamlit, so every
    st.xxx(...) call records a step instead of rendering a widget."""
    st = StepRecorder()
    st.markdown("### Algebra Solution")
    
    # ------------------------------
    # CLEAN & PARSE INPUT
    # ------------------------------
    question_clean = question.replace("^", "**").replace(" ", "")
    question_clean = re.sub(r'(\))(\()', r'\1*\2', question_clean)
    question_clean = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', question_clean)
    question_clean = question_clean.replace("≤", "<=").replace("≥", ">=")
    
    raw_eqs = question_clean.split(",")
    symbols_in_expr = detect_variables(question_clean)
    symbols_dict = {s: sp.symbols(s) for s in symbols_in_expr}
    var_list = list(symbols_dict.values())
    
    try:
        parsed_eqs = []
        is_inequality = False
    
        for eq_str in raw_eqs:
            if any(op in eq_str for op in ["<=", ">=", "<", ">"]):
                is_inequality = True
                parsed_eqs.append(safe_parse(eq_str, symbols_dict))
            elif "=" in eq_str:
                lhs_str, rhs_str = eq_str.split("=")
                lhs = safe_parse(lhs_str, symbols_dict)
                rhs = safe_parse(rhs_str, symbols_dict)
                parsed_eqs.append(lhs - rhs)
            else:
                parsed_eqs.append(safe_parse(eq_str, symbols_dict))
    
    #---------------------------------------------START INEQUALITY SOLVER----------------------------------------------------------------------------------
        # ---------------------------------------------
        # START INEQUALITY SOLVER (CLEAN VERSION)
        # ---------------------------------------------
        if is_inequality:
    
            var = var_list[0]
            inequality = parsed_eqs[0]
    
            st.write("##### 💡 Step 1: Analyse the inequality")
            st.latex(sp.latex(inequality))
    
            # ---------------------------------------------
            # STEP 2.1: Write in standard form
            # ---------------------------------------------
            st.write("##### 📝 Step 2: Calculation")
    
            lhs, rhs = inequality.lhs, inequality.rhs
            expr = sp.simplify(lhs - rhs)
    
            st.markdown("**Step 2.1: Write the inequality with zero on one side**")
            st.latex(sp.latex(inequality.func(expr, 0)))
    
            # ---------------------------------------------
            # STEP 2.2: Determine degree
            # ---------------------------------------------
            degree = sp.degree(expr, var)
            st.markdown("**Step 2.2: Determine the degree of the expression**")
            st.write(f"The degree of the expression is **{degree}**.")
    
            roots = []
            can_proceed = False
    
            # ---------------------------------------------
            # STEP 2.3: Find the roots
            # ---------------------------------------------
            st.markdown("**Step 2.3: Find the roots of the expression**")
    
            factored = sp.factor(expr)
            expanded = sp.expand(expr)
    
            # CASE 1: Already factorised
            if expr.is_Mul:
                st.write("The expression is already factorised.")
                st.latex(sp.latex(expr))
                roots = sp.solve(expr, var)
                can_proceed = True
    
            # CASE 2: Factorisable after factoring
            elif factored != expanded:
                st.write("Factorising the expression:")
                st.latex(sp.latex(factored))
                roots = sp.solve(factored, var)
                can_proceed = True
    
            # CASE 3: Quadratic but not factorisable
            elif degree == 2:
                st.write("The expression cannot be factorised easily, We use the quadratic formula.")
                #st.write("We use the quadratic formula.")
    
                a = expanded.coeff(var, 2)
                b = expanded.coeff(var, 1)
                c = expanded.coeff(var, 0)
    
                st.latex(rf"a = {a}, \quad b = {b}, \quad c = {c}")
                st.latex(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
                st.latex(rf"x = \frac{{-({b}) \pm \sqrt{{({b})^2 - 4({a})({c})}}}}{{2({a})}}")
    
                discriminant = b**2 - 4*a*c
                st.latex(rf"\Delta = ({b})^2 - 4({a})({c})")
                st.latex(rf"\Delta = {sp.latex(discriminant)}")
    
                if discriminant.is_negative:
                    st.error(
                        "Since the discriminant is negative, there are **no real roots**."
                    )
                    st.info("Grade 12 learners do not work with complex numbers.")
                    can_proceed = False
                else:
                    st.info(
                        "Since the discriminant is non-negative, real roots exist."
                    )
                    roots = sp.solve(expanded, var)
                    can_proceed = True
    
            # CASE 4: Higher degree (Grade 12 limit)
            else:
                st.warning(
                    "This inequality cannot be solved using Grade 12 methods."
                )
                can_proceed = False
    
            # ---------------------------------------------
            # STEP 2.4: Display roots
            # ---------------------------------------------
            if can_proceed and roots:
                st.markdown("**Step 2.4: Critical values**")
                for r in roots:
                    st.latex(f"{sp.latex(var)} = {sp.latex(r)}")
    
                # ---------------------------------------------
                # STEP 2.5: Solve inequality
                # ---------------------------------------------
                st.markdown("**Step 2.5: Solve the inequality**")
                solution = solve_univariate_inequality(
                    inequality, var, relational=False
                )
    
                # ---------------------------------------------
                # FINAL ANSWER
                # ---------------------------------------------
                st.markdown("### 🏁 Final Answer")
    
                if isinstance(solution, sp.Interval):
                    left, right = solution.start, solution.end
                    left_op = "<" if solution.left_open else r"\leq"
                    right_op = "<" if solution.right_open else r"\leq"
    
                    st.latex(
                        rf"{sp.latex(left)} {left_op} {sp.latex(var)} {right_op} {sp.latex(right)}"
                    )
                else:
                    st.latex(sp.latex(solution))
    
    
    #--------------------------------------------------END INEQUALITY SOLVER----------------------------------------------------------------------------------
    
        # --------------------------------------------------
        # ALGEBRAIC EQUATION SOLVER (NO INEQUALITIES)
        # GRADE 12 SAFE – REAL ROOTS ONLY
        # --------------------------------------------------
        else:
            breakpoint = False
        #st.markdown("✏️ **Algebraic Equation Solution**")
    
        # Assumptions:
        # - parsed_eqs: list of sympy expressions already equal to 0
        # - raw_eqs: original user input strings
        # - var_list: detected variables
        # - symbols_dict: sympy symbol dictionary
    
            if len(parsed_eqs) == 1 and len(var_list) == 1:
                var = var_list[0]
                expr = parsed_eqs[0]
    
                # ----------------------------------
                # STEP 1: Write equation
                # ----------------------------------
                st.markdown("###### Step 1: Write the equation")
    
                if "=" in raw_eqs[0]:
                    lhs_str, rhs_str = raw_eqs[0].split("=")
                    lhs = safe_parse(lhs_str, symbols_dict)
                    rhs = safe_parse(rhs_str, symbols_dict)
                    equation = lhs - rhs
                    st.latex(sp.latex(sp.Eq(lhs, rhs)))
                else:
                    equation = expr
                    st.latex(sp.latex(expr) + " = 0")
    
                # ----------------------------------
                # STEP 2: Standard form
                # ----------------------------------
    
                st.markdown("###### Step 2: Write in standard form")
    
                # expr_raw = equation BEFORE expansion
                expr_raw = expr
    
                # RHS is zero because we moved everything to LHS
                rhs_is_zero = True
    
                # ----------------------------------
                # CASE 1: Already factorised (product form)
                # ----------------------------------
                if rhs_is_zero and expr_raw.is_Mul:
                    st.write("The equation is already factorised.")
                    st.latex(sp.latex(expr_raw) + " = 0")
    
                    factored = expr_raw
    
                # ----------------------------------
                # CASE 2: Not factorised → try factorising
                # ----------------------------------
                elif rhs_is_zero:
                    expr_std = sp.expand(expr_raw)
                    st.latex(sp.latex(expr_std) + " = 0")
    
                    degree = sp.degree(expr_std, var)
                    st.info(f"The degree of the equation is **{degree}**.")
    
                    factored = sp.factor(expr_std)
    
                    if factored != expr_std:
                        st.write("Factorising the expression:")
                        st.latex(sp.latex(factored) + " = 0")
                    else:
                        pass
                        #st.warning("Expression cannot be factorised further using Grade 12 methods.")
                        #factored = expr_std
    
                # ----------------------------------
                # CASE 3: RHS ≠ 0 → must expand
                # ----------------------------------
                else:
                    st.write("Right-hand side is not zero. Rewrite in standard form.")
                    expr_std = sp.expand(expr_raw)
                    st.latex(sp.latex(expr_std) + " = 0")
                    factored = sp.factor(expr_std)
    
    
                # ----------------------------------
                # STEP 4: Solve factor-by-factor
                # ----------------------------------
                #st.info("Solve each factor:")
    
                factors = factored.as_ordered_factors()
                all_roots = []
    
                for f in factors:
    
                    # Remove powers: (x-2)^2 → x-2
                    base, power = f.as_base_exp()
                    base = sp.factor(base)
    
                    if not base.has(var):
                        continue
    
                    deg = sp.degree(base, var)
    
                    # ------------------------------
                    # LINEAR FACTOR
                    # ------------------------------
    
                    if deg == 1:
                        st.markdown(f"**Solve:** ${sp.latex(base)} = 0$")
                        root = sp.solve(base, var)[0]
                        st.latex(rf"{sp.latex(var)} = {sp.latex(root)}")
                        all_roots.append(root)
    
                    # ------------------------------
                    # QUADRATIC FACTOR
                    # ------------------------------
                    elif deg == 2:
                        st.info(f"**Solve quadratic factor:** ${sp.latex(base)} = 0$")
    
                        a = base.coeff(var, 2)
                        b = base.coeff(var, 1)
                        c = base.coeff(var, 0)
    
                        st.markdown("Quadratic Formula:")
                        st.latex(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
                        st.latex(rf"a = {a}, \quad b = {b}, \quad c = {c}")
                        st.latex(rf"{sp.latex(var)} = \frac{{-({b}) \pm \sqrt{{({b})^2 - 4({a})({c})}}}}{{2({a})}}")
    
                        discriminant = b**2 - 4*a*c
                        st.latex(r"\Delta = b^2 - 4ac")
                        st.latex(rf"\Delta = ({b})^2 - 4({a})({c})")
                        st.latex(rf"\Delta = {sp.latex(discriminant)}")
    
                        if discriminant < 0:
                            st.error("No real roots (ignored at Grade 12 level).")
                            continue
    
                        roots = sp.solve(base, var)
                        for r in roots:
                            st.latex(rf"{sp.latex(var)} = {sp.latex(r)}")
                            all_roots.append(r)
    
                    # ------------------------------
                    # HIGHER DEGREE (IGNORED)
                    # ------------------------------
                    else:
                        st.warning(
                            f"Factor ${sp.latex(base)}$ is degree {deg} and "
                            "cannot be solved using Grade 12 methods."
                        )
    
                # ----------------------------------
                # FINAL ANSWER
                # ----------------------------------
                st.markdown("###### 🏁 Final Answer")
    
                # Remove duplicates (handles repeated roots)
                final_roots = list(dict.fromkeys(all_roots))
    
                if final_roots:
                    answer = " \\text{ or } ".join(
                        [rf"{sp.latex(var)} = {sp.latex(r)}" for r in final_roots]
                    )
                    st.latex(answer)
                else:
                    st.error("No real solutions found.")
    
            #else:
            #    st.warning("This solver currently supports ONE equation with ONE variable only.")
    
                            # -----------------------------------
                    # MULTI-VARIABLE SYSTEM (STEP-BY-STEP)
                    # -----------------------------------
            else:
                st.markdown("### 🔢 Solving Simultaneous Equations (Elimination Method)")
    
                # Only handle 2 equations & 2 variables for step-by-step
                if len(parsed_eqs) == 2 and len(var_list) == 2:
                    x, y = var_list
                    eq1, eq2 = parsed_eqs
    
                    # Convert to Eq objects if needed
                    if not isinstance(eq1, sp.Equality):
                        eq1 = sp.Eq(eq1, 0)
                    if not isinstance(eq2, sp.Equality):
                        eq2 = sp.Eq(eq2, 0)
    
                    st.markdown("**Step 1: Write the equations**")
    
                    # Use raw equations exactly as entered
                    lhs1, rhs1 = raw_eqs[0].split("=")
                    lhs2, rhs2 = raw_eqs[1].split("=")
    
                    eq1_display = sp.Eq(
                        safe_parse(lhs1, symbols_dict),
                        safe_parse(rhs1, symbols_dict)
                    )
    
                    eq2_display = sp.Eq(
                        safe_parse(lhs2, symbols_dict),
                        safe_parse(rhs2, symbols_dict)
                    )
    
                    st.latex(sp.latex(eq1_display))
                    st.latex(sp.latex(eq2_display))
    
    
                    # Move to standard form
                    expr1 = eq1.lhs - eq1.rhs
                    expr2 = eq2.lhs - eq2.rhs
    
                    a1 = expr1.coeff(x)
                    b1 = expr1.coeff(y)
                    c1 = -expr1.subs({x: 0, y: 0})
    
                    a2 = expr2.coeff(x)
                    b2 = expr2.coeff(y)
                    c2 = -expr2.subs({x: 0, y: 0})
    
                    st.markdown("**Step 2: Write in standard form**")
                    #st.latex(rf"{a1}{sp.latex(x)} + {b1}{sp.latex(y)} = {c1}")
                    #st.latex(rf"{a2}{sp.latex(x)} + {b2}{sp.latex(y)} = {c2}")
                    st.latex(sp.latex(eq1))
                    st.latex(sp.latex(eq2))
    
                    # -----------------------------------
                    # Step 3: Eliminate one variable (SHOW FULL SIMPLIFICATION)
                    # -----------------------------------
                    st.markdown("**Step 3: Eliminate one variable**")
    
                    st.markdown("Subtract equation (2) from equation (1):")
    
                    # Step 3.1: Write subtraction explicitly
                    st.markdown("**Step 3.1: Substitute and subtract**")
                    st.latex(
                        rf"({sp.latex(expr1)}) - ({sp.latex(expr2)}) = 0"
                    )
    
                    # Step 3.2: Remove brackets (change signs)
                    st.markdown("**Step 3.2: Remove brackets**")
    
                    # Get terms of expr1 and expr2 separately
                    terms1 = expr1.as_ordered_terms()
                    terms2 = [-t for t in expr2.as_ordered_terms()]  # flip signs manually
    
                    # Combine terms without simplifying
                    all_terms = terms1 + terms2
    
                    # Convert each term to LaTeX and join with proper signs
                    def term_latex(term):
                        s = sp.latex(term)
                        # ensure unary plus is handled nicely
                        if s[0] != '-' :
                            s = '+' + s
                        return s
    
                    latex_terms = ''.join([term_latex(t) for t in all_terms])
    
                    # Remove leading '+' if present
                    if latex_terms[0] == '+':
                        latex_terms = latex_terms[1:]                               
                    #result_expr = sp.expand(removed_brackets)
                    st.latex(
                        rf"{latex_terms} = 0"
                    )
    
                    # Step 3.3: Expand terms
                    st.markdown("**Step 3.3: Expand terms**")
    
                    expanded = sp.expand(expr1 - expr2)
                    st.latex(sp.latex(expanded) + " = 0")
                    #rf"{sp.latex(expanded)} = 0"
                    #st.latex(sp.latex(expanded))
    
                    # Step 3.4: Rearrange to standard form
                    st.markdown("**Step 3.4: Rearrange and simplify**")
    
                    simplified = sp.simplify(expanded)
                    st.latex(sp.latex(simplified) + " = 0")
    
                    new_eq = simplified
    
    
    
                    # Solve for y
                    y_value = sp.solve(new_eq, y)[0]
    
                    # --- Step 4: Solve for y ---
                    # We calculate the expression for y first
                    y_expr = sp.solve(new_eq, y)[0] 
    
                    st.markdown("**Step 4: Solve for** $y$")
                    # If y_expr still contains 'x', we show it as an intermediate step
                    st.latex(rf"{sp.latex(y)} = {sp.latex(y_expr)}")
    
                    # --- Step 5: Substitute into one of the original equations ---
                    st.markdown("**Step 5: Substitute into one of the original equations**")
                    substituted = eq1.subs(y, y_expr)
                    st.latex(sp.latex(substituted))
    
                    # --- Step 6: Solve for x ---
                    x_value = sp.solve(substituted, x)[0]
                    st.markdown("**Step 6: Solve for** $x$")
                    st.latex(rf"{sp.latex(x)} = {sp.latex(x_value)}")
    
                    # --- Final Answer (With explicit substitution for y) ---
                    st.markdown("### 🏁 Final Answer")
    
                    # 1. Substitute the numerical x_value into the y_expression to show the "work"
                    y_final_substitution = y_expr.subs(x, x_value)
                    y_final_numeric = sp.simplify(y_final_substitution)
    
                    # 2. Display x
                    st.latex(rf"{sp.latex(x)} = {sp.latex(x_value)}")
    
                    # 3. Display y substitution step (e.g., y = 30 - 3)
                    # We check if y_expr was dependent on x to avoid redundant lines if y was already a number
                    if y_expr.has(x):
                        st.latex(rf"{sp.latex(y)} = {sp.latex(y_expr.subs(x, sp.Symbol(sp.latex(x_value))))}") 
    
                    # 4. Display y final result (e.g., y = 27)
                    st.latex(rf"{sp.latex(y)} = {sp.latex(y_final_numeric)}")
    
                else:
                    st.warning("Step-by-step solution is currently supported for 2 equations with 2 variables only.")
                    solution = sp.solve(parsed_eqs, var_list, dict=True)
                    for sol in solution:
                        for var in var_list:
                            st.latex(f"{sp.latex(var)} = {sp.latex(sol[var])}")
    
    
    except Exception as e:
        st.error("Error parsing expression.")
        st.caption(str(e))
    return st.steps


def solve_sequences(question: str) -> list:
    """Solve a Grade 12 arithmetic/geometric sequence question. Ported
    from the Streamlit AI Tutor's Sequences branch - see solve_algebra's
    docstring for the StepRecorder pattern this follows."""
    st = StepRecorder()
    try:
        st.markdown("### 🔢 Sequence Analyzer")

        try:
            raw = question.strip()

            # ------------------------------
            # STEP 1: Split at ...
            # ------------------------------
            if "..." in raw or ".." in raw:
                parts = re.split(r"\.\.\.|\.{2}", raw, maxsplit=1)
                left_part = parts[0]
                right_part = parts[1] if len(parts) > 1 else ""
            else:
                left_part = raw
                right_part = ""

            # Normalize separators
            left_part = left_part.replace("+", ",")
            right_part = right_part.replace("+", ",")

            # Extract numbers
            left_numbers = re.findall(r"-?\d+\.?\d*", left_part)
            seq = [int(n) for n in left_numbers]

            right_numbers = re.findall(r"-?\d+\.?\d*", right_part)
            last_term = int(right_numbers[-1]) if right_numbers else None

            # ------------------------------
            # STEP 2: Display given sequence
            # ------------------------------
            st.markdown("**Step 1: Write the sequence**")
            st.latex(",\\;".join(map(str, seq)) + (",\\;\\ldots" if "..." in raw else ""))

            if len(seq) < 3:
                st.error("At least 3 terms are required to identify a sequence.")
                st.stop()

            # ------------------------------
            # STEP 3: Detect sequence type
            # ------------------------------
            diffs = [seq[i+1] - seq[i] for i in range(len(seq)-1)]
            ratios = []

            if all(seq[i] != 0 for i in range(len(seq)-1)):
                ratios = [seq[i+1] / seq[i] for i in range(len(seq)-1)]

            TOL = 1e-6
            is_arithmetic = all(abs(d - diffs[0]) < TOL for d in diffs)
            is_geometric = ratios and all(abs(r - ratios[0]) < TOL for r in ratios)

            # ------------------------------
            # ARITHMETIC SEQUENCE
            # ------------------------------
            if is_arithmetic:
                a = seq[0]
                d = diffs[0]

                st.success("This is an **Arithmetic Sequence**")

                st.markdown("**Step 2: Identify parameters**")

                #st.markdown("### 🔍 Step 2: Find a and d")

                # Ensure at least 2 terms exist
                if len(seq) < 2:
                    st.error("At least two terms are required to find a and d.")
                else:
                    # First term
                    a = seq[0]
                    # Common difference
                    d = seq[1] - seq[0]

                    # Display steps
                    st.markdown("**First term (a):**")
                    st.latex(r"a = T_1")
                    st.latex(rf"a = {a}")

                    st.markdown("**Common difference (d):**")
                    st.latex(r"d = T_2 - T_1")
                    #st.latex(rf"d = {seq[1]} - {seq[0]} = {d}")
                    st.latex(rf"d = {seq[1]} - {seq[0]}")
                    #st.latex(rf"a = {a}, \quad d = {d}")
                    st.latex(rf"\quad d = {d}")


                st.markdown("**Step 3: General term**")
                st.latex(r"T_n = a + (n-1)d")
                st.latex(rf"T_n = {a} + (n-1)({d})")
                st.latex(rf"T_n = {a} + {d}n-{d}")
                expanded = sp.expand(a + (sp.Symbol('n') - 1)*d)
                #st.markdown("**Expand**")
                st.latex(rf"T_n = {sp.latex(expanded)}")
                #simplified = sp.simplify(expanded)
                #st.markdown("**Simplified general term**")
                #st.latex(rf"T_n = {sp.latex(simplified)}")



                if last_term is not None:
                    st.markdown("**Step 4: Find number of terms**")
                    st.latex(rf"{last_term} = {a} + (n-1){d}")
                    n = (last_term - a) / d + 1
                    n = int(n) if n.is_integer() else n
                    st.latex(rf"n = {n}")

                    st.markdown("**Step 5: Sum of terms**")
                    st.latex(r"S_n = \frac{n}{2}(a + l)")
                    st.latex(rf"S_{n} = \frac{{{n}}}{2}({a}+{last_term})")

            # ------------------------------
            # GEOMETRIC SEQUENCE
            # ------------------------------
            elif is_geometric:
                a = seq[0]
                r = ratios[0]

                st.success("This is a **Geometric Sequence**")

                st.markdown("**Step 2: Identify parameters**")


                a = seq[0]
                #st.markdown("**Step 2: Identify the first term (a)**")
                st.latex(r"a = T_1")
                st.latex(rf"a = {a}")

                # Step 3: Identify common ratio (r)
                if len(seq) >= 2:
                    r = seq[1] / seq[0]
                    #st.markdown("**Step 3: Identify the common ratio (r)**")
                    st.latex(r"r = \frac{T_2}{T_1}=\frac{T_3}{T_2}")
                    st.latex(rf"r = \frac{{{seq[1]}}}{{{seq[0]}}}")
                    #r_frac = sp.Rational(r).limit_denominator()
                    #st.latex(rf"\quad r = \frac{{{r_frac.numerator}}}{{{r_frac.denominator}}}")
                    st.latex(rf"\quad r = {r}")

                st.markdown("**Step 3: General term**")
                st.latex(r"T_n = ar^{n-1}")
                st.latex(rf"T_n = {a}({r})^{{n-1}}")

                if last_term is not None:
                    st.markdown("**Step 4: Find number of terms**")
                    st.latex(rf"{last_term} = {a}({r})^{{n-1}}")
                    n = sp.solve(sp.Eq(last_term, a * r**(sp.symbols("n")-1)), sp.symbols("n"))
                    st.latex(rf"n = {sp.latex(n)}")

            # ------------------------------
            # NEITHER
            # ------------------------------
            else:
                st.error("This sequence is neither arithmetic nor geometric.")

        except Exception as e:
            st.error("Could not analyse the sequence.")
            st.caption(str(e))
    except _StopSolving:
        pass
    return st.steps


# =====================================================
# FINANCIAL MATHEMATICS — WORD PROBLEM INTERPRETER
# =====================================================
# Grade 12 CAPS Finance, Growth & Decay word problems are almost always
# built from the same handful of ingredients (an amount, a rate, a term,
# a compounding frequency, and sometimes a regular payment). Rather than
# forcing learners to type "P=1000,i=0.1,n=2", we scan the plain-English
# question for these ingredients and pick the right formula automatically.
FINANCE_FREQ_KEYWORDS = [
    ("semi-annually", 2), ("semi annually", 2),
    ("half-yearly", 2), ("half yearly", 2),
    ("quarterly", 4),
    ("monthly", 12),
    ("daily", 365),
    ("annually", 1), ("yearly", 1), ("per annum", 1), ("p.a.", 1), ("p.a", 1),
]

def _find_money_amounts(original_question):
    """Return [(value, char_index, lowercased_context_window)] for every
    Rand amount in the question, in the order they appear. Matched against
    the ORIGINAL (not lowercased) text and anchored on a capital "R" at a
    word boundary — matching case-insensitively on a bare "r" would also
    catch the last letter of ordinary words like "for 4 years" and
    misread them as amounts."""
    amounts = []
    for m in re.finditer(r"\bR\s?([\d][\d,]*\.?\d*)", original_question):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        window = original_question[max(0, m.start() - 25):m.start()].lower()
        amounts.append((value, m.start(), window))
    return amounts

def extract_financial_params(question):
    """Best-effort extraction of P (principal), rate (annual %), term
    (years), compounding frequency, and x (recurring payment) from a
    free-text finance question. Returns a dict of whatever it could find
    — callers must fall back to manual inputs for anything missing."""
    q = question.lower()
    params = {}

    amounts = _find_money_amounts(question)
    payment_triggers = ["save", "deposit", "payment of", "instalment", "installment", "pays", "pay "]
    principal_triggers = ["invest", "principal", "worth", "cost", "loan of", "borrow", "value of"]

    unclassified = []
    for value, _, window in amounts:
        if any(t in window for t in payment_triggers) and "x" not in params:
            params["x"] = value
        elif any(t in window for t in principal_triggers) and "P" not in params:
            params["P"] = value
        else:
            unclassified.append(value)
    # Anything not explicitly flagged as a recurring payment defaults to
    # being the principal/loan amount (the common case: "R5000 is invested...").
    if "P" not in params and unclassified:
        params["P"] = unclassified[0]

    rate_match = re.search(r"([\d]*\.?\d+)\s*%", q)
    if rate_match:
        params["rate"] = float(rate_match.group(1)) / 100

    years_match = re.search(r"([\d]*\.?\d+)\s*year", q)
    if years_match:
        params["years"] = float(years_match.group(1))
    else:
        months_match = re.search(r"([\d]*\.?\d+)\s*month", q)
        if months_match:
            params["years"] = float(months_match.group(1)) / 12

    params["freq"] = 1
    for kw, freq in FINANCE_FREQ_KEYWORDS:
        if kw in q:
            params["freq"] = freq
            break

    if "reducing balance" in q or "reducing-balance" in q or "declining balance" in q or "diminishing" in q:
        params["type"] = "depreciation_reducing"
    elif "straight line" in q or "straight-line" in q or "depreciat" in q:
        params["type"] = "depreciation_straight"
    elif any(w in q for w in ["loan", "repaid", "repayment", "bond", "borrow"]):
        params["type"] = "annuity_present"
    elif "x" in params and any(w in q for w in ["save", "deposit", "future value", "accumulate"]):
        params["type"] = "annuity_future"
    elif "simple interest" in q:
        params["type"] = "simple"
    else:
        params["type"] = "compound"

    return params

def plot_finance_chart(kind, P, i_period, n_period, x=None):
    """Small value-vs-time chart for a finance scenario — a picture makes
    growth/decay and amortisation much more concrete for learners than a
    single final number."""
    periods = np.arange(0, int(round(n_period)) + 1)
    if kind == "compound":
        values = P * (1 + i_period) ** periods
    elif kind == "simple":
        values = P * (1 + periods * i_period)
    elif kind == "depreciation_reducing":
        values = P * (1 - i_period) ** periods
    elif kind == "depreciation_straight":
        values = np.clip(P * (1 - periods * i_period), 0, None)
    elif kind == "annuity_future":
        values = x * ((1 + i_period) ** periods - 1) / i_period
    elif kind == "annuity_present":
        values = [P]
        balance = P
        for _ in periods[1:]:
            balance = balance * (1 + i_period) - x
            values.append(max(balance, 0))
        values = np.array(values)
    else:
        return None

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(periods, values, marker="o", linewidth=2, color="#2563eb")
    ax.fill_between(periods, values, alpha=0.1, color="#2563eb")
    ax.set_xlabel("Period")
    ax.set_ylabel("Value (R)")
    ax.set_title("Value over time")
    ax.grid(True, linestyle="--", alpha=0.5)
    return fig


def solve_financial_mathematics(question: str) -> list:
    """Solve a Grade 12 Finance/Growth/Decay question. Ported from the
    Streamlit AI Tutor's Financial Mathematics branch, with one
    simplification: Streamlit let a learner manually override the
    auto-detected calculation type/amount/rate/term/frequency via
    selectbox/number_input widgets before solving. This API-facing
    version has no such refinement step - it solves directly with
    whatever extract_financial_params()/the P=/i=/n= shorthand detects,
    the same defaults those widgets started from."""
    st = StepRecorder()
    try:
        st.markdown("### 💰 Finance, Growth & Decay")

        # Legacy shorthand "P=1000,i=10,n=2" still works exactly
        # as before. Anything else is treated as a plain-English
        # word problem and run through the finance parser.
        P_match = re.search(r"\bP\s*=\s*([-+]?\d*\.?\d+)", question)
        i_match = re.search(r"\bi\s*=\s*([-+]?\d*\.?\d+)", question)
        n_match = re.search(r"\bn\s*=\s*([-+]?\d*\.?\d+)", question)

        if P_match and i_match and n_match:
            detected = {
                "type": "compound", "P": float(P_match.group(1)),
                "rate": float(i_match.group(1)) / 100,
                "years": float(n_match.group(1)), "freq": 1,
            }
        else:
            detected = extract_financial_params(question)

        TYPE_LABELS = {
            "compound": "Compound Interest / Growth",
            "simple": "Simple Interest",
            "depreciation_straight": "Straight-line Depreciation",
            "depreciation_reducing": "Reducing-balance Depreciation",
            "annuity_future": "Future Value Annuity (regular savings)",
            "annuity_present": "Present Value Annuity (loan repayments)",
        }
        calc_type = detected.get("type", "compound")
        st.caption(f"Detected calculation type: {TYPE_LABELS[calc_type]}")

        P = float(detected.get("P", 1000.0))
        rate_pct = float(detected.get("rate", 0.1) * 100)
        years = float(detected.get("years", 1.0))

        if calc_type in ("compound", "annuity_future", "annuity_present"):
            freq = detected.get("freq", 1)
        else:
            freq = 1

        rate = rate_pct / 100
        i = rate / freq
        n = years * freq

        if calc_type in ("annuity_future", "annuity_present"):
            x = float(detected.get("x", 500.0))

        st.markdown("###### ✏️ Step-by-step Solution")

        if calc_type == "compound":
            st.latex(r"A = P(1+i)^n")
            st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
            A = P * (1 + i) ** n
            st.latex(rf"A = {P:.4g}(1+{i:.6g})^{{{n:.4g}}} = R{A:,.2f}")
            final_value, chart_kind, chart_args = A, "compound", dict(P=P, i_period=i, n_period=n)

        elif calc_type == "simple":
            st.latex(r"A = P(1+ni)")
            A = P * (1 + n * i) if freq != 1 else P * (1 + years * rate)
            n_disp = years if freq == 1 else n
            i_disp = rate if freq == 1 else i
            st.latex(rf"A = {P:.4g}(1+{n_disp:.4g}\times{i_disp:.6g}) = R{A:,.2f}")
            final_value, chart_kind, chart_args = A, "simple", dict(P=P, i_period=i_disp, n_period=n_disp)

        elif calc_type == "depreciation_straight":
            st.latex(r"A = P(1-ni)")
            A = max(P * (1 - years * rate), 0)
            st.latex(rf"A = {P:.4g}(1-{years:.4g}\times{rate:.6g}) = R{A:,.2f}")
            final_value, chart_kind, chart_args = A, "depreciation_straight", dict(P=P, i_period=rate, n_period=years)

        elif calc_type == "depreciation_reducing":
            st.latex(r"A = P(1-i)^n")
            A = P * (1 - rate) ** years
            st.latex(rf"A = {P:.4g}(1-{rate:.6g})^{{{years:.4g}}} = R{A:,.2f}")
            final_value, chart_kind, chart_args = A, "depreciation_reducing", dict(P=P, i_period=rate, n_period=years)

        elif calc_type == "annuity_future":
            st.latex(r"F = \frac{x[(1+i)^n - 1]}{i}")
            st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
            F = x * ((1 + i) ** n - 1) / i
            st.latex(rf"F = \frac{{{x:.4g}[(1+{i:.6g})^{{{n:.4g}}} - 1]}}{{{i:.6g}}} = R{F:,.2f}")
            final_value, chart_kind, chart_args = F, "annuity_future", dict(P=0, i_period=i, n_period=n, x=x)

        else:  # annuity_present — loan, solve for the instalment x
            st.latex(r"P = \frac{x[1-(1+i)^{-n}]}{i} \;\Rightarrow\; x = \frac{Pi}{1-(1+i)^{-n}}")
            st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
            instalment = P * i / (1 - (1 + i) ** (-n))
            st.latex(rf"x = \frac{{{P:.4g}\times{i:.6g}}}{{1-(1+{i:.6g})^{{-{n:.4g}}}}} = R{instalment:,.2f} \;\text{{per period}}")
            final_value, chart_kind, chart_args = instalment, "annuity_present", dict(P=P, i_period=i, n_period=n, x=instalment)

        st.success(f"🏁 Final Answer: R{final_value:,.2f}")

        fig = plot_finance_chart(chart_kind, **chart_args)
        if fig is not None:
            st.pyplot(fig, use_container_width=True)

    except Exception as e:
        st.error("Could not parse financial parameters from the question.")
        st.caption(str(e))
    except _StopSolving:
        pass
    return st.steps


def solve_calculus(question: str) -> list:
    """Solve a Grade 12 differentiation question via power rule + first principles side by side. Ported from the Streamlit AI Tutor's Calculus branch."""
    st = StepRecorder()
    try:
        st.markdown("### 📐 Differentiation: Comparison of Methods")

        try:
            # --- 1. CLEAN & PARSE INPUT ---
            expr_str = question.lower()
            # Remove common prefixes (any single-letter dependent variable,
            # e.g. "y=", "f(x)=", "g(t)=", not just x)
            expr_str = re.sub(r"(find derivative of|differentiate|d\w*/d\w*)", "", expr_str)
            expr_str = re.sub(r"^[a-zA-Z]\([a-zA-Z]\)\s*=", "", expr_str)
            expr_str = re.sub(r"^[a-zA-Z]\s*=", "", expr_str)
            expr_str = expr_str.strip()

            # Handle implicit multiplication and powers
            expr_str = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', expr_str)
            expr_str = re.sub(r'(\))(\()', r'\1*\2', expr_str)
            expr_str = expr_str.replace("^", "**")

            # Detect whichever variable the learner used (x, a, t, ...)
            detected_vars = detect_variables(expr_str)
            var_name = detected_vars[0] if detected_vars else "x"
            x = sp.symbols(var_name)
            symbols_dict = {var_name: x}

            expr = safe_parse(expr_str, symbols_dict)
            h = sp.symbols("h")

            # --- 2. CREATE SIDE-BY-SIDE COLUMNS ---
            col1, col2 = st.columns(2)

            # --- LEFT COLUMN: POWER RULE ---
            with col1:
                st.subheader("🚀 Power Rule")
                st.info("The standard shortcut method.")

                derivative_pr = sp.diff(expr, x)

                st.markdown("**Step 1: Apply rules to terms**")
                terms = expr.as_ordered_terms()
                for term in terms:
                    coeff, power = term.as_coeff_exponent(x)
                    if power != 0:
                        st.latex(rf"\frac{{d}}{{d{var_name}}}({sp.latex(term)}) = {sp.latex(coeff * power)}{var_name}^{{{sp.latex(power-1)}}}")
                    else:
                        st.latex(rf"\frac{{d}}{{d{var_name}}}({sp.latex(term)}) = 0")

                st.markdown("**Final Result (Power Rule):**")
                st.latex(rf"f'({var_name}) = {sp.latex(derivative_pr)}")

            # --- RIGHT COLUMN: FIRST PRINCIPLE ---
            with col2:
                st.subheader("📝 First Principle")
                st.info("Definition using limits.")

                # Step 1: Formula and Substitution
                st.markdown("**Step 1: Substitution**")
                f_x = expr
                f_xh = expr.subs(x, x + h)

                st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{f({var_name}+h) - f({var_name})}}{{h}}")
                st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{{sp.latex(f_xh)} - ({sp.latex(f_x)})}}{{h}}")

                # Step 2: Simplify numerator
                st.markdown("**Step 2: Expand Numerator**")
                numerator_expanded = sp.expand(f_xh - f_x)
                st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{{sp.latex(numerator_expanded)}}}{{h}}")

                # Step 3: Factor and Cancel h
                st.markdown("**Step 3: Cancel $h$**")
                # We divide by h manually to show the cancellation clearly
                terms_after_h = sp.expand(numerator_expanded / h)
                st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} ({sp.latex(terms_after_h)})")

                # Step 4: Final Limit
                st.markdown("**Step 4: Final Result**")
                derivative_fp = sp.limit(numerator_expanded / h, h, 0)
                st.latex(rf"f'({var_name}) = {sp.latex(derivative_fp)}")

        except Exception as e:
            st.error("Could not parse the expression for differentiation.")
            st.caption(f"Error details: {str(e)}")
    except _StopSolving:
        pass
    return st.steps


def solve_functions_graphs(question: str) -> list:
    """Solve/analyse a Grade 12 function or relation and sketch its graph. Ported from the Streamlit AI Tutor's Functions & Graphs branch."""
    st = StepRecorder()
    try:
        st.markdown("### 📈 Functions & Graphs")

        try:
            # ---------------------------------------------------
            # 1. CLEAN INPUT
            # ---------------------------------------------------
            expr_str = question.lower()
            expr_str = re.sub(r"(graph|sketch|draw)", "", expr_str)
            expr_str = expr_str.strip()
            expr_str = expr_str.replace("^", "**")

            # Handle implicit multiplication
            expr_str = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', expr_str)
            expr_str = re.sub(r'(\))(\()', r'\1*\2', expr_str)

            # ---------------------------------------------------
            # 1b. DETECT VARIABLES — works whichever letters the
            # learner used, and understands BOTH "y = x**2" AND
            # "x = y**2" (variable roles swapped), or any other
            # letter pair like "b = a**2 - 4a + 2".
            # ---------------------------------------------------
            detected_vars = detect_variables(expr_str)
            symbols_dict = {v: sp.symbols(v) for v in detected_vars}

            if "=" in expr_str:
                lhs_str, rhs_str = expr_str.split("=", 1)
                lhs_expr = safe_parse(lhs_str, symbols_dict)
                rhs_expr = safe_parse(rhs_str, symbols_dict)
            else:
                # No '=' given, e.g. just "x**2-4x+2" -> assume it's
                # the formula for a dependent variable "y" (or a
                # fresh name if "y" is itself the only detected var).
                rhs_expr = safe_parse(expr_str, symbols_dict)
                dep_name = "y" if "y" not in detected_vars else "z"
                lhs_expr = sp.symbols(dep_name)
                symbols_dict[dep_name] = lhs_expr
                detected_vars = sorted(set(detected_vars) | {dep_name})

            equation = lhs_expr - rhs_expr
            eq_symbols = sorted(equation.free_symbols, key=lambda s: s.name)

            if len(eq_symbols) > 2:
                st.error("This solver currently supports relations between two variables only (e.g. x and y).")
                st.stop()

            # ----------------------------------
            # DECIDE WHICH SYMBOL IS "DEPENDENT" (out_var) vs
            # "INDEPENDENT" (indep_var) FOR THE STEP-BY-STEP ANALYSIS.
            # Prefer whichever side of "=" was a single bare symbol
            # (e.g. "y=..." -> out_var=y ; "x=y**2" -> out_var=x).
            # ----------------------------------
            out_var = None
            indep_var = None
            formula = None

            if isinstance(lhs_expr, sp.Symbol) and lhs_expr in eq_symbols:
                out_var = lhs_expr
                formula = rhs_expr
            elif isinstance(rhs_expr, sp.Symbol) and rhs_expr in eq_symbols:
                out_var = rhs_expr
                formula = lhs_expr
            else:
                # True implicit relation (both sides mix variables),
                # e.g. a circle x**2+y**2=25 -- fall back to solving.
                out_var = eq_symbols[-1] if len(eq_symbols) > 1 else eq_symbols[0]
                formula = None

            remaining = [s for s in eq_symbols if s != out_var]
            indep_var = remaining[0] if remaining else sp.symbols(
                "x" if out_var.name != "x" else "t"
            )

            # For PLOTTING, always show x horizontally and y vertically
            # when those are the two letters in play; otherwise plot
            # alphabetically first symbol horizontally.
            if {s.name for s in eq_symbols} == {"x", "y"}:
                plot_horiz = sp.symbols("x")
                plot_vert = sp.symbols("y")
            elif len(eq_symbols) == 2:
                plot_horiz, plot_vert = eq_symbols[0], eq_symbols[1]
            else:
                plot_horiz = indep_var
                plot_vert = out_var

            # branches = expression(s) for plot_vert purely in terms
            # of plot_horiz, e.g. "x=y**2" -> [sqrt(x), -sqrt(x)].
            # We ALWAYS solve directly against the full relation
            # (rather than trusting `formula` blindly) because
            # `formula` can be expressed in terms of the WRONG
            # variable whenever the learner writes the equation with
            # variables "swapped", e.g. "x = y**2" instead of the
            # usual "y = x**2". Solving explicitly for plot_vert is
            # what makes graphs like x=y^2 render correctly instead
            # of silently being plotted as if it said y=x^2.
            if formula is not None and out_var == plot_vert:
                branches = [formula]
            else:
                try:
                    branches = sp.solve(sp.Eq(lhs_expr, rhs_expr), plot_vert)
                except Exception:
                    branches = None
                if not branches:
                    branches = None

            is_explicit_function = bool(
                branches is not None and len(branches) == 1
                and not branches[0].has(plot_vert)
            )

            x = indep_var  # kept for readability in the walkthrough below
            expr = branches[0] if is_explicit_function else None

            st.markdown("##### 🔹 Given Relation")
            st.latex(sp.latex(sp.Eq(lhs_expr, rhs_expr)))

            if branches and not is_explicit_function:
                branch_strs = " or ".join(
                    rf"${sp.latex(plot_vert)}={sp.latex(b)}$" for b in branches
                )
                st.caption(f"Rewritten to isolate ${sp.latex(plot_vert)}$: {branch_strs}")

            # ---------------------------------------------------
            # DETAILED STEP-BY-STEP ANALYSIS
            # Only fully meaningful when we have one explicit
            # formula: out_var = f(indep_var). For genuinely
            # implicit relations (e.g. circles, or "x=y**2" which
            # isn't a function of x at all — it fails the vertical
            # line test) we skip straight to generic intercepts
            # plus the graph, further down.
            # ---------------------------------------------------
            if is_explicit_function:

                # ---------------------------------------------------
                # 2. DOMAIN
                # ---------------------------------------------------
                st.markdown(f"##### 🔹 Domain (in terms of {sp.latex(indep_var)})")
                domain = sp.calculus.util.continuous_domain(expr, indep_var, sp.S.Reals)
                st.latex(r"\text{Domain: } " + sp.latex(domain))

                # ---------------------------------------------------
                # 3. Y-INTERCEPT (value of out_var when indep_var = 0)
                # ---------------------------------------------------
                st.markdown(f"##### 🔹 {sp.latex(out_var)}-intercept")
                try:
                    y_int = expr.subs(indep_var, 0)
                    st.latex(rf"\text{{intercept: }} ({sp.latex(indep_var)}=0,\ {sp.latex(out_var)}={sp.latex(y_int)})")
                except Exception:
                    st.latex(r"\text{No intercept found}")

                # ---------------------------------------------------
                # 4. X-INTERCEPTS (indep_var values where out_var = 0)
                # ---------------------------------------------------
                st.markdown(f"##### 🔹 {sp.latex(indep_var)}-intercepts")
                real_roots = []
                try:
                    roots = sp.solve(expr, indep_var)
                    for r in roots:
                        if r.is_real:
                            real_roots.append(r)
                            st.latex(rf"({sp.latex(r)}, 0)")
                    if not real_roots:
                        st.latex(r"\text{No real intercepts}")
                except Exception:
                    st.write("Could not determine intercepts symbolically.")

                # ---------------------------------------------------
                # 5. FIRST DERIVATIVE
                # ---------------------------------------------------
                st.markdown("##### 🔹 First Derivative")
                derivative = sp.diff(expr, indep_var)
                st.latex(rf"\frac{{d{sp.latex(out_var)}}}{{d{sp.latex(indep_var)}}} = " + sp.latex(derivative))

                # ---------------------------------------------------
                # 6. TURNING POINTS
                # ---------------------------------------------------
                st.markdown("##### 🔹 Turning Points")
                turning_points = []
                try:
                    turning_x = sp.solve(derivative, indep_var)
                    if turning_x:
                        second_derivative = sp.diff(derivative, indep_var)
                        for tx in turning_x:
                            if tx.is_real:
                                ty = expr.subs(indep_var, tx)
                                turning_points.append(ty)
                                st.latex(rf"{sp.latex(indep_var)} = {sp.latex(tx)}, {sp.latex(out_var)} = {sp.latex(ty)}")

                                nature = second_derivative.subs(indep_var, tx)
                                if nature > 0: st.latex(r"\text{Minimum}")
                                elif nature < 0: st.latex(r"\text{Maximum}")
                                else: st.latex(r"\text{Inflection}")
                    else:
                        st.latex(r"\text{No turning points}")
                except Exception:
                    st.write("Calculated numerically in graph.")

                # ---------------------------------------------------
                # 7. AXIS OF SYMMETRY
                # ---------------------------------------------------
                try:
                    if sp.degree(expr, indep_var) == 2:
                        st.markdown("##### 🔹 Axis of Symmetry")
                        a_coeff = expr.coeff(indep_var, 2)
                        b_coeff = expr.coeff(indep_var, 1)
                        axis = -b_coeff / (2 * a_coeff)
                        st.latex(rf"{sp.latex(indep_var)} = {sp.latex(axis)}")
                except Exception:
                    pass

                # ---------------------------------------------------
                # 8. RANGE
                # ---------------------------------------------------
                st.markdown("##### 🔹 Range")
                try:
                    if sp.degree(expr, indep_var) in [0, 1]:
                        st.latex(r"\text{Range: } (-\infty, \infty)")
                    elif turning_points:
                        deg = sp.degree(expr, indep_var)
                        lead_coeff = expr.coeff(indep_var, deg)
                        y_min, y_max = min(turning_points), max(turning_points)
                        if deg % 2 == 0:
                            if lead_coeff > 0: st.latex(rf"{sp.latex(out_var)} \ge {sp.latex(y_min)}")
                            else: st.latex(rf"{sp.latex(out_var)} \le {sp.latex(y_max)}")
                        else: st.latex(r"\text{Range: } (-\infty, \infty)")
                except Exception:
                    st.write("Determined by function type.")

                # ---------------------------------------------------
                # 9. ASYMPTOTES
                # ---------------------------------------------------
                st.markdown("##### 🔹 Asymptotes")
                try:
                    num, den = sp.fraction(expr)
                    vert_asym = sp.solve(den, indep_var) if den != 1 else []
                    for va in vert_asym:
                        if va.is_real:
                            st.latex(rf"{sp.latex(indep_var)} = {sp.latex(va)}")

                    horiz_pos = sp.limit(expr, indep_var, sp.oo)
                    horiz_neg = sp.limit(expr, indep_var, -sp.oo)
                    if horiz_pos.is_finite: st.latex(rf"{sp.latex(out_var)} = {sp.latex(horiz_pos)}")
                    if horiz_neg.is_finite: st.latex(rf"{sp.latex(out_var)} = {sp.latex(horiz_neg)}")
                except Exception:
                    pass
            else:
                st.info(
                    f"This relation is not a function of ${sp.latex(plot_horiz)}$ in the usual "
                    "sense (it fails the vertical line test) — showing its intercepts, domain "
                    "and graph below instead."
                )
                relation_eq = sp.Eq(lhs_expr, rhs_expr)

                st.markdown(f"##### 🔹 {sp.latex(plot_vert)}-intercept(s)")
                try:
                    y_ints = [r for r in sp.solve(relation_eq.subs(plot_horiz, 0), plot_vert) if r.is_real]
                    if y_ints:
                        for yi in y_ints:
                            st.latex(rf"({sp.latex(plot_horiz)}=0,\ {sp.latex(plot_vert)}={sp.latex(yi)})")
                    else:
                        st.latex(r"\text{No real intercepts}")
                except Exception:
                    st.write("Could not determine intercepts symbolically.")

                st.markdown(f"##### 🔹 {sp.latex(plot_horiz)}-intercept(s)")
                try:
                    x_ints = [r for r in sp.solve(relation_eq.subs(plot_vert, 0), plot_horiz) if r.is_real]
                    if x_ints:
                        for xi in x_ints:
                            st.latex(rf"({sp.latex(xi)},\ {sp.latex(plot_vert)}=0)")
                    else:
                        st.latex(r"\text{No real intercepts}")
                except Exception:
                    st.write("Could not determine intercepts symbolically.")

                if branches:
                    try:
                        domain = sp.Union(*[
                            sp.calculus.util.continuous_domain(b, plot_horiz, sp.S.Reals)
                            for b in branches
                        ])
                        st.markdown(f"##### 🔹 Domain (in terms of {sp.latex(plot_horiz)})")
                        st.latex(r"\text{Domain: } " + sp.latex(domain))
                    except Exception:
                        pass

            # ---------------------------------------------------
            # 📉 SKETCH OF THE GRAPH (SMART MODE, generic variables)
            # ---------------------------------------------------
            st.markdown("##### 📉 Sketch of the Graph")

            horiz_vals = np.linspace(-10, 10, 4000)
            fig, ax = plt.subplots(figsize=(7, 5))

            if not branches:
                st.warning("No real solutions exist for this relation, so it cannot be graphed.")
            else:
                expr_str_for_type = str(branches[0])
                is_trig = any(f in expr_str_for_type for f in ["sin", "cos", "tan", "sec", "csc"])

                if len(branches) > 1:
                    # Multiple branches, e.g. x=y**2 -> y=+-sqrt(x)
                    for sol in branches:
                        f = sp.lambdify(plot_horiz, sol, "numpy")
                        vert_vals = f(horiz_vals)
                        vert_vals = np.where(np.isfinite(vert_vals), vert_vals, np.nan)
                        ax.plot(horiz_vals, vert_vals, linewidth=2)
                elif is_trig:
                    f = sp.lambdify(plot_horiz, branches[0], "numpy")
                    vert_vals = f(horiz_vals)
                    vert_vals = np.where(np.abs(vert_vals) > 50, np.nan, vert_vals)
                    ax.plot(horiz_vals, vert_vals, linewidth=2)
                else:
                    plot_expr = branches[0]
                    f = sp.lambdify(plot_horiz, plot_expr, "numpy")
                    vert_vals = f(horiz_vals)

                    num, den = sp.fraction(plot_expr)
                    vertical_asymptotes = []
                    if den != 1:
                        vertical_asymptotes = [float(v) for v in sp.solve(den, plot_horiz) if v.is_real]
                    for va in vertical_asymptotes:
                        vert_vals[np.abs(horiz_vals - va) < 0.05] = np.nan
                        ax.axvline(va, linestyle="--", color="red", linewidth=2)

                    lim_pos = sp.limit(plot_expr, plot_horiz, sp.oo)
                    lim_neg = sp.limit(plot_expr, plot_horiz, -sp.oo)
                    if lim_pos.is_real and lim_pos.is_finite:
                        ax.axhline(float(lim_pos), linestyle="--", color="red", linewidth=2)
                    if lim_neg.is_real and lim_neg.is_finite:
                        ax.axhline(float(lim_neg), linestyle="--", color="red", linewidth=2)

                    vert_vals = np.where(np.isfinite(vert_vals), vert_vals, np.nan)
                    ax.plot(horiz_vals, vert_vals, linewidth=2)

            ax.axhline(0, color="black", linewidth=0.8)
            ax.axvline(0, color="black", linewidth=0.8)
            ax.grid(True, linestyle="--", alpha=0.5)

            ax.set_xlabel(str(plot_horiz))
            ax.set_ylabel(str(plot_vert))
            ax.set_title("Sketch of the Function")

            st.pyplot(fig, use_container_width=True)



        except Exception as e:
            st.error("Could not parse the function for graphing.")
            st.caption(str(e))
    except _StopSolving:
        pass
    return st.steps


def solve_analytical_geometry(question: str) -> list:
    """Solve a Grade 12 coordinate-geometry question (distance, midpoint,
    gradient, line equation) between two points. Ported from the
    Streamlit AI Tutor's Analytical Geometry branch, with one
    simplification: Streamlit let a learner override the two points
    (auto-detected from "(x,y)" pairs in the question text) via
    number_input widgets. This version has no such refinement step - it
    solves directly with whatever was detected (or the same defaults
    those widgets started from, A(1,2)/B(4,6), if nothing was found)."""
    st = StepRecorder()
    st.markdown("### 📏 Points, Distance, Gradient & Line Equation")

    coord_matches = re.findall(r"\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)", question)

    x1 = float(coord_matches[0][0]) if len(coord_matches) >= 1 else 1.0
    y1 = float(coord_matches[0][1]) if len(coord_matches) >= 1 else 2.0
    x2 = float(coord_matches[1][0]) if len(coord_matches) >= 2 else 4.0
    y2 = float(coord_matches[1][1]) if len(coord_matches) >= 2 else 6.0

    st.markdown(f"**Points:** $A({_fmt_num(x1)},{_fmt_num(y1)})$ and $B({_fmt_num(x2)},{_fmt_num(y2)})$")

    st.markdown("**Step 1: Distance**")
    st.latex(r"d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}")
    d = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    st.latex(rf"d=\sqrt{{({_fmt_num(x2)}-{_fmt_num(x1)})^2+({_fmt_num(y2)}-{_fmt_num(y1)})^2}}={round(d, 3)}")

    st.markdown("**Step 2: Midpoint**")
    st.latex(r"M=\left(\frac{x_1+x_2}{2},\frac{y_1+y_2}{2}\right)")
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    st.latex(rf"M=({_fmt_num(mx)},{_fmt_num(my)})")

    st.markdown("**Step 3: Gradient**")
    st.latex(r"m=\frac{y_2-y_1}{x_2-x_1}")
    if x2 != x1:
        m = (y2 - y1) / (x2 - x1)
        st.latex(rf"m=\frac{{{_fmt_num(y2)}-{_fmt_num(y1)}}}{{{_fmt_num(x2)}-{_fmt_num(x1)}}}={round(m, 3)}")

        st.markdown("**Step 4: Equation of the line** $AB$")
        st.latex(r"y-y_1=m(x-x_1)")
        c = y1 - m * x1
        sign = "+" if c >= 0 else "-"
        st.latex(rf"y={round(m,3)}x{sign}{round(abs(c),3)}")
    else:
        st.warning("The line through A and B is vertical (undefined gradient).")
        st.latex(rf"x={_fmt_num(x1)}")

    st.markdown("##### 📉 Plot")
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([x1, x2], [y1, y2], "o-", color="#2563eb", linewidth=2, markersize=8)
    ax.annotate(f"A({_fmt_num(x1)},{_fmt_num(y1)})", (x1, y1), textcoords="offset points", xytext=(8, 8))
    ax.annotate(f"B({_fmt_num(x2)},{_fmt_num(y2)})", (x2, y2), textcoords="offset points", xytext=(8, 8))
    ax.plot(mx, my, "rs")
    ax.annotate(f"M({_fmt_num(mx)},{_fmt_num(my)})", (mx, my), textcoords="offset points", xytext=(8, -12), color="red")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_aspect("equal", adjustable="datalim")
    st.pyplot(fig, use_container_width=True)

    return st.steps


def solve_trigonometry(question: str) -> list:
    """Solve a Grade 12 trigonometry question - either an equation to
    solve over an interval, or a plain angle to evaluate sin/cos/tan for.
    Ported from the Streamlit AI Tutor's Trigonometry branch, with one
    simplification: the ratio-calculator branch let a learner override
    the auto-detected angle via a number_input widget; this version uses
    the detected value (or the same 30° default) directly."""
    st = StepRecorder()
    st.markdown("### 📐 Trigonometry")

    q_lower = question.lower()
    is_equation = ("=" in question) and any(f in q_lower for f in ["sin", "cos", "tan"])

    if is_equation:
        try:
            eq_clean = question.replace("^", "**")

            domain_match = re.search(
                r"(-?\d+(?:\.\d+)?)\s*(?:<=|≤)\s*[a-zA-Zθ]+\s*(?:<=|≤)\s*(-?\d+(?:\.\d+)?)",
                eq_clean,
            )
            if domain_match:
                lo, hi = float(domain_match.group(1)), float(domain_match.group(2))
                eq_only = eq_clean[:domain_match.start()] + eq_clean[domain_match.end():]
            else:
                lo, hi = 0.0, 360.0
                eq_only = eq_clean

            eq_only = re.sub(r"(?i)\bsolve\b(\s+for\s+[a-zA-Z]+)?", "", eq_only)
            eq_only = re.sub(r"(?i)\bfor\b", "", eq_only)
            eq_only = eq_only.strip(" ,:")
            eq_only = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', eq_only)

            detected_vars = detect_variables(eq_only)
            var_name = detected_vars[0] if detected_vars else "x"
            xvar = sp.symbols(var_name)
            symbols_dict = {var_name: xvar}

            lhs_str, rhs_str = eq_only.split("=")
            lhs = safe_parse(lhs_str, symbols_dict)
            rhs = safe_parse(rhs_str, symbols_dict)

            st.markdown("**Step 1: Write the equation**")
            st.latex(sp.latex(sp.Eq(lhs, rhs)))

            # Trig functions need radians internally, but NSC
            # questions are always posed in degrees — substituting
            # x -> x*pi/180 lets sympy solve/period-detect directly
            # in "x = degrees" units, so no extra conversion needed
            # on the solutions it returns.
            expr_deg = lhs - rhs
            expr_rad = expr_deg.subs(xvar, xvar * sp.pi / 180)

            base_solutions = [s for s in sp.solve(sp.Eq(expr_rad, 0), xvar) if s.is_real]
            period = sp.periodicity(expr_rad, xvar)
            period_deg = float(period) if period else 360.0

            st.markdown(
                f"**Step 2: Find all solutions in the interval** "
                f"${lo:g}^\\circ \\le {var_name} \\le {hi:g}^\\circ$ "
                f"(period $={period_deg:g}^\\circ$)"
            )

            all_solutions = set()
            for base in base_solutions:
                base_deg = float(base)
                k = int(np.floor((lo - base_deg) / period_deg)) - 1
                while True:
                    candidate = base_deg + k * period_deg
                    if candidate > hi + 1e-6:
                        break
                    if candidate >= lo - 1e-6:
                        all_solutions.add(round(candidate, 2))
                    k += 1

            if all_solutions:
                sol_list = sorted(all_solutions)
                for s in sol_list:
                    st.latex(rf"{var_name}={s:g}^\circ")
                st.success("🏁 Final Answer: " + ", ".join(f"{s:g}°" for s in sol_list))
            else:
                st.error("No solutions found in the given interval.")

        except Exception as e:
            st.error("Could not solve this trigonometric equation.")
            st.caption(str(e))

    else:
        st.markdown("#### Trigonometric Ratio Calculator")
        angle_match = re.search(r"-?\d+\.?\d*", question)
        angle = float(angle_match.group()) if angle_match else 30.0
        rad = np.deg2rad(angle)

        st.latex(rf"\sin({angle:g}^\circ) = {round(np.sin(rad),3)}")
        st.latex(rf"\cos({angle:g}^\circ) = {round(np.cos(rad),3)}")
        st.latex(rf"\tan({angle:g}^\circ) = {round(np.tan(rad),3)}")

        st.markdown("##### 🔵 Unit Circle")
        fig, ax = plt.subplots(figsize=(4, 4))
        theta = np.linspace(0, 2 * np.pi, 200)
        ax.plot(np.cos(theta), np.sin(theta), color="#94a3b8")
        ax.plot([0, np.cos(rad)], [0, np.sin(rad)], "o-", color="#2563eb", linewidth=2)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_aspect("equal")
        ax.set_title(f"{angle:g}° on the unit circle")
        st.pyplot(fig, use_container_width=True)

    return st.steps


def solve_statistics(question: str) -> list:
    """Solve a Grade 12 descriptive-statistics question (mean, median,
    mode, variance, five-number summary, box plot) for a comma-separated
    list of numbers. Ported from the Streamlit AI Tutor's Statistics
    branch - the data IS the question text there (a text_input just let
    a learner tweak it before solving), so this version reads it
    directly from `question`."""
    st = StepRecorder()
    st.markdown("### 📊 Descriptive Statistics")

    data = question if re.search(r"\d", question) else "2,4,6,8,10,12"
    values = sorted(float(v) for v in re.findall(r"-?\d+\.?\d*", data))

    if len(values) < 2:
        st.warning("Please enter at least two numbers, separated by commas.")
    else:
        n_vals = len(values)
        mean = float(np.mean(values))
        median = float(np.median(values))
        counts = {v: values.count(v) for v in set(values)}
        max_count = max(counts.values())
        modes = sorted(v for v, c in counts.items() if c == max_count) if max_count > 1 else []
        variance = float(np.var(values))
        std_dev = float(np.std(values))
        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))

        def _fmt(v):
            return str(int(v)) if float(v).is_integer() else f"{v:.4g}"

        st.markdown("**Step 1: Arrange the data in ascending order**")
        st.latex(",\;".join(_fmt(v) for v in values))

        st.markdown("**Step 2: Mean**")
        st.latex(r"\bar{x}=\frac{\sum x}{n}")
        st.latex(rf"\bar{{x}}=\frac{{{_fmt(sum(values))}}}{{{n_vals}}}={_fmt(mean)}")

        st.markdown("**Step 3: Median**")
        st.latex(rf"\text{{Median}}={_fmt(median)}")

        st.markdown("**Step 4: Mode**")
        if modes:
            st.latex(r"\text{Mode}=" + ",\;".join(_fmt(m) for m in modes))
        else:
            st.latex(r"\text{No mode — every value occurs once}")

        st.markdown("**Step 5: Range**")
        st.latex(rf"\text{{Range}}={_fmt(max(values))}-{_fmt(min(values))}={_fmt(max(values)-min(values))}")

        st.markdown("**Step 6: Variance and Standard Deviation**")
        st.latex(r"\sigma^2=\frac{\sum(x-\bar{x})^2}{n}")
        st.latex(rf"\sigma^2={_fmt(variance)}")
        st.latex(r"\sigma=\sqrt{\sigma^2}")
        st.latex(rf"\sigma={_fmt(std_dev)}")

        st.markdown("**Step 7: Five-number summary**")
        st.latex(
            rf"\text{{Min}}={_fmt(min(values))},\;Q_1={_fmt(q1)},\;"
            rf"\text{{Median}}={_fmt(median)},\;Q_3={_fmt(q3)},\;\text{{Max}}={_fmt(max(values))}"
        )

        st.markdown("##### 📦 Box-and-Whisker Diagram")
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.boxplot(values, vert=False, widths=0.6, patch_artist=True,
                   boxprops=dict(facecolor="#93c5fd"))
        ax.set_yticks([])
        ax.set_xlabel("Value")
        st.pyplot(fig, use_container_width=True)

    return st.steps
# =====================================================
# PROBABILITY — WORD PROBLEM INTERPRETER
# =====================================================
def _dice_favourable(desc, faces=6):
    """Given a phrase like 'greater than 4', 'even', 'a prime number',
    return the set of face values on a `faces`-sided die that satisfy it."""
    desc = desc.lower()
    outcomes = set(range(1, faces + 1))
    m = re.search(r"greater than (\d+)", desc)
    if m:
        return {o for o in outcomes if o > int(m.group(1))}
    m = re.search(r"at least (\d+)", desc)
    if m:
        return {o for o in outcomes if o >= int(m.group(1))}
    m = re.search(r"less than (\d+)", desc)
    if m:
        return {o for o in outcomes if o < int(m.group(1))}
    m = re.search(r"at most (\d+)", desc)
    if m:
        return {o for o in outcomes if o <= int(m.group(1))}
    if "even" in desc:
        return {o for o in outcomes if o % 2 == 0}
    if "odd" in desc:
        return {o for o in outcomes if o % 2 == 1}
    if "prime" in desc:
        return {o for o in outcomes if o in (2, 3, 5, 7, 11, 13) and o <= faces}
    m = re.search(r"\b(\d+)\b", desc)
    if m and int(m.group(1)) in outcomes:
        return {int(m.group(1))}
    return outcomes

BAG_ITEM_NOUNS = [
    "balls", "marbles", "counters", "sweets", "cards", "discs", "tiles",
    "pens", "chips", "apples", "oranges", "tickets", "sweets", "beads",
]

def parse_bag_of_items(q):
    """Detect 'A bag contains 5 red and 3 blue balls...' style questions.
    Returns (counts_by_label dict, target_label) or (None, None). The list
    of colours/labels usually only has the noun ("balls") once, at the very
    end (e.g. "5 red and 3 blue balls"), so we first locate that noun and
    then pull every "<number> <label>" pair out of the list before it."""
    list_pattern = (
        r"((?:\d+\s+[a-zA-Z]+\s*,?\s*(?:and)?\s*)+)(?:" + "|".join(BAG_ITEM_NOUNS) + r")"
    )
    list_match = re.search(list_pattern, q)
    if not list_match:
        return None, None
    matches = re.findall(r"(\d+)\s+([a-zA-Z]+)", list_match.group(1))
    if not matches:
        return None, None
    counts = {label: int(n) for n, label in matches}

    target = None
    m = re.search(r"(?:drawing|selecting|choosing|picking|getting|obtaining)\s+(?:a|an)?\s*([a-zA-Z]+)", q)
    if m and m.group(1) in counts:
        target = m.group(1)
    if target is None:
        m = re.search(r"\bis\s+([a-zA-Z]+)\b", q)
        if m and m.group(1) in counts:
            target = m.group(1)
    if target is None and counts:
        target = list(counts.keys())[-1]
    return counts, target

def interpret_probability_text(question):
    """Best-effort natural-language interpretation of a Grade 12 probability
    question. Returns a dict describing how to solve + display it, or None
    if the text isn't recognised (caller falls back to manual entry)."""
    q = question.lower().strip()

    # ---- 1. Symbolic P(A)/P(B) rules (mutually exclusive / independent / complement) ----
    pa_match = re.search(r"p\(a\)\s*=\s*(\d+(?:\.\d+)?)", q)
    pb_match = re.search(r"p\(b\)\s*=\s*(\d+(?:\.\d+)?)", q)
    if pa_match and pb_match:
        pa, pb = float(pa_match.group(1)), float(pb_match.group(1))
        p_and_match = re.search(r"p\(a\s*(?:and|∩)\s*b\)\s*=\s*(\d+(?:\.\d+)?)", q)
        mutually_exclusive = "mutually exclusive" in q
        independent = "independent" in q

        wants_or = bool(re.search(r"p\(a\s*(?:or|∪)\s*b\)", q)) or "or b" in q
        wants_and = bool(re.search(r"find\s+p\(a\s*(?:and|∩)\s*b\)", q))
        wants_not_a = bool(re.search(r"p\(not\s*a\)|p\(a'\)|complement", q))

        if wants_not_a:
            return {"kind": "symbolic", "formula": r"P(A')=1-P(A)",
                    "steps": [rf"P(A')=1-{pa}"], "answer": 1 - pa}
        if wants_and and independent:
            return {"kind": "symbolic", "formula": r"P(A \text{ and } B)=P(A)\times P(B)",
                    "steps": [rf"P(A\text{{ and }}B)={pa}\times{pb}"], "answer": pa * pb}
        if wants_or and mutually_exclusive:
            return {"kind": "symbolic", "formula": r"P(A \text{ or } B)=P(A)+P(B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}"], "answer": pa + pb}
        if wants_or and p_and_match:
            p_and = float(p_and_match.group(1))
            return {"kind": "symbolic",
                    "formula": r"P(A \text{ or } B)=P(A)+P(B)-P(A \text{ and } B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}-{p_and}"], "answer": pa + pb - p_and}
        if wants_or:
            return {"kind": "symbolic", "formula": r"P(A \text{ or } B)=P(A)+P(B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}"], "answer": pa + pb}

    # ---- 2. Bag / box of labelled items ----
    counts, target = parse_bag_of_items(q)
    if counts and target:
        total = sum(counts.values())
        return {
            "kind": "bag", "counts": counts, "target": target,
            "favourable": counts[target], "total": total,
            "answer": counts[target] / total,
        }

    # ---- 3. Combined two-stage independent events (die & coin, coin & coin, die & die) ----
    has_die = "die" in q or "dice" in q
    has_coin = "coin" in q

    if has_die and has_coin and (" and " in q):
        clauses = q.split(" and ")
        die_fav = _dice_favourable(clauses[-2] if len(clauses) > 1 else q)
        coin_target = "head" if "head" in q else ("tail" if "tail" in q else None)
        p_die = len(die_fav) / 6
        p_coin = 0.5 if coin_target else 1.0
        answer = p_die * p_coin
        return {
            "kind": "tree", "stages": [("Die", 6, len(die_fav)), ("Coin", 2, 1 if coin_target else 2)],
            "steps": [
                rf"P(\text{{die event}})=\frac{{{len(die_fav)}}}{{6}}",
                rf"P(\text{{coin event}})=\frac{{1}}{{2}}" if coin_target else r"P(\text{coin event})=1",
                rf"P(\text{{die}}\;\text{{and}}\;\text{{coin}})=\frac{{{len(die_fav)}}}{{6}}\times\frac12",
            ],
            "answer": answer,
        }

    # ---- 4. Single die ----
    if has_die:
        fav = _dice_favourable(q)
        return {
            "kind": "die", "favourable_set": fav, "faces": 6,
            "answer": len(fav) / 6,
        }

    # ---- 5. Single/double coin ----
    if has_coin:
        two_coins = bool(re.search(r"two coins|2 coins|both coins", q))
        if two_coins:
            outcomes = ["HH", "HT", "TH", "TT"]
            if "at least one head" in q:
                fav = [o for o in outcomes if "H" in o]
            elif "at least one tail" in q:
                fav = [o for o in outcomes if "T" in o]
            elif "two heads" in q or "both heads" in q:
                fav = ["HH"]
            elif "two tails" in q or "both tails" in q:
                fav = ["TT"]
            else:
                fav = outcomes
            return {"kind": "coins", "outcomes": outcomes, "favourable": fav,
                    "answer": len(fav) / len(outcomes)}
        else:
            return {"kind": "coin", "answer": 0.5}

    return None

def draw_tree_diagram(stage_labels):
    """Draw a simple two-stage probability tree diagram, e.g. for
    [("Die", ["1-6 outcomes"]), ("Coin", ["H", "T"])]."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.axis("off")
    ax.plot(0, 0.5, "ko")
    stage1_name, stage1_opts = stage_labels[0]
    stage2_name, stage2_opts = stage_labels[1]
    n1 = len(stage1_opts)
    y1_positions = np.linspace(0.1, 0.9, n1)
    for y1, opt1 in zip(y1_positions, stage1_opts):
        ax.plot([0, 1], [0.5, y1], "b-", linewidth=1)
        ax.text(1.05, y1, str(opt1), va="center", fontsize=9)
        n2 = len(stage2_opts)
        y2_positions = np.linspace(y1 - 0.08, y1 + 0.08, n2) if n2 > 1 else [y1]
        for y2, opt2 in zip(y2_positions, stage2_opts):
            ax.plot([1.3, 2], [y1, y2], "g-", linewidth=1)
            ax.text(2.05, y2, str(opt2), va="center", fontsize=8)
    ax.set_xlim(-0.2, 3)
    ax.set_ylim(0, 1)
    ax.set_title(f"{stage1_name} → {stage2_name}", fontsize=10)
    return fig


def solve_probability(question: str) -> list:
    """Solve a Grade 12 probability question via best-effort natural-
    language interpretation (dice, coins, bags of items, P(A)/P(B)
    symbolic rules). Ported from the Streamlit AI Tutor's Probability
    branch, with one simplification: when the text can't be interpreted
    at all, Streamlit let a learner manually enter favourable/total
    outcomes via number_input widgets; this version just reports 1/6
    (the same defaults those widgets started from) in that fallback case."""
    st = StepRecorder()
    st.markdown("### 🎲 Probability")

    result = interpret_probability_text(question)

    if result is None:
        st.info(
            "Couldn't automatically interpret this as a word problem — "
            "try phrasing like the examples shown above (e.g. dice, coins, "
            "or a bag of coloured balls). Showing a generic 1-in-6 example below."
        )
        favourable, total = 1, 6
        prob = favourable / total
        st.latex(r"P(E)=\frac{n(E)}{n(S)}")
        st.latex(rf"P(E)={round(prob,3)}")

    else:
        kind = result["kind"]

        if kind == "symbolic":
            st.markdown("**Using the appropriate probability rule:**")
            st.latex(result["formula"])
            for step in result["steps"]:
                st.latex(step)
            st.success(f"🏁 P = {result['answer']:.4g}")

        elif kind == "bag":
            st.markdown("**Step 1: Identify the sample space**")
            counts_str = ", ".join(f"{v} {k}" for k, v in result["counts"].items())
            st.write(f"The bag/box contains: {counts_str} (total = {result['total']}).")
            st.markdown(f"**Step 2: Favourable outcomes — {result['target']}**")
            st.latex(r"P(E)=\frac{n(E)}{n(S)}")
            st.latex(rf"P(\text{{{result['target']}}})=\frac{{{result['favourable']}}}{{{result['total']}}}={result['answer']:.4g}")
            st.success(f"🏁 P({result['target']}) = {result['answer']:.4g}")

            fig, ax = plt.subplots(figsize=(5, 3))
            ax.bar(list(result["counts"].keys()), list(result["counts"].values()), color="#60a5fa")
            ax.set_ylabel("Count")
            ax.set_title("Contents of the bag/box")
            st.pyplot(fig, use_container_width=True)

        elif kind == "tree":
            st.markdown("**Step 1: Draw a tree diagram for the two independent stages**")
            st.latex(r"P(A \text{ and } B) = P(A)\times P(B)")
            for step in result["steps"]:
                st.latex(step)
            st.success(f"🏁 P = {result['answer']:.4g}")

            fig = draw_tree_diagram([("Die", list(range(1, 7))), ("Coin", ["H", "T"])])
            st.pyplot(fig, use_container_width=True)

        elif kind == "die":
            fav = sorted(result["favourable_set"])
            st.markdown("**Step 1: Sample space of a die**")
            st.latex(r"S=\{1,2,3,4,5,6\}")
            st.markdown("**Step 2: Favourable outcomes**")
            st.latex(r"E=\{" + ",".join(map(str, fav)) + r"\}" if fav else r"E=\varnothing")
            st.latex(r"P(E)=\frac{n(E)}{n(S)}")
            st.latex(rf"P(E)=\frac{{{len(fav)}}}{{6}}={result['answer']:.4g}")
            st.success(f"🏁 P(E) = {result['answer']:.4g}")

        elif kind == "coins":
            st.markdown("**Step 1: Sample space of two coins**")
            st.latex(r"S=\{HH,HT,TH,TT\}")
            st.markdown("**Step 2: Favourable outcomes**")
            st.latex(r"E=\{" + ",".join(result["favourable"]) + r"\}")
            st.latex(rf"P(E)=\frac{{{len(result['favourable'])}}}{{4}}={result['answer']:.4g}")
            st.success(f"🏁 P(E) = {result['answer']:.4g}")

        else:  # single coin
            st.markdown("**Sample space:** $S=\\{H,T\\}$")
            st.latex(r"P(E)=\frac12=0.5")
            st.success("🏁 P(E) = 0.5")

    return st.steps

# =====================================================
# EUCLIDEAN GEOMETRY — CIRCLE THEOREMS
# =====================================================
def solve_euclidean_geometry(question):
    """Recognise the handful of Grade 12 circle-theorem question shapes and
    apply the matching theorem. Returns None if nothing matches (caller
    shows the theorem reference instead)."""
    q = question.lower()

    if "centre" in q and "circumference" in q:
        m_centre = re.search(r"centre\D{0,15}?(\d+(?:\.\d+)?)", q)
        m_circ = re.search(r"circumference\D{0,15}?(\d+(?:\.\d+)?)", q)
        if m_centre:
            v = float(m_centre.group(1))
            return {"kind": "centre_circumference", "given": "centre", "value": v, "answer": v / 2}
        if m_circ:
            v = float(m_circ.group(1))
            return {"kind": "centre_circumference", "given": "circumference", "value": v, "answer": v * 2}

    if "cyclic quadrilateral" in q:
        m = re.search(r"(\d+(?:\.\d+)?)", q)
        if m:
            v = float(m.group(1))
            return {"kind": "cyclic_quad", "value": v, "answer": 180 - v}

    if "tangent" in q and ("chord" in q or "alternate segment" in q):
        m = re.search(r"(\d+(?:\.\d+)?)", q)
        if m:
            v = float(m.group(1))
            return {"kind": "tan_chord", "value": v, "answer": v}

    return None

def draw_euclidean_diagram(kind):
    """Illustrative (not-to-scale) circle-theorem schematic matching the
    detected theorem type."""
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    circle = plt.Circle((0, 0), 1, fill=False, color="#2563eb", linewidth=2)
    ax.add_patch(circle)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.4, 1.4)
    ax.set_aspect("equal")
    ax.axis("off")

    if kind == "centre_circumference":
        O = (0, 0)
        A = (np.cos(np.radians(200)), np.sin(np.radians(200)))
        B = (np.cos(np.radians(-20)), np.sin(np.radians(-20)))
        C = (np.cos(np.radians(90)), np.sin(np.radians(90)))
        ax.plot(*O, "ko"); ax.text(0.05, 0.05, "O")
        for P, label in [(A, "A"), (B, "B"), (C, "C")]:
            ax.plot(*P, "ko")
            ax.text(P[0] * 1.1, P[1] * 1.1, label, ha="center")
        ax.plot([O[0], A[0]], [O[1], A[1]], "b-")
        ax.plot([O[0], B[0]], [O[1], B[1]], "b-")
        ax.plot([C[0], A[0]], [C[1], A[1]], "g-")
        ax.plot([C[0], B[0]], [C[1], B[1]], "g-")
        ax.set_title("Angle at centre = 2 × angle at circumference", fontsize=9)

    elif kind == "cyclic_quad":
        pts = {name: (np.cos(np.radians(a)), np.sin(np.radians(a)))
               for name, a in [("A", 100), ("B", 20), ("C", -80), ("D", 190)]}
        order = ["A", "B", "C", "D"]
        for i in range(4):
            p1, p2 = pts[order[i]], pts[order[(i + 1) % 4]]
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], "g-")
        for name, p in pts.items():
            ax.plot(*p, "ko")
            ax.text(p[0] * 1.1, p[1] * 1.1, name, ha="center")
        ax.set_title("Cyclic quadrilateral: opposite angles are supplementary", fontsize=9)

    else:  # tan_chord
        T = (np.cos(np.radians(-90)), np.sin(np.radians(-90)))
        P = (np.cos(np.radians(140)), np.sin(np.radians(140)))
        tangent_dir = np.array([-np.sin(np.radians(-90)), np.cos(np.radians(-90))])
        t1 = np.array(T) - 0.8 * tangent_dir
        t2 = np.array(T) + 0.8 * tangent_dir
        ax.plot([t1[0], t2[0]], [t1[1], t2[1]], "r-", label="Tangent")
        ax.plot([T[0], P[0]], [T[1], P[1]], "g-", label="Chord")
        ax.plot(*T, "ko"); ax.text(T[0], T[1] - 0.12, "T", ha="center")
        ax.plot(*P, "ko"); ax.text(P[0] * 1.1, P[1] * 1.1, "P", ha="center")
        ax.set_title("Tan-chord: angle = angle in alternate segment", fontsize=9)

    return fig


def solve_euclidean_geometry_topic(question: str) -> list:
    """Solve a Grade 12 circle-theorem question (angle at centre/
    circumference, cyclic quadrilateral, tangent-chord) and show a
    schematic diagram + quick-reference theorem list. Ported from the
    Streamlit AI Tutor's Euclidean Geometry branch. Named "_topic" to
    avoid clashing with solve_euclidean_geometry(question) above, which
    is pure detection logic (returns a dict or None) with no StepRecorder
    involvement - this function is the UI-facing wrapper around it."""
    st = StepRecorder()
    try:
        st.markdown("### ⚪ Euclidean Geometry")

        result = solve_euclidean_geometry(question)

        if result is None:
            st.info(
                "Type a question using keywords like 'angle at centre', "
                "'angle at circumference', 'cyclic quadrilateral', or "
                "'tangent chord' — or browse the theorem reference below."
            )
        else:
            kind = result["kind"]
            if kind == "centre_circumference":
                st.markdown("**Theorem:** The angle at the centre is twice the angle at the circumference subtended by the same arc.")
                st.latex(r"\hat{O}=2\hat{C}")
                if result["given"] == "centre":
                    st.latex(rf"\hat{{C}}=\frac{{{result['value']:g}^\circ}}{{2}}={result['answer']:g}^\circ")
                else:
                    st.latex(rf"\hat{{O}}=2\times{result['value']:g}^\circ={result['answer']:g}^\circ")
            elif kind == "cyclic_quad":
                st.markdown("**Theorem:** Opposite angles of a cyclic quadrilateral are supplementary.")
                st.latex(r"\hat{A}+\hat{C}=180^\circ")
                st.latex(rf"\hat{{C}}=180^\circ-{result['value']:g}^\circ={result['answer']:g}^\circ")
            else:
                st.markdown("**Theorem (tan-chord):** The angle between a tangent and a chord equals the angle in the alternate segment.")
                st.latex(rf"\text{{Angle in alternate segment}}={result['answer']:g}^\circ")

            st.success(f"🏁 Answer: {result['answer']:g}°")
            fig = draw_euclidean_diagram(kind)
            st.pyplot(fig, use_container_width=True)

        with st.expander("📖 Circle Theorem Quick Reference"):
            st.latex(r"\hat{O}=2\hat{C}\quad\text{angle at centre}=2\times\text{angle at circumference}")
            st.latex(r"\hat{A}+\hat{C}=180^\circ\quad\text{opposite angles of a cyclic quadrilateral}")
            st.latex(r"\text{Angles subtended by the same chord/arc in the same segment are equal}")
            st.latex(r"\text{Tangent-chord angle}=\text{angle in the alternate segment}")
            st.latex(r"\text{A line from the centre perpendicular to a chord bisects the chord}")

    except Exception as e:
        st.error("Invalid expression or input")
        st.caption(str(e))
    except _StopSolving:
        pass
    return st.steps
