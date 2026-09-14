.pragma library

const SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ"
};

const SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ"
};

const COMMANDS = {
    neq: "≠", ne: "≠", leq: "≤", le: "≤", geq: "≥", ge: "≥",
    approx: "≈", sim: "∼", equiv: "≡", propto: "∝",
    times: "×", cdot: "·", ast: "∗", circ: "∘", bullet: "•",
    pm: "±", mp: "∓", div: "÷",
    infty: "∞", partial: "∂", nabla: "∇",
    sum: "∑", prod: "∏", int: "∫", oint: "∮",
    sqrt: "√",
    inf: "∞",
    to: "→", rightarrow: "→", leftarrow: "←",
    Rightarrow: "⇒", Leftarrow: "⇐",
    implies: "⇒", iff: "⇔", leftrightarrow: "↔",
    in: "∈", notin: "∉", ni: "∋",
    subset: "⊂", supset: "⊃", subseteq: "⊆", supseteq: "⊇",
    cup: "∪", cap: "∩", emptyset: "∅", varnothing: "∅",
    forall: "∀", exists: "∃", nexists: "∄",
    land: "∧", lor: "∨", neg: "¬", lnot: "¬",
    ldots: "…", cdots: "⋯", vdots: "⋮", ddots: "⋱",
    quad: "  ", qquad: "    ",
    alpha: "α", beta: "β", gamma: "γ", delta: "δ",
    epsilon: "ε", varepsilon: "ε", zeta: "ζ", eta: "η",
    theta: "θ", vartheta: "ϑ", iota: "ι", kappa: "κ",
    lambda: "λ", mu: "μ", nu: "ν", xi: "ξ",
    pi: "π", varpi: "ϖ", rho: "ρ", sigma: "σ",
    tau: "τ", upsilon: "υ", phi: "φ", varphi: "φ",
    chi: "χ", psi: "ψ", omega: "ω",
    Alpha: "Α", Beta: "Β", Gamma: "Γ", Delta: "Δ",
    Theta: "Θ", Lambda: "Λ", Xi: "Ξ", Pi: "Π",
    Sigma: "Σ", Phi: "Φ", Psi: "Ψ", Omega: "Ω",
    ell: "ℓ", hbar: "ℏ", Re: "ℜ", Im: "ℑ",
    cdotp: "·", ldotp: ".",
    degree: "°", perp: "⊥", parallel: "∥",
    angle: "∠", triangle: "△",
    lfloor: "⌊", rfloor: "⌋", lceil: "⌈", rceil: "⌉",
    langle: "⟨", rangle: "⟩",
    vert: "|", Vert: "∥",
    mid: "∣", nmid: "∤",
    setminus: "∖",
    because: "∵", therefore: "∴",
    cong: "≅", ncong: "≇",
    ll: "≪", gg: "≫",
    prec: "≺", succ: "≻",
    oplus: "⊕", otimes: "⊗", ominus: "⊖",
    wedge: "∧", vee: "∨"
};

function _mapChars(str, table) {
    let out = "";
    for (let i = 0; i < str.length; i++) {
        const ch = str[i];
        if (ch === " ") {
            out += " ";
            continue;
        }
        if (table[ch] !== undefined)
            out += table[ch];
        else
            return null;
    }
    return out;
}

function _replaceFracs(s) {
    const re = /\\(?:dfrac|tfrac|frac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}/;
    let prev;
    do {
        prev = s;
        s = s.replace(re, "($1)/($2)");
    } while (s !== prev);
    return s;
}

function _replaceBinoms(s) {
    const re = /\\binom\s*\{([^{}]*)\}\s*\{([^{}]*)\}/;
    let prev;
    do {
        prev = s;
        s = s.replace(re, "C($1,$2)");
    } while (s !== prev);
    return s;
}

function _replaceScripts(s) {
    function singles(str, marker, table, fallbackPrefix) {
        return str.replace(new RegExp("\\" + marker + "([^\\{])", "g"), function (m, ch) {
            return table[ch] !== undefined ? table[ch] : fallbackPrefix + ch;
        });
    }
    function braced(str, marker, table, fallbackPrefix) {
        return str.replace(new RegExp("\\" + marker + "\\{([^{}]*)\\}", "g"), function (m, body) {
            const mapped = _mapChars(body, table);
            if (mapped !== null)
                return mapped;
            return fallbackPrefix + "(" + body + ")";
        });
    }
    s = singles(s, "^", SUP, "^");
    s = singles(s, "_", SUB, "_");
    s = braced(s, "^", SUP, "^");
    s = braced(s, "_", SUB, "_");
    return s;
}

