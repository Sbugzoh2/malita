"""
Malita (Pty) Ltd — Practice Questions data + grading.

Shared by app.py (Streamlit) and api_server.py (FastAPI, used by the
native app) so both apps offer the exact same question bank.
"""

import re


def _extract_numbers(s):
    """Pull every number (incl. negatives/decimals) out of a string,
    ignoring LaTeX/units around it — used to loosely grade practice
    answers without needing full symbolic equivalence checking."""
    return sorted(round(float(n), 4) for n in re.findall(r"-?\d+\.?\d*", s))

def check_practice_answer(user_answer, expected_latex):
    """Best-effort grading: compares the multiset of numbers in the
    learner's typed answer against the expected answer. Returns True/False,
    or None if the expected answer has no numbers to compare against."""
    if not user_answer.strip():
        return None
    expected_nums = _extract_numbers(expected_latex)
    if not expected_nums:
        return None
    return _extract_numbers(user_answer) == expected_nums

# =====================================================
# PRACTICE QUESTIONS (FULL – PAPER 1 & 2)
# =====================================================
practice_data = {
"Paper 1": {
"Algebra": [
{"question": r"\text{Solve for } x:\; x^2 - 5x + 6 = 0",
 "hint": r"\text{Try to factorise into two brackets that multiply to give } 6 \text{ and add to give } {-5}.",
 "solution_steps":[
 {"explain": "Factorise the trinomial into two brackets that multiply out to give the original expression.", "latex": r"(x-2)(x-3)=0 \quad (1 Mark)"},
 {"explain": "Apply the zero product law: if two factors multiply to give zero, at least one of them must itself be zero.", "latex": r"x-2=0 \;\text{or}\; x-3=0 \quad (1 Mark)"},
 {"explain": "Solve each of the two simple linear equations for x.", "latex": r"x=2 \;\text{or}\; x=3 \quad (1 Mark)"},
 ],
 "final_answer": r"x=2 \;\text{or}\; x=3",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; 3x^2=12",
 "hint": r"\text{Divide both sides by 3 first, then take the square root of both sides.}",
 "solution_steps":[
 {"explain": "Divide both sides by 3 to isolate x².", "latex": r"x^2=4 \quad (1 Mark)"},
 {"explain": "Take the square root of both sides — remember a square root always gives BOTH a positive and a negative answer.", "latex": r"x=\pm2 \quad (2 Marks)"},
 ],
 "final_answer": r"x=\pm2",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; x^2 - 2x - 4 = 0 \;(\text{correct to 2 decimal places})",
 "hint": r"\text{This does not factorise nicely — use the quadratic formula.}",
 "solution_steps":[
 {"explain": "Identify the coefficients a, b and c so they can be substituted into the quadratic formula.", "latex": r"a=1,\;b=-2,\;c=-4 \quad (1 Mark)"},
 {"explain": "Substitute a, b and c into the quadratic formula.", "latex": r"x=\frac{-(-2)\pm\sqrt{(-2)^2-4(1)(-4)}}{2(1)} \quad (2 Marks)"},
 {"explain": "Simplify the numbers inside and outside the square root.", "latex": r"x=\frac{2\pm\sqrt{20}}{2} \quad (1 Mark)"},
 {"explain": "Use a calculator to evaluate both the + and − roots, rounding each to 2 decimal places.", "latex": r"x=3.24 \;\text{or}\; x=-1.24 \quad (2 Marks)"},
 ],
 "final_answer": r"x=3.24 \;\text{or}\; x=-1.24",
 "Marks":6,"difficulty":"Medium"},
{"question": r"\text{Solve for } x:\; 2x^2 + 3x - 5 \le 0",
 "hint": r"\text{Find the critical values first, then decide which region satisfies the inequality using a number line.}",
 "solution_steps":[
 {"explain": "Factorise the quadratic expression, exactly as you would for an equation.", "latex": r"(2x+5)(x-1)\le 0 \quad (2 Marks)"},
 {"explain": "Set each factor equal to zero to find the critical values — the points where the expression changes sign.", "latex": r"x=-\frac{5}{2} \;\text{or}\; x=1 \quad (1 Mark)"},
 {"explain": "Since the parabola opens upward (positive x² coefficient), it is ≤0 BETWEEN the two critical values.", "latex": r"-\frac{5}{2}\le x\le 1 \quad (2 Marks)"},
 ],
 "final_answer": r"-\frac{5}{2}\le x\le 1",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Solve simultaneously for } x \text{ and } y:\; x+y=10,\; 2x-y=2",
 "hint": r"\text{Add the two equations together to eliminate } y.",
 "solution_steps":[
 {"explain": "Write down the first equation and label it (1) so it can be referred back to.", "latex": r"x+y=10 \quad \text{...(1)}"},
 {"explain": "Write down the second equation and label it (2).", "latex": r"2x-y=2 \quad \text{...(2)}"},
 {"explain": "Add equation (1) and (2) together — the +y and −y terms cancel out, leaving only x.", "latex": r"\text{Adding (1) and (2)}: 3x=12 \quad (2 Marks)"},
 {"explain": "Divide both sides by 3 to solve for x.", "latex": r"x=4 \quad (1 Mark)"},
 {"explain": "Substitute x=4 back into equation (1) to solve for y.", "latex": r"y=10-4=6 \quad (2 Marks)"},
 ],
 "final_answer": r"x=4,\; y=6",
 "Marks":5,"difficulty":"Medium"},
],
"Sequences": [
{"question": r"\text{Find the 10th term of } 3,7,11,\dots",
 "hint": r"\text{This is arithmetic — find the common difference } d \text{ first.}",
 "solution_steps":[
 {"explain": "Identify the first term a, and the common difference d (each term minus the one before it).", "latex": r"a=3,\; d=4 \quad (1 Mark)"},
 {"explain": "Write down the general term formula for an arithmetic sequence.", "latex": r"T_n=a+(n-1)d \quad (1 Mark)"},
 {"explain": "Substitute n=10, a and d into the formula and simplify.", "latex": r"T_{10}=39 \quad (1 Mark)"},
 ],
 "final_answer": r"39",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the 8th term of the geometric sequence } 2,6,18,\dots",
 "hint": r"\text{Find the common ratio } r=\frac{T_2}{T_1} \text{ then use } T_n=ar^{n-1}.",
 "solution_steps":[
 {"explain": "Identify the first term a, and the common ratio r (each term divided by the one before it).", "latex": r"a=2,\; r=3 \quad (1 Mark)"},
 {"explain": "Write down the general term formula for a geometric sequence.", "latex": r"T_n=ar^{n-1} \quad (1 Mark)"},
 {"explain": "Substitute n=8, a and r into the formula and simplify.", "latex": r"T_8=2(3)^7=4374 \quad (2 Marks)"},
 ],
 "final_answer": r"4374",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Calculate the sum of the first 15 terms of } 5,9,13,\dots",
 "hint": r"\text{Use } S_n=\frac{n}{2}[2a+(n-1)d].",
 "solution_steps":[
 {"explain": "Identify a, d, and the number of terms n we're summing.", "latex": r"a=5,\; d=4,\; n=15 \quad (1 Mark)"},
 {"explain": "Substitute these values into the arithmetic series sum formula.", "latex": r"S_{15}=\frac{15}{2}[2(5)+(14)(4)] \quad (2 Marks)"},
 {"explain": "Simplify the bracket first, then multiply to get the final total.", "latex": r"S_{15}=\frac{15}{2}(66)=495 \quad (2 Marks)"},
 ],
 "final_answer": r"495",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Determine the sum to infinity of } 8,4,2,1,\dots",
 "hint": r"\text{Since } |r|<1 \text{, use } S_\infty=\frac{a}{1-r}.",
 "solution_steps":[
 {"explain": "Identify a and r. Since |r|<1, the terms shrink towards zero and a sum to infinity exists.", "latex": r"a=8,\; r=\frac12 \quad (1 Mark)"},
 {"explain": "Substitute a and r into the sum-to-infinity formula.", "latex": r"S_\infty=\frac{a}{1-r}=\frac{8}{1-\frac12} \quad (2 Marks)"},
 {"explain": "Simplify the fraction to get the final answer.", "latex": r"S_\infty=16 \quad (1 Mark)"},
 ],
 "final_answer": r"16",
 "Marks":4,"difficulty":"Medium"},
],
"Financial Mathematics": [
{"question": r"\text{Find } A \text{ if } P=1000,\; i=10\%,\; n=2 \text{ (compound interest)}",
 "hint": r"\text{Use the compound growth formula } A=P(1+i)^n.",
 "solution_steps":[
 {"explain": "Write down the compound growth formula (interest earns interest each period).", "latex": r"A=P(1+i)^n \quad (1 Mark)"},
 {"explain": "Substitute P, i (as a decimal) and n, then evaluate.", "latex": r"A=1000(1.1)^2=1210 \quad (2 Marks)"},
 ],
 "final_answer": r"R1210",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{R5000 is invested at 8\% p.a. simple interest for 3 years. Find the accumulated amount.}",
 "hint": r"\text{Simple interest uses } A=P(1+ni), \text{ not the power formula.}",
 "solution_steps":[
 {"explain": "Write down the simple interest formula — unlike compound interest, each year's interest is calculated only on the ORIGINAL principal, not on previous interest.", "latex": r"A=P(1+ni) \quad (1 Mark)"},
 {"explain": "Substitute P=5000, n=3 years and i=0.08.", "latex": r"A=5000(1+3\times0.08) \quad (2 Marks)"},
 {"explain": "Simplify inside the brackets, then multiply out.", "latex": r"A=5000(1.24)=6200 \quad (1 Mark)"},
 ],
 "final_answer": r"R6200",
 "Marks":4,"difficulty":"Easy"},
{"question": r"\text{A car costing R240 000 depreciates on the reducing-balance method at 12\% p.a. Find its value after 5 years.}",
 "hint": r"\text{Reducing balance depreciation uses } A=P(1-i)^n.",
 "solution_steps":[
 {"explain": "Write down the reducing-balance depreciation formula — the value drops by the same PERCENTAGE each year, so it's a decay version of the compound growth formula (minus instead of plus).", "latex": r"A=P(1-i)^n \quad (1 Mark)"},
 {"explain": "Substitute P=240000, i=0.12 and n=5.", "latex": r"A=240000(1-0.12)^5 \quad (2 Marks)"},
 {"explain": "Simplify inside the brackets first, then raise to the power of 5 and multiply.", "latex": r"A=240000(0.88)^5\approx126934.61 \quad (2 Marks)"},
 ],
 "final_answer": r"\approx R126\,934.61",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Thabo saves R800 at the end of every month into an account earning 9\% p.a. compounded monthly for 4 years. Find the future value.}",
 "hint": r"\text{This is an ordinary annuity — use } F=\frac{x[(1+i)^n-1]}{i} \text{ with monthly } i \text{ and } n.",
 "solution_steps":[
 {"explain": "Since deposits are monthly, convert the annual rate and term into MONTHLY units: divide the rate by 12, and multiply the years by 12.", "latex": r"x=800,\; i=\frac{0.09}{12}=0.0075,\; n=4\times12=48 \quad (2 Marks)"},
 {"explain": "Write down the future value annuity formula for a series of equal regular deposits.", "latex": r"F=\frac{x[(1+i)^n-1]}{i} \quad (1 Mark)"},
 {"explain": "Substitute x, i and n, then evaluate with a calculator.", "latex": r"F=\frac{800[(1.0075)^{48}-1]}{0.0075}\approx45699.94 \quad (3 Marks)"},
 ],
 "final_answer": r"\approx R45\,699.94",
 "Marks":6,"difficulty":"Hard"},
],
"Calculus": [
{"question": r"\text{Differentiate } f(x)=3x^2",
 "hint": r"\text{Use the power rule: bring the exponent down and reduce it by 1.}",
 "solution_steps":[
 {"explain": "Use the power rule: multiply the coefficient by the exponent, then reduce the exponent by 1.", "latex": r"\frac{d}{dx}(3x^2)=6x \quad (3 Marks)"},
 ],
 "final_answer": r"6x",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine } f'(x) \text{ if } f(x)=2x^3-5x^2+4",
 "hint": r"\text{Differentiate each term separately using the power rule.}",
 "solution_steps":[
 {"explain": "Differentiate each term one at a time using the power rule; the constant term (4) disappears since the derivative of a constant is 0.", "latex": r"f'(x)=6x^2-10x \quad (3 Marks)"},
 ],
 "final_answer": r"f'(x)=6x^2-10x",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Use first principles to find } f'(x) \text{ if } f(x)=x^2",
 "hint": r"\text{Use } f'(x)=\lim_{h\to0}\frac{f(x+h)-f(x)}{h}.",
 "solution_steps":[
 {"explain": "Write down the first-principles definition of the derivative, and substitute f(x+h) and f(x).", "latex": r"f'(x)=\lim_{h\to0}\frac{(x+h)^2-x^2}{h} \quad (2 Marks)"},
 {"explain": "Expand (x+h)² and simplify the numerator — the x² terms cancel out.", "latex": r"=\lim_{h\to0}\frac{2xh+h^2}{h} \quad (2 Marks)"},
 {"explain": "Divide every term in the numerator by h, then let h→0 (h simply disappears).", "latex": r"=\lim_{h\to0}(2x+h)=2x \quad (2 Marks)"},
 ],
 "final_answer": r"f'(x)=2x",
 "Marks":6,"difficulty":"Medium"},
{"question": r"\text{Find the } x\text{-value(s) where } f(x)=x^3-3x \text{ has a turning point.}",
 "hint": r"\text{Turning points occur where } f'(x)=0.",
 "solution_steps":[
 {"explain": "Differentiate f(x) using the power rule.", "latex": r"f'(x)=3x^2-3 \quad (2 Marks)"},
 {"explain": "Turning points occur where the gradient is zero, so set f'(x)=0 and solve for x².", "latex": r"3x^2-3=0 \Rightarrow x^2=1 \quad (2 Marks)"},
 {"explain": "Take the square root of both sides — remember both the positive and negative root.", "latex": r"x=1 \;\text{or}\; x=-1 \quad (2 Marks)"},
 ],
 "final_answer": r"x=1 \;\text{or}\; x=-1",
 "Marks":6,"difficulty":"Medium"},
],
"Functions & Graphs": [
{"question": r"\text{Determine the } y\text{-intercept of } f(x)=x^2-4x+3",
 "hint": r"\text{Substitute } x=0 \text{ into the equation.}",
 "solution_steps":[
 {"explain": "The y-intercept is where the graph crosses the y-axis, i.e. where x=0 — substitute and simplify.", "latex": r"f(0)=0^2-4(0)+3=3 \quad (2 Marks)"},
 ],
 "final_answer": r"(0,3)",
 "Marks":2,"difficulty":"Easy"},
{"question": r"\text{Determine the } x\text{-intercepts of } f(x)=x^2-4x+3",
 "hint": r"\text{Set } f(x)=0 \text{ and factorise.}",
 "solution_steps":[
 {"explain": "The x-intercepts are where the graph crosses the x-axis, i.e. where f(x)=0 — set it to zero and factorise.", "latex": r"(x-1)(x-3)=0 \quad (2 Marks)"},
 {"explain": "Apply the zero product law to solve for x.", "latex": r"x=1 \;\text{or}\; x=3 \quad (1 Mark)"},
 ],
 "final_answer": r"(1,0) \;\text{and}\;(3,0)",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the equations of the asymptotes of } f(x)=\frac{2}{x-1}+3",
 "hint": r"\text{The asymptotes come directly from the values that make the denominator zero, and the vertical shift.}",
 "solution_steps":[
 {"explain": "The vertical asymptote occurs where the denominator of the fraction equals zero (division by zero is undefined).", "latex": r"\text{Vertical asymptote: } x=1 \quad (2 Marks)"},
 {"explain": "As x gets very large, 2/(x-1) approaches 0, so f(x) approaches the constant added outside the fraction.", "latex": r"\text{Horizontal asymptote: } y=3 \quad (2 Marks)"},
 ],
 "final_answer": r"x=1,\; y=3",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Determine the coordinates of the turning point of } f(x)=x^2-2x-3",
 "hint": r"\text{Use the axis of symmetry } x=-\frac{b}{2a}, \text{ then substitute back to find } y.",
 "solution_steps":[
 {"explain": "For a parabola, the turning point lies on the axis of symmetry x=-b/(2a) — substitute a and b.", "latex": r"x=-\frac{-2}{2(1)}=1 \quad (2 Marks)"},
 {"explain": "Substitute this x-value back into f(x) to find the corresponding y-coordinate.", "latex": r"f(1)=1-2-3=-4 \quad (2 Marks)"},
 ],
 "final_answer": r"(1,-4)",
 "Marks":4,"difficulty":"Medium"},
]
},
"Paper 2": {
"Analytical Geometry": [
{"question": r"\text{Find the distance between } A(1,2), B(4,6)",
 "hint": r"\text{Use the distance formula } d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}.",
 "solution_steps":[
 {"explain": "Substitute the coordinates of A and B into the distance formula (a consequence of Pythagoras' theorem) and simplify.", "latex": r"d=\sqrt{(4-1)^2+(6-2)^2}=5 \quad (3 Marks)"},
 ],
 "final_answer": r"5",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine the midpoint of } A(-2,3) \text{ and } B(6,-1)",
 "hint": r"\text{Use } M=\left(\frac{x_1+x_2}{2},\frac{y_1+y_2}{2}\right).",
 "solution_steps":[
 {"explain": "Substitute the coordinates into the midpoint formula: average the x-values and average the y-values.", "latex": r"M=\left(\frac{-2+6}{2},\frac{3+(-1)}{2}\right) \quad (2 Marks)"},
 {"explain": "Simplify each fraction.", "latex": r"M=(2,1) \quad (1 Mark)"},
 ],
 "final_answer": r"(2,1)",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the gradient of the line through } A(1,1) \text{ and } B(5,9)",
 "hint": r"\text{Use } m=\frac{y_2-y_1}{x_2-x_1}.",
 "solution_steps":[
 {"explain": "Substitute the coordinates into the gradient formula: the change in y divided by the change in x.", "latex": r"m=\frac{9-1}{5-1}=\frac{8}{4}=2 \quad (3 Marks)"},
 ],
 "final_answer": r"m=2",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine the equation of the line through } A(2,3) \text{ with gradient } 4",
 "hint": r"\text{Use } y-y_1=m(x-x_1).",
 "solution_steps":[
 {"explain": "Substitute the given point and gradient into the point-gradient form of a straight line.", "latex": r"y-3=4(x-2) \quad (2 Marks)"},
 {"explain": "Expand the brackets and simplify to the standard y=mx+c form.", "latex": r"y=4x-5 \quad (2 Marks)"},
 ],
 "final_answer": r"y=4x-5",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Determine the equation of the circle with centre } (0,0) \text{ and radius } 5",
 "hint": r"\text{Use } (x-a)^2+(y-b)^2=r^2 \text{ with centre } (a,b).",
 "solution_steps":[
 {"explain": "Substitute the centre (a,b) and radius r into the standard equation of a circle.", "latex": r"(x-0)^2+(y-0)^2=5^2 \quad (2 Marks)"},
 ],
 "final_answer": r"x^2+y^2=25",
 "Marks":2,"difficulty":"Easy"},
],
"Trigonometry": [
{"question": r"\text{Solve } \sin x=\frac12,\; 0^\circ\le x\le360^\circ",
 "hint": r"\text{Sine is positive in the 1st and 2nd quadrants.}",
 "solution_steps":[
 {"explain": "Use a calculator/known value to find the reference angle (30°), then apply the CAST rule: sine is positive in the 1st quadrant (30°) and the 2nd quadrant (180°−30°=150°).", "latex": r"x=30^\circ,\;150^\circ \quad (3 Marks)"},
 ],
 "final_answer": r"30^\circ,\;150^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; \cos x=-\frac{\sqrt3}{2},\; 0^\circ\le x\le360^\circ",
 "hint": r"\text{Cosine is negative in the 2nd and 3rd quadrants.}",
 "solution_steps":[
 {"explain": "Ignore the negative sign for now to find the reference (acute) angle.", "latex": r"\text{Reference angle}=30^\circ \quad (1 Mark)"},
 {"explain": "Cosine is negative in the 2nd quadrant, so use 180°−reference angle.", "latex": r"x=180^\circ-30^\circ=150^\circ \quad (1 Mark)"},
 {"explain": "Cosine is also negative in the 3rd quadrant, so use 180°+reference angle.", "latex": r"x=180^\circ+30^\circ=210^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"150^\circ,\;210^\circ",
 "Marks":3,"difficulty":"Medium"},
{"question": r"\text{In } \triangle ABC,\; a=7,\;b=9,\; C=40^\circ. \text{ Find } c \text{ using the cosine rule.}",
 "hint": r"\text{Use } c^2=a^2+b^2-2ab\cos C.",
 "solution_steps":[
 {"explain": "Substitute the two known sides and the angle between them into the cosine rule.", "latex": r"c^2=7^2+9^2-2(7)(9)\cos40^\circ \quad (2 Marks)"},
 {"explain": "Evaluate the right-hand side with a calculator.", "latex": r"c^2\approx 33.48 \quad (1 Mark)"},
 {"explain": "Take the square root of both sides to find c.", "latex": r"c\approx5.79 \quad (1 Mark)"},
 ],
 "final_answer": r"c\approx5.79",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Simplify: } \frac{\sin^2\theta}{1-\cos^2\theta}",
 "hint": r"\text{Use the identity } \sin^2\theta+\cos^2\theta=1.",
 "solution_steps":[
 {"explain": "Use the Pythagorean identity sin²θ+cos²θ=1, rearranged to replace the denominator.", "latex": r"1-\cos^2\theta=\sin^2\theta \quad (2 Marks)"},
 {"explain": "The numerator and denominator are now identical, so they cancel to 1.", "latex": r"\frac{\sin^2\theta}{\sin^2\theta}=1 \quad (2 Marks)"},
 ],
 "final_answer": r"1",
 "Marks":4,"difficulty":"Medium"},
],
"Statistics & Probability": [
{"question": r"\text{Find the mean of } 2,4,6,8",
 "hint": r"\text{Add all values and divide by how many there are.}",
 "solution_steps":[
 {"explain": "Add up all the values, then divide by how many values there are (n=4).", "latex": r"\bar{x}=\frac{20}{4}=5 \quad (3 Marks)"},
 ],
 "final_answer": r"5",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the median of } 3,7,9,12,15",
 "hint": r"\text{Arrange the data set — it's already sorted — and pick the middle value.}",
 "solution_steps":[
 {"explain": "The data is already sorted. With 5 (an odd number of) values, the median is simply the middle one — the 3rd value.", "latex": r"\text{Middle value of 5 sorted numbers is the 3rd value} \quad (2 Marks)"},
 ],
 "final_answer": r"9",
 "Marks":2,"difficulty":"Easy"},
{"question": r"\text{Find the standard deviation of } 2,4,6,8 \;(\text{population})",
 "hint": r"\text{Use } \sigma=\sqrt{\frac{\sum(x-\bar x)^2}{n}}.",
 "solution_steps":[
 {"explain": "First calculate the mean, since it's needed for every deviation below.", "latex": r"\bar{x}=5 \quad (1 Mark)"},
 {"explain": "Find how far each value is from the mean, square each deviation (so negatives don't cancel positives), and add them all up.", "latex": r"\sum(x-\bar{x})^2=(2-5)^2+(4-5)^2+(6-5)^2+(8-5)^2=20 \quad (2 Marks)"},
 {"explain": "Divide by n (the number of values) and take the square root to undo the earlier squaring.", "latex": r"\sigma=\sqrt{\frac{20}{4}}=\sqrt5\approx2.24 \quad (2 Marks)"},
 ],
 "final_answer": r"\approx2.24",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{A die is rolled once. Find the probability of getting a number greater than 4.}",
 "hint": r"\text{List the favourable outcomes out of the 6 possible outcomes.}",
 "solution_steps":[
 {"explain": "List every outcome on the die that satisfies \"greater than 4\".", "latex": r"\text{Favourable outcomes: } \{5,6\} \quad (1 Mark)"},
 {"explain": "Divide the number of favourable outcomes by the total number of possible outcomes (6 faces), and simplify.", "latex": r"P(E)=\frac{2}{6}=\frac13 \quad (2 Marks)"},
 ],
 "final_answer": r"\frac13",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Events A and B are mutually exclusive with } P(A)=0.3 \text{ and } P(B)=0.4. \text{ Find } P(A \text{ or } B).",
 "hint": r"\text{For mutually exclusive events, } P(A\text{ or }B)=P(A)+P(B).",
 "solution_steps":[
 {"explain": "Since A and B are mutually exclusive (they can never both happen at once), there's no overlap to subtract — simply add the two probabilities.", "latex": r"P(A\text{ or }B)=P(A)+P(B) \quad (2 Marks)"},
 {"explain": "Substitute the given probabilities and add.", "latex": r"P(A\text{ or }B)=0.3+0.4=0.7 \quad (1 Mark)"},
 ],
 "final_answer": r"0.7",
 "Marks":3,"difficulty":"Medium"},
],
"Euclidean Geometry": [
{"question": r"\text{O is the centre of a circle. The angle at the centre } AOB=100^\circ. \text{ Find the angle at the circumference } ACB.",
 "hint": r"\text{The angle at the centre is twice the angle at the circumference subtended by the same arc.}",
 "solution_steps":[
 {"explain": "Apply the theorem: the angle at the centre is always double the angle at the circumference, when both are subtended by the same arc.", "latex": r"ACB=\frac12 \times AOB \quad (2 Marks)"},
 {"explain": "Substitute the given central angle and simplify.", "latex": r"ACB=\frac12\times100^\circ=50^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"50^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{ABCD is a cyclic quadrilateral with } \hat{A}=110^\circ. \text{ Find } \hat{C}.",
 "hint": r"\text{Opposite angles in a cyclic quadrilateral are supplementary (add to } 180^\circ\text{).}",
 "solution_steps":[
 {"explain": "Apply the cyclic quadrilateral theorem: opposite angles always add up to 180°.", "latex": r"\hat{A}+\hat{C}=180^\circ \quad (2 Marks)"},
 {"explain": "Substitute the known angle and solve for the other one.", "latex": r"\hat{C}=180^\circ-110^\circ=70^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"70^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{A tangent touches a circle at point } T. \text{ The angle between the tangent and chord } TP \text{ is } 55^\circ. \text{ Find the angle in the alternate segment.}",
 "hint": r"\text{Tan-chord theorem: the angle between a tangent and a chord equals the angle in the alternate segment.}",
 "solution_steps":[
 {"explain": "Apply the tan-chord theorem directly: the angle between a tangent and a chord always equals the angle in the alternate segment — no calculation needed, just identify the equal angle.", "latex": r"\text{Angle in alternate segment}=55^\circ \quad (2 Marks)"},
 ],
 "final_answer": r"55^\circ",
 "Marks":2,"difficulty":"Medium"},
]
}
}

