// Wrap a JSON Schema in strict instructions that push a chat model (Claude/GPT)
// to reply with a single schema-valid JSON object — so the pasted reply passes
// the validate-response / validate-adjudicator stages on the first try.
export const buildFormatPrompt = (schemaJson: string, label: string): string =>
  `# OUTPUT FORMAT — ${label}

Return your answer as a SINGLE JSON object and NOTHING else.

Rules:
- No prose, commentary, or markdown code fences before or after the JSON.
- The object MUST validate against the JSON Schema below (Draft 2020-12).
- Include every required field. Do not add fields the schema does not list —
  \`additionalProperties\` is false, so any extra key is rejected.
- Honor every \`enum\`, \`const\`, \`pattern\`, and min/max constraint exactly.
- Use valid JSON: double-quoted keys/strings, no trailing commas, no comments.

JSON Schema:
\`\`\`json
${schemaJson}
\`\`\`

Respond now with only the JSON object.`