function latexToUnicode(input) {
    let s = String(input || "");
    s = s.replace(/^\s*\$+|\$+\s*$/g, "").trim();
    s = s.replace(/\\left/g, "").replace(/\\right/g, "");
    s = s.replace(/\\(?:text|mathrm|mathbf|mathit|operatorname|mathsf|mathtt|textrm)\s*\{([^{}]*)\}/g, "$1");
    s = _replaceFracs(s);
    s = _replaceBinoms(s);
    s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
    s = s.replace(/\\sqrt\s+([A-Za-z0-9])/g, "√$1");
    s = s.replace(/\\[,;:!]/g, " ");
    s = s.replace(/\\\{/g, "\uE000").replace(/\\\}/g, "\uE001");
    s = s.replace(/\\%/g, "%");
    s = s.replace(/\\ /g, " ");
    s = s.replace(/\\([a-zA-Z]+)/g, function (m, name) {
        return COMMANDS[name] !== undefined ? COMMANDS[name] : name;
    });
    s = _replaceScripts(s);
    s = s.replace(/[{}]/g, "");
    s = s.replace(/\uE000/g, "{").replace(/\uE001/g, "}");
    s = s.replace(/~/g, " ");
    s = s.replace(/[ \t]+/g, " ").trim();
    return s;
}

function _parseRow(line) {
    let t = String(line || "").trim();
    if (!t.length)
        return [];
    if (t.charAt(0) === "|")
        t = t.slice(1);
    if (t.charAt(t.length - 1) === "|")
        t = t.slice(0, -1);
    return t.split("|").map(function (c) {
        return c.trim();
    });
}

function _isSeparatorRow(cells) {
    if (!cells || cells.length < 2)
        return false;
    for (let i = 0; i < cells.length; i++) {
        if (!/^:?-{2,}:?$/.test(cells[i]))
            return false;
    }
    return true;
}

function _alignFromSep(cell) {
    const left = cell.charAt(0) === ":";
    const right = cell.charAt(cell.length - 1) === ":";
    if (left && right)
        return "center";
    if (right)
        return "right";
    return "left";
}

function _looksLikeHeader(cells) {
    let letters = 0;
    for (let i = 0; i < cells.length; i++) {
        if (/[A-Za-z]/.test(cells[i]) && !/^[+-]?\d+(\.\d+)?%?$/.test(cells[i]))
            letters++;
    }
    return letters > 0;
}

function _looksLikeTableLine(line) {
    const t = String(line || "").trim();
    if (!t.length)
        return false;
    if (t.indexOf("|") === -1)
        return false;
    if (_isSeparatorRow(_parseRow(t)))
        return true;
    const pipes = (t.match(/\|/g) || []).length;
    if (t.charAt(0) === "|" && pipes >= 2)
        return true;
    if (t.charAt(t.length - 1) === "|" && pipes >= 2)
        return true;
    return t.indexOf(" | ") !== -1;
}

function _splitLeadingProse(line) {
    const raw = String(line || "");
    const trimmed = raw.trim();
    if (!trimmed.length || trimmed.charAt(0) === "|")
        return null;
    const idx = raw.indexOf("|");
    if (idx <= 0)
        return null;
    const prose = raw.slice(0, idx).trim();
    const rest = raw.slice(idx);
    const cells = _parseRow(rest);
    if (!prose.length || cells.length < 2 || _isSeparatorRow(cells))
        return null;
    if (!_looksLikeTableLine(rest))
        return null;
    return {
        prose: prose,
        table: rest
    };
}

function _flattenPipeCells(lines) {
    const cells = [];
    for (let i = 0; i < lines.length; i++) {
        const row = _parseRow(lines[i]);
        for (let j = 0; j < row.length; j++)
            cells.push(row[j]);
    }
    return cells;
}

function _chunkCells(cells, n) {
    const filtered = [];
    for (let i = 0; i < cells.length; i++) {
        if (cells[i] === "" && (filtered.length % n === 0))
            continue;
        filtered.push(cells[i]);
    }
    const rows = [];
    for (let i = 0; i < filtered.length; i += n) {
        const row = filtered.slice(i, i + n);
        while (row.length < n)
            row.push("");
        rows.push(row.slice(0, n));
    }
    return rows;
}

