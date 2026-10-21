// Shared rendering normalization. Keep identical to frontend src/client/lib/mermaidMath.js.
// This only restores legacy TeX grouping and adapts math delimiters for Mermaid.

function readGroup(text, start) {
  while (/\s/.test(text[start] ?? '') && start < text.length) start += 1
  const open = text[start]
  const close = open === '(' ? ')' : open === '{' ? '}' : null
  if (!close) return null
  let depth = 1
  for (let pos = start + 1; pos < text.length; pos += 1) {
    if (text[pos] === '\\' && '{}()'.includes(text[pos + 1] ?? '')) {
      pos += 1
      continue
    }
    if (text[pos] === open) depth += 1
    if (text[pos] === close && --depth === 0) {
      return { inner: text.slice(start + 1, pos), end: pos + 1 }
    }
  }
  return null
}

const TWO_ARGUMENTS = new Set(['frac', 'dfrac', 'tfrac', 'binom', 'overset', 'underset'])
const MACROS = /\\(frac|dfrac|tfrac|binom|overset|underset|sqrt|hat|widehat|tilde|widetilde|bar|overline|underline|vec|text|textbf|textrm|textit|operatorname|mathbf|mathbb|mathcal|mathrm|mathit|boldsymbol)(?![A-Za-z])/g

function restoreGrouping(input) {
  // Nested inline delimiters were produced when escaped braces were replaced in old labels.
  let text = input.replace(/\\([()])/g, '$1')
  const macros = new RegExp(MACROS.source, 'g')
  let result = ''
  let cursor = 0
  for (let match; (match = macros.exec(text));) {
    const groups = []
    let end = match.index + match[0].length
    const arity = TWO_ARGUMENTS.has(match[1]) ? 2 : 1
    for (let index = 0; index < arity; index += 1) {
      const group = readGroup(text, end)
      if (!group) break
      groups.push(group.inner)
      end = group.end
    }
    if (groups.length !== arity) continue
    result += text.slice(cursor, match.index) + match[0]
    result += groups.map(inner => `{${restoreGrouping(inner)}}`).join('')
    cursor = end
    macros.lastIndex = end
  }
  text = result + text.slice(cursor)

  const scripts = /[_^]\s*(?=\()/g
  result = ''
  cursor = 0
  for (let match; (match = scripts.exec(text));) {
    const group = readGroup(text, match.index + match[0].length)
    if (!group) continue
    result += text.slice(cursor, match.index) + match[0][0] + `{${restoreGrouping(group.inner)}}`
    cursor = group.end
    scripts.lastIndex = group.end
  }
  return result + text.slice(cursor)
}

export function normalizeMermaidMath(code) {
  return code.replace(/(?<![\\$])(\${1,2})(?!\$)([\s\S]+?)(?<![\\$])\1(?!\$)/g,
    (_match, _delimiter, formula) => `$$${restoreGrouping(formula)}$$`)
}
