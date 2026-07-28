export const RUNTIME_API_VERSION = 1;

function stripJsonComments(source) {
  let result = "";
  let inString = false;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];
    if (lineComment) {
      if (char === "\n") {
        lineComment = false;
        result += char;
      }
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (inString) {
      result += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (char === "\"") {
      inString = true;
      result += char;
    } else if (char === "/" && next === "/") {
      lineComment = true;
      index += 1;
    } else if (char === "/" && next === "*") {
      blockComment = true;
      index += 1;
    } else {
      result += char;
    }
  }
  return result;
}

function normalizeNumericDivisions(source) {
  const divisionPattern = /(^|[^\w.])(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\s*\/\s*(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)(?![\w.])/gi;
  let result = "";
  let segment = "";
  let inString = false;
  let escaped = false;
  const normalizeSegment = (value) => value.replace(
    divisionPattern,
    (match, prefix, numerator, denominator) => {
      const divisor = Number(denominator);
      if (!Number.isFinite(divisor) || divisor === 0) return match;
      return `${prefix}${Number(numerator) / divisor}`;
    },
  );
  for (const char of source) {
    if (inString) {
      result += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
    } else if (char === "\"") {
      result += normalizeSegment(segment);
      segment = "";
      result += char;
      inString = true;
    } else {
      segment += char;
    }
  }
  return result + normalizeSegment(segment);
}

function parseJsonCandidate(source) {
  const candidate = source.trim();
  if (!candidate) return null;
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch (_err) {
    try {
      const normalized = normalizeNumericDivisions(
        stripJsonComments(candidate).replace(/,\s*([}\]])/g, "$1"),
      );
      const parsed = JSON.parse(normalized);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
    } catch (_innerErr) {
      return null;
    }
  }
}

function balancedJsonSpan(source, start) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < source.length; index += 1) {
    const char = source[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (char === "\"") {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) return { start, end: index + 1 };
    }
  }
  return null;
}

function cleanAssistantProse(text) {
  return text
    .replace(
      /\s*(?:Here(?:'s| is)|Below is)[^.!?\n]*(?:JSON|structured request|structured command)[^.!?\n]*:\s*(?=\n|$)/gim,
      "",
    )
    .replace(/^\s*```(?:json)?\s*$/gim, "")
    .replace(/\n[ \t]+\n/g, "\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function parseAssistantResponse(text) {
  if (!text || typeof text !== "string") return { parsed: null, prose: "" };
  const source = text.trim();
  const fencedPattern = /```(?:json)?\s*([\s\S]*?)```/gi;
  let fencedMatch = fencedPattern.exec(source);
  while (fencedMatch) {
    const parsed = parseJsonCandidate(fencedMatch[1]);
    if (parsed) {
      const prose = cleanAssistantProse(
        `${source.slice(0, fencedMatch.index)}\n${source.slice(fencedPattern.lastIndex)}`,
      );
      return { parsed, prose };
    }
    fencedMatch = fencedPattern.exec(source);
  }

  const whole = parseJsonCandidate(source);
  if (whole) return { parsed: whole, prose: "" };

  for (let start = source.indexOf("{"); start >= 0; start = source.indexOf("{", start + 1)) {
    const span = balancedJsonSpan(source, start);
    if (!span) continue;
    const parsed = parseJsonCandidate(source.slice(span.start, span.end));
    if (parsed) {
      const prose = cleanAssistantProse(
        `${source.slice(0, span.start)}\n${source.slice(span.end)}`,
      );
      return { parsed, prose };
    }
  }
  return { parsed: null, prose: cleanAssistantProse(source) };
}