function _tableFromLines(lines) {
    if (!lines.length)
        return null;
    const first = _parseRow(lines[0]).filter(function (c) {
        return c.length > 0;
    });
    if (first.length < 2)
        return null;
    let start = 0;
    let headers = first;
    let aligns = [];
    if (lines.length > 1 && _isSeparatorRow(_parseRow(lines[1]))) {
        aligns = _parseRow(lines[1]).map(_alignFromSep);
        start = 2;
    } else if (_looksLikeHeader(first)) {
        start = 1;
    } else {
        headers = [];
        for (let i = 0; i < first.length; i++)
            headers.push("");
        start = 0;
    }
    const n = headers.length || first.length;
    if (n < 2)
        return null;
    while (aligns.length < n)
        aligns.push("left");
    const bodyLines = lines.slice(start).filter(function (ln) {
        return !_isSeparatorRow(_parseRow(ln));
    });
    const cells = _flattenPipeCells(bodyLines);
    const rows = _chunkCells(cells, n);
    if (!headers.filter(function (h) {
        return h.length > 0;
    }).length && !rows.length)
        return null;
    if (!rows.length && start === 0)
        return null;
    return {
        type: "table",
        headers: headers,
        rows: rows,
        aligns: aligns.slice(0, n)
    };
}

function _splitTables(text) {
    const lines = String(text || "").split("\n");
    const out = [];
    let buf = [];
    let i = 0;

    function flushBuf() {
        if (!buf.length)
            return;
        out.push({
            type: "text",
            content: buf.join("\n")
        });
        buf = [];
    }

    while (i < lines.length) {
        const split = _splitLeadingProse(lines[i]);
        const tableLine = split ? split.table : lines[i];
        if (_looksLikeTableLine(tableLine)) {
            if (split && split.prose.length)
                buf.push(split.prose);
            const block = [tableLine];
            i++;
            while (i < lines.length && (_looksLikeTableLine(lines[i]) || !String(lines[i] || "").trim().length)) {
                if (!String(lines[i] || "").trim().length) {
                    if (i + 1 < lines.length && _looksLikeTableLine(lines[i + 1])) {
                        i++;
                        continue;
                    }
                    break;
                }
                const inner = _splitLeadingProse(lines[i]);
                block.push(inner ? inner.table : lines[i]);
                if (inner && inner.prose.length)
                    buf.push(inner.prose);
                i++;
            }
            const table = _tableFromLines(block);
            if (table && table.rows.length > 0) {
                flushBuf();
                out.push(table);
            } else {
                for (let b = 0; b < block.length; b++)
                    buf.push(block[b]);
            }
            continue;
        }
        buf.push(lines[i]);
        i++;
    }
    flushBuf();
    return out;
}

function _isDisplayMathBody(body) {
    const t = String(body || "").trim();
    if (!t.length)
        return false;
    if (t.length > 400)
        return false;
    if (/\n\s*\n/.test(body))
        return false;
    if (/(^|\n)\s*#{1,6}\s|(^|\n)\s*\*\*[^*]/.test(t))
        return false;
    return /[\\^_=+\-*/<>()[\]0-9]|[a-zA-Z]\s*[\^_]/.test(t);
}

function _findDisplayMath(s, start) {
    if (s.indexOf("$$", start) === start) {
        const close = s.indexOf("$$", start + 2);
        if (close === -1) {
            const body = s.slice(start + 2);
            if (_isDisplayMathBody(body) || (body.trim().length > 0 && body.trim().length < 80 && !/\s{2,}/.test(body)))
                return {
                    end: s.length,
                    body: body,
                    incomplete: true
                };
            return null;
        }
        const body = s.slice(start + 2, close);
        if (!_isDisplayMathBody(body))
            return null;
        return {
            end: close + 2,
            body: body,
            incomplete: false
        };
    }
    if (s.indexOf("\\[", start) === start) {
        const close = s.indexOf("\\]", start + 2);
        if (close === -1) {
            const body = s.slice(start + 2);
            if (_isDisplayMathBody(body))
                return {
                    end: s.length,
                    body: body,
                    incomplete: true
                };
            return null;
        }
        const body = s.slice(start + 2, close);
        if (!_isDisplayMathBody(body))
            return null;
        return {
            end: close + 2,
            body: body,
            incomplete: false
        };
    }
    return null;
}

function _splitDisplayMath(text) {
    const s = String(text || "");
    const out = [];
    let last = 0;
    let i = 0;
    while (i < s.length) {
        if (s.indexOf("$$", i) === i || s.indexOf("\\[", i) === i) {
            const found = _findDisplayMath(s, i);
            if (!found) {
                if (i > last)
                    out.push({
                        type: "text",
                        content: s.slice(last, i)
                    });
                i += s.indexOf("$$", i) === i ? 2 : 2;
                last = i;
                continue;
            }
            if (i > last)
                out.push({
                    type: "text",
                    content: s.slice(last, i)
                });
            const rendered = latexToUnicode(found.body);
            if (rendered.length)
                out.push({
                    type: "math",
                    content: rendered,
                    latex: found.body.trim()
                });
            i = found.end;
            last = i;
            continue;
        }
        i++;
    }
    if (last < s.length)
        out.push({
            type: "text",
            content: s.slice(last)
        });
    return out;
}

function _isMathy(body) {
    const t = body.trim();
    if (!t.length)
        return false;
    if (t.length > 200)
        return false;
    return /[\\^_=+\-*/<>]|\\[a-zA-Z]+|[a-zA-Z]\s*\^/.test(t) || t.length <= 24;
}

function substituteInlineMath(text) {
    let s = String(text || "");

    s = s.replace(/\\\(([\s\S]+?)\\\)/g, function (m, body) {
        const u = latexToUnicode(body);
        return u.length ? "`" + u + "`" : m;
    });

    let out = "";
    let i = 0;
    while (i < s.length) {
        if (s.startsWith("$$", i)) {
            out += s[i];
            i++;
            continue;
        }
        if (s[i] === "$") {
            const close = s.indexOf("$", i + 1);
            if (close !== -1 && s[close + 1] !== "$") {
                const body = s.slice(i + 1, close);
                if (body.indexOf("\n") === -1 && _isMathy(body)) {
                    const u = latexToUnicode(body);
                    out += u.length ? "`" + u + "`" : body;
                    i = close + 1;
                    continue;
                }
            }
            i++;
            continue;
        }
        out += s[i];
        i++;
    }

    out = out.replace(/\\([a-zA-Z]+)/g, function (m, name) {
        return COMMANDS[name] !== undefined ? COMMANDS[name] : m;
    });
    out = out.replace(/\$\$/g, "");
    out = out.replace(/\$/g, "");
    return out;
}

function _splitCode(text) {
    const s = String(text || "");
    const out = [];
    const re = /```([^\n`]*)\n?([\s\S]*?)```/g;
    let last = 0;
    let match;
    while ((match = re.exec(s)) !== null) {
        if (match.index > last)
            out.push({
                type: "text",
                content: s.slice(last, match.index)
            });
        out.push({
            type: "code",
            language: (match[1] || "text").trim() || "text",
            content: String(match[2] || "").replace(/\n$/, "")
        });
        last = re.lastIndex;
    }
    const open = s.indexOf("```", last);
    if (open !== -1) {
        if (open > last)
            out.push({
                type: "text",
                content: s.slice(last, open)
            });
        const rest = s.slice(open + 3);
        const nl = rest.indexOf("\n");
        const lang = (nl === -1 ? rest : rest.slice(0, nl)).trim() || "text";
        const body = nl === -1 ? "" : rest.slice(nl + 1);
        out.push({
            type: "code",
            language: lang,
            content: body
        });
        return out;
    }
    if (last < s.length || !out.length)
        out.push({
            type: "text",
            content: last < s.length ? s.slice(last) : (out.length ? "" : s)
        });
    return out;
}

function splitParts(text) {
    const src = String(text || "");
    if (!src.length)
        return [];
    const afterCode = _splitCode(src);
    const out = [];
    for (let c = 0; c < afterCode.length; c++) {
        const token = afterCode[c];
        if (token.type === "code") {
            out.push(token);
            continue;
        }
        const mathSplit = _splitDisplayMath(token.content || "");
        for (let m = 0; m < mathSplit.length; m++) {
            const mt = mathSplit[m];
            if (mt.type === "math") {
                out.push(mt);
                continue;
            }
            const tableSplit = _splitTables(mt.content || "");
            for (let t = 0; t < tableSplit.length; t++) {
                const tt = tableSplit[t];
                if (tt.type === "table") {
                    const headers = [];
                    for (let h = 0; h < tt.headers.length; h++)
                        headers.push(substituteInlineMath(tt.headers[h]));
                    const rows = [];
                    for (let r = 0; r < tt.rows.length; r++) {
                        const row = [];
                        for (let k = 0; k < tt.rows[r].length; k++)
                            row.push(substituteInlineMath(tt.rows[r][k]));
                        rows.push(row);
                    }
                    out.push({
                        type: "table",
                        headers: headers,
                        rows: rows,
                        aligns: tt.aligns
                    });
                    continue;
                }
                const content = substituteInlineMath(tt.content || "");
                if (content.trim().length)
                    out.push({
                        type: "text",
                        content: content
                    });
            }
        }
    }
    return out;
}
